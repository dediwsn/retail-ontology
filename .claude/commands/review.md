---
description: Run code review on the current diff
---

Review the unstaged + staged changes in the current branch and report:

1. Bugs and logic errors (with file:line references)
2. Security issues — secrets, IAM scope, input validation, SSRF/SQLi/XSS surface
3. Convention drift — does it follow the patterns in CLAUDE.md and module-level CLAUDE.md files?
4. Performance concerns — N+1 queries, missing pagination, blocking calls in async paths
5. Missing tests or docs

Use confidence-based filtering: only flag high-priority issues that would block a PR. For each issue, propose a concrete fix.

Start by running `git diff` and `git status` to capture the current state.

## Output format

Mirror the `.claude/agents/code-reviewer.md` contract exactly so direct `/review` invocations and agent invocations produce structurally identical output:

```
[Severity] file:line — short description
Current: <quoted code or behavior>
Fix:     <concrete patch or replacement>
```

Severity rubric (Title Case, matching the agent file):

- **Critical** — security exposure, data loss, broken auth
- **High** — correctness regression, broken contract
- **Medium** — performance issue, race condition, leak
- **Low** — convention drift, naming, minor refactor (suppress unless explicitly requested)

Group findings by severity (Critical → Low). Skip severities with zero findings.

If no issues at Medium+ severity, end with exactly:

`No high-confidence issues at Medium+ severity.`
