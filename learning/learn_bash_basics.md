# Bash Basics

## Overview

The terminal is a text interface to your computer. Instead of clicking buttons, you type
commands. **Bash** (Bourne Again SHell) is the program that reads what you type and runs
it. On macOS, the default is **zsh** — a close relative of bash with the same core commands.

Data engineers use the terminal constantly:

- Running pipelines: `python run_pipeline.py`
- Managing dbt: `dbt run`, `dbt test`, `dbt seed`
- Installing packages: `pip install -r requirements.txt`
- Setting environment variables before running tools
- Navigating to the right directory before running anything
- Searching through code and logs

## Everyday analogy

The terminal is like giving instructions to a very literal assistant: "Go to the project
folder. List everything in it. Copy this file here." Every command is an instruction with
a specific format. The assistant does exactly what you say — no more, no less — which is
both its power and its danger.

---

## In the project

### The prompt

When you open a terminal you see something like:

```
gavin.reid@Gavins-MacBook catalog_data_platform %
```

Breaking it down:
- `gavin.reid` — your username
- `@Gavins-MacBook` — the machine name
- `catalog_data_platform` — the current directory you are in
- `%` — the prompt character (zsh uses `%`, bash uses `$`)

Everything you type appears after the prompt. Press Enter to run it.

---

### Part 1 — Navigation

#### `pwd` — where am I?

```bash
pwd
```

**P**rint **W**orking **D**irectory. Prints the full path of the directory you are
currently in. Always a good first command if you are disoriented.

```
/Users/gavin.reid/gavin/catalog_data_platform
```

#### `ls` — what is in here?

```bash
ls              # list files and folders
ls -l           # long format — shows permissions, size, date
ls -lh          # long format with human-readable sizes (KB, MB, GB)
ls docs/        # list the contents of a specific folder
```

```
-rw-r--r--  1 gavin.reid  41K  28 Apr  learn_dbt_fundamentals.docx
-rw-r--r--  1 gavin.reid  13K  28 Apr  learn_dbt_fundamentals.md
```

The columns in `-l` format: permissions | owner | size | date | filename.

#### `cd` — move to a different directory

```bash
cd dbt_project          # go into the dbt_project folder
cd ..                   # go up one level (to the parent directory)
cd ../..                # go up two levels
cd ~                    # go to your home directory (/Users/gavin.reid)
cd -                    # go back to the previous directory
cd /Users/gavin.reid/gavin/catalog_data_platform  # go to an absolute path
```

**Relative vs absolute paths:**
- Relative: `cd dbt_project` — relative to where you currently are
- Absolute: `cd /Users/gavin.reid/gavin/catalog_data_platform` — from the root of the filesystem

**Project use:** Most tools in this project must be run from the project root or a specific
subdirectory. dbt commands run from `dbt_project/`:

```bash
cd dbt_project && dbt run
```

---

### Part 2 — Working with files and directories

#### `mkdir` — create a directory

```bash
mkdir docs              # create a folder called docs
mkdir -p docs/learning  # create docs/learning, creating docs first if needed
```

The `-p` flag means "create parent directories as needed" and does not error if the
directory already exists. You will use `-p` almost every time.

#### `cp` — copy a file

```bash
cp .env.example .env            # copy .env.example to a new file called .env
cp file.py backup_file.py       # copy within the same directory
cp -r docs/ docs_backup/        # copy a whole directory (-r means recursive)
```

**Project use:** Setting up credentials for the first time:
```bash
cp .env.example .env
# then open .env and fill in your actual keys
```

#### `mv` — move or rename a file

```bash
mv old_name.py new_name.py      # rename a file
mv file.py extractor/file.py    # move a file to a different directory
mv folder/ new_folder/          # rename a directory
```

`mv` does not copy — after moving, the file only exists in the new location.

#### `rm` — delete a file

```bash
rm file.py                  # delete a file
rm -r old_folder/           # delete a directory and everything inside it
```

**Warning:** There is no Recycle Bin. `rm` is permanent. `rm -r` on the wrong
directory can delete large amounts of work instantly. Double-check before running.

#### `touch` — create an empty file

```bash
touch __init__.py           # create an empty file
```

Commonly used to create the empty `__init__.py` files that Python needs to treat a
directory as a package.

---

### Part 3 — Reading files

#### `cat` — print a whole file

```bash
cat .env.example            # print the whole file to the terminal
cat requirements.txt
```

Short files only — `cat` prints everything at once with no way to scroll.

#### `head` and `tail` — first or last lines

```bash
head -20 extractor/endpoints.py     # first 20 lines
tail -20 extractor/endpoints.py     # last 20 lines
tail -f pipeline.log                # follow a file as it grows (useful for logs)
```

`tail -f` streams new lines as they are written. Press `Ctrl+C` to stop.

#### `less` — scroll through a file

```bash
less extractor/endpoints.py
```

Opens the file in a pager you can scroll through. Navigation:
- `Space` / `f` — page down
- `b` — page up
- `q` — quit
- `/search_term` — search forward
- `n` — next match

---

### Part 4 — Searching

#### `grep` — search for text inside files

```bash
grep "product_ref" extractor/endpoints.py          # search in one file
grep -r "product_ref" extractor/                   # search recursively in a folder
grep -r "product_ref" extractor/ -l                # list only filenames with matches
grep -r "product_ref" extractor/ -n                # show line numbers
grep -i "makito" docs/                             # case-insensitive search
grep -v "^#" .env                                  # show lines that do NOT start with #
```

**Project use:** Finding where a variable or function is used across the codebase:
```bash
grep -rn "add_to_basket" ui/
```

Finding lines in `.env` that are not comments (used when loading env vars):
```bash
grep -v '^#' .env | grep -v '^ '
```

#### `find` — search for files by name or type

```bash
find . -name "*.parquet"            # find all parquet files from current directory
find . -name "*.py" -type f         # find all Python files
find . -name "__pycache__" -type d  # find all __pycache__ directories
find dbt_project -name "*.sql"      # find all SQL files in dbt_project
```

**Project use:** Checking what Parquet files the pipeline has created:
```bash
find . -name "*.parquet" -type f
```

---

### Part 5 — Environment variables

Environment variables are named values stored in your shell session. Programs read them
to get configuration — credentials, paths, settings — without those values being hardcoded
in the source code.

#### `export` — set an environment variable

```bash
export DUCKDB_PATH=/Users/gavin.reid/gavin/catalog_data_platform/data/catalog_data_platform.duckdb
export AWS_DEFAULT_REGION=eu-south-2
```

`export` makes the variable available to any child processes (programs you run from this
shell). Without `export`, the variable would only be visible in the current shell script.

**Project use:** Setting the DuckDB path before running dbt:
```bash
export DUCKDB_PATH=/Users/gavin.reid/gavin/catalog_data_platform/data/catalog_data_platform.duckdb
cd dbt_project && dbt run
```

Variables set with `export` only last for the current terminal session. Close the terminal
and they are gone.

#### `echo` — print a value

```bash
echo $DUCKDB_PATH           # print the value of an env var (note the $ prefix)
echo "Hello, world"
echo $HOME                  # your home directory
echo $PATH                  # the list of directories where the shell looks for commands
```

#### `env` — list all environment variables

```bash
env                         # print every environment variable and its value
env | grep AWS              # filter to only show AWS-related variables
```

#### Loading `.env` files

The `.env` file contains variables in `KEY=VALUE` format, one per line. A common pattern
to load them into your shell without installing any extra tools:

```bash
export $(grep -v '^#' .env | grep -v '^ ' | xargs)
```

Breaking this down:
- `grep -v '^#'` — skip comment lines (lines starting with `#`)
- `grep -v '^ '` — skip blank/whitespace-only lines
- `xargs` — converts the newline-separated list into space-separated arguments
- `export $(...)` — exports each `KEY=VALUE` pair as an environment variable

**Project use:** When running dbt manually without `run_pipeline.py`:
```bash
export $(grep -v '^#' .env | grep -v '^ ' | xargs)
cd dbt_project && dbt run
```

---

### Part 6 — Chaining commands

#### `&&` — run the next command only if the previous succeeded

```bash
cd dbt_project && dbt run
dbt seed && dbt run && dbt test
```

If `cd dbt_project` fails (the directory does not exist), `dbt run` will not run.
Use `&&` when the second command depends on the first succeeding.

**Project use:** The full dbt pipeline:
```bash
cd dbt_project && dbt seed && dbt run && dbt test
```

#### `;` — run the next command regardless

```bash
dbt run ; echo "dbt finished"
```

The `echo` runs whether `dbt run` succeeds or fails. Use `;` when you want cleanup
commands to always run.

#### `|` — pipe output from one command into another

```bash
grep -r "import" ui/ | grep "basket"        # find import lines containing "basket"
ls -lh docs/ | grep ".md"                   # list only .md files in docs/
env | grep -i aws                            # find AWS environment variables
cat requirements.txt | grep dbt             # find dbt packages in requirements
```

The pipe `|` takes the output of the left command and feeds it as input to the right
command. This is the Unix philosophy: small tools that do one thing, chained together.

#### `>` and `>>` — redirect output to a file

```bash
dbt run > dbt_output.log 2>&1       # save all output (stdout + stderr) to a file
dbt run >> dbt_output.log 2>&1      # append to the file instead of overwriting
```

- `>` overwrites the file
- `>>` appends to the file
- `2>&1` redirects error output (stderr) to the same place as standard output (stdout)

---

### Part 7 — Processes and running programs

#### `python3` / `python`

```bash
python3 run_pipeline.py             # run the pipeline
python3 -m pytest tests/            # run tests (using the module runner)
python3 -c "import duckdb; print(duckdb.__version__)"   # run a snippet inline
```

#### Virtual environments

```bash
python3 -m venv .venv               # create a virtual environment
source .venv/bin/activate           # activate it (prompt changes to show (.venv))
deactivate                          # deactivate — back to system Python
which python3                       # check which Python is active
pip install -r requirements.txt     # install all packages
pip list                            # see installed packages
```

**Project use:** Always activate the virtual environment before working:
```bash
source .venv/bin/activate
```

#### `which` — find where a command lives

```bash
which python3       # /Users/gavin.reid/gavin/catalog_data_platform/.venv/bin/python3
which dbt           # /Users/gavin.reid/gavin/catalog_data_platform/.venv/bin/dbt
which git           # /usr/bin/git
```

If `which python3` shows the system Python instead of your venv, the venv is not activated.

#### `ps` and `kill` — managing processes

```bash
ps aux | grep streamlit     # find the Streamlit process
kill 12345                  # send a stop signal to process ID 12345
kill -9 12345               # force kill (use if regular kill doesn't work)
```

**Project use:** Finding a process that is holding the DuckDB file lock:
```bash
ps aux | grep streamlit
```

---

### Part 8 — Shortcuts and quality of life

| Shortcut | What it does |
|---|---|
| `Tab` | Autocomplete file and directory names |
| `Tab Tab` | Show all possible completions |
| `↑` / `↓` | Scroll through previous commands |
| `Ctrl+C` | Stop the currently running process |
| `Ctrl+L` | Clear the terminal screen |
| `Ctrl+A` | Jump to start of line |
| `Ctrl+E` | Jump to end of line |
| `!!` | Repeat the last command |
| `history` | Show all recent commands |
| `history | grep dbt` | Find previous dbt commands |

---

## Glossary

| Term | Meaning |
|---|---|
| Shell | The program that interprets commands (bash, zsh) |
| Terminal | The window/app that runs the shell |
| Working directory | The directory you are currently "in" |
| Absolute path | A path from the root of the filesystem: `/Users/gavin.reid/...` |
| Relative path | A path relative to the current directory: `docs/learning/` |
| `..` | The parent directory |
| `.` | The current directory |
| `~` | Your home directory |
| `$VAR` | The value of environment variable `VAR` |
| Pipe (`\|`) | Pass the output of one command as input to another |
| `&&` | Run next command only if previous succeeded |
| `>` | Redirect output to a file (overwrites) |
| `>>` | Redirect output to a file (appends) |
| `stdin` / `stdout` / `stderr` | Standard input, output, and error streams |
| Flag / option | A modifier to a command, usually prefixed with `-` or `--` |
| Recursive | Applies to a directory and everything inside it (`-r` flag) |

---

## Cheat sheet

```bash
# Navigation
pwd                             # where am I?
ls -lh                          # what's in here?
cd folder/                      # go into folder
cd ..                           # go up one level
cd -                            # go back to previous location

# Files
cp source dest                  # copy
mv source dest                  # move/rename
rm file                         # delete file
rm -r folder/                   # delete folder (careful!)
mkdir -p path/to/folder         # create directory (and parents)
touch file.py                   # create empty file

# Reading
cat file                        # print whole file
head -20 file                   # first 20 lines
tail -f file                    # follow a growing file
less file                       # scrollable view (q to quit)

# Searching
grep "term" file                # search in a file
grep -rn "term" folder/         # recursive, with line numbers
find . -name "*.py"             # find files by name

# Environment
export KEY=value                # set an environment variable
echo $KEY                       # print its value
env | grep KEY                  # check if it's set

# Chaining
cmd1 && cmd2                    # run cmd2 only if cmd1 succeeds
cmd1 | cmd2                     # pipe output of cmd1 into cmd2
cmd > file.log 2>&1             # save all output to a file

# Python / project
source .venv/bin/activate       # activate virtual environment
which python3                   # check which Python is active
python3 run_pipeline.py         # run the pipeline
python3 -m pytest tests/        # run tests
streamlit run ui/app.py         # start the UI
```

---

## Practice

**Questions:**

1. What is the difference between an absolute path and a relative path? Give an example
   of each using the project structure.

2. Why does `&&` exist as a way to chain commands, rather than using `;`? Give an
   example from the project where the difference matters.

3. What does `export` do that setting a variable without it does not, and why does it
   matter when running dbt?

4. You type `dbt run` and get `zsh: command not found: dbt`. What are two likely causes,
   and what command would you run first to diagnose which it is?

**Short tasks:**

5. Print the full path of your current directory. Then navigate to
   `dbt_project/models/intermediate/` and list its contents. Return to the project root
   in one command.

6. Find all `.sql` files in `dbt_project/`. How many are there?

7. Set the `DUCKDB_PATH` environment variable to the correct local path. Confirm it is
   set with `echo $DUCKDB_PATH`.
