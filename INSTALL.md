# Installation and local verification

## Prerequisites

- Python **3.12** (verified locally with 3.12.11), or Docker Desktop / Docker Engine.
- A current browser. No Node.js, cloud account, paid API, or external database is needed.
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
Times are stored in UTC. The pages use Pacific Time (`America/Los_Angeles`),
with PST or PDT shown for individual slots. Slot API timestamps require `Z` or an
explicit offset.

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
   Change the status; the booking remains. On Interviews, use Add a specific time
   to create a 30-minute slot more than two weeks out. Reload, find that date
   in the calendar, and remove the slot. Check it no longer appears after reload.
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
