# Matchwork

Matchwork is a locally runnable recruiting platform built for CSC4801.
Candidates discover jobs by skill match, employers manage their postings and
applicants, and both sides share an interview scheduling workflow.

The application uses Flask, SQLite, and a browser interface built with HTML,
CSS, and JavaScript. Flask serves both the pages and the JSON API. No cloud
account, paid API, or Node.js build step is needed to run the application.

## What you can do

| Role | Main features |
|---|---|
| Candidate | Register and sign in; maintain a profile, technical skills and text resume; browse jobs and match scores; save jobs in the browser; apply and follow application status; book an offered interview time. |
| Employer | Maintain a company profile; create, edit and close job postings; review applicants ordered by match; update application status; offer and manage interview availability. |

Accounts have exactly one of the two roles: `Candidate` or `Employer`.
Both roles use the same [sign-in page](http://127.0.0.1:8080/sign-in).

## Quick start

Run these commands from the repository root. See [INSTALL.md](INSTALL.md)
for prerequisite versions, platform-specific setup, environment variables,
existing-container instructions, and troubleshooting.

### Docker

With Docker Engine or Docker Desktop running, create a new local instance:

```sh
docker build -t common-ground .
docker volume create common-ground-data
docker run -d --name common-ground -p 127.0.0.1:8080:8080 -v common-ground-data:/app/data common-ground
```

Wait until the [sign-in page](http://127.0.0.1:8080/sign-in) opens, then load
the demo accounts and jobs:

```sh
docker exec common-ground python -m flask --app recruiting seed --yes
```

Use a demo account below to sign in. Startup applies migrations automatically. The named volume retains the
database when the container is recreated with the same volume.

The seed command creates demo data by resetting the configured database.
Running it again removes existing records in that database and signs out
existing sessions.

### Python

Use Python **3.12** in an activated virtual environment; creation and activation
commands for Windows and Unix are in [Local setup](INSTALL.md#local-setup).

```sh
python -m pip install -r requirements.txt
python -m flask --app recruiting init-db
python -m flask --app recruiting seed --yes
python -m recruiting
```

Open [Matchwork](http://127.0.0.1:8080). Local Python runs use
`instance/recruiting.sqlite3` by default. Optional settings are listed in
[INSTALL.md](INSTALL.md#environment); `.env.example` is a reference and is not
loaded automatically.

## Local demo accounts


These identities are synthetic. **All demo passwords: `DemoPass123!`.**
Do not use these credentials or this dataset for a production service.

| Email | Role | Seeded context |
|---|---|---|
| `alex@example.test` | Candidate | Python + SQL; Interviewing for Backend Engineer |
| `blair@example.test` | Candidate | Python; Interviewing for the same job and eligible for the same slots |
| `casey@example.test` | Candidate | Rust; additional application statuses |
| `north@example.test` | Employer | Northstar Studio; Backend Engineer and Data Analyst |
| `field@example.test` | Employer | Fieldwork Labs; Systems Engineer and Graduate Programme |

The seed also loads the Matchwork catalog from `candidate/assets/jobs.json`. Each catalog company has a demo Employer account. Its email uses the lowercase company name with runs of non-alphanumeric characters replaced by hyphens, followed by `@example.test`; for example, `google@example.test`. These accounts use the same demo password.

## Matching and interviews

Match scores use normalized technical skills: trim surrounding whitespace,
convert to lowercase, remove blanks, and deduplicate. The score is the
percentage of required skills the candidate has, rounded down. A job with no
required skills scores 100. For example, Python against Python + SQL scores 50.

The backend supplies scores and ordering to both portals. Jobs sort by score,
then case-insensitive title and stable job ID; applicants sort by score, then
case-insensitive display name and stable candidate ID. Skills and job edits
update the results after saving. Other open pages refresh when focused and
periodically while visible; unsaved drafts are protected.

An interview starts with an application. The employer moves it to
`Interviewing` and offers future 30-minute slots; the candidate chooses an
available time. Each application has at most one booking, and a slot can be
reserved once. The booking remains associated if the application later changes
status to `Pending`, `Rejected`, or `Accepted`.

Times are stored in UTC and shown in **Pacific Time**: PST (UTC-8) or PDT (UTC-7),
depending on the date.

## Architecture and project layout

The browser communicates with Flask through JSON. Backend services enforce
roles, ownership, matching and scheduling rules; SQLite stores the persistent
records. Waitress serves the local application.

| Location | Responsibility |
|---|---|
| `recruiting/__init__.py` | Application factory, configuration and security headers. |
| `recruiting/api.py`, `recruiting/auth.py`, `recruiting/pages.py` | JSON endpoints, sessions and page delivery. |
| `recruiting/accounts.py`, `recruiting/jobs.py`, `recruiting/matching.py`, `recruiting/scheduling.py` | Account, job, matching and booking services. |
| `recruiting/db.py`, `recruiting/migrations/` | SQLite connections, transactions and versioned schema. |
| `recruiting/seed.py` | Explicit local/demo database reset and catalog loading. |
| `candidate/` | Candidate dashboard, profile, jobs, applications and interviews. |
| `recruiter/` | Employer dashboard, company, jobs, applicants and availability. |
| `shared/`, `login.html` | Shared browser helpers and sign-in/registration page. |

Booking uses a database transaction and uniqueness constraints to prevent
double booking. Match scores come from the backend; browser pages display its
results. Raw resume text never contributes to matching scores.

## Current scope and limitations

- This version targets local/course use. SQLite serializes writes and is
  intended for small workloads.
- Optional AI, PDF upload, email verification, password recovery, email/push
  notifications and booking cancellation are not implemented.
- Employers cannot read raw resumes. Saved jobs live in the browser's
  session storage.
- Closed jobs remain visible to candidates but stop accepting new applications.
  Jobs with applications or interview slots cannot be deleted.
- New availability is attached to the employer's oldest job. Eligible
  applications to the same employer may book those slots.
- The candidate interview calendar shows dates with offered slots; it does not
  create availability.

## Documentation

| Document | Contents |
|---|---|
| [INSTALL.md](INSTALL.md) | Setup, configuration, migrations, demo reset, startup and troubleshooting. |
| [SPEC.md](SPEC.md) | Architecture, data relationships, API routes, matching and scheduling contracts. |
| [Course specification](final_project_spec/README.md) | Normative project requirements and submission material. |
| [Peer-audit rules](final_project_spec/PEER_REVIEW.md) | Course review process and scope. |
| [AGENTS.md](AGENTS.md) | Repository working rules and implementation milestones. |
| [Verification record](docs/verification.md) | Development verification history and links to detailed records. |

## Requirement–test mapping

Tests listed below are team-owned behavior assertions, replacing starter `pass`
functions. Paths below are relative to `tests/unit/` unless stated otherwise.
Non-functional rows identify verification steps; external course actions remain
team responsibilities, not claims of automated completion.

| Requirement | Implementation | Named tests / verification evidence |
|---|---|---|
| FP-ARCH-1 | `recruiting/__init__.py`, `db.py`, `pages.py`, `api.py`, Dockerfile | `test_web.py::test_candidate_and_employer_api_browser_workflow`; `test_api.py::test_sign_in_page_and_static_files_are_served`; clean Docker workflow in INSTALL.md |
| FP-AUTH-1 | `accounts.py`, `auth.py`, `api.py`, `login.html` | `test_auth.py::test_registration_login_and_salted_hashes`, `test_invalid_registration`, `test_duplicate_and_invalid_login`; `test_web.py::test_registration_and_session_lifecycle`; `test_api.py::test_api_login_role_and_logout`, `test_api_register_starts_a_session`; `test_entry_boundaries.py::test_register_and_login_reject_roles_without_writes`, `test_credentials_type_length_and_email_boundaries`, `test_rotated_and_expired_sessions_cannot_be_reused` |
| FP-AUTH-2 | `accounts.py` | `test_auth.py::test_registration_login_and_salted_hashes` |
| FP-AUTH-3 | `accounts.py`, `jobs.py`, `scheduling.py`, `auth.py` | `test_workflows.py::test_wrong_roles_ownership_and_missing_objects`; `test_web.py::test_auth_errors_and_role_boundaries`, `test_other_employer_cannot_manage_a_job`; `test_regressions.py::test_oversized_path_id_is_not_found`, `test_forbidden_scheduling_requests_are_403_before_bad_input`; `test_round2_contracts.py::test_role_owner_matrix_with_direct_requests` |
| FP-CAN-1 | `accounts.py`, `api.py`, `candidate/profile.html` | `test_auth.py::test_profile_skills_and_private_resume`; `test_web.py::test_resume_stays_private_and_user_text_is_json`; `test_round2_contracts.py::test_failed_writes_leave_all_related_and_unrelated_rows` |
| FP-CAN-2 | `jobs.py`, `candidate/dashboard.html` | `test_workflows.py::test_recommendations_fields_all_jobs_and_tie_breakers`; `test_round2_contracts.py::test_both_views_recompute_oracle_and_stable_ties`; `test_authoritative_matching.py::test_preview_is_read_only_and_uses_the_course_formula`; real save/preview/refresh browser regression |
| FP-CAN-3 | `jobs.py`, `candidate/applications.html` | `test_workflows.py::test_applications_pending_duplicate_owner_and_statuses`; `test_web.py::test_malformed_booking_and_other_application_access`; `test_round2_contracts.py::test_json_resource_id_does_not_coerce_or_crash` |
| FP-EMP-1 | `accounts.py`, `recruiter/` company screens | `test_auth.py::test_company_profile`; `test_round2_contracts.py::test_same_name_companies_remain_distinct_in_candidate_api` |
| FP-EMP-2 | `jobs.py`, recruiter job screens | `test_workflows.py::test_job_crud_validation_and_dependent_deletion`, `test_wrong_roles_ownership_and_missing_objects`; `test_scheduling.py::test_slot_ownership_and_job_dependency`; `test_acceptance_regressions.py::test_rejected_job_creation_preserves_database`, `test_acceptance_regressions.py::test_rejected_job_edit_preserves_all_fields`; `test_round2_contracts.py::test_failed_writes_leave_all_related_and_unrelated_rows` |
| FP-EMP-3 | `jobs.py`, `recruiter/applicants.html` | `test_workflows.py::test_applicants_fields_and_both_tie_breakers`, `test_applications_pending_duplicate_owner_and_statuses`; `test_scheduling.py::test_booking_visible_preserved_and_deletion_rejected`; `test_round2_contracts.py::test_both_views_recompute_oracle_and_stable_ties`; `test_authoritative_matching.py::test_status_response_keeps_score_and_rank`, `test_preview_and_ranked_results_keep_role_and_owner_boundaries` |
| FP-MATCH-1 | `matching.py`, `jobs.py`, `api.py`, `present.py`, live JS API projection | `test_matching.py::test_score_examples_normalization_and_floor`, `test_skill_normalization`; `test_workflows.py::test_recommendations_fields_all_jobs_and_tie_breakers`, `test_applicants_fields_and_both_tie_breakers`; `test_round2_contracts.py::test_independent_golden_scores`, `test_round2_contracts.py::test_seeded_score_oracle_and_metamorphic_relations`; `test_entry_boundaries.py::test_unicode_edge_whitespace_persists_and_matches_both_services`; `tests/frontend/matching.test.cjs`; `tests/acceptance/matching_parity.py`; `test_authoritative_matching.py::test_unicode_scores_and_order_flow_through_real_api`, `test_api_title_ties_and_large_ids_are_authoritative`; `tests/frontend/server.test.cjs`; `tests/browser/authoritative.cjs` |
| FP-MATCH-2 | Not implemented | N/A — optional AI enhancement |
| FP-SCHED-1 | `scheduling.py`, `recruiter/interviews.html` | `test_scheduling.py::test_create_slot_timezone_and_delete`, `test_invalid_slots`; `test_regressions.py::test_slot_requires_a_renderable_utc_time`; `test_booking_visible_preserved_and_deletion_rejected`, `test_slot_ownership_and_job_dependency`; `test_acceptance_regressions.py::test_slot_api_requires_explicit_timezone`, `test_acceptance_regressions.py::test_unrenderable_slot_is_rejected_without_server_error`; `test_round2_contracts.py::test_time_boundaries_offsets_and_failed_state`, `test_round2_contracts.py::test_booked_slot_is_redacted_and_unavailable_to_other_candidate`; `test_entry_boundaries.py::test_generated_future_slots_and_offsets_have_exact_utc` |
| FP-SCHED-2 | `scheduling.py`, `candidate/interviews.html` | `test_scheduling.py::test_booking_visible_preserved_and_deletion_rejected`, `test_ineligible_bookings_leave_no_partial_changes`, `test_same_employer_cross_job_and_one_booking_per_application`; `test_round2_contracts.py::test_booking_state_machine_and_exact_future_boundary`; `test_entry_boundaries.py::test_seeded_application_booking_operation_model` |
| FP-SCHED-3 | `db.py`, `scheduling.py`, migration constraints | `test_scheduling.py::test_booking_conflict_contract`; `tests/integration/test_concurrency.py::test_two_candidates_race_for_one_slot`; `test_round2_contracts.py::test_storage_contention_is_distinct_and_transaction_recovers` |
| FP-SEC-1 | Account/job/scheduling ownership checks | `test_auth.py::test_profile_skills_and_private_resume`; `test_workflows.py::test_wrong_roles_ownership_and_missing_objects`; `test_scheduling.py::test_ineligible_bookings_leave_no_partial_changes`; direct-request tests in `test_web.py`; `test_round2_contracts.py::test_role_owner_matrix_with_direct_requests` |
| FP-SEC-2 | Parameterized service queries | `test_security.py::test_sql_metacharacters_remain_bound_values` records bound login parameters and verifies malicious job text persists as data |
| FP-SEC-3 | JSON responses, page escaping, CSP | `test_web.py::test_resume_stays_private_and_user_text_is_json` returns script text as JSON data and keeps it out of another user's bootstrap and the static page; `tests/frontend/html.test.cjs`: `product escape: script-tag`, `event-attribute`, `attribute-breakout`; actual DOM checks in `tests/browser/acceptance.cjs` |
| FP-SEC-4 | `tests/conftest.py`, `.env.example`, ignore files | Temporary database per test; no external-service test code; source/secret review before submission |
| FP-PROC-1 | SPEC.md and this mapping | Maintain specification alongside behavior; team members must review and explain submitted code |
| FP-DOC-1 | INSTALL.md, Dockerfile, CLI | Execute the documented clean-checkout build/start/migrate/seed/test flow |
| FP-DOC-2 | README.md | This table covers every normative requirement ID; document index and demo credentials above/below |
| FP-DOC-3 | `seed.py` | `test_seed.py::test_seed_is_repeatable_and_covers_requirements`, `test_reset_invalidates_existing_sessions_and_requires_confirmation` |
| FP-TEST-1 | `tests/`, `.github/workflows/tests.yml` | `python -m pytest tests/unit -q`; full suite also includes the real concurrency check; complete backend/frontend units and bounded parity: `python tests/run_units.py`; the Unicode CI gate verifies the authoritative API chain; hosted status is recorded separately |
| FP-SUB-1 | Dockerfile, INSTALL.md, GitHub audit templates | Clean container verification; team must publish repository and submit the exact permanent `main` commit URL before the course deadline |

## Verification commands

Run the required unit suite with
`python -m pytest tests/unit -q`, or the full suite including the synchronized
booking race with `python -m pytest -q`. With Node.js 24 installed, `python tests/run_units.py` runs all backend and frontend units plus the authenticated API-to-frontend contract; add `--include-concurrency` for the real race too.

## Team handoff

Complete the team roster and contribution attribution before submission.
Every member must understand and be able to modify the implementation.

The supplied audit form and label definitions are in
[.github/ISSUE_TEMPLATE/audit_bug_report.yml](.github/ISSUE_TEMPLATE/audit_bug_report.yml)
and [.github/labels.yml](.github/labels.yml). Repository visibility, label import,
hosted CI results, and the permanent graded commit require separate team actions.
Follow the course submission protocol using the final commit on main.
