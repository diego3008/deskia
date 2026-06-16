---
name: smart-commit
description: Use this skill when the user wants to commit all pending changes and create a pull request, asks to "commit everything", "make commits for my changes", "push and PR", "commit and push", or any similar request to package up repo changes into structured commits followed by a pull request. Always invoke this skill when the user wants to go from dirty working tree to a PR — don't handle this ad-hoc.
---

# Smart Commit

Your job is to look at everything uncommitted in the repo, group the changes into semantically meaningful commits, propose them to the user for approval, execute the commits, and open a pull request to `main`.

The goal is a clean, readable git history — each commit should represent one coherent unit of work, not one file.

---

## Phase 1 — Assess the working tree

Run these to understand the full picture:

```bash
git status
git diff --stat          # unstaged changes
git diff --cached --stat # staged changes
```

Then read the actual diffs to understand *what* changed and *why*:

```bash
git diff
git diff --cached
```

Also list untracked files:
```bash
git ls-files --others --exclude-standard
```

For untracked files that matter, read them to understand their purpose.

---

## Phase 2 — Group changes semantically

Look at everything — modified files, new files, deleted files — and group them by what they *do together*, not by file type or directory alone.

Good grouping signals:
- A source file and its test file belong together
- Files changed for the same bug fix or feature belong together
- Config/dependency changes (e.g. `package.json`, `requirements.txt`) belong together unless they're unrelated
- Wiki or documentation updates for the same topic belong together
- Completely unrelated changes across the codebase belong in separate commits

Think of it from the reviewer's perspective: if someone reads the commit, will all the files in it make sense together?

---

## Phase 3 — Draft commit messages

For each group, write a commit message with this structure:

```
<type>(<scope>): <what changed>

<why it was changed and what impact it has>
```

- **type**: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`
- **scope**: the area of the codebase (e.g. `wiki`, `interviewer-skill`, `course-schedule`)
- **first line**: 50–72 chars, imperative mood ("add X", not "added X")
- **body**: 1–3 sentences on the motivation and effect. Be concrete — mention the pattern, algorithm, or behavior affected.

Example:

```
feat(wiki): add pattern confidence tracking to database schema

Extended database.csv to include `pattern` and `confidence_delta` columns
so the technical interviewer skill can rank problems by weakness. Without
this, problem selection was purely random and couldn't adapt to the
candidate's history.
```

---

## Phase 4 — Present the plan for approval

Show the user the proposed commit plan before touching the index. Format it clearly:

```
## Proposed commits

### Commit 1 — feat(wiki): add pattern confidence tracking to database schema
Files: wiki/database.csv, wiki/log.md
> Extended database.csv to include `pattern` and `confidence_delta` columns...

### Commit 2 — chore(skills): add technical-interviewer and smart-commit skills
Files: .claude/SKILLS/technical-interviewer/SKILL.md, .claude/SKILLS/smart-commit/SKILL.md
> New mock interview and batch-commit skills for the job hunt workflow...

---
Proceed with these commits? (yes / edit / cancel)
```

Wait for the user's response before doing anything to the repo.

- **yes** → proceed to Phase 5
- **edit** → let them tell you what to change (merge groups, split a commit, reword a message), then re-present
- **cancel** → stop, leave the working tree untouched

---

## Phase 5 — Execute the commits

For each commit in order:
1. Stage only the files for that commit: `git add <file1> <file2> ...`
2. Commit with the full message (subject + body) using a heredoc to preserve formatting
3. Confirm the commit succeeded before moving to the next

Never use `git add .` or `git add -A` — stage file by file so each commit contains exactly what was planned.

---

## Phase 6 — Push and open the PR

Push the current branch to the remote:

```bash
git push -u origin HEAD
```

Then create the PR targeting `main`:

```bash
gh pr create --title "<concise PR title>" --body "$(cat <<'EOF'
## Summary
- <bullet 1>
- <bullet 2>
- <bullet 3>

## Changes
<brief description of what this PR as a whole accomplishes>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

The PR title should describe the overall theme of the batch (e.g. "Add mock interview skill and smart-commit workflow"). The body should list the main changes across all commits — not a per-commit repeat, but a high-level picture for the reviewer.

Return the PR URL to the user when done.
