# Recruiting Platform Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task with test-first checks and a final independent review.

**Goal:** Deliver the required local recruiting platform with a clean browser UI.
**Architecture:** Flask application factory and feature blueprints call shared business services. SQLite transactions and constraints enforce data integrity. Jinja renders escaped local HTML/CSS.
**Tech Stack:** Python 3.12, Flask, Jinja, SQLite, pytest, Waitress, Docker.
**Spec:** [SPEC.md](../../../SPEC.md), plus the normative course requirements.

## Global constraints

- Roles: exactly Candidate and Employer; statuses: Pending, Interviewing, Rejected, Accepted.
- Resume owner only; no hosted dependencies; no optional AI for this version.
- 30-minute future slots; a same-slot loser receives 409 `Slot already booked`.
- Preserve unrelated local files; work on `codex/recruiting-platform` in the current checkout.
- User explicitly requested coding; proceed inline without another planning approval round.

## Review focus

- Malformed/empty forms must produce validation errors, not tracebacks (Tasks 1–3).
- Same-employer cross-job booking must work despite slot/job association (Task 2).
- Duplicate submissions and concurrent deletion/status changes must not corrupt state (Task 2).
- Reset seed must not let old sessions access newly recreated identities (Task 3).
- Long text and small screens must preserve usable forms and readable content (Task 3).

## Task 1: Foundation, matching, accounts, and profiles

Files: `recruiting/__init__.py`, `db.py`, `errors.py`, `matching.py`, `accounts.py`,
`migrations/001_initial.sql`; `tests/conftest.py`, `tests/unit/test_matching.py`,
`tests/unit/test_auth.py`.

Interfaces: `create_app(config=None)`; `db.get_db()`, `db.migrate()`;
`matching.normalize_skills(values)`, `matching.score(candidate, required)`;
`accounts.register(email,password,role,display_name) -> dict`,
`accounts.authenticate(email,password) -> dict`, `accounts.profile(actor,id)`,
`accounts.update_profile(actor,display_name,skills,resume)`,
`accounts.update_company(actor,name,description)`; `DomainError(status,message)`.

- [x] Replace matching/auth placeholders with real normalization, 100/50/0/empty,
  floor, invalid registration, unique identifier, salted hashing, privacy tests.
- [x] Run focused tests and observe missing implementation failures.
- [x] Implement connection/migrations, shared matching, accounts and profile services.
- [x] Run focused tests and complete unit suite; record results.

## Task 2: Recruiting and scheduling services

Files: `recruiting/jobs.py`, `recruiting/scheduling.py`;
`tests/unit/test_workflows.py`, `test_scheduling.py`, `test_security.py`;
`tests/integration/test_concurrency.py`.

Interfaces: `jobs.create_job(actor,title,description,skills)`,
`jobs.update_job(actor,id,title,description,skills)`, `jobs.delete_job(actor,id)`,
`jobs.recommendations(actor)`, `jobs.apply(actor,job_id)`,
`jobs.applications(actor)`, `jobs.application(actor,id)`,
`jobs.applicants(actor,job_id)`, `jobs.set_status(actor,id,status)`;
`scheduling.create_slot(actor,job_id,start,end)`, `delete_slot(actor,id)`,
`available_slots(actor,application_id)`, `book(actor,application_id,slot_id)`.

- [x] Write tests for all workflows, both tie-breakers, forbidden ownership,
  missing records, duplicate/dependent conflicts, SQL metacharacters, eligibility,
  UTC validation, booked-slot preservation, same-employer cross-job booking.
- [x] Observe failures before implementing services.
- [x] Implement parameterized services and atomic write transactions.
- [x] Verify unit suite and synchronized two-client race: [200,409], one booking.

## Task 3: Browser workflows, seed, and reproducible delivery

Files: `recruiting/web.py`, `auth.py`, `seed.py`, `__main__.py`, templates and static
CSS; `tests/unit/test_web.py`, `test_seed.py`; Dockerfile, `.env.example`,
`.github/workflows/tests.yml`, README.md, INSTALL.md, AGENTS.md.

Interfaces: routes as in SPEC; CLI `flask --app recruiting init-db`,
`flask --app recruiting seed --yes [--at ISO]`; `python -m recruiting` runs Waitress.

- [x] Write browser-boundary tests for registration/login/logout, CSRF, roles,
  rendered escaping, forms, redirects, errors, reset-session invalidation and seed.
- [x] Observe failures, then implement routes/templates/CSS/CLI/seed.
- [x] Run complete suite and CLI smoke checks. Check desktop/mobile layout and
  candidate/employer workflows in a real browser.
- [x] Complete Docker startup, pinned dependencies, CI, command docs and every
  requirement's named test mapping. Attempt actual Docker build and smoke test.
- [x] Obtain one independent final code review, fix actionable findings with
  regression tests, and update AGENTS.md with evidence and remaining limitations.

## Execution ledger

- 2026-11-14: Inspected visual reference HTML/CSS; adopted navy/blue/card/tab patterns.
- Ruling: implement in current checkout on a feature branch, preserving untracked
  user files — matches desktop workflow; no separate worktree needed.
- Ruling: proceed inline after user's explicit coding request — no additional
  design approval round; design choices are documented in SPEC.md for review.
- Pre-flight: Tasks 2 and 3 consume Task 1's actor dictionaries and database context;
  Task 3 consumes Task 2 service dictionaries. Business errors share one type.
- Environment: Python 3.12.11 available; Docker daemon initially stopped.

- Task 1: complete — matching and account/profile behavior passed after missing-code
  failures; all starter placeholders replaced during subsequent tasks.
- Task 2: complete — workflow, scheduling, ownership, SQL-binding and actual
  concurrent booking tests pass.
- Task 3: complete for local delivery — 48 unit tests / 49 full-suite tests pass;
  final Docker suite also passes 49 with no warnings. Browser checks and persistent
  container startup verified. External publishing/submission remains with the team.
- Final review: three malformed-input defects reproduced and fixed with regressions;
  the timestamp edge was also fixed because it could persist an unrenderable slot.
- Final: browser-discovered schedule overflow fixed and verified at 390px width.
- Ruling: use revocable server sessions instead of only signed user-ID cookies —
  logout must invalidate copied cookies; this adds a small sessions table.
- Ruling: treat UTC-range normalization as a required service validation fix —
  persisted unrenderable slots are unacceptable even for unusual inputs; the cost
  is rejecting timestamps outside Python's supported UTC range.
- Ruling: retain the working changes uncommitted for user review — no merge/push
  was requested; a graded commit must be created and verified before submission.
- Detailed evidence: `docs/verification.md`. No review findings deferred.
