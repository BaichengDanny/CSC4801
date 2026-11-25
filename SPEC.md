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
| GET `/api/auth/csrf` | Issue or read the current session's CSRF token before sign-in or registration |
| POST `/api/auth/register`, POST `/api/auth/login`, POST `/api/auth/logout`, GET `/api/auth/me` | JSON registration and session |
| GET `/api/candidate/bootstrap`, POST `/api/candidate/profile`, POST `/api/candidate/matching-preview`, POST `/api/candidate/applications`, POST `/api/candidate/applications/<id>/book` | Candidate reads and writes |
| GET and POST `/api/candidate/<candidate_id>/resume` | Read or replace the owning candidate's raw-text resume |
| GET `/api/employer/bootstrap`, POST `/api/employer/jobs`, POST `/api/employer/jobs/<id>`, POST `/api/employer/jobs/<id>/delete`, POST `/api/employer/applications/<id>/status`, POST `/api/employer/slots`, POST `/api/employer/slots/<id>/delete`, POST `/api/employer/company` | Employer reads and writes |

JSON routes that consume a request payload require a JSON object; malformed, empty, null and scalar bodies return 400. Explicit empty objects remain valid for partial updates. JSON resource IDs accept positive signed-64-bit integers or integer strings; booleans and floats are rejected as missing records (404) rather than coerced.

Job services validate core fields and page metadata together and save them in one transaction. Nested service transactions use SQLite savepoints, so a failed composed write rolls back the complete request.

JSON routes return `{ok, message}` with the same 401/403/404/409 contract.
Every POST requires the session's CSRF token in `X-CSRF-Token`. Missing or
mismatched tokens return 403. The sign-in page obtains the token from
`/api/auth/csrf`. Successful login or registration rotates it. Signed-in
pages use the token returned by `/api/auth/me`. Token responses use `no-store`.
The direct resume route returns 403 for other candidates and employers before
reading the profile or validating the write body. An owner whose profile row
is missing receives 404. POST accepts a `resume` string and updates only that
field. A profile edit that omits `resume` preserves the stored resume.

Matchwork shows slot times in Pacific Time; values are stored as
UTC. An employer's new slots are attached to that employer's oldest job so the
existing slot-to-job rule still applies. Candidate job and slot cards carry the
same employer ID. Candidate company profiles are keyed by this ID, and the
booking picker uses it to identify eligible slots across that employer’s jobs.
The candidate bootstrap returns the viewer's own bookings, including past
bookings, and future unbooked slots for employers with an `Interviewing`
application of the viewer that has yet to be booked.

Job create and edit validate and save the title, description, skills, summary,
location, job type, and posting status in one database operation. Partial edits
resolve omitted fields from the current record inside the write transaction.

## Interface design

The browser product is **Matchwork**. Pages use Plus Jakarta Sans from Google
Fonts, a light card layout, and a sidebar on the dashboards. Sign-in and account
creation share `login.html`; the candidate and employer roles are tabs on that
page. Job cards, applicant rows, and interview slots are rendered by the page
scripts from JSON. The page scripts escape text before inserting it into HTML. Live candidate and employer portals share `shared/html.js::escape`, which handles HTML text and quoted attributes and is called directly by Node unit tests. URL validation is a separate responsibility.
Live job cards include the stable employer ID as `owner` and the compatible `employerId` alias. Candidate company records are keyed by that ID, and availability is matched against slot owner IDs; company names are display text and need not be unique. The standalone demo keeps its name-keyed catalog.

Saved jobs are kept in `sessionStorage` under `mw.saved`. Mobile layouts stack
the columns. The repository and Docker image name remain Common Ground.

## Matching

`recruiting.matching.score(candidate_skills, required_skills)` is the authority
for both live roles. It normalizes inputs, returns 100 for an empty required set,
otherwise `100 * len(C & R) // len(R)`. Resume text is not consulted.
The existing Python 3.12 lowercase behavior is retained; no character-specific
patch, NFC/NFKC, casefold, or schema migration is introduced.

The explicit edge-whitespace set is U+0009–000D, U+001C–0020, U+0085, U+00A0,
U+1680, U+2000–200A, U+2028/2029, U+202F, U+205F, U+3000, U+FEFF.
Internal whitespace and U+200B/U+180E remain data. Stored skills are normalized
again when scored/presented, so legacy values do not require destructive reset.

Candidate API job cards include integer `score` (0–100) and `rank`. They include
every non-deleted job and order by (-score, title.lower(), job_id).
Employer application cards use the same score function and rank by
(-score, display_name.lower(), candidate_id); a final application-ID key makes
the optional all-jobs view deterministic when the same candidate has multiple
applications. Filtering that global list by job preserves the required per-job order.

The live candidate/employer pages consume these facts through
`shared/match.js::fromServer` and `byServerRank`. They do not recalculate scores,
Unicode case normalization, or match ordering in JavaScript. IDs remain strings.
Skills sent to live editors are canonicalized by the backend, and the browser
compares already canonical skill values without applying a second lowercase.

POST `/api/candidate/matching-preview` requires Candidate authorization and a
validated skills list. It is read-only and uses the same recommendation service,
returning sorted draft cards with `score`/`rank` plus `baselineScore` for the
currently saved profile. This preserves the existing before/after skill preview,
including when job requirements change while a draft is open.

Profile and job mutations return a fresh `snapshot`; status changes do too.
Live state accepts it immediately, preserving saved jobs and notification-read
state. Navigation, window focus, and becoming visible also refresh from the API.
Visible pages attempt a refresh every five seconds, applying changed results to
the current DOM. Existing unsaved-form guards pause background adoption until the
draft is saved or discarded. This is polling/focus refresh, not push delivery.

The standalone file/demo retains its local calculator for offline behavior.
The original raw Python/JS comparison remains available as
`matching_parity.py --legacy-functions` and
`unicode_version_probe.py --legacy-functions`. Its runtime casing differences
are diagnostic facts about that unused online calculator; the live regression
now verifies authenticated API -> actual frontend consumption and real pages.
See [QA3-04](docs/issues/QA3-04-unicode-version.md) for the repaired chain and
the retained counterexamples.

## Scheduling and concurrency

The slot API accepts ISO timestamps with explicit offsets or `Z`, at whole-second
precision. It stores UTC epoch seconds. Matchwork uses `America/Los_Angeles`
(Pacific Time, PST in winter and PDT in summer). Manual entry rejects skipped
and repeated wall times during clock changes. Times spanning midnight end on
the following date when the start is in the 23:00 hour and the end is in the
00:00 hour. The employer calendar shows the next 14 days plus any farther future
date with a slot. It also includes the date selected by a valid `day` URL
parameter for today or later, even after the last slot on that day is removed.
A configurable `NOW` callable supplies the current UTC time for testing and seeding.

Slot creation validates a future start and exactly 30 minutes. It checks for
overlap with the same employer’s slots inside the write transaction.
Booking uses `BEGIN IMMEDIATE` to serialize competing writers. Inside the same
transaction it verifies application ownership, `Interviewing` status, and the
absence of a previous booking before looking up the slot. It checks the slot's
employer and future start before reporting its booking state. Unique constraints
on slot and application IDs provide a second database guard. The loser of an
eligible same-slot race gets 409 with exactly `Slot already booked`. SQLite waits
up to 10 seconds for a writer. Unrelated lock exhaustion returns 503.
Status changes, deletion, and booking use write transactions so validations and
mutations see consistent state. A booking survives later status changes.

## Security and limits

Parameterized SQL only; dynamic identifiers are internal constants. API
responses are JSON, so user text is data rather than an HTML document. The
Matchwork pages escape user text before inserting it. Protected routes authenticate
with the SameSite session cookie. The request hook verifies the session-bound
CSRF token for every POST, including those with empty bodies. Limit request
bodies to 1 MiB, passwords to 256 characters,
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
