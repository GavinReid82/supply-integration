# GitHub Setup — Version Control and Publishing Your Portfolio

## What We Did

We initialised a git repository in the project, made an initial commit, created a
repository on GitHub, and pushed the code. The project is now publicly visible on
GitHub as part of your portfolio.

---

## Core Concepts

### Git vs GitHub

These are two different things that are often confused:

**Git** is a version control system — a tool installed on your computer that tracks
changes to files over time. It works completely offline. Every project that uses git
has a hidden `.git/` folder that stores the full history of every change ever made.

**GitHub** is a website that hosts git repositories in the cloud. It lets you back up
your code, share it publicly, and collaborate with others. There are alternatives
(GitLab, Bitbucket) but GitHub is the dominant platform for open source and portfolios.

The relationship: git is the tool, GitHub is a hosting service for git repositories.
You push your local git history up to GitHub.

---

### Why version control matters for a portfolio project

- Every change is recorded with a message explaining why — interviewers look at commit
  history to understand how you think and work
- You can roll back any mistake
- GitHub serves as proof that the code is yours and when you wrote it
- A public GitHub profile with real projects is often more persuasive than a CV

---

### What `.gitignore` does

Git tracks every file in your project by default. Some files must never be committed:

- `.env` — contains AWS keys and API credentials. If committed and pushed to a public
  repo, anyone on the internet could find and use them. This has happened to many
  developers and resulted in large unexpected AWS bills from automated bots.
- `.venv/` — thousands of files from installed packages. These are reproducible from
  `requirements.txt` and shouldn't be in version control.
- `data/` — the local DuckDB file. Large binary file, not source code.
- `__pycache__/`, `*.pyc` — Python bytecode, auto-generated, not source code.
- `dbt_project/target/` — dbt's compiled SQL output, auto-generated.

`.gitignore` is a file that lists patterns git should ignore. Git won't track any file
matching those patterns, and won't suggest adding them either.

---

## The Commands

### `git init`

```bash
git init
```

Creates a new git repository in the current directory. Adds a hidden `.git/` folder
that stores all version history. Run this once per project.

---

### `git add .`

```bash
git add .
```

Stages all changes — tells git "include these files in the next commit". The `.`
means "everything in the current directory". You can also add specific files:
`git add extractor/client.py`.

Staging is a deliberate step. It lets you review what you're about to commit before
committing. Always run `git status` after `git add` to check what's staged.

---

### `git status`

```bash
git status
```

Shows the current state: which files are staged (green), which are modified but not
staged (red), and which are untracked. Before any commit, read this output carefully.
The most common mistake is accidentally committing a file you didn't mean to.

---

### `git commit -m "..."`

```bash
git commit -m "Initial commit — MKO extraction, dbt/DuckDB transform, project docs"
```

Creates a snapshot of everything that's staged. The `-m` flag provides the commit
message inline. The message should explain **why** this change exists, not what files
changed (git already records that).

Good commit messages:
- `Add retry logic to handle Makito's ChunkedEncodingError`
- `Fix DuckDB S3 endpoint for eu-south-2 region`

Bad commit messages:
- `fix`
- `update code`
- `changes`

Your commit history is read by interviewers. Thoughtful messages signal that you work
carefully.

---

### `git remote add origin <url>`

```bash
git remote add origin https://github.com/GavinReid82/supply-integration.git
```

A "remote" is a copy of the repository hosted somewhere else (in this case GitHub).
`origin` is the conventional name for the primary remote. This command tells your
local git where to push to. You only run this once.

---

### `git branch -M main`

```bash
git branch -M main
```

Renames the default branch to `main`. Older git versions defaulted to `master`.
GitHub expects `main` now. This just keeps them consistent.

---

### `git push -u origin main`

```bash
git push -u origin main
```

Pushes your local commits to GitHub. Breaking it down:
- `push` — send commits to the remote
- `-u` — sets `origin main` as the default upstream, so future pushes can just be `git push`
- `origin` — the remote to push to
- `main` — the branch to push

After the first push, subsequent pushes are just:
```bash
git add .
git commit -m "your message"
git push
```

---

### Personal Access Tokens

GitHub stopped accepting account passwords for command-line operations in 2021.
Instead you use a **Personal Access Token (PAT)** — a long randomly generated string
that acts as a password specifically for API/command-line access.

PATs have scopes (what they're allowed to do) and expiry dates. Ours has `repo` scope
(read/write repositories) and 90 days expiry. When git prompts for a password,
you paste the PAT.

**Why not just use your password?**
A PAT can be scoped (only allows specific actions) and revoked individually without
changing your main account password. If a PAT leaks, you revoke just that token.
If your account password leaked, everything would be exposed.

---

## Issues We Hit

### Token pasted as username

**What happened:** git prompted for Username then Password. The Personal Access Token
was pasted into the Username field. The push still succeeded because GitHub is
tolerant of tokens in the username field — but the token was exposed in the terminal
output.

**Fix:** Revoked the token in GitHub Settings → Developer settings → Personal access
tokens → Revoke. Then generated a new one. The push had already succeeded so no
work was lost.

**Lesson:** Treat tokens exactly like passwords. If one is ever visible in a chat,
a log, a screenshot, or a commit — revoke it immediately. The time to revoke and
regenerate a token is less than 2 minutes.

---

## Useful Git Commands for Day-to-Day Work

```bash
git status                    # what's changed?
git diff                      # show exactly what changed in each file
git log --oneline             # view commit history, one line per commit
git add <file>                # stage a specific file
git add .                     # stage everything
git commit -m "message"       # commit staged changes
git push                      # push to GitHub (after first push with -u)
git pull                      # pull latest changes from GitHub
```

---

## What You Should Be Able to Explain

- The difference between git (the tool) and GitHub (the hosting service)
- What `.gitignore` does and why `.env` must be in it
- What staging is and why it's a separate step from committing
- What `git add`, `git commit`, and `git push` each do
- What a remote is and what `origin` refers to
- Why GitHub uses Personal Access Tokens instead of passwords
- Why commit messages matter for a portfolio
