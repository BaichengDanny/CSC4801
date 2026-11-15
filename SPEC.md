# Common Ground — Project Specification

## Scope and architecture

A local recruiting platform for Candidates and Employers, implementing the
normative [course requirements](final_project_spec/REQUIREMENTS.md). The UI uses
Flask/Jinja with local CSS and no frontend build or external assets. Python 3.12,
SQLite through the standard `sqlite3` module, Werkzeug password hashing, pytest,
and Waitress are the implementation choices. Optional AI and PDF extraction are
out of scope for this version.

`recruiting.create_app(config=None)` owns configuration, request security, and
blueprint registration. Routes translate forms into service calls; services own
validation, roles, ownership, and transactions. Database connections are scoped
to the Flask application context and enable foreign keys and a busy timeout.

## Data model

- `users`: ID, unique case-normalized email, password hash, role constrained to
  Candidate/Employer, display name.
- `candidate_profiles`: user FK, private raw resume. `candidate_skills`: candidate
  FK plus normalized skill, composite primary key.
- `companies`: employer FK, name, description. One company per employer.
- `jobs`: employer FK, title, description. `job_skills`: job FK and normalized skill.
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

Forms use POST for mutations with CSRF tokens. Success uses a redirect back to a
GET page; errors render escaped messages with their actual HTTP status.

| Method/path | Behavior |
|---|---|
| GET `/` | Redirect to login or role dashboard |
| GET, POST `/register` | Create Candidate or Employer |
| GET, POST `/login`; POST `/logout` | Session lifecycle |
| GET `/dashboard` | Candidate ranked jobs or employer owned jobs and summary |
| GET, POST `/profile` | Edit own candidate profile/skills or company profile |
| GET, POST `/candidates/<id>/resume` | Owner-only raw-text resume |
| GET `/jobs/<id>` | Job description; employer read restricted to own job |
| GET, POST `/jobs/new`; GET, POST `/jobs/<id>/edit` | Owned job creation/editing |
| POST `/jobs/<id>/delete` | Delete only if no applications or slots |
| POST `/jobs/<id>/apply` | Candidate application, once, Pending |
| GET `/applications`; GET `/applications/<id>` | Candidate own applications/detail |
| GET `/jobs/<id>/applicants` | Employer's ranked applicants |
| POST `/applications/<id>/status` | Owning employer changes status |
| GET, POST `/schedule`; POST `/jobs/<id>/slots` | Employer availability and creation |
| POST `/slots/<id>/delete` | Delete unbooked owned slot |
| POST `/applications/<id>/book` | Candidate books submitted slot ID atomically |
| GET `/health` | Lightweight health endpoint |

## Interface design

Visual reference: Food-Ordering-System `client/css/style.css` and
`client/index.html` at commit `340a5de9d36f2f48c64b97e30ed0e09dafc340ce`.
Use a navy header, blue primary actions, white cards on a pale background,
clear tab navigation, system fonts, status badges, and generous spacing. Adapt
visual patterns only. Brand working name: **Common Ground**. The dashboard lists
job cards, applicant management uses a readable table, and editing uses focused
forms. Mobile layouts stack columns. Use visible labels, keyboard focus, readable
contrast, and explicit empty/error/success states. No external fonts or scripts.

## Matching

`recruiting.matching.score(candidate_skills, required_skills)` normalizes inputs,
returns 100 for an empty required set, otherwise `100 * len(C & R) // len(R)`.
Resume text is not consulted. Both services call this function. Candidate results
include every job, sorted by (-score, title.lower(), job_id). Employer applicants
sort by (-score, display_name.lower(), candidate_id). Profile or job skill edits
are reflected on the next read; scores are not stale snapshots.

## Scheduling and concurrency

The UI labels all times **UTC**. Browser `datetime-local` values are explicitly
interpreted as UTC; service inputs must be timezone-aware ISO timestamps and are
stored as epoch seconds. A configurable `NOW` callable supplies the current UTC
time, allowing fixed-clock tests and reproducible seed commands.

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

Parameterized SQL only; dynamic identifiers are internal constants. Jinja
escapes all user text; raw text retains line breaks through CSS. CSRF is checked
on all POSTs, including login/logout. Limit request bodies to 1 MiB, passwords to
256 characters, resumes/descriptions to documented service limits. Security
headers include a same-origin content policy and frame denial. HTTPS deployments
set `COOKIE_SECURE=1`; local HTTP uses the default false setting.

No real secrets, personal data, cloud services, or paid credentials are needed.
Tests create isolated temporary SQLite databases. The seed command is explicitly
destructive and requires `--yes`; it preserves deterministic identities and
relative ordering. By default slots start on the next UTC day; `--at` accepts a
fixed ISO reference clock for exact fixture reproduction. Reset is for local demo
use only. Existing signed sessions are invalidated on reset through a database
session-generation value, avoiding reuse of seeded user IDs.

SQLite is intended for local/course-scale use. There are no email verification,
password recovery, file uploads, chat, calendar integration, or booking cancellation
flows in this scope. Unit tests and a synchronized two-client test verify behavior;
Docker verification and manual browser results are recorded separately.
