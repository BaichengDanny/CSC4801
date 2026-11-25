# Installation Guide

Run commands from the repository root. The Docker path includes the app and its test runtime. Use the local Python path to run the app from source.

## Prerequisites and Versions

| Tool | Version | Use |
|---|---|---|
| Docker Desktop or Docker Engine | Docker 27.4 verified | Build and run the container |
| Python | 3.12, with 3.12.11 verified | Local app and Python tests |
| Node.js | 22 or newer for the Python suite's JavaScript checks. Use 24 for the combined suite and CI. | Tests outside Docker |
| Browser | A current Chrome, Edge, Firefox, or Safari. Use Chromium for automated acceptance. | Open the app and run the browser checks |

The first build or dependency install downloads the pinned packages and images. The app runs with SQLite on the same machine. Web fonts are optional and the pages fall back to system fonts.

## Dependency Installation

For a local Python install, use a virtual environment. The lock file pins Flask 3.1.2, Waitress 3.0.2, pytest 8.4.2, and their dependencies.

macOS or Linux

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The Docker build installs the same Python dependencies. The optional browser suite installs its own dependencies under [Running Unit Tests](#running-unit-tests).

## Environment Variables

Set configuration in the process environment. [.env.example](.env.example) is a reference file. Flask reads these settings from the environment at startup.

| Variable | Local default | Docker default | Purpose |
|---|---|---|---|
| `DATABASE` | `instance/recruiting.sqlite3` | `/app/data/recruiting.sqlite3` | SQLite file. Use the same path for migrations, seed, and startup. |
| `HOST` | `127.0.0.1` | `0.0.0.0` | Listen address. The Docker run command below restricts the host port to loopback. |
| `PORT` | `8080` | `8080` | Waitress port |
| `SECRET_KEY` | Random per process | Random per process | Signs session cookies. Set a persistent random value if sessions must survive restarts. |
| `COOKIE_SECURE` | `0` | `0` | Keep `0` for the local HTTP demo. Set `1` for HTTPS. |

The default configuration works for the local demo without supplying a secret. Changing the process secret invalidates existing cookies. Server-side sessions expire after 12 hours, and logout revokes the session immediately.

## Database Setup and Migrations

```sh
python -m flask --app recruiting init-db
```

The command applies pending SQL files in `recruiting/migrations/` in filename order and records them in `schema_migrations`. It is safe to rerun on an existing database. Migration 005 adds application status history, timestamps for bookings and resume changes, and candidate work preferences. The Docker entry point applies migrations before starting Waitress.

## Demo Data and Reset Command

Run this against a disposable local database. It replaces the existing data with demo fixtures and invalidates existing sessions.

```sh
python -m flask --app recruiting seed --yes
```

The command requires `--yes`. It loads three candidates, two employers, four core jobs, and all four application statuses. Two candidates are eligible for the same slot. It then loads the 39 sample jobs in `candidate/assets/jobs.json`, with one demo employer per company. Account names, skills, statuses, and slot offsets repeat across resets. Password salts and session-generation values are random. [README.md](README.md#demo-accounts) lists the accounts and matching examples.

The default clock places slots at 18:00, 19:00, or 20:00 UTC the next UTC day. The first slot shows as 10:00 AM Pacific in winter or 11:00 AM in summer. Pass an explicit offset to reproduce exact slot times. Use the default for a live demo so the slots are still in the future.

```sh
python -m flask --app recruiting seed --yes --at 2030-01-01T00:00:00+00:00
```

## Docker Build

```sh
docker build -t matchwork .
```

The root `Dockerfile` uses `python:3.12.11-slim-bookworm` and copies the Node.js binary from `node:22.23.5-bookworm-slim` for the renderer tests. SQLite runs inside the application container.

## Docker Startup

```sh
docker volume create matchwork-data
docker run -d --name matchwork -p 127.0.0.1:8080:8080 \
  -v matchwork-data:/app/data matchwork
```

After [the health endpoint](http://127.0.0.1:8080/health) returns `{"status":"ok"}`, use these commands to verify migrations and populate a fresh demo volume.

```sh
docker exec matchwork python -m flask --app recruiting init-db
docker exec matchwork python -m flask --app recruiting seed --yes
docker exec matchwork python -m pytest tests/unit -q
```

Open [Matchwork](http://127.0.0.1:8080/sign-in) and sign in with a seeded account. Reuse the named volume to retain data across container restarts. For an existing volume, run `seed --yes` only when you intend to reset its data. The container runs as UID 10001, so a bind mount must be writable by that user.

To open a database from an earlier installation, use `docker volume ls` to find its volume and substitute that name for `matchwork-data` in the mount argument.

Stop and remove the container with these commands. The named volume stays available for the next run.

```sh
docker stop matchwork
docker rm matchwork
```

## Local Development

With the virtual environment active, initialize a local database, seed it for the first demo, and start Waitress.

```sh
python -m flask --app recruiting init-db
python -m flask --app recruiting seed --yes
python -m recruiting
```

Open [Matchwork](http://127.0.0.1:8080/sign-in). The legacy `/login` and `/register` paths redirect to the sign-in or registration view. Waitress is also the server used by Docker.

### Browser smoke test

Start with a fresh demo seed and use the password in [Demo Accounts](README.md#demo-accounts).

1. Sign in on the candidate tab as `alex@example.test`. Check that the dashboard lists current jobs in score order. In My Profile, save a skill or replace the resume and reload. Check that the edit persists and the dashboard shows the updated score after a skill change.
2. Open Interviews and book an open Northstar slot for Backend Engineer. The picker offers dates with open slots, and the confirmed booking shows its time in Pacific Time.
3. Sign out and use the recruiter tab to sign in as `north@example.test`. Open Applicants and check Alex's status, skills, score, and booking. The resume is private. Change the status and confirm the booking remains visible.
4. In recruiter Interviews, add a slot more than two weeks out. Delete the slot, reload, and confirm that the calendar still shows the selected date.
5. Sign in as `blair@example.test`. Check that Northstar's remaining open slots appear and that Alex's booked slot is unavailable.
6. Sign in as `field@example.test`. Check that My Jobs shows Fieldwork Labs postings. Northstar jobs belong to the other account.
7. Sign out and use Create a free profile on the candidate tab to register a demo account. The new user lands on the candidate dashboard.

## Running Unit Tests

```sh
python -m pytest tests/unit -q
```

The unit suite uses temporary SQLite databases and runs the shipped HTML renderer and calendar checks in Node.js. It exits with a nonzero status on failure. Node's built-in runner is enough for these checks.

Run the full Python suite or the booking race by itself:

```sh
python -m pytest -q
python -m pytest tests/integration/test_concurrency.py -q
```

The full Python suite can run in a disposable Docker container without network access:

```sh
docker run --rm --network none matchwork python -m pytest -q
```

### Frontend checks and matching parity

With Node.js 24, run the Python and JavaScript units plus the authenticated API-to-frontend matching check. Add `--include-concurrency` to include the synchronized SQLite race.

```sh
python tests/run_units.py
python tests/run_units.py --include-concurrency
```

To run the JavaScript or matching checks separately:

```sh
npm test
python tests/acceptance/matching_parity.py
python tests/acceptance/unicode_version_probe.py
```

`unicode_version_probe.py` checks both known Unicode casing cases against the API and live frontend consumer. The `--browser` option uses the running local app. The `--legacy-functions` option on either Python script runs the offline calculator comparison. It can report Unicode differences between runtimes. Python coverage measures Python execution. The JavaScript checks run separately.

### Browser acceptance

Keep a local demo instance running and use a disposable database. The browser tests create synthetic accounts and records. Install the pinned Playwright dependency and Chromium, then run the suites against the local instance.

```sh
npm ci
npx playwright install chromium
export QA_BASE_URL=http://127.0.0.1:8080
npm run test:browser
npm run test:normalization
npm run test:authoritative
node tests/browser/round2.cjs
```

CI installs Chromium with `npx playwright install --with-deps chromium` on Ubuntu. The scripts default to installed Edge on Windows and Playwright's Chromium on other platforms. Set `QA_BROWSER` to use another executable and `QA_OUTPUT` to give a run its own results directory under ignored `output/`. The HTTP smoke test runs one synchronized two-client race against the same local instance.

```sh
python tests/acceptance/http_smoke.py --base-url http://127.0.0.1:8080
```

The GitHub Actions workflow runs frontend units, matching parity and Unicode checks, Docker build and Python tests, seeded browser acceptance, and the HTTP booking race. It keeps browser and verification results as workflow artifacts. Use the run for the exact commit to check its status.

### Optional regression and persistence checks

Use these commands for fixed-seed probes and isolated mutation checks:

```sh
python tests/acceptance/round2_probe.py --output output/qa-round2/probe-after.json
python tests/acceptance/mutation_check.py
```

The mutation runner copies the sources under ignored `output/` and applies changes to those copies. It checks that the working files are intact. Branch coverage is a separate development check:

```sh
python -m pip install coverage==7.10.7
python -m coverage run --branch --source=recruiting --data-file=output/qa-round2/.coverage -m pytest -q
python -m coverage report --data-file=output/qa-round2/.coverage -m
```

`tests/acceptance/docker_persistence.py` verifies that demo data survives recreating a Docker container with its volume. Run it only on a dedicated local QA container. Supply its matching `--container`, `--image`, `--volume`, and explicitly published `--port`. `--reset-after` resets that QA database after the check.

## Troubleshooting

| Problem | What to check |
|---|---|
| Docker daemon unavailable | Start Docker Desktop or Docker Engine. |
| Port 8080 occupied | Publish `-p 127.0.0.1:8081:8080` in Docker or run `PORT=8081 python -m recruiting` locally. Use the new port in the browser. |
| `no such table` | Run `init-db` with the server's `DATABASE` value. |
| Demo accounts missing | Run the seed command on the demo database after it starts. |
| Sign-in loops on local HTTP | Check that `COOKIE_SECURE` is unset or `0`. Multiple server processes must share the same `SECRET_KEY`. |
| Node.js missing during pytest | Put Node.js on `PATH` or run the suite in Docker. |
| `503 Database is busy.` | Close the process or SQLite shell holding the write transaction, then retry. The busy timeout is 10 seconds. |
| No times offered | Confirm the application is `Interviewing`, has no booking, and its employer has a future unbooked slot. |
