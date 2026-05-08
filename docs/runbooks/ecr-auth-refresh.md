# Runbook: ECR Auth Token Refresh

**When to use**: any time `docker push` returns `denied: Your authorization token has expired`. Common during long deploy sessions where the build phase exceeds the 12-hour ECR auth window, or when a session is resumed across days.

**Symptom**:

```
$ docker push 061525506239.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-api:abc123
8298bbf736c7: Waiting
6a7ea9d7f58d: Waiting
denied: Your authorization token has expired. Reauthenticate and try again.
```

ECR tokens last 12 hours. The `docker login` Helper does not auto-refresh.

---

## Fix

```bash
aws ecr get-login-password --region ap-northeast-2 \
  | docker login --username AWS --password-stdin 061525506239.dkr.ecr.ap-northeast-2.amazonaws.com
```

Expected output ends with `Login Succeeded`.

Then re-run the push:

```bash
docker push 061525506239.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-api:$TAG
docker push 061525506239.dkr.ecr.ap-northeast-2.amazonaws.com/ontology-retail-dev-api:latest
```

**Layers already pushed are skipped** (you'll see `Layer already exists`), so re-running after expiry is fast and safe.

---

## Why this happens

- AWS ECR auth tokens are issued by `GetAuthorizationToken`. They expire after **12 hours** by design.
- The Docker daemon caches the credentials; when the cache hits ECR with an expired token, ECR returns 403.
- There's no automatic refresh — the `aws ecr get-login-password` call must be re-run manually (or via a wrapper script with cron).

If you push to ECR *frequently* throughout the day, the easiest workaround is a shell function:

```bash
ecr-login() {
  aws ecr get-login-password --region ap-northeast-2 \
    | docker login --username AWS --password-stdin \
        $(aws sts get-caller-identity --query Account --output text).dkr.ecr.ap-northeast-2.amazonaws.com
}
# call ecr-login at the start of each session
```

---

## Adjacent failure modes (look-alike)

| Symptom | Likely cause | Fix |
|---|---|---|
| `no basic auth credentials` | Never logged in to this ECR registry | run the `aws ecr get-login-password` command above |
| `unauthorized: authentication required` | Wrong region or account ID in the registry URL | verify `$AWS_ACCOUNT_ID` and region match the ECR repo's account/region |
| `401 Unauthorized` from `GetAuthorizationToken` itself | IAM credentials expired (SSO / role assumption timeout) | run `aws sso login` (SSO) or refresh assumed-role creds |
| `denied: requested access to the resource is denied` | IAM principal lacks `ecr:BatchCheckLayerAvailability` / `ecr:PutImage` on the repo | add `ecr:PowerUser` policy or grant repo-level permissions |

## See also

- [`deploy-production.md`](deploy-production.md) — full deploy flow that calls this implicitly.
- AWS docs: [ECR private auth tokens](https://docs.aws.amazon.com/AmazonECR/latest/userguide/registry_auth.html).
