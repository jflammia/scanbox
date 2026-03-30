---
name: ship
description: End-to-end git workflow for ScanBox — branch, commit, push, PR, wait for CI, fix failures, squash-merge, cleanup. Use when the user says "ship it", "land this", "commit push PR", "merge this", or any variation of wanting to take completed work through the full git lifecycle. Also use after completing a feature or fix when it's time to get it into main. Includes CI monitoring — waits for checks to pass and fixes failures before merging.
---

# Ship: Branch → Commit → Push → PR → CI Green → Squash-Merge

This is the ScanBox git workflow. It takes completed work from the working tree all the way to a squash-merged commit on main. Every step is sequential — each depends on the previous one succeeding.

The pre-commit hook runs lint, format, and the full test suite automatically. The pre-push hook runs lint, format, and rebase. You don't need to run these manually — but if they fail, fix the issue before retrying. Never use `--no-verify`.

## The Workflow

### 1. Assess the state

Before anything, understand what you're working with:

```
git status          # what's changed?
git diff            # what exactly changed? (staged + unstaged)
git log --oneline -5  # recent commit style
```

If there are no changes, stop — there's nothing to ship.

### 2. Create a feature branch

Branch naming follows conventional commit types:

```
git checkout -b <type>/<short-description>
```

Types: `feat/`, `fix/`, `docs/`, `test/`, `ci/`, `chore/`, `refactor/`

Examples: `feat/sse-progress`, `fix/broken-badge`, `docs/readme-screenshots`

If already on a feature branch (not `main`), skip this step.

### 3. Stage specific files

Stage files by name. Never use `git add -A` or `git add .` — these can accidentally include secrets, build artifacts, or unrelated changes.

```
git add path/to/file1 path/to/file2
```

Review what you're about to commit: `git diff --cached`

### 4. Commit with a conventional message

Write a concise conventional commit message. Focus on **why**, not what. The diff shows what changed.

```
git commit -m "$(cat <<'EOF'
type: short summary of the change

Optional body explaining motivation or context if the summary
isn't self-explanatory. Keep it to 1-3 sentences.
EOF
)"
```

Rules:
- **No AI attribution.** No `Co-Authored-By`, `Signed-off-by`, or similar trailers. This is a project rule.
- The pre-commit hook will run `ruff check`, `ruff format --check`, and `pytest`. If it fails, fix the issue and create a **new** commit (don't amend).
- Use the imperative mood: "add feature" not "added feature"

### 5. Push to remote

```
git push -u origin <branch-name>
```

The pre-push hook runs lint, format checks, and `git pull --rebase --autostash`. If rebase conflicts arise, resolve them before retrying.

### 6. Create a pull request

Use `gh pr create` with this structure:

```
gh pr create --title "<type>: short title" --body "$(cat <<'EOF'
## Summary
- <1-3 bullet points explaining what and why>

## Test plan
- [ ] <verification steps>

EOF
)"
```

The title should be under 70 characters and use the same conventional commit prefix as the commit. Keep details in the body, not the title.

### 7. Wait for CI and fix failures

**This step is mandatory.** Never squash-merge until all CI checks pass.

Check CI status:

```
gh pr checks <number>
```

CI runs four checks: **Lint**, **Test**, **Docker Build**, and **Validate Conventional Commit**.

**If checks are still running**, wait and re-check:

```
gh pr checks <number> --watch --fail-fast
```

**If any check fails**, diagnose and fix:

1. Identify which check failed from `gh pr checks <number>`
2. Get the failed run ID from the URL and view the logs:
   ```
   gh run view <run-id> --log-failed
   ```
3. Diagnose the root cause from the log output
4. Fix the issue in the working tree
5. Stage, commit (new commit, not amend), and push:
   ```
   git add <fixed-files>
   git commit -m "fix: <what was fixed for CI>"
   git push
   ```
6. Wait for CI again — go back to the top of this step

**Repeat this loop until all checks pass.** Common CI failures:

| Check | Common cause | Fix |
|-------|-------------|-----|
| Lint | Unused import, formatting | `ruff check --fix && ruff format`, then commit |
| Test | Missing fixture, import error | Read the traceback, fix the test or code |
| Docker Build | Missing system dep, syntax error | Check Dockerfile and dependencies |
| Validate Conventional Commit | PR title format | `gh pr edit <number> --title "type: ..."` |

**After all checks pass, verify zero warnings:**

```
gh run view <run-id> --log 2>&1 | grep '##\[warning\]'
```

This must produce **no output**. If any `##[warning]` lines appear, they must be fixed before merging. Common warnings:

| Warning | Fix |
|---------|-----|
| Node.js deprecation on actions | Upgrade action to latest major version (e.g. `checkout@v6`) |
| pip root user / upgrade notice | Add `--root-user-action=ignore --disable-pip-version-check` to Dockerfile |
| Python DeprecationWarning | Fix the deprecated API usage in the code |

### 8. Squash-merge and delete the branch

Only proceed here when all checks pass AND zero warnings exist.

```
gh pr merge <number> --squash --delete-branch
```

This maintains linear history (no merge commits) and cleans up the remote branch in one step.

### 9. Return to main

```
git checkout main && git pull
```

Verify the merge landed:

```
git log --oneline -3
```

## When things go wrong

**Pre-commit hook fails:** Fix the lint/format/test issue. Create a new commit — never amend, because the failed commit didn't actually happen and amending would modify the previous commit.

**Push is rejected:** The pre-push hook rebases automatically. If there are conflicts, resolve them manually, then push again.

**PR has CI failures:** Follow step 7 — diagnose, fix, push, re-check. Never skip CI.

**Squash-merge fails:** Usually a branch protection issue or pending CI. Check `gh pr checks <number>` to see what's blocking.

## What this workflow does NOT do

- It does not skip CI — never merge with failing checks
- It does not force push or amend commits — linear history means new commits only
- It does not push to main directly — always goes through a PR
