---
description: Build, push, and deploy API and Web container images
---

Deterministic deploy flow that avoids `:latest` cache traps. Both images are ARM64.

**Prerequisites**: `AWS_ACCOUNT_ID` env var must be set (the commands below use it
literally). The simplest way is to derive it from the active AWS identity:

```bash
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
```

1. **Determine the SHA tag**:
   ```bash
   TAG="$(git rev-parse --short HEAD)-$(date +%s)"
   ```

2. **ECR login**:
   ```bash
   aws ecr get-login-password --region ap-northeast-2 \
     | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.ap-northeast-2.amazonaws.com
   ```

3. **Build both images** (ARM64):
   ```bash
   docker build --platform linux/arm64 -f api/Dockerfile \
     -t $AWS_ACCOUNT_ID.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-api:$TAG \
     -t $AWS_ACCOUNT_ID.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-api:latest .

   docker build --platform linux/arm64 -f web/Dockerfile \
     -t $AWS_ACCOUNT_ID.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-web:$TAG \
     -t $AWS_ACCOUNT_ID.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-web:latest .
   ```

4. **Push** (both SHA tag and `:latest`):
   ```bash
   docker push $AWS_ACCOUNT_ID.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-api:$TAG
   docker push $AWS_ACCOUNT_ID.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-api:latest
   docker push $AWS_ACCOUNT_ID.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-web:$TAG
   docker push $AWS_ACCOUNT_ID.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-web:latest
   ```

5. **Register SHA-pinned task definitions** (avoids ECR `:latest` cache). Run for each of `api` and `web`:
   ```bash
   for svc in api web; do
     # 5a. Describe the current task definition (stripping fields the register
     #     API rejects on input — registeredAt, taskDefinitionArn, status, etc.)
     aws ecs describe-task-definition \
       --task-definition ontology-retail-dev-$svc \
       --query 'taskDefinition.{family:family,taskRoleArn:taskRoleArn,executionRoleArn:executionRoleArn,networkMode:networkMode,requiresCompatibilities:requiresCompatibilities,cpu:cpu,memory:memory,runtimePlatform:runtimePlatform,containerDefinitions:containerDefinitions}' \
       > /tmp/td-$svc.json

     # 5b. Swap in the SHA tag for the container image
     python3 -c "
   import json, sys
   td = json.load(open('/tmp/td-$svc.json'))
   td['containerDefinitions'][0]['image'] = (
       '$AWS_ACCOUNT_ID.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-$svc:$TAG'
   )
   json.dump(td, open('/tmp/td-$svc.json', 'w'))
   "

     # 5c. Register the new revision
     NEW_REV=$(aws ecs register-task-definition \
       --cli-input-json file:///tmp/td-$svc.json \
       --query 'taskDefinition.revision' --output text)

     # 5d. Force a new deployment pinned to the new revision
     aws ecs update-service \
       --cluster ontology-retail-dev-cluster \
       --service ontology-retail-dev-$svc \
       --task-definition ontology-retail-dev-$svc:$NEW_REV \
       --force-new-deployment >/dev/null
     echo "[$svc] rolled out task def revision $NEW_REV"
   done
   ```

6. **Wait for rollout** to reach `COMPLETED` for both services:
   ```bash
   aws ecs wait services-stable \
     --cluster ontology-retail-dev-cluster \
     --services ontology-retail-dev-api ontology-retail-dev-web
   ```
   If `wait services-stable` times out (>10 min), the rollout is stuck. Inspect:
   ```bash
   aws ecs describe-services \
     --cluster ontology-retail-dev-cluster \
     --services ontology-retail-dev-api ontology-retail-dev-web \
     --query 'services[].events[0:5].message'
   ```
   `events[0].message` usually points at the root cause (image pull failure, ENI/SG, ELB health check). Roll back by updating the service to the previous task-def revision (`--task-definition ontology-retail-dev-$svc:$((NEW_REV-1))`).

7. **Verify** with the smoke checks from `/test-all`.

If any task fails ELB health check, inspect CloudWatch logs at `/aws/ecs/ontology-retail-dev/{api,web}` for the failing task ID — common causes are syntax errors in newly added routers or missing env vars.
