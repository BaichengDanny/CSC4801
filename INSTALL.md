# Installation and local verification

## Prerequisites

- Python **3.12** (verified locally with 3.12.11), or Docker Desktop / Docker Engine.
- A current browser. Running the product needs no Node.js, cloud account, paid API, or external database. Full frontend QA additionally uses Node.js 24.
- Internet is needed to install the pinned packages or build the image initially.

Run all commands from the repository root. The application does not load `.env`
automatically; `.env.example` documents optional process environment settings.

## Local setup

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m flask --app recruiting init-db
python -m flask --app recruiting seed --yes
python -m recruiting
```

Open http://127.0.0.1:8080. That opens the Matchwork sign-in page. Old `/login`
and `/register` addresses redirect there. The server is Waitress, not Flask's
debug server.
On Windows activate with `.venv\Scripts\activate` and use `py -3.12` for venv creation.

### Environment

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE` | `instance/recruiting.sqlite3` under the repository | SQLite file; parent directory is created |
| `SECRET_KEY` | Random process key | Set a locally generated persistent secret to retain cookies across restarts |
| `HOST` | `127.0.0.1` | Bind interface; Docker sets `0.0.0.0` internally |
| `PORT` | `8080` | HTTP port |
| `COOKIE_SECURE` | `0` | Set `1` when serving through HTTPS; keep `0` for local HTTP |

A restart with the default random secret signs out existing users. Server sessions
expire after 12 hours and logout revokes them. Keep real secrets out of source
control. Do not use the documented demo accounts in a public production service.

## Migrations, seed, and reset

`python -m flask --app recruiting init-db` applies versioned migrations without
resetting data. Run it after updating source before starting the app.

The following single command resets **all data in the configured database** and
creates the synthetic demo dataset. It is safe to run while the server is up
(including via `docker exec`): the reset invalidates every existing session, so
signed-in browsers must sign in again.

```sh
python -m flask --app recruiting seed --yes
```

It creates the course fixtures — three candidates, two employers, four jobs, all
four application statuses, and two candidates eligible to race for the same
future interview slot — then one demo employer and jobs for each company in
`candidate/assets/jobs.json`. Every demo password is `DemoPass123!`; emails are
listed in README.md. Seeding invalidates old sessions. Without `--yes`, the
command refuses to reset data.

IDs, skills, statuses, and slot offsets are deterministic. Password salts and
session-generation secrets are intentionally random. By default the reference
clock is now and slots begin tomorrow at 10:00 UTC. To reproduce a fixture exactly:

```sh
python -m flask --app recruiting seed --yes --at 2030-01-01T00:00:00+00:00
```

Fixed reference times can produce past slots when replayed later. For interactive
review use the default seed command so booking eligibility remains demonstrable.
Stored times are UTC. The pages label them Pacific Time (PST UTC-8 / PDT UTC-7).

## Automated tests

```sh
python -m pytest tests/unit -q
```

This runs the entire required unit suite non-interactively and exits nonzero on
failure. Tests use temporary, isolated databases and never call external services.
Run the complete suite, including the optional synchronized concurrency test:

```sh
python -m pytest -q
```

For the two-connection booking race alone:

```sh
python -m pytest tests/integration/test_concurrency.py -q
```

## Frontend units, matching parity and CI

With Node.js **24** and the pinned Python requirements installed, one command
runs all backend units, the real shared JavaScript escape/matching units, and
the fixed-seed authenticated API-to-frontend contract:

```sh
python tests/run_units.py
```

Add `--include-concurrency` to run the synchronized database race in that command.
Python-only `pytest` commands above keep working without Node.js. These are
separate test layers; Python coverage does not include JavaScript execution.

Individual frontend checks need only Node's built-in test runner:

```sh
node --test tests/frontend/html.test.cjs tests/frontend/matching.test.cjs
python tests/acceptance/matching_parity.py
```

For browser acceptance install the locked QA dependency and Chromium:

```sh
npm ci
npx playwright install chromium
```

GitHub Actions uses `npx playwright install --with-deps chromium` on Ubuntu.
The browser scripts use managed Chromium on Linux and installed Edge on Windows;
`QA_BROWSER` can specify another executable. Set `QA_BASE_URL` to an explicitly
local test instance and `QA_OUTPUT` to an ignored artifacts directory.
Then run `npm run test:browser`, `npm run test:normalization`,
`npm run test:authoritative` and `node tests/browser/round2.cjs`.

The existing CI workflow now runs frontend units, authoritative API matching,
Docker build/full pytest, seed/health, the browser business/DOM flow, normalization
and employer-identity regressions, and HTTP concurrency. Failure artifacts are
retained. Finite mutation checks and extra probes remain independent commands.
Local equivalents are verified in the [supplement report](docs/qa-supplement-2026-11-25.md);
a hosted Actions run still requires publishing the reviewed changes.

The independent `unicode_version_probe.py` remains an unsuppressed CI gate. Its default now verifies authenticated API scores/ranks consumed by the product frontend, including both QA3-04 counterexamples. `--browser` verifies the deployed pages (set QA_BASE_URL); `--legacy-functions` preserves the former raw offline calculator diagnostic, which can still exit 1 by design. See the [repair verification](docs/qa3-04-fix-2026-11-25.md).

## Optional deeper QA

The required commands above need only the pinned project requirements.
For the fixed-seed probes and isolated semantic mutation checks:

```sh
python tests/acceptance/round2_probe.py --output output/qa-round2/probe-after.json
python tests/acceptance/mutation_check.py
```

The mutation runner copies files into hidden directories under ignored `output/`
and verifies that product sources are unchanged. It never mutates the checkout.

Optional branch coverage (development tool, not a product dependency):

```sh
python -m pip install coverage==7.10.7
python -m coverage run --branch --source=recruiting --data-file=output/qa-round2/.coverage -m pytest -q
python -m coverage report --data-file=output/qa-round2/.coverage -m
```

See the [round-2 report](docs/qa-2026-11-25.md) for browser commands, the
explicit-container persistence command and the [case matrix](docs/qa-round2-matrix.md).
The persistence script requires matching container/image/volume/port arguments;
`--reset-after` explicitly opts into resetting only that QA instance.

## Docker build and startup

The only base image is `python:3.12.11-slim-bookworm`, declared in the root
`Dockerfile`. SQLite runs inside the application; no additional images are needed.
The container runs as UID 10001. The named volume persists demo data across runs.

```sh
docker build -t common-ground .
docker volume create common-ground-data
docker run -d --name common-ground \
  -p 127.0.0.1:8080:8080 \
  -v common-ground-data:/app/data \
  common-ground
docker exec common-ground python -m flask --app recruiting init-db
docker exec common-ground python -m flask --app recruiting seed --yes
docker exec common-ground python -m pytest tests/unit -q
```

Open http://127.0.0.1:8080. Startup applies pending migrations automatically; the
explicit migration command above is safe to repeat. Startup never resets/seeds data.
The seed command must be run after startup; an image does not include a seeded DB.
For an isolated full-suite run:

```sh
docker run --rm common-ground python -m pytest -q
```

Stop and remove the container while retaining its database:

```sh
docker stop common-ground
docker rm common-ground
```

Recreate it with the same volume to retain data. To reset the configured demo DB,
run the explicit seed command again; do not remove unrelated volumes. A bind mount
instead of the named volume must be writable by UID 10001.

## Browser smoke test

Matchwork, at http://127.0.0.1:8080/sign-in:

1. Choose the candidate tab and sign in as `alex@example.test` / `DemoPass123!`.
   The dashboard lists seeded jobs and match scores.
2. Open Profile, change skills or the private resume, and save. Reload and confirm
   the change is still there.
3. Open Interviews for an Interviewing application. Day choices appear only for
   days that already have an open slot. Book one and confirm the reserved time.
4. Sign out. On the recruiter tab, sign in as `north@example.test` with the same
   password. Open Applicants and confirm Alex's booking. The resume stays private.
   Change the status; the booking remains. Add a 30-minute slot on Interview schedule.
5. Sign out and sign in as `field@example.test`. Northstar jobs are not in that
   account's job list.
6. From the signed-out page, use Create a new profile, fill the candidate fields,
   and confirm the new account lands on the candidate dashboard.

## Troubleshooting

- **Docker daemon unavailable:** start Docker Desktop/Engine before building.
- **Port 8080 occupied:** stop the existing local preview or map Docker using
  `-p 127.0.0.1:8081:8080`; for local Python use `PORT=8081 python -m recruiting`.
- **No such table:** apply `init-db` against the same `DATABASE` used by the server.
- **No demo accounts/jobs:** run the documented seed command; migrations alone
  create an empty application.
- **Login seems to loop:** unset `COOKIE_SECURE=1` for local HTTP, and ensure all
  processes share a `SECRET_KEY` if running more than one app process.
- **Database is busy (503):** close tools holding SQLite write transactions and
  retry. The configured busy timeout is 10 seconds. Do not relabel unrelated
  storage errors as slot conflicts.
- **No available slots:** use fresh seed data, or create a future 30-minute slot.
  Only unbooked Interviewing applications can reserve one.
