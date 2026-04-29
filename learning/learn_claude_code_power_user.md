# Getting the Most Out of Claude Code

## Overview

Claude Code is an AI coding assistant that runs in your terminal and talks directly to your files, shell, and version control. Beyond chatting, it can execute multi-step tasks autonomously, run shell commands, edit files, spawn sub-agents, and trigger automated behaviours through hooks. The difference between a casual user and a power user is understanding these layers: the conversation layer (prompts, skills, memory), the automation layer (hooks, settings), and the extension layer (MCP servers, sub-agents).

---

## Everyday Analogy

Think of Claude Code like a new senior engineer joining your team. On day one they're capable but uninformed — they don't know your conventions, your pipeline, or your preferences. Over time you teach them: you write a project brief (CLAUDE.md), set up automatic checks (hooks), give them specialist colleagues to call on (skills and MCP servers), and let them remember things between conversations (memory). The more you invest in that onboarding, the more autonomously and accurately they work.

---

## In the Project

Your current setup already has good TypeScript automation. Here is where you stand and where the gaps are:

| Layer | What you have | What you could add |
|---|---|---|
| Hooks | `test-ts.sh` (PostToolUse), `check-ts.sh` + `build-ts.sh` (Stop) | PreToolUse linting, notifications, Python/SQL hooks |
| Skills | 10 skills including `supply-integration`, `learn-me` | New skills for daily workflows |
| Settings | `auto` mode, `skipAutoPermissionPrompt` | Per-project settings files, env vars |
| MCP servers | None configured | Google Drive, Gmail, Linear, BigQuery |
| Memory | Auto-memory active | Manual memory writes for key decisions |
| CLAUDE.md | Unknown (see practice below) | Project-level context docs |

---

## The Five Layers

### 1. Hooks — Automate on Events

Hooks are shell scripts that Claude Code runs at specific moments. They receive a JSON payload on stdin describing what just happened.

**Hook events:**

| Event | Fires when | Your use |
|---|---|---|
| `PreToolUse` | Before Claude calls a tool | Block dangerous commands, lint before edits |
| `PostToolUse` | After a tool call completes | Run tests (you have this) |
| `Notification` | Claude sends a notification | Desktop alert, Slack ping |
| `Stop` | Claude finishes its turn | Type check + build (you have this) |
| `SubagentStop` | A sub-agent finishes | Same as Stop but for agents |

**Example — notify when a long task finishes (Stop hook):**

```bash
#!/usr/bin/env bash
# ~/.claude/hooks/notify-done.sh
input=$(cat)
osascript -e 'display notification "Claude finished" with title "Claude Code"'
```

Add to `settings.json`:
```json
"Stop": [{ "hooks": [{ "type": "command", "command": "~/.claude/hooks/notify-done.sh" }] }]
```

**Example — block `rm -rf` (PreToolUse hook):**

```bash
#!/usr/bin/env bash
input=$(cat)
cmd=$(echo "$input" | jq -r '.tool_input.command // ""')
if echo "$cmd" | grep -q 'rm -rf'; then
  echo '{"decision":"block","reason":"rm -rf is blocked by hook policy"}'
  exit 0
fi
exit 0
```

**Hook exit codes:**
- `0` = success, pass feedback to Claude
- `2` = block the tool call (PreToolUse only)
- Non-zero = error, Claude sees the output as feedback

**Adding a Python/dbt hook** — useful for your pipeline work:

```bash
#!/usr/bin/env bash
input=$(cat)
file=$(echo "$input" | jq -r '.tool_input.file_path // ""')
[[ "$file" != *.sql ]] && exit 0
# run sqlfluff on the edited file
sqlfluff lint "$file" 2>&1
exit $?
```

---

### 2. CLAUDE.md — Project Context Files

CLAUDE.md files are read at the start of every session and injected into Claude's context. They tell Claude about the project without you having to explain it each time. Claude Code looks for them in the current directory and every parent directory up to `~`.

**Where to put them:**

```
~/.claude/CLAUDE.md               ← global, applies everywhere
~/gavin/catalog_data_platform/CLAUDE.md  ← applies when working in this repo
~/gavin/supply_integration/CLAUDE.md     ← applies when working here
```

**What to put in them:**

```markdown
# catalog_data_platform

## Architecture
- BigQuery dataset: `catalog_data_platform`
- dbt models: `models/` — staging → intermediate → mart layers
- Orchestration: Airflow, DAGs in `dags/`
- Variants must have `is_available` and `attribute_json` fields (not yet added)

## Conventions
- All dbt models use `{{ ref() }}` — never hardcoded table names
- Per-supplier intermediates, then UNION ALL at mart layer
- print_prices schema change required before adding XDC supplier

## Do not
- Do not use `SELECT *` in mart models
- Do not modify `models/marts/` without checking the print_prices schema first
```

Run `/init` in any project directory to have Claude generate a CLAUDE.md automatically.

---

### 3. Skills — Custom Slash Commands

Skills are markdown files that Claude reads as instructions when you type `/skill-name`. They live in `~/.claude/skills/<name>/skill.md`.

**You already have:** `supply-integration`, `learn-me`, `todays-plan`, `grill-me`, `update-docs`, and others.

**Anatomy of a skill:**

```
~/.claude/skills/my-skill/
  skill.md         ← instructions Claude follows
  resources/       ← any files Claude can reference
```

**Writing a new skill** — use `/write-a-skill` to scaffold one. Example prompt:

```
/write-a-skill
Name: daily-standup
Purpose: Generate a standup update from today's git commits across my projects
```

**Useful skill ideas for your stack:**

| Skill name | What it would do |
|---|---|
| `dbt-review` | Review a dbt model for conventions before committing |
| `supplier-checklist` | Walk through the supplier integration checklist for supply_integration |
| `bq-query` | Run a BigQuery query and return results in a table |
| `pr-summary` | Write a PR description from git diff |

---

### 4. MCP Servers — Connect External Tools

MCP (Model Context Protocol) servers give Claude tools to talk to external services: databases, APIs, file stores. You have none configured yet — this is your biggest untapped area.

**Configure in `~/.claude/settings.json`:**

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/gavin.reid/gavin"]
    },
    "bigquery": {
      "command": "uvx",
      "args": ["mcp-server-bigquery", "--project", "your-gcp-project"]
    }
  }
}
```

**MCP servers relevant to your work:**

| Server | What it gives Claude | Install |
|---|---|---|
| `@modelcontextprotocol/server-filesystem` | Read/write files outside the working dir | `npx -y @modelcontextprotocol/server-filesystem <path>` |
| `mcp-server-bigquery` | Run BigQuery queries directly | `uvx mcp-server-bigquery` |
| `@modelcontextprotocol/server-github` | Read PRs, issues, repos | `npx -y @modelcontextprotocol/server-github` |
| `@modelcontextprotocol/server-postgres` | Query a Postgres DB | `npx -y @modelcontextprotocol/server-postgres <conn-string>` |

**Claude.ai also has built-in MCP integrations** (Gmail, Google Drive, Linear, etc.) — you can see these in your session as `mcp__claude_ai_*` tools.

---

### 5. Memory — Persistent Context Across Sessions

Claude Code has an auto-memory system that writes to `~/.claude/projects/.../memory/`. It stores user profile, feedback, project state, and references.

**You can also write memories manually:**

```
Remember that in supply_integration, the 'all' product type means corporate gifts, not a catch-all.
```

**Four memory types:**

| Type | What it stores | Example |
|---|---|---|
| `user` | Your role, preferences, expertise | "Gavin is a data engineer comfortable with Python and SQL" |
| `feedback` | How Claude should behave | "Don't add comments explaining what code does" |
| `project` | Current goals, decisions, deadlines | "Merge freeze starts 2026-05-01 for XDC launch" |
| `reference` | Where to find things | "supply_integration DAGs are in airflow/dags/" |

**Memory vs CLAUDE.md:**
- CLAUDE.md = stable project facts (architecture, conventions) — check it into git
- Memory = dynamic, personal, cross-project context (preferences, current tasks)

---

## Advanced Techniques

### Sub-agents and Parallel Work

Claude can spawn sub-agents to run tasks in parallel. You trigger this implicitly when you ask Claude to "research X and Y simultaneously" or explicitly via the `Agent` tool in skills. Each sub-agent gets its own context — useful for:

- Running the same analysis on multiple suppliers at once
- Doing independent code review while you write new code
- Researching a question while implementing something else

### Git Worktrees for Isolation

Claude can work in an isolated git worktree — a separate checkout of the same repo. Use `/worktree` or the `isolation: "worktree"` parameter in skills. This means Claude can experiment on a branch without touching your working tree.

### Context Management

- `/clear` — wipe conversation context, start fresh (Claude re-reads CLAUDE.md)
- `/compact` — compress long conversations to save context space
- `!<command>` — run a shell command inline from the prompt; its output lands in the conversation
- `/fast` — toggle Opus fast mode (faster output, same model)

### Per-project Settings

You can have a `.claude/settings.json` inside any project directory. Settings cascade: project overrides global.

```
~/.claude/settings.json              ← global defaults
~/gavin/supply_integration/.claude/settings.json  ← project overrides
```

Useful for project-specific permissions:

```json
{
  "permissions": {
    "allow": ["Bash(gcloud:*)", "Bash(bq:*)"]
  }
}
```

### Environment Variables in Settings

```json
{
  "env": {
    "BIGQUERY_PROJECT": "helloprint-data",
    "DBT_PROFILES_DIR": "/Users/gavin.reid/gavin/catalog_data_platform"
  }
}
```

These are set for every Claude Code session automatically.

### The `fewer-permission-prompts` Skill

You have this skill. Run `/fewer-permission-prompts` — it scans your recent transcripts for common tool calls and adds them to an allowlist so you stop being prompted. Worth running every few weeks.

---

## Glossary

| Term | Meaning |
|---|---|
| Hook | Shell script triggered by a Claude Code event (PreToolUse, PostToolUse, Stop, etc.) |
| CLAUDE.md | Markdown file injected into context at session start — project documentation for Claude |
| Skill | Custom slash command — a markdown file of instructions Claude follows |
| MCP server | External process that gives Claude new tools (BigQuery, GitHub, filesystem, etc.) |
| Memory | Persistent notes stored between sessions in `~/.claude/projects/.../memory/` |
| Sub-agent | A separate Claude instance spawned to handle a task in parallel |
| Worktree | Isolated git checkout Claude can work in without touching your main branch |
| `/fast` | Toggle for Opus fast-output mode |
| `!<cmd>` | Inline shell command; output appears in the conversation |

---

## Cheat Sheet

```bash
# Session commands
/clear                    # wipe context, re-read CLAUDE.md
/compact                  # compress long conversation
/fast                     # toggle fast mode (Opus only)
/init                     # generate CLAUDE.md for current project
/fewer-permission-prompts # auto-allowlist common tool calls

# Inline shell
! git log --oneline -10   # run command, output into conversation
! bq query "SELECT..."    # run BQ query inline

# Memory
"Remember that X..."      # Claude writes a memory entry
"Forget that X..."        # Claude removes a memory entry

# Skills you have
/supply-integration       # supply_integration pipeline work
/learn-me <topic>         # create a learning document
/todays-plan              # prioritised next steps
/grill-me                 # stress-test a plan
/update-docs              # update project documentation
/update-on-ai             # digest of recent AI releases
/write-a-skill            # scaffold a new skill
/design-an-interface      # generate multiple interface designs in parallel

# Hook placement in settings.json
"PreToolUse"   ← fires before tool; exit 2 = block
"PostToolUse"  ← fires after tool; your test-ts.sh lives here
"Stop"         ← fires at end of turn; your check-ts + build live here
"Notification" ← fires on notifications
```

---

## Practice

1. **Inspect your CLAUDE.md files.** Run `find ~/gavin -name "CLAUDE.md" | head -20` in the terminal. If you find none in `catalog_data_platform/` or `supply_integration/`, run `/init` in each project to generate one, then review and edit what Claude wrote.

2. **Add a desktop notification hook.** Write a `notify-done.sh` hook (macOS `osascript` example above) and add it to the `Stop` event in your `settings.json`. Test it by asking Claude to do a small task.

3. **Try an MCP server.** Install the filesystem server for your `~/gavin` directory. Then ask Claude "list all CLAUDE.md files under ~/gavin" — it should be able to do this without a Bash call.

4. **Write a new skill.** Think of a task you repeat across sessions (e.g. generating a standup, reviewing a dbt model, checking a supplier config). Run `/write-a-skill` and describe what you want. Use it the next day to see if it saves time.

5. **Run `/fewer-permission-prompts`.** After a few working sessions, run this skill to add common safe tools to your allowlist. Then note how many fewer prompts you see in the next session.

---

## Q&A

### Q: How do I set up a BigQuery MCP server with read-only permissions?

Use two layers of protection:

**Layer 1 — GCP IAM (the real lock).** Create a dedicated service account and grant it only two roles: `roles/bigquery.dataViewer` (can SELECT and list tables) and `roles/bigquery.jobUser` (can submit query jobs). Do not grant `dataEditor`, `dataOwner`, or `admin`. Even if a DELETE query is sent, Google will refuse it at the API level.

```bash
gcloud iam service-accounts create claude-bq-readonly --display-name="Claude Code BigQuery Read-Only"
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:claude-bq-readonly@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer"
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:claude-bq-readonly@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"
gcloud iam service-accounts keys create ~/.claude/bq-readonly-key.json \
  --iam-account=claude-bq-readonly@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

**Layer 2 — PreToolUse hook (belt-and-braces).** A hook at `~/.claude/hooks/block-bq-writes.sh` intercepts MCP tool calls and blocks any query containing DELETE, DROP, TRUNCATE, INSERT, UPDATE, MERGE, or CREATE OR REPLACE before it is sent.

**Wire it up in `~/.claude/settings.json`:**

```json
{
  "mcpServers": {
    "bigquery": {
      "command": "uvx",
      "args": ["mcp-server-bigquery", "--project", "your-gcp-project-id"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/Users/gavin.reid/.claude/bq-readonly-key.json"
      }
    }
  }
}
```

Use `settings.local.json` (gitignored) for the key path so it stays off version control.

---

### Q: Can I scope an MCP server (or any permission) to one project and not others?

Yes — settings cascade from global down to project level. A `.claude/settings.json` inside a project directory merges with and overrides `~/.claude/settings.json` for that project only.

```
~/.claude/settings.json                              ← global defaults
~/gavin/catalog_data_platform/.claude/settings.json  ← active only in this project
~/gavin/supply_integration/.claude/settings.json     ← different rules here
```

Put the `mcpServers` block and any BigQuery permissions in the project-level file. In every other project the BigQuery MCP tools simply don't exist — Claude has no way to call them.

Use `settings.local.json` (same location, gitignored) for machine-specific values like credential file paths.
