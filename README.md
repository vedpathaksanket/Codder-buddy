# Coder Buddy

Turn a project description into a plan, implementation tasks, and downloadable source files using Groq and LangGraph. This version adds a browser studio while preserving a command-line workflow.

## What works

- Planner → architect → coder pipeline with validated structured responses.
- Responsive browser interface with progress, persistent history, a source viewer, deletion, and ZIP downloads.
- Per-project directories, safe relative paths, blocked symlinks, and no generated-code execution on the server.
- Complete planned-file coverage, nonempty-file checks, Python/JSON syntax validation, and one syntax-repair attempt per file.
- Bearer-token access, bounded input/output sizes, a four-job queue, and a 100-project storage limit.
- Explicit failures for missing configuration, provider errors, invalid output, and interrupted jobs.
- Locked dependencies, automated tests, CI, and a non-root Docker image.

**Deployment scope:** a private, single-owner application with one application worker and one shared access token. Anyone with that token can access every project. It is not a multi-user SaaS service. Do not expose it publicly without TLS and appropriate access controls. Generated projects are drafts requiring human review and isolated runtime testing; a completed job does not certify that its generated application is correct or production-ready.

## Quick start (Windows PowerShell, macOS, Linux)

Install Python 3.11–3.13 and [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
git clone https://github.com/vedpathaksanket/Codder-buddy.git
cd Codder-buddy
uv sync --frozen
```

Copy `.env.example` to `.env`:

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

```sh
# macOS / Linux
cp .env.example .env
```

Generate a server access token:

```sh
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Edit `.env` locally:

```dotenv
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b
CODER_BUDDY_TOKEN=paste_your_generated_random_token_here
CODER_BUDDY_DATA_DIR=data
```

Obtain the provider key from [Groq](https://console.groq.com/keys). The configured model must support tool calling and be available to your account. Provider usage and rate limits apply. Never commit `.env` or paste secrets into project prompts.

Start the application:

```sh
uv run uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

Open **http://127.0.0.1:8000**, enter `CODER_BUDDY_TOKEN`, and describe a project. The token is kept only in tab memory. Start with a small app, inspect its README and source, download the ZIP, and run its documented checks in a disposable environment.

Example brief:

> Build a responsive task manager using HTML, CSS and JavaScript. Include add/edit/delete, priorities, filters and local storage. Add setup and manual test instructions.

## CLI

```sh
uv run python main.py --prompt "Create a Python greeting program with a README" --output generated_projects/hello
```

With no `--prompt`, the CLI asks interactively. Each default run gets a new directory; an explicitly supplied output directory must be empty. CLI use needs `GROQ_API_KEY`, but not the web access token.

## Docker

After configuring `.env`:

```sh
docker compose up --build -d
docker compose logs -f
```

Compose binds only to `127.0.0.1:8000`, stores projects in a named volume, and runs as a non-root user. Stop with `docker compose down`; do not add `-v` unless you intend to delete saved data. For remote private hosting, place it behind an authenticated HTTPS reverse proxy or private network. Do not increase the worker count or run multiple replicas against the same data directory.

## Verification

```sh
uv sync --frozen
uv run pytest -q
uv run ruff check .
node --check web/app.js
# Browser test (requires Node.js 22+)
npm ci
npx playwright install chromium
npm run test:e2e
```

Tests cover the full three-stage pipeline with controlled model responses, file coverage, repair limits, path traversal, symlink escapes, authentication, persistent history, downloads, deletion, provider failure redaction, request limits, and queue isolation. They do not call Groq or spend API credits. The browser test starts a separate deterministic fixture server and exercises sign-in, generation, source viewing, ZIP download, mobile layout, deletion and disconnect. Local Chromium execution was blocked by the development environment; browser verification is configured in CI.

For a live smoke test, configure your key, request a tiny Python greeting project, inspect the downloaded files, and run its tests in isolation. Compare the actual result with the prompt. Repeat with a small browser project. A live provider test requires valid account credentials and was not performed in the development environment.

## Architecture and operations

- `agent/states.py`: validated planning, task and generated-file contracts.
- `agent/graph.py`: lazy model setup and bounded planner/architect/coder workflow.
- `agent/tools.py`: workspace confinement and non-executing syntax checks.
- `app.py`: authenticated API, single generation worker and SQLite metadata.
- `web/`: framework-free browser interface. Source is displayed as text, never rendered as executable HTML.
- `main.py`: CLI entry point.
- `tests/`: provider-free integration and regression tests.

A request moves through `queued → running → completed/failed`. The UI shows planning, architecture, coding and validation stages. Each model request has a 90-second timeout and at most two provider retries. A project is limited to 20 files, 100,000 characters per file, and 180,000 characters of existing-file context. These limits deliberately keep generation bounded. There is no shell tool, dependency installer, or runtime runner exposed to the model.

Jobs and prompts persist in `data/jobs.sqlite3`; files live in `data/projects/<id>/`. Treat this directory as private. Back it up while the application is stopped. Jobs active during a restart become failed and can be retried manually. Generation is serialized, and excess submissions return HTTP 429. Delete completed or failed projects to reclaim space. Rotating the token in `.env` requires a restart and disconnects existing clients.

`GET /healthz` is a public process liveness check, not a provider availability check. All `/api/*` routes require `Authorization: Bearer <token>`. Provider responses, secrets and source code are excluded from error logs; logs include the job ID and exception class for diagnosis.

## Output assurance and limitations

A completed result means every planned file was written, nonempty, and passed supported syntax checks. It does **not** mean JavaScript/HTML/CSS was runtime-tested, dependencies are secure, imports resolve, or the user's acceptance criteria passed. The UI and API expose this distinction. Review the code before installing dependencies or executing it.

Before a public multi-user release, add individual accounts and per-user authorization, an external durable queue, per-user quotas and billing controls, a sandboxed build/test service, dependency scanning, production monitoring, and load/security testing. The Docker configuration is supplied but must be built and verified on the target deployment host.

## Troubleshooting

- **Server refuses to start:** set a random `CODER_BUDDY_TOKEN` of at least 32 characters.
- **401:** use the server token, not the Groq API key.
- **503 on Generate:** configure `GROQ_API_KEY` and restart.
- **Failed generation:** check the logged exception class, provider quota, model access and network. Retry with a smaller project. Partial output is not offered as a successful download.
- **Queue full:** wait for a job to finish.
- **Project limit reached:** delete old projects.
- **File validation failure:** retry with a simpler brief; invalid output never receives a successful status.

Original project copyright: Codebasics Inc. All rights reserved. Existing sample projects remain unchanged.
