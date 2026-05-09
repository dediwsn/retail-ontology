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

Mirror the `code-reviewer` agent's contract so direct command invocations and agent invocations produce structurally identical output:

```
[CRITICAL|HIGH|MEDIUM|LOW] <file>:<line> — <one-line description>
  Current: <quoted code or behavior>
  Fix:     <concrete patch or replacement>
```

Severity rubric:
- **CRITICAL**: data loss, security breach, deploy-breaking syntax error
- **HIGH**: bug producing wrong results, missing tests for new code with logic, IAM/auth scope creep
- **MEDIUM**: convention drift, performance smell with measurable impact, missing error handling at a known failure boundary
- **LOW**: style, naming, marginal optimization (suppressed unless explicitly requested)

Group findings by severity (CRITICAL first). End with a single termination line:

- If issues found: `Total: <N> CRITICAL, <N> HIGH, <N> MEDIUM blocking issues.`
- If clean: `No high-confidence issues at MEDIUM+ severity.`
