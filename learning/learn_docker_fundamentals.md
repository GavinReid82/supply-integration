# Docker Fundamentals

## Overview

Software that runs perfectly on your laptop can fail on a colleague's machine or on a
server because of different Python versions, missing libraries, or conflicting environment
variables.

**Docker solves this by packaging your code *together with everything it needs to run*** —
the operating system slice, Python version, libraries, and config — into a single portable
unit called a **container**.

Key concepts:

| Concept | What it is |
|---|---|
| **Image** | A read-only snapshot of an environment. A recipe for a container. |
| **Container** | A running instance of an image. Isolated process with its own filesystem. |
| **Dockerfile** | Text file of instructions that define how to build an image. |
| **Docker Compose** | Tool for defining and running multi-container applications. |
| **Volume** | A mount that links a host directory to a container directory. |
| **Port mapping** | Forwarding a host port to a container port (e.g., `8501:8501`). |

## Everyday analogy

Think of a Docker container like a self-contained lunch box: everything needed for the
meal is inside, and it works the same whether you open it at your desk, on a train, or
in a different country.

- A **Docker image** is like a cake mould — a recipe that is inert on its own.
- A **container** is the actual cake — a running instance made from that mould.
- **Docker Compose** is like a stage manager: it cues each performer (container) in
  the right order and makes sure they can communicate.
- A **volume** is a hatch between your host machine and the container — things written
  inside the container to that path appear on your host, and survive when the container stops.

---

## In the project

### Core concepts in detail

**Layers** — Each line in a Dockerfile creates a cached snapshot. If you change line 5,
only lines 5 onwards are re-run on the next build.

**Environment variables** — Sensitive config (API keys, credentials) should never be
baked into an image. `env_file: .env` tells Docker to inject variables from your `.env`
file into the container at runtime without copying the file into the image.

**`.dockerignore`** — Tells Docker what to exclude when copying files into the image.
Works exactly like `.gitignore`. Excluding `.venv/` keeps the image lean. Excluding
`.env` keeps secrets out of the image.

---

### The `catalog_data_platform` Dockerfile — line by line

```dockerfile
FROM python:3.11-slim
```
**Base image.** Start from an official Python 3.11 image built on a minimal Debian Linux.
"Slim" means no extras — keeps the image small.

```dockerfile
WORKDIR /app
```
**Working directory.** All subsequent commands run from `/app` inside the container.
If `/app` doesn't exist, Docker creates it.

```dockerfile
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```
**Dependency layer.** Copy *only* `requirements.txt` first, then install. This is a
deliberate ordering trick: Docker caches each layer. If your code changes but
`requirements.txt` doesn't, Docker skips re-installing packages on the next build —
saving minutes.

```dockerfile
COPY . .
```
**Application code.** Now copy everything else (filtered by `.dockerignore`). This layer
invalidates every time code changes, but since packages were already installed in a prior
cached layer, the build stays fast.

```dockerfile
CMD ["python", "run_pipeline.py"]
```
**Default command.** What to run when the container starts. This is overridden in
`docker-compose.yml` for the `ui` service.

---

### The `docker-compose.yml` — service by service

```yaml
services:
  pipeline:
    build: .                              # build image from Dockerfile in this directory
    env_file: .env                        # inject credentials at runtime
    volumes:
      - ./data:/app/data                  # persist DuckDB file on host
      - ./dbt_project:/app/dbt_project    # live-edit dbt models without rebuilding
    command: python run_pipeline.py       # override CMD: run the ELT pipeline
```

The **pipeline** service runs the full ELT: extract supplier data → load to DuckDB →
dbt transform. The `./data` volume means the resulting DuckDB database file survives
after the container stops.

```yaml
  ui:
    build: .                              # same image as pipeline
    env_file: .env
    ports:
      - "8501:8501"                       # expose Streamlit on your browser
    volumes:
      - ./data:/app/data                  # reads the DuckDB file written by pipeline
      - ./ui:/app/ui                      # live-edit UI code without rebuilding
    command: streamlit run ui/app.py --server.address=0.0.0.0
    depends_on:
      pipeline:
        condition: service_completed_successfully   # only start after pipeline finishes
```

The **ui** service reads the same DuckDB file the pipeline wrote, then serves the
Streamlit app. `service_completed_successfully` means the UI won't start until the
pipeline has run to completion without errors.

**How the two services share data:**

```
Host filesystem
  └── ./data/catalog.duckdb
         ▲                    ▼
  pipeline container       ui container
  (writes DuckDB)         (reads DuckDB)
         └──── volume ────────┘
```

Both containers mount `./data` at `/app/data` simultaneously. The DuckDB file on the
host acts as the handoff point between the two services.

---

### The `.dockerignore` — what gets left out

```
.venv/        → local Python virtualenv — the image installs its own
.env          → secrets — injected at runtime, not baked in
data/         → DuckDB file — provided via volume, not baked in
.git/         → version control history — not needed at runtime
__pycache__/  → compiled Python bytecache — not needed, regenerated
*.pyc / *.pyo → compiled Python files — same reason
.DS_Store     → Mac metadata junk
```

Keeping the image free of `.env` is a **security practice**: if you ever push an image
to a registry, credentials won't be inside it.

---

## Glossary

| Term | Meaning |
|---|---|
| **Image** | A read-only snapshot of an environment. A recipe for a container. |
| **Container** | A running instance of an image. Isolated process with its own filesystem. |
| **Dockerfile** | Text file of instructions that define how to build an image. |
| **Layer** | A cached step in a Dockerfile. Layers are reused if unchanged. |
| **Docker Compose** | Tool for defining and running multi-container applications. |
| **Volume** | A mount that links a host directory to a container directory. |
| **Port mapping** | Forwarding a host port to a container port (e.g., `8501:8501`). |
| **`env_file`** | Injects environment variables from a file at container start. |
| **`.dockerignore`** | List of files/directories to exclude from the image build context. |
| **`depends_on`** | Compose directive controlling startup order between services. |
| **`service_completed_successfully`** | Condition ensuring a service only starts after another has exited with code 0. |
| **`CMD`** | Default command run when a container starts; can be overridden. |
| **`WORKDIR`** | Sets the working directory inside the container for subsequent steps. |
| **Base image** | The starting point for a Dockerfile (e.g., `python:3.11-slim`). |

---

## Cheat sheet

```
DOCKERFILE INSTRUCTIONS
  FROM <image>          — base image to start from
  WORKDIR <path>        — set working directory
  COPY <src> <dest>     — copy files from host into image
  RUN <command>         — execute a shell command during build
  CMD [...]             — default command when container starts
  ENV KEY=VALUE         — set env variable in the image

COMPOSE DIRECTIVES
  build: .              — build image from local Dockerfile
  env_file: .env        — load env vars from file at runtime
  volumes:              — mount host paths into container
  ports:                — map host:container ports
  command:              — override CMD from Dockerfile
  depends_on:           — control service startup order

KEY COMMANDS
  docker compose up --build     — build & start all services
  docker compose down           — stop & remove containers
  docker compose logs -f        — stream logs
  docker compose run --rm <svc> — run a one-off container
  docker ps                     — list running containers
  docker images                 — list images
  docker system prune           — clean up unused resources
```

---

## Practice

**Questions:**

1. What is the difference between a Docker *image* and a Docker *container*?

2. Why does the Dockerfile copy `requirements.txt` and run `pip install` *before*
   copying the rest of the code? What would happen if you swapped the order?

3. What does `service_completed_successfully` do, and why is it necessary in this
   project? What would go wrong if the `ui` service started at the same time as
   `pipeline`?

4. Why is `.env` listed in `.dockerignore`? What security risk does leaving it out of
   the ignore file create?

**Short tasks:**

5. Run `docker compose run --rm pipeline` and confirm the pipeline runs to completion.
   Check `data/` on your host to verify the DuckDB file was written.

6. Add `echo "Pipeline starting..."` as a shell step before `run_pipeline.py` executes.
   (Hint: change `command:` in `docker-compose.yml`.)

7. Intentionally break `requirements.txt` by adding a fake package name. Run
   `docker compose up --build` and read the error. Then fix it.
