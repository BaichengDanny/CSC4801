# Project guide for coding agents

Last updated: 2026-11-25 (Asia/Shanghai).

## Purpose and current state

Build the CSC4801 recruiting and candidate-matching platform. The user chose
**Flask + SQLite**. The browser UI is the Matchwork pages; the earlier Jinja
screens were removed on 2026-11-24. Keep the implementation small, readable,
locally runnable, and understandable by every team member.

The required local application is implemented under `recruiting/`, with real
unit tests, a synchronized booking race test, synthetic seed data, and a working
Docker environment. The user authorized implementation on 2026-11-14. Current
work is on `platform-draft`. See the [Matchwork specification audit](docs/matchwork-spec-audit-2026-11-25.md)
for the baseline at `a48647f` and the local repair checks. The [2026-11-14 verification record](docs/verification.md)
predates the Matchwork UI.

This file records working rules, decisions, and milestone status. Update it as
work progresses. It does not replace the product specification or installation
guide, and its roadmap is not evidence that a feature has been implemented.

## Read first and keep sources consistent

1. Read this file and inspect `git status --short` before changing the project.
2. Read [REQUIREMENTS.md](final_project_spec/REQUIREMENTS.md) for normative product
   behavior; use its `FP-*` identifiers in implementation planning and verification.
3. Read [SPEC.md](SPEC.md) for the application's design, [INSTALL.md](INSTALL.md)
   for commands, and [README.md](README.md) for the requirement–test mapping.
4. For delivery or auditing, also read [DOCKER.md](final_project_spec/DOCKER.md),
   [PEER_REVIEW.md](final_project_spec/PEER_REVIEW.md), and the course
   [overview](final_project_spec/README.md).

Treat `final_project_spec/` as course-owned reference material. Do not rewrite
requirements to make an implementation appear compliant. If a proposed change
conflicts with a course requirement, explain the conflict before proceeding.
Current explicit user instructions govern the requested work; record changes to
previous decisions instead of silently treating an old proposal as binding.

Keep document responsibilities separate:

| Document | Responsibility |
|---|---|
| `AGENTS.md` | Working rules, decisions, milestone status, next step |
| `SPEC.md` | Architecture, schema, permissions, routes, screens, algorithms, transactions |
| `INSTALL.md` | Exact setup, migration, reset/seed, run, test, and Docker commands |
| `README.md` | Overview, demo credentials, document index, limitations, every requirement mapped to evidence |

## Decisions and scope

| Decision | State | Reason |
|---|---|---|
| Flask backend, persistent SQLite database | Confirmed by user, 2026-11-14 | Chosen project stack |
| Matchwork pages replace the Jinja screens | Confirmed by user, 2026-11-24 | Colleague frontend is the browser UI; JSON API reuses the services |
| Root `AGENTS.md` as the maintained agent guide | Confirmed by user, 2026-11-14 | Standard instruction discovery |
| Flask application factory, feature blueprints, thin routes, shared service functions | Implemented agent decision, 2026-11-14 | Separate HTTP handling from testable business rules |
| pytest, versioned SQL migrations, Docker, GitHub Actions configuration | Implemented agent decision, 2026-11-14 | Reproducible development and verification |
| Required core before optional AI, PDF parsing, or hosted deployment | Implemented scope, 2026-11-14 | Complete graded behavior first |

Do not replace the chosen stack or introduce an SPA, external database, paid
service, or optional feature without discussing the scope change with the user.
Routine implementation choices within the agreed scope can be made and documented
without repeated permission requests.

Implemented design choices are documented in `SPEC.md`:

- Standard-library `sqlite3`, versioned SQL migrations, normalized skill tables.
- Slots belong to a job and derive their employer owner. Same-employer cross-job
  booking is allowed; job deletion respects dependent slots.
- Integer UTC timestamps and an injectable `NOW` clock. Matchwork displays Pacific Time (`America/Los_Angeles`) and uses explicit UTC offsets in the slot API.
- `BEGIN IMMEDIATE`, unique booking constraints, 10-second busy timeout; actual
  same-slot conflicts return 409, unrelated storage contention returns 503.
- Fixed seed identities and slot offsets; optional `seed --at` reference time.
- Browser product name Matchwork. The repository and Docker image name remain Common Ground.

## Required product invariants

These are reminders of high-risk requirements, not a substitute for the full spec.

- **Accounts and access:** exactly `Candidate` and `Employer`; unique login
  identifiers; established password hashing; no credential hashes or secrets in
  responses. Enforce roles and ownership on the server for every protected action.
  Return `401` or login redirect when unauthenticated, `403` for wrong role/owner,
  and `404` for a missing object the caller would otherwise be allowed to access.
- **Privacy:** only the candidate owner can read or replace their raw-text resume.
  Other candidates and employers receive `403`, including via direct requests.
  Candidates can access only their own applications and cannot change statuses.
- **Applications and jobs:** one application per candidate/job, initially
  `Pending`. Only the job owner can set `Pending`, `Interviewing`, `Rejected`, or
  `Accepted`. Job title and description must be non-empty. Reject deletion with
  `409` if applications or slots depend on the job; leave all records unchanged.
- **Matching:** trim, lowercase, remove empty skills, and deduplicate. Score is
  `100` for empty required skills, otherwise `100 * len(C & R) // len(R)`.
  Resume text is never an input. Both dashboards call the same implementation.
  List all current jobs. Sort by descending score, then case-insensitive job
  title/stable job ID or candidate display name/stable candidate ID respectively.
- **Scheduling:** future slots must last exactly 30 minutes with an explicit
  timezone. Booked slots cannot be deleted or advertised as available. Booking
  requires application ownership, the matching employer, `Interviewing` status,
  a future unbooked slot, and no existing booking for the application. Failed
  operations leave no partial changes. Later status changes preserve bookings.
- **Concurrency:** enforce booking exclusivity in SQLite, not merely in Python.
  Use transactions and database constraints for unique slot and application
  bookings. A same-slot race must yield one success, one `409` with exactly
  `Slot already booked`, and one database booking. Do not report every database
  error as a booking conflict or assume SQLite supports row-level `FOR UPDATE`.

## Engineering and security rules

- Keep authorization and business validation in reusable server-side logic.
  Page scripts may control presentation but cannot be the enforcement boundary.
- Use bound query parameters or a correctly used ORM. Never interpolate request
  values into SQL. Enable SQLite foreign-key enforcement on every connection.
- Return user text as JSON. Escape it in page scripts before inserting HTML.
  Do not mark untrusted content safe. Prefer plain text over rich-HTML rendering.
- Protect state-changing browser forms against CSRF. Use appropriate session
  cookie settings and document any local HTTP versus HTTPS differences.
- Keep secrets, personal data, local databases, and generated artifacts out of
  version control. `.env.example` contains placeholders only. Seed accounts are
  explicitly synthetic, local/demo accounts.
- Tests use isolated fixtures/databases and no real third-party calls. A future
  optional LLM feature must have a deterministic fake or non-LLM fallback, must
  preserve baseline matching/order, and must document untrusted-input data flow.
- Keep dependencies minimal and pinned. Make targeted dependency updates; avoid
  unrelated lockfile churn. Document new setup requirements when introduced.
- Preserve unrelated user changes. Avoid destructive Git commands and do not
  publish, push, change repository visibility, or contact others unless authorized.
- Keep changes focused and explain non-obvious behavior in code comments. Do not
  add abstractions solely for hypothetical future features.

## Verification and delivery

- Write meaningful unit tests against actual business logic for every functional
  requirement, covering success plus applicable validation, authorization, and
  conflicts. Add a regression test for each fixed behavioral bug.
- Cover all four required matching examples, normalization, integer flooring,
  both tie-breakers, `401`/`403`/`404`, cross-owner access, bound SQL metacharacters,
  escaped `<script>alert(1)</script>`, and booking conflict handling.
- Run focused tests during development and the complete required suite before
  declaring a milestone complete. Never weaken assertions or leave `pass` tests
  to manufacture a green result. Report failures and unrun checks explicitly.
- Unit tests are required by the course. A small synchronized two-client booking
  check is an additional proposed verification step; mocks alone do not establish
  database atomicity. Do not substitute load testing for this small check.
- Map every requirement ID in `README.md` to implementation files and named tests
  or suitable non-functional evidence. Mark unimplemented optional AI as `N/A`.
- Seed at least two candidates, two employers, two jobs with required skills, all
  four matching examples, all four statuses, and two `Interviewing` candidates
  eligible to race for the same slot. Provide one documented reset/seed command.
- Verify clean-checkout Docker build, startup, migrations, seed, tests, and both
  browser workflows. No undocumented images, commands, secrets, or hosted services
  may be required. Persist/reset data explicitly; an image does not preserve a
  database volume.
- After the course feature freeze, restrict delivery changes to bug fixes and
  documentation corrections. Final submission is a permanent public GitHub commit
  URL on `main` whose own Dockerfile builds and runs the complete environment.
- Peer audits are limited to the latest target `main` checkout and its locally
  built Docker environment. Follow `PEER_REVIEW.md`; never test deployed targets,
  perform destructive/load testing, or publish secrets. Confirmed repairs need
  regression evidence and an issue-linked fix PR under the course process.

### Command status

Use Python 3.12 and the pinned `requirements.txt` / `requirements.lock`.
The exact local and Docker commands live in `INSTALL.md`:

- Migrate: `python -m flask --app recruiting init-db`.
- Reset/seed local demo data: `python -m flask --app recruiting seed --yes`.
- Run: `python -m recruiting` (Waitress, default localhost:8080).
- Required unit suite: `python -m pytest tests/unit -q` (56 passing in the full run on 2026-11-25).
- Complete suite: `python -m pytest -q` (57 passing locally and in Docker on 2026-11-25, including the booking race).
- Docker: `docker build -t common-ground .`; see INSTALL.md for persistent-volume startup.

Tests passed locally and inside the image. Keep reset operations restricted to
explicit demo/test databases; never seed a user database just to run tests.

## Milestone tracker

Use `todo`, `in progress`, `blocked`, or `done`. Mark `done` only with concrete
evidence. Implementation was authorized by the user; design details chosen by the
agent remain labeled as such. External submission actions are tracked separately.

| ID | Milestone | Status | Completion evidence |
|---|---|---|---|
| M0 | Read course material, inspect starter, select stack | done | Course documents and starter inspected; user selected Flask/Jinja/SQLite |
| M1 | Define architecture, schema, routes, permissions, screens, and transaction design | done | SPEC.md and implementation plan; agent choices recorded |
| M2 | Application factory, database/migrations, configuration, Docker foundation | done | Docker build, startup, repeat migration, and volume persistence verified |
| M3 | Authentication, authorization, candidate/company profiles, private resumes | done | Auth/profile/direct-request/session regression tests pass |
| M4 | Jobs, matching, applications, employer applicant management | done | Workflow tests, matching, deletion conflicts, and invalid job writes pass |
| M5 | Availability and atomic interview booking | done | Ownership, time validation, remote dates, and the synchronized race verified |
| M6 | Security checks and browser workflow polish | in progress | Scheduling fixes verified in Chrome. The separate JavaScript rendering security test is deferred |
| M7 | Deterministic seed, CI, documentation, audit and submission readiness | in progress | Clean Docker build and draft CI passed. GitHub is private, audit labels are absent, and the reviewed commit is absent from remote `main` |

Security, tests, and documentation accompany each milestone; M6 and M7 consolidate
their verification rather than postponing them until the end.

## Maintaining this file

- At the start of a task, identify the milestone and inspect current evidence.
- After meaningful progress or a changed decision, update the relevant row, date,
  current-state description, and next action. Keep proposed and confirmed choices
  distinct. A user's stack choice alone does not approve an unwritten design.
- Record verification commands and outcomes with links to tests, CI runs, or
  durable documentation when available. Do not invent a commit SHA or successful
  result. Documentation-only changes need document/link checks, not application tests.
- If blocked, record the concrete cause and next action. Continue independent
  authorized work where possible.
- Keep the guide concise. Put detailed design in `SPEC.md`, command instructions
  in `INSTALL.md`, and test mapping in `README.md`; use Git history for old progress.

**Next action:** resume the deferred security verification when requested. The
Matchwork audit also tracks remaining application and course delivery findings.

## Reference patterns

Reviewed on 2026-11-14. These informed the guide's structure; their project-specific
policies and tooling do not apply to this repository.

- [Codex instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md):
  standard root `AGENTS.md` discovery and scoped repository instructions.
- [pandas AGENTS.md](https://github.com/pandas-dev/pandas/blob/main/AGENTS.md):
  repository orientation and links to authoritative development documentation.
- [uv AGENTS.md](https://github.com/astral-sh/uv/blob/main/AGENTS.md):
  concrete engineering rules, focused verification, and targeted dependency changes.
