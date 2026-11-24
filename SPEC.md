# Common Ground — Project Specification

## Scope and architecture

A local recruiting platform for Candidates and Employers, implementing the
normative [course requirements](final_project_spec/REQUIREMENTS.md). The browser
UI is the static Matchwork pages under `candidate/`, `recruiter/`, `shared/`,
and `login.html`, served by Flask and backed by the JSON API. The earlier Jinja
screens have been removed. Python 3.12,
SQLite through the standard `sqlite3` module, Werkzeug password hashing, pytest,
and Waitress are the implementation choices. Optional AI and PDF extraction are
out of scope for this version.

`recruiting.create_app(config=None)` owns configuration, request security, and
blueprint registration. JSON routes translate request bodies into service calls;
services own validation, roles, ownership, and transactions. Database connections
are scoped to the Flask application context and enable foreign keys and a busy timeout.

## Data model

- `users`: ID, unique case-normalized email, password hash, role constrained to
  Candidate/Employer, display name.
- `candidate_profiles`: user FK, private raw resume. `candidate_skills`: candidate
  FK plus normalized skill, composite primary key.
- `companies`: employer FK, name, description. One company per employer. Matchwork
  also stores industry, size, location, website, and an optional logo path.
- `jobs`: employer FK, title, description, plus display fields used by Matchwork
  (summary, location, type, categories, optional logo, Active/Closed label, created time). `job_skills`:
  job FK and normalized skill. Closed jobs stay listed; new applications to them
  are rejected.
- `applications`: candidate FK, job FK, status constrained to Pending,
  Interviewing, Rejected, Accepted; unique(candidate_id, job_id).
- `slots`: job FK, UTC integer start/end timestamps; exactly 1800 seconds.
  Owner is the job's employer. Slots are associated with a job for creation and
  deletion dependencies, but are bookable by any eligible application to the
  same employer, as required by FP-SCHED-2.
- `bookings`: application FK (unique), slot FK (unique). Restrictive foreign keys
  protect applications, slots, and jobs with dependents.

Skills are trimmed, lowercased, deduplicated strings stored in child tables.
Versioned SQL migrations live in `recruiting/migrations/`; applied versions are
recorded in `schema_migrations`. There is no implicit destructive startup seed.

## Authentication and authorization

Registration creates exactly one role-specific profile. Emails are stripped and
lowercased; passwords require at least eight characters and are stored using
Werkzeug scrypt with random salts. Signed HttpOnly, SameSite=Lax cookies hold a
random session token, generation value, and CSRF token, never password hashes or
resume text. SHA-256 digests of random tokens are stored in `auth_sessions` with
user IDs and 12-hour expiry; logout removes the corresponding server record. Login/logout clear
session state. `SECRET_KEY` may be configured; otherwise a random process key
means restarting invalidates existing sessions.

All protected routes require login (401) and services enforce roles and object
ownership (403). Missing accessible objects return 404. Candidate profile/resume
routes are owner-only even for employers. Employer applicant lists expose only
candidate identity, skills, score, status, and booking; never raw resumes or
password hashes. Candidate application reads are owner-only; status writes are
employer/job-owner-only. Rejected writes leave the database unchanged.

## Routes and screens

Mutations are JSON POSTs. Errors return `{ok: false, message}` with the actual
HTTP status. GET `/login` and GET `/register` only redirect into the Matchwork
sign-in page.

| Method/path | Behavior |
|---|---|
| GET `/` | Redirect to sign-in, or to the signed-in role's dashboard |
| GET `/login` | Redirect to `/sign-in` |
| GET `/register` | Redirect to `/sign-in#signup` |
| GET `/health` | Lightweight health endpoint |
| GET `/sign-in` | Matchwork sign-in and account creation |
| GET `/candidate/...`, GET `/recruiter/...`, GET `/shared/...` | Matchwork HTML, CSS, and scripts |
| POST `/api/auth/register`, POST `/api/auth/login`, POST `/api/auth/logout`, GET `/api/auth/me` | JSON registration and session |
| GET `/api/candidate/bootstrap`, POST `/api/candidate/profile`, POST `/api/candidate/applications`, POST `/api/candidate/applications/<id>/book` | Candidate reads and writes |
| GET `/api/employer/bootstrap`, POST `/api/employer/jobs`, POST `/api/employer/jobs/<id>`, POST `/api/employer/jobs/<id>/delete`, POST `/api/employer/applications/<id>/status`, POST `/api/employer/slots`, POST `/api/employer/slots/<id>/delete`, POST `/api/employer/company` | Employer reads and writes |

JSON routes return `{ok, message}` with the same 401/403/404/409 contract.
They authenticate with the SameSite session cookie and do not use the form
CSRF token. Matchwork shows slot times in Pacific Time; values are stored as
UTC. An employer's new slots are attached to that employer's oldest job so the
existing slot-to-job rule still applies.

## Interface design

The browser product is **Matchwork**. Pages use Plus Jakarta Sans from Google
Fonts, a light card layout, and a sidebar on the dashboards. Sign-in and account
creation share `login.html`; the candidate and employer roles are tabs on that
page. Job cards, applicant rows, and interview slots are rendered by the page
scripts from JSON. The page scripts escape text before inserting it into HTML.
Saved jobs are kept in `sessionStorage` under `mw.saved`. Mobile layouts stack
the columns. The repository and Docker image name remain Common Ground.

## Matching

`recruiting.matching.score(candidate_skills, required_skills)` normalizes inputs,
returns 100 for an empty required set, otherwise `100 * len(C & R) // len(R)`.
Resume text is not consulted. Both services call this function. Candidate results
include every job, sorted by (-score, title.lower(), job_id). Employer applicants
sort by (-score, display_name.lower(), candidate_id). Profile or job skill edits
are reflected on the next read; scores are not stale snapshots.

## Scheduling and concurrency

Service inputs must be timezone-aware ISO timestamps and are stored as epoch
seconds. The Matchwork pages label those times Pacific (UTC−8). A configurable
`NOW` callable supplies the current UTC time, allowing fixed-clock tests and
reproducible seed commands.

Slot creation validates future start and exactly 30 minutes before writing.
Booking uses `BEGIN IMMEDIATE` to serialize competing writers. Inside the same
transaction it reloads application/status and slot ownership/availability, checks
all eligibility predicates, and inserts one booking. Unique constraints on slot
and application IDs provide a second database guard. The loser of a same-slot race
gets 409 with exactly `Slot already booked`. SQLite waits up to 10 seconds for a
writer; unrelated lock exhaustion is 503, not falsely labeled a booked slot.
Status changes, deletion, and booking use write transactions so validations and
mutations see consistent state. A booking survives later status changes.

## Security and limits

Parameterized SQL only; dynamic identifiers are internal constants. API
responses are JSON, so user text is data rather than an HTML document. The
Matchwork pages escape user text before inserting it. JSON routes authenticate
with the SameSite session cookie. Any other POST still requires the session
CSRF token. Limit request bodies to 1 MiB, passwords to 256 characters,
resumes/descriptions to documented service limits. Security headers include a
same-origin content policy that allows the Google font stylesheets used by the
pages, plus frame denial. HTTPS deployments set `COOKIE_SECURE=1`; local HTTP
uses the default false setting.

No real secrets, personal data, cloud services, or paid credentials are needed.
Tests create isolated temporary SQLite databases. The seed command is explicitly
destructive and requires `--yes`; it preserves deterministic identities and
relative ordering, then loads the Matchwork catalog in `candidate/assets/jobs.json`
as one demo employer per company. By default slots start on the next UTC day; `--at` accepts a
fixed ISO reference clock for exact fixture reproduction. Reset is for local demo
use only. Existing signed sessions are invalidated on reset through a database
session-generation value, avoiding reuse of seeded user IDs.

SQLite is intended for local/course-scale use. There are no email verification,
password recovery, file uploads, chat, calendar integration, or booking cancellation
flows in this scope. Unit tests and a synchronized two-client test verify behavior;
Docker verification and manual browser results are recorded separately.
