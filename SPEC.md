# Project Specification

The [course requirements](final_project_spec/REQUIREMENTS.md) define the graded behavior. [README.md](README.md#requirementtest-mapping) maps each requirement to its implementation and tests.

## Product Scope

Matchwork supports two roles, `Candidate` and `Employer`. Candidates maintain a profile with skills and a private plain-text resume, browse current jobs by match score, apply once per job, and book an interview when eligible. Employers maintain a company profile, publish jobs, review ranked applicants, change application status, and publish interview availability.

## Architecture

| Component | Files | Responsibility |
|---|---|---|
| Browser | `login.html`, `candidate/`, `recruiter/`, `shared/` | Static HTML, CSS, and JavaScript render JSON from the API. |
| Flask | `recruiting/__init__.py`, `recruiting/pages.py`, `recruiting/api.py`, `recruiting/auth.py`, `recruiting/present.py` | Serves pages, parses requests, authenticates sessions, and serializes responses. |
| Services | `recruiting/accounts.py`, `recruiting/jobs.py`, `recruiting/scheduling.py`, `recruiting/matching.py` | Validate input, enforce permissions, score matches, and commit writes. |
| Storage | `recruiting/db.py`, `recruiting/migrations/` | Manages SQLite connections, transactions, schema versions, and foreign keys. |

Waitress serves the application. The Docker image contains the server and test runtime, with the database on a mounted volume. Flask opens a SQLite connection on demand for each application context through Python's `sqlite3` module. It enables foreign keys, sets a 10-second busy timeout, and closes the connection at teardown. Tests and seeding use the configurable `NOW` callable for UTC time.

`create_app(config=None)` loads settings, registers Flask blueprints, and turns application and HTTP errors into JSON. The API delegates writes to the service modules and uses `present.py` to shape the response. The entry point is `python -m recruiting`. Versioned SQL migrations and the demo seed have separate CLI commands. Starting the container applies migrations and leaves existing data in place.

## Data Model and Relationships

Migrations 001 through 005 create the schema. Timestamps use integer UTC epoch seconds.

| Table | Columns | Relationships and constraints |
|---|---|---|
| `users` | `id`, `email`, `password_hash`, `role`, `display_name` | Email is unique and case-insensitive. The role is `Candidate` or `Employer`. The display name must be non-empty. |
| `candidate_profiles` | `user_id`, `resume`, `resume_updated_at`, `headline`, `location`, `pref_job_type`, `pref_remote` | One profile per candidate user. The job preference is `Full-time`, `Contract`, `Any`, or empty if unset. The remote preference is stored as 0 or 1. |
| `candidate_skills` | `candidate_id`, `skill` | The candidate and skill form the primary key. |
| `companies` | `employer_id`, `name`, `description`, `industry`, `size`, `location`, `website`, `logo`, `logo_w`, `logo_h` | One company profile per employer user. |
| `jobs` | `id`, `employer_id`, `title`, `description`, `summary`, `location`, `job_type`, `posting_status`, `created_at`, `logo`, `logo_w`, `logo_h`, `categories` | Each job belongs to an employer's company. Title and description must be non-empty. |
| `job_skills` | `job_id`, `skill` | Job and skill form the primary key. Job deletion removes its skill rows. |
| `applications` | `id`, `candidate_id`, `job_id`, `status`, `created_at` | `UNIQUE(candidate_id, job_id)` permits one application per pair. The initial status is `Pending`. |
| `application_events` | `id`, `application_id`, `status`, `created_at` | One row per recorded status change. |
| `slots` | `id`, `job_id`, `starts_at`, `ends_at` | The job supplies the employer. `CHECK(ends_at - starts_at = 1800)` enforces the duration. |
| `bookings` | `id`, `application_id`, `slot_id`, `created_at` | Both foreign keys are separately unique. Pre-005 bookings have `created_at = 0`. |
| `auth_sessions` | `token_hash`, `user_id`, `expires_at` | Stores the token digest for each active sign-in. |
| `metadata` | `key`, `value` | Stores `session_generation`, which changes on demo reset. |
| `schema_migrations` | `version` | Tracks applied SQL filenames. |

Registration creates the account and its candidate profile or company in one transaction. Jobs require a non-empty title and description. An employer can delete a job only when it has no applications or slots. The service returns `409` for a dependent record, and the foreign keys enforce the same restriction. Application statuses are `Pending`, `Interviewing`, `Rejected`, and `Accepted`. An existing booking also blocks deletion of its slot or application at the database layer.

The job service validates the types `Full-time`, `Part-time`, `Contract`, and `Internship`, plus the listing statuses `Active` and `Closed`. It validates listing metadata and core job fields together. Partial edits read the existing job inside the write transaction and preserve omitted fields. Nested service writes use SQLite savepoints.

## Authentication and Authorization

Registration trims and lowercases email addresses, checks their format, and returns `409` for a duplicate. Passwords must be 8 to 256 characters and a display name must contain 1 to 100. Werkzeug stores a salted scrypt hash through `generate_password_hash` and checks it with `check_password_hash`. An unknown email and a wrong password return the same `401`. Valid credentials submitted for the other role return `403`.

At sign-in or registration, `auth.start_session` removes the previous browser session and any expired records. It stores a SHA-256 digest of a new random token with a 12-hour expiry. The signed Flask cookie holds the token, current session generation, and a fresh CSRF token. Cookies use `HttpOnly` and `SameSite=Lax`. Set `COOKIE_SECURE=1` for HTTPS. The default process-specific `SECRET_KEY` invalidates existing cookies on restart.

`auth.load_user` checks the digest, expiry, and generation on each request. An invalid session is cleared. Logout removes the corresponding server record, and reseeding changes the generation and invalidates all sessions.

| Request | Result |
|---|---|
| Protected API route without a valid session | `401` |
| Wrong role or owner | `403` |
| Missing record the caller could otherwise access | `404` |
| POST with the wrong or missing CSRF token after the session check | `403` |

Protected routes check the role with `as_role`. Service operations check role and record ownership with `require_role` and `require_owner`. Candidates manage their own profiles and resumes and see only their own applications. Employers manage their own jobs, applicants, and slots. Only the employer who owns a job can change the application status. The direct resume route checks ownership before reading the record or parsing a write body. An owner whose profile row is missing receives `404`.

## API Routes or Server Actions

| Page route | Behavior |
|---|---|
| GET `/` | Redirect to sign-in or the signed-in role's dashboard. |
| GET `/sign-in` | Serve the sign-in and registration page. |
| GET `/login`, `/register` | Redirect to `/sign-in` and `/sign-in#signup`, respectively. |
| GET `/candidate/<page>`, `/recruiter/<page>`, `/shared/<file>` | Serve the portal pages and assets. Extensionless paths resolve to `.html`. |
| GET `/health` | Return `{"status":"ok"}`. |

The public HTML pages check `/api/auth/me` before loading private data. API errors use `{"ok":false,"message":"..."}` and the corresponding HTTP status. Routes that read a body require a JSON object. Empty, malformed, non-object, or deeply nested JSON returns `400`. An explicit empty object is valid for partial updates. The request size limit is 1 MiB. The body IDs `jobId` and `slotId` accept a JSON integer or a string of up to 19 ASCII digits in the range `1` through `2^63 - 1`. Booleans, fractional values, and strings with whitespace return `404`. The same positive integer range applies to path IDs.

| Method and path | Access and behavior |
|---|---|
| GET `/api/auth/csrf` | Returns the CSRF token for the current browser session, including before login. |
| POST `/api/auth/register` | Accept `email`, `password`, `role`, and `name`, with an optional `company` for employers. Create the account and session, rotate the CSRF token, and return `201`. |
| POST `/api/auth/login` | Accept `email`, `password`, and `role`. Start the session and rotate the CSRF token. |
| GET `/api/auth/me`, POST `/api/auth/logout` | Read `id`, `email`, `role`, `name`, and `csrfToken`, or end the current session. |
| GET `/api/candidate/bootstrap` | Candidate's profile, ranked jobs with company records, own applications and timelines, and visible slots. |
| POST `/api/candidate/profile` | Update supplied `name`, `skills`, `headline`, `location`, `resume`, or `prefs`. The API validates the fields before saving and returns the updated profile and candidate snapshot. Omitted fields, including the resume, keep their values. |
| GET or POST `/api/candidate/<candidate_id>/resume` | Read or replace the owning candidate's raw resume in the `resume` field. This write changes the resume and its update timestamp. |
| POST `/api/candidate/matching-preview` | Score draft skills against current jobs. Returns scores, ranks, and saved-profile baseline scores without writing the draft. |
| POST `/api/candidate/applications` | Create a `Pending` application for `jobId` and return `201`. Duplicate applications and applications to a closed job return `409`. |
| POST `/api/candidate/applications/<id>/book` | Book `slotId` with the candidate's own eligible application. |
| GET `/api/employer/bootstrap` | Return the employer's company, jobs, ranked applicants, and slots. Applicant cards include name, headline, location, email, and skills. Applications carry score, rank, status, and the timeline. Resume text stays private. |
| POST `/api/employer/company` | Update `name`, `about`, `industry`, `size`, `location`, or `website` on the employer's company. |
| POST `/api/employer/jobs` | Create an owned job with `title`, `body` or `desc`, and `skills`. Optional fields include `location`, `type`, and `status`. Return `201`, the job, and the employer snapshot. |
| POST `/api/employer/jobs/<id>` | Partially edit an owned job. Return the job and updated employer snapshot. |
| POST `/api/employer/jobs/<id>/delete` | Delete an owned job and return an updated snapshot. Jobs with applications or slots return `409`. |
| POST `/api/employer/applications/<id>/status` | Set `status` to one of the four allowed values. A real change records an event. Return the updated application and employer snapshot. |
| POST `/api/employer/slots` | Create a 30-minute slot from `start` and `end`, and return `201`. |
| POST `/api/employer/slots/<id>/delete` | Delete an owned unbooked slot. Booked slots return `409`. |

`prefs` contains a job `type` and a Boolean `remote` flag. Candidate job and slot cards carry the employer's ID. Job cards expose it as `owner` and `employerId`. Company records use that ID as the key, so identical company names still lead to the correct profiles and availability.

## User Interface and Workflows

The sign-in page has candidate and recruiter tabs and a registration form. Employers can supply a company name at sign-up. The account's display name is the fallback. The hosted pages use a sidebar and card layout, with stacked columns on small screens and a system-font fallback for Plus Jakarta Sans.

| Portal and page | What the page shows or does |
|---|---|
| Candidate dashboard | Counts by application status, the next interview, and current jobs ranked by score. Each job has a title, company, location, required skills, and an apply action or state. |
| Find Jobs and Saved Jobs | Search and filter job listings, open full descriptions, and revisit jobs saved in the current browser tab. |
| My Profile | Edit the display name, headline, location, skills, work preferences, and plain-text resume. Show the resume's last saved date when available and preview score changes for unsaved skills. |
| My Applications | Show each job, company, status, booking, and the timeline of submission, status changes, and booking. |
| Candidate Interviews | Show reserved times and a picker for each unbooked `Interviewing` application. Date labels such as Today and Tomorrow use the Pacific calendar day. |
| Employer dashboard | Show job and application counts, recent applicants, and upcoming interviews. |
| My Jobs | Create, edit, close, reopen, and delete postings. An empty location displays as `Not listed`. The `locationSet` flag keeps that label out of saved data. When deletion is blocked, explain which dependent records exist. |
| Applicants | Select a job to see ranked applicants with identity, skills, score, status, and any booking. Status controls use the four application statuses. |
| Employer Interviews | Show a calendar, a 30-minute slot grid, a form for a specific time, and booked interviews. |
| Company Profile | Edit company name, description, industry, size, location, and website. |

A candidate adds skills and applies to a job. The application starts as `Pending`. The employer reviews the applicant and moves it to `Interviewing`. The candidate selects a future open time offered by that employer. Both sides see the booking after confirmation, even if the employer later accepts or rejects the application.

Profile edits, job writes, and status changes return a refreshed API snapshot. The portals apply it immediately. Navigation, focus, and becoming visible also trigger refreshes. Visible pages poll every five seconds, and unsaved skill drafts or job edits delay automatic refresh. A failed save shows the server's message without clearing the draft. If the session ends, a protected API's `401` returns the user to the sign-in tab for their role.

Saved jobs use `sessionStorage` under `mw.saved.<id>` and are cleared at logout. The candidate and recruiter notification-read keys are `mw.notifSeen.<id>` and `rw.notifSeen.<id>` in `localStorage`. Snapshots preserve this browser state. Reminders are reconstructed from application and booking data during refresh.

## Matching Algorithm and Skill Storage

`recruiting.matching.normalize_skills` trims the edges of each value, applies Python's lowercase conversion, removes blanks, and deduplicates. It accepts up to 100 normalized skills of at most 80 characters each. Surrounding whitespace covers U+0009 through U+000D, U+001C through U+0020, U+0085, U+00A0, U+1680, U+2000 through U+200A, U+2028, U+2029, U+202F, U+205F, U+3000, and the U+FEFF byte-order mark. Internal whitespace, U+200B, and U+180E remain part of the skill. The service uses lowercase conversion without case folding or Unicode composition.

Candidate and employer edits store one normalized skill per row in `candidate_skills` or `job_skills`. Sample catalog rows can keep the capitalization from `candidate/assets/jobs.json`. `score` normalizes both skill lists when it calculates a result, and the live API emits canonical skill values. An existing database can keep its old skill rows.

For candidate skills `C` and required skills `R`, the score is `100` when `R` is empty. Otherwise it is `100 * len(C & R) // len(R)`, an integer from 0 through 100. Only skills enter the calculation. The score is computed from the current profile and job requirements when the service reads them.

`jobs.recommendations` orders every non-deleted job by descending score, then case-insensitive title, then numeric job ID. `jobs.applicants` orders each job's applicants by descending score, then case-insensitive display name, then numeric candidate ID. `jobs.ranked_applications` adds the application ID as a final tie-breaker for the employer's all-jobs list. Filtering that list to one job preserves the per-job order.

Both services call the same Python scorer. The API returns integer `score` and zero-based `rank` fields and serializes record IDs as strings in the ranked cards. The live portals use `shared/match.js` through `fromServer` and `byServerRank`, keeping the server's order and comparing the canonical skill values it supplies. The draft preview calls the same scorer on the server and compares the draft result to the saved-profile `baselineScore`. Draft skills remain unsaved until the candidate confirms. See [INSTALL.md](INSTALL.md#frontend-checks-and-matching-parity) for the live parity suite and the JavaScript calculator diagnostic.

## Interview Scheduling and Booking Transaction

A slot must start in the future and last exactly 30 minutes. The API accepts ISO 8601 timestamps with `Z` or an explicit offset and uses whole seconds. Invalid timestamps or durations return `400`. SQLite stores UTC timestamps and the interface converts them to Pacific Time (`America/Los_Angeles`). The manual form rejects nonexistent or ambiguous wall times when clocks change. A start in the `23:00` hour and end in the `00:00` hour place the end on the next date.

The employer calendar shows the next 14 days and later dates with slots. A valid `day` URL parameter for today or a future date stays selected on reload, even after the final slot on that date is removed. The candidate picker shows only dates with eligible open times.

`scheduling.create_slot` returns `400` when the employer has no job. It checks for overlap with that employer's slots inside the write transaction and returns `409` for a conflict. The API attaches new slots to the employer's oldest job by ID so job deletion can enforce the slot dependency. An eligible candidate can book any of that employer's slots, including one attached to a different job. A booked slot stays reserved and cannot be deleted.

Candidate bootstrap returns the caller's booked slots, including past ones, and future unbooked slots at employers where the caller has an `Interviewing` application without a booking. The employer API returns that employer's own slots and bookings.

`scheduling.book` starts a SQLite `BEGIN IMMEDIATE` transaction before reading eligibility. It checks the application first, then the slot.

| Check in transaction order | If the check fails |
|---|---|
| The application exists and belongs to the candidate. | `404` if missing, `403` if owned by another candidate |
| The application has no booking and is `Interviewing`. | `409` with the reason |
| The slot exists and belongs to the application's employer. | `404` if missing, `403` for another employer |
| The slot starts in the future. | `409` because the time has passed |
| The slot is unbooked. | `409` with `Slot already booked` |

The service inserts the booking and its creation timestamp before committing. A rejected request rolls back the transaction without changing the data.

For two eligible candidates requesting the same future slot, the next writer reads the first committed booking and receives `409` with exactly `Slot already booked`. The unique slot and application constraints enforce one booking at the database layer. The transaction uses SQLite's write lock because SQLite allows one writer at a time. Lock contention that outlasts the 10-second wait returns `503` with `Database is busy. Please try again.` Status changes and deletions also use write transactions. Later status changes preserve the booking and leave the slot unavailable.

## Security Controls

- Service queries bind user-provided values with SQLite parameters. The seed command formats SQL with a fixed internal list of table names.
- Browser renderers use text nodes or call `shared/html.js` to escape values before inserting text or quoted attributes into HTML. The company profile renders website links with an HTTPS prefix. The renderer tests exercise the shipped escape function.
- The server sends a same-origin Content Security Policy with exceptions for inline page scripts and Google Fonts. It also sends `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Referrer-Policy: same-origin`. Authenticated responses and HTML use `Cache-Control: no-store`, as does the CSRF token endpoint.
- Each POST, including one with no body, requires the current session's `X-CSRF-Token`. Login and registration get it from `/api/auth/csrf`. The portals get the current token from `/api/auth/me` when they open.
- The server limits email to 254 characters, display and company names to 100, job titles to 150, and job and company descriptions to 10,000. The resume limit is 50,000. Text fields checked by the shared service validator reject NUL characters. See the API section for the request-size limit.
- Static files resolve within the portal and shared asset directories. A path outside these directories returns `404`.
- Demo credentials are synthetic. `.env.example` contains placeholders. Local databases and secrets stay out of Git. The test fixture uses a temporary SQLite database and a fixed clock, and unit tests run without external services.

## Optional AI Features and Data Flow

FP-MATCH-2 is N/A. The live site computes scores locally in Python and keeps resumes and skills in SQLite.

## Design Decisions and Limitations

- SQLite serializes writers and suits a local course demo. Booking state is enforced by the database and survives a restart when the volume is kept.
- Migration 005 starts recording status changes, booking actions, and resume updates. A pre-005 booking action or a current non-Pending status with no recorded history uses `null` in the timeline response and `Time unknown` in the interface. The booked interview keeps its scheduled start and end.
- Closed postings stay visible and reject new applications. Existing bookings remain valid after an application status change.
- The resume field accepts plain text. Account recovery, email verification, file uploads, booking cancellation, and external notification delivery are outside the current scope.
