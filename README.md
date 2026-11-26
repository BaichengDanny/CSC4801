# Matchwork

A locally runnable full-stack recruiting and candidate-matching platform built for **CSC4801**.

[Overview](#project-overview) · [Architecture](#architecture-summary) · [Quick Start](#quick-start) · [Demo Accounts](#demo-accounts) · [Unit Tests](#running-unit-tests) · [Requirement–Test Mapping](#requirementtest-mapping) · [Documents](#document-index) · [Limitations](#known-limitations)

---

## Project Overview

Matchwork connects candidates and employers through deterministic skill-based matching, application tracking, and database-atomic interview scheduling. Built with **Flask**, **Waitress**, **SQLite**, and vanilla **HTML/CSS/JavaScript**, the entire application runs locally from a single Docker image or Python 3.12 environment—requiring no cloud account, paid API, or frontend build step.

| Role | Capabilities |
|---|---|
| `Candidate` | Register and sign in, manage a skills profile and private plain-text resume, browse ranked job listings, save jobs in the browser session, apply once per job, track application status, and book available interviews. |
| `Employer` | Manage a company profile, create/edit/close/reopen job postings, delete postings without dependent records, review ranked applicants, update application statuses, and publish or remove 30-minute interview slots. |

Each account holds exactly one role (`Candidate` or `Employer`), and both roles share the sign-in portal at `http://127.0.0.1:8080/sign-in`.

## Team Members

| Name | Student ID |
|---|---|
| Baicheng Chen | 123090015 |
| Yuyang Qin | 122090433 |
| Xuanxue Zheng | 123090886 |

## Architecture Summary

Flask serves the static portal pages and exposes a JSON API under `/api`, enforcing authentication, role/ownership checks, CSRF validation, and business rules on the server. SQLite persists accounts, normalized skills, postings, applications, and interview bookings in a single relational database file, served in production and Docker by Waitress.

| Location | Responsibility |
|---|---|
| `login.html`, `candidate/`, `recruiter/`, `shared/` | Sign-in view, candidate and employer portals, and shared browser escaping/matching helpers. |
| `recruiting/__init__.py`, `recruiting/pages.py`, `recruiting/api.py`, `recruiting/present.py` | Application factory, page routing, JSON API endpoints, and response serialization. |
| `recruiting/auth.py`, `recruiting/accounts.py` | Revocable server-side sessions, CSRF protection, account lifecycle, and profile permissions. |
| `recruiting/jobs.py`, `recruiting/matching.py`, `recruiting/scheduling.py` | Job/application workflows, shared deterministic scoring, and atomic interview booking. |
| `recruiting/db.py`, `recruiting/migrations/`, `recruiting/seed.py` | SQLite connections, `BEGIN IMMEDIATE` transactions, versioned SQL migrations, and deterministic demo seeding. |
| `tests/unit/`, `tests/frontend/`, `tests/integration/` | Backend service/API unit tests, frontend JavaScript checks, and a synchronized two-client booking race test. |

Both portals consume scores and rankings directly from `recruiting/matching.py`. Skills are trimmed, lowercased, filtered for blanks, and deduplicated before computing `floor(100 * |C ∩ R| / |R|)` (or `100` when no skills are required), with deterministic tie-breaking by title/display name and stable record ID. Resume text is never read by the matcher. Interview booking executes inside a SQLite `BEGIN IMMEDIATE` transaction backed by unique constraints on both `slot_id` and `application_id`. See [SPEC.md](SPEC.md) for the full schema, API contract, and security controls.

## Quick Start

For full prerequisites, environment variables, migrations, and troubleshooting, see [INSTALL.md](INSTALL.md).

### Docker (Recommended)

Build the image from the repository root and start a container backed by a persistent named volume:

```sh
docker build -t matchwork .
docker volume create matchwork-data
docker run -d --name matchwork -p 127.0.0.1:8080:8080 \
  -v matchwork-data:/app/data matchwork
```

Startup automatically applies pending migrations. Once `GET http://127.0.0.1:8080/health` returns `{"status":"ok"}`, populate a fresh or disposable demo volume:

```sh
docker exec matchwork python -m flask --app recruiting seed --yes
```

Open `http://127.0.0.1:8080/sign-in` and sign in with any demo account below. Reusing `matchwork-data` preserves state across container restarts; re-running `seed --yes` resets the database and invalidates existing sessions. Stop and remove the container with `docker stop matchwork && docker rm matchwork` (see [INSTALL.md](INSTALL.md#docker-startup)).

### Local Python

Activate a Python 3.12 virtual environment first (see [Dependency Installation](INSTALL.md#dependency-installation)), then install, migrate, seed, and start the server:

```sh
python -m pip install -r requirements.txt
python -m flask --app recruiting init-db
python -m flask --app recruiting seed --yes
python -m recruiting
```

By default, local runs store the SQLite database at `instance/recruiting.sqlite3` and listen on `http://127.0.0.1:8080`.

## Demo Accounts

> [!NOTE]
> All seeded accounts are **synthetic local/demo credentials** containing no real personal data. Every seeded account shares the demo password `DemoPass123!`.

| Email | Role | Seeded Data |
|---|---|---|
| `alex@example.test` | Candidate | Skills: `Python`, `SQL`. `Interviewing` for Backend Engineer; `Pending` for Data Analyst. |
| `blair@example.test` | Candidate | Skills: `Python`. `Interviewing` for Backend Engineer; `Rejected` for Systems Engineer. |
| `casey@example.test` | Candidate | Skills: `Rust`. `Accepted` for Graduate Programme. |
| `north@example.test` | Employer | **Northstar Studio** — owns Backend Engineer and Data Analyst; 3 open future slots. |
| `field@example.test` | Employer | **Fieldwork Labs** — owns Systems Engineer and Graduate Programme; 1 open future slot. |

The seed covers all four required `FP-MATCH-1` scoring examples and leaves both `alex@example.test` and `blair@example.test` eligible to race for the same Northstar Studio interview slot:

| Candidate | Candidate Skills | Job | Required Skills | Expected Score |
|---|---|---|---|---:|
| Alex | `Python, SQL` | Backend Engineer | `Python, SQL` | `100` |
| Blair | `Python` | Backend Engineer | `Python, SQL` | `50` |
| Casey | `Rust` | Backend Engineer | `Python, SQL` | `0` |
| Any candidate | Any skills | Graduate Programme | *(empty)* | `100` |

In addition to the core fixtures, the seed loads 39 catalog postings across 26 companies from `candidate/assets/jobs.json`. Each catalog company receives a demo employer account formatted as `<slug>@example.test` (e.g., `google@example.test`) using the same local demo password.

## Running Unit Tests

Run the required unit-test suite non-interactively (exits nonzero on failure):

```sh
python -m pytest tests/unit -q
```

Inside the Docker container:

```sh
docker exec matchwork python -m pytest tests/unit -q
```

Additional verification commands (detailed in [INSTALL.md](INSTALL.md#running-unit-tests)):

- **Full Python suite (unit + synchronized booking race):** `python -m pytest -q` (or offline in Docker: `docker run --rm --network none matchwork python -m pytest -q`)
- **Frontend JavaScript units (Node.js 24):** `npm test`
- **Combined Python, JS, API-to-frontend parity, and concurrency suite:** `python tests/run_units.py --include-concurrency`

Continuous integration in [.github/workflows/tests.yml](.github/workflows/tests.yml) automatically verifies frontend units, API-to-frontend matching parity, Docker build, offline container tests, seeded browser acceptance checks, and live HTTP booking concurrency on every push and pull request.

## Requirement–Test Mapping

All requirement IDs refer to [final_project_spec/REQUIREMENTS.md](final_project_spec/REQUIREMENTS.md). Python test files reside under `tests/unit/` unless a full path is shown.

| Requirement ID | Behavior Verified | Implementation File(s) | Unit Tests / Verification Evidence |
|---|---|---|---|
| FP-ARCH-1 | Browser UI, server-side rules, persistent relational storage | `recruiting/__init__.py`, `recruiting/pages.py`, `recruiting/api.py`, `recruiting/db.py`, `Dockerfile` | `test_api.py::test_sign_in_page_and_static_files_are_served`; `test_api.py::test_candidate_and_employer_api_workflow`; `test_web.py::test_candidate_and_employer_api_browser_workflow`; `test_audit_fixes.py::test_deeply_nested_json_is_a_client_error`; clean Docker build and volume persistence check |
| FP-AUTH-1 | Two roles, unique email, register, log in, log out | `recruiting/accounts.py`, `recruiting/auth.py`, `recruiting/api.py`, `login.html` | `test_auth.py::test_registration_login_and_salted_hashes`; `test_auth.py::test_duplicate_and_invalid_login`; `test_auth.py::test_invalid_registration`; `test_web.py::test_registration_and_session_lifecycle`; `test_api.py::test_api_login_role_and_logout`; `test_api.py::test_api_register_starts_a_session`; `test_entry_boundaries.py::test_register_and_login_reject_roles_without_writes`; `test_entry_boundaries.py::test_credentials_type_length_and_email_boundaries`; `test_entry_boundaries.py::test_rotated_and_expired_sessions_cannot_be_reused`; `test_regressions.py::test_non_ascii_login_is_rejected_without_crashing` |
| FP-AUTH-2 | Salted password hashing; no credential secrets in responses or UI | `recruiting/accounts.py`, `recruiting/api.py`, `recruiting/present.py` | `test_auth.py::test_registration_login_and_salted_hashes`; `test_api.py::test_api_register_starts_a_session` |
| FP-AUTH-3 | Server-side session, role, and ownership enforcement (`401`/`403`/`404`) | `recruiting/accounts.py`, `recruiting/auth.py`, `recruiting/api.py`, `recruiting/jobs.py`, `recruiting/scheduling.py` | `test_web.py::test_auth_errors_and_role_boundaries`; `test_workflows.py::test_wrong_roles_ownership_and_missing_objects`; `test_round2_contracts.py::test_role_owner_matrix_with_direct_requests`; `test_web.py::test_other_employer_cannot_manage_a_job`; `test_regressions.py::test_oversized_path_id_is_not_found`; `test_regressions.py::test_forbidden_scheduling_requests_are_403_before_bad_input`; `test_security.py::test_csrf_token_rotates_after_login`; `test_security.py::test_account_creation_and_login_require_csrf`; `test_security.py::test_bodyless_writes_require_this_sessions_csrf_token` |
| FP-CAN-1 | Candidate self-profile, skills, and owner-only private raw-text resume | `recruiting/accounts.py`, `recruiting/api.py`, `candidate/profile.html` | `test_auth.py::test_profile_skills_and_private_resume`; `test_web.py::test_direct_resume_requires_candidate_ownership`; `test_web.py::test_direct_resume_returns_404_when_owners_profile_is_missing`; `test_web.py::test_profile_edit_preserves_resume_saved_since_profile_was_read`; `test_web.py::test_resume_stays_private_and_user_text_is_json`; `test_audit_fixes.py::test_work_preferences_are_saved_and_validated`; `test_audit_fixes.py::test_application_history_and_resume_dates_are_real`; `test_round2_contracts.py::test_failed_writes_leave_all_related_and_unrelated_rows`; `test_regressions.py::test_nul_text_is_rejected_without_partial_changes` |
| FP-CAN-2 | All current jobs shown with match score, title, company, skills, and description | `recruiting/jobs.py`, `recruiting/present.py`, `candidate/dashboard.html`, `shared/match.js` | `test_workflows.py::test_recommendations_fields_all_jobs_and_tie_breakers`; `test_api.py::test_candidate_and_employer_api_workflow`; `test_round2_contracts.py::test_both_views_recompute_oracle_and_stable_ties`; `test_authoritative_matching.py::test_preview_is_read_only_and_uses_the_course_formula` |
| FP-CAN-3 | Apply once per job (`Pending`), duplicate rejection, owner-only application visibility | `recruiting/jobs.py`, `recruiting/api.py`, `candidate/applications.html` | `test_workflows.py::test_applications_pending_duplicate_owner_and_statuses`; `test_web.py::test_malformed_booking_and_other_application_access`; `test_audit_fixes.py::test_legacy_application_history_does_not_invent_dates`; `test_audit_fixes.py::test_application_history_and_resume_dates_are_real`; `test_round2_contracts.py::test_json_resource_id_does_not_coerce_or_crash` |
| FP-EMP-1 | View and edit the employer's company profile | `recruiting/accounts.py`, `recruiting/api.py`, `recruiter/company.html` | `test_auth.py::test_company_profile`; `test_api.py::test_api_register_starts_a_session`; `test_round2_contracts.py::test_same_name_companies_remain_distinct_in_candidate_api` |
| FP-EMP-2 | Job posting CRUD, validation, cross-owner `403`, and `409` on dependent deletion | `recruiting/jobs.py`, `recruiting/api.py`, `recruiter/jobs.html` | `test_workflows.py::test_job_crud_validation_and_dependent_deletion`; `test_workflows.py::test_wrong_roles_ownership_and_missing_objects`; `test_web.py::test_other_employer_cannot_manage_a_job`; `test_api.py::test_invalid_job_create_and_edit_leave_listing_unchanged`; `test_scheduling.py::test_slot_ownership_and_job_dependency`; `test_acceptance_regressions.py::test_rejected_job_creation_preserves_database`; `test_acceptance_regressions.py::test_rejected_job_edit_preserves_all_fields`; `test_round2_contracts.py::test_failed_writes_leave_all_related_and_unrelated_rows`; `test_audit_fixes.py::test_job_cards_say_whether_a_location_was_entered`; `test_audit_fixes.py::test_page_scripts_show_server_scores_real_days_and_real_blockers` |
| FP-EMP-3 | Ranked applicants per owned job and owner-only status transitions | `recruiting/jobs.py`, `recruiting/api.py`, `recruiter/applicants.html` | `test_workflows.py::test_applicants_fields_and_both_tie_breakers`; `test_workflows.py::test_applications_pending_duplicate_owner_and_statuses`; `test_scheduling.py::test_booking_visible_preserved_and_deletion_rejected`; `test_authoritative_matching.py::test_status_response_keeps_score_and_rank`; `test_authoritative_matching.py::test_preview_and_ranked_results_keep_role_and_owner_boundaries`; `test_round2_contracts.py::test_both_views_recompute_oracle_and_stable_ties`; `test_audit_fixes.py::test_api_sends_the_server_match_score_to_both_portals` |
| FP-MATCH-1 | Deterministic skill-overlap score, normalization, flooring, tie-breakers, and cross-portal parity | `recruiting/matching.py`, `recruiting/jobs.py`, `recruiting/api.py`, `recruiting/present.py`, `shared/match.js` | `test_matching.py::test_score_examples_normalization_and_floor`; `test_matching.py::test_skill_normalization`; `test_workflows.py::test_recommendations_fields_all_jobs_and_tie_breakers`; `test_workflows.py::test_applicants_fields_and_both_tie_breakers`; `test_round2_contracts.py::test_independent_golden_scores`; `test_round2_contracts.py::test_seeded_score_oracle_and_metamorphic_relations`; `test_round2_contracts.py::test_both_views_recompute_oracle_and_stable_ties`; `test_authoritative_matching.py::test_unicode_scores_and_order_flow_through_real_api`; `test_authoritative_matching.py::test_api_title_ties_and_large_ids_are_authoritative`; `test_entry_boundaries.py::test_unicode_edge_whitespace_persists_and_matches_both_services`; `test_audit_fixes.py::test_api_sends_the_server_match_score_to_both_portals`; `test_audit_fixes.py::test_match_js_normalizes_exactly_like_python`; `test_seed.py::test_seed_is_repeatable_and_covers_requirements`; `tests/frontend/matching.test.cjs`; `tests/frontend/server.test.cjs`; `tests/acceptance/matching_parity.py`; `tests/browser/authoritative.cjs` |
| FP-MATCH-2 | Optional AI enhancement | N/A | N/A |
| FP-SCHED-1 | Future 30-minute availability slots with explicit timezones; booked slots protected | `recruiting/scheduling.py`, `recruiting/api.py`, `recruiter/interviews.html` | `test_scheduling.py::test_create_slot_timezone_and_delete`; `test_scheduling.py::test_invalid_slots`; `test_scheduling.py::test_slot_ownership_and_job_dependency`; `test_scheduling.py::test_booking_visible_preserved_and_deletion_rejected`; `test_api.py::test_slot_api_requires_explicit_timezone_and_preserves_far_future_slot`; `test_regressions.py::test_interview_calendar_preserves_selected_day_after_last_slot_is_deleted`; `test_regressions.py::test_slot_requires_a_renderable_utc_time`; `test_acceptance_regressions.py::test_slot_api_requires_explicit_timezone`; `test_acceptance_regressions.py::test_unrenderable_slot_is_rejected_without_server_error`; `test_round2_contracts.py::test_time_boundaries_offsets_and_failed_state`; `test_round2_contracts.py::test_booked_slot_is_redacted_and_unavailable_to_other_candidate`; `test_entry_boundaries.py::test_generated_future_slots_and_offsets_have_exact_utc` |
| FP-SCHED-2 | Full booking eligibility checks, mutual visibility, and preservation after status changes | `recruiting/scheduling.py`, `recruiting/api.py`, `recruiting/present.py`, `candidate/interviews.html` | `test_scheduling.py::test_ineligible_bookings_leave_no_partial_changes`; `test_scheduling.py::test_same_employer_cross_job_and_one_booking_per_application`; `test_scheduling.py::test_booking_visible_preserved_and_deletion_rejected`; `test_scheduling.py::test_booking_checks_application_eligibility_before_reading_slot`; `test_scheduling.py::test_expired_slot_does_not_report_booking_state`; `test_api.py::test_candidate_schedule_contains_only_own_bookings_and_eligible_open_slots`; `test_api.py::test_candidate_bootstrap_distinguishes_same_name_employers`; `test_round2_contracts.py::test_booking_state_machine_and_exact_future_boundary`; `test_entry_boundaries.py::test_seeded_application_booking_operation_model` |
| FP-SCHED-3 | Database-atomic booking; concurrent race yields one booking and one `409` (`Slot already booked`) | `recruiting/scheduling.py`, `recruiting/db.py`, `recruiting/migrations/001_initial.sql` | `test_scheduling.py::test_booking_conflict_contract`; `test_round2_contracts.py::test_storage_contention_is_distinct_and_transaction_recovers`; `tests/integration/test_concurrency.py::test_two_candidates_race_for_one_slot` |
| FP-SEC-1 | Direct-request authorization boundaries across resumes, applications, jobs, applicants, and bookings | `recruiting/accounts.py`, `recruiting/api.py`, `recruiting/jobs.py`, `recruiting/scheduling.py` | `test_web.py::test_direct_resume_requires_candidate_ownership`; `test_web.py::test_malformed_booking_and_other_application_access`; `test_web.py::test_other_employer_cannot_manage_a_job`; `test_auth.py::test_profile_skills_and_private_resume`; `test_workflows.py::test_wrong_roles_ownership_and_missing_objects`; `test_scheduling.py::test_ineligible_bookings_leave_no_partial_changes`; `test_scheduling.py::test_booking_checks_application_eligibility_before_reading_slot`; `test_round2_contracts.py::test_role_owner_matrix_with_direct_requests`; `test_regressions.py::test_forbidden_scheduling_requests_are_403_before_bad_input`; `test_api.py::test_candidate_schedule_contains_only_own_bookings_and_eligible_open_slots`; `test_security.py::test_bodyless_writes_require_this_sessions_csrf_token`; `test_audit_fixes.py::test_body_record_ids_must_be_whole_numbers` |
| FP-SEC-2 | Parameterized SQL queries keeping metacharacters bound as data | `recruiting/accounts.py`, `recruiting/jobs.py`, `recruiting/scheduling.py` | `test_security.py::test_sql_metacharacters_remain_bound_values` |
| FP-SEC-3 | HTML escaping of user-controlled text against XSS | `shared/html.js`, `candidate/assets/matchwork.js`, `recruiter/assets/recruiter.js`, `recruiting/__init__.py` | `test_security.py::test_matchwork_renders_script_text_as_escaped_html`; `test_web.py::test_resume_stays_private_and_user_text_is_json`; `tests/frontend/html.test.cjs`; `tests/browser/acceptance.cjs` |
| FP-SEC-4 | No committed secrets or personal data; isolated test databases and fixtures | `.env.example`, `.gitignore`, `.dockerignore`, `tests/conftest.py` | Per-test temporary SQLite fixture in `tests/conftest.py`; full Python suite verified inside Docker with `--network none` |
| FP-PROC-1 | Living specification aligned with the submitted codebase | `SPEC.md`, `README.md` | Schema, route permissions, matching rules, and booking transaction audited against source |
| FP-DOC-1 | Reproducible setup, migrations, seed, startup, and Docker instructions | `INSTALL.md`, `Dockerfile` | Clean Docker build, container startup, migrations, seed, and test execution verified against `INSTALL.md` |
| FP-DOC-2 | Complete README with overview, demo accounts, test command, and requirement mapping | `README.md` | Every `FP-*` ID in `final_project_spec/REQUIREMENTS.md` mapped above with implementation and test evidence |
| FP-DOC-3 | Single-command deterministic local demo reset and seed | `recruiting/seed.py` | `test_seed.py::test_seed_is_repeatable_and_covers_requirements`; `test_seed.py::test_reset_invalidates_existing_sessions_and_requires_confirmation`; `test_audit_fixes.py::test_seeded_interviews_are_in_pacific_business_hours` |
| FP-TEST-1 | Non-interactive student-written unit suite covering every functional requirement | `tests/unit/`, `.github/workflows/tests.yml` | `python -m pytest tests/unit -q` (and `python tests/run_units.py --include-concurrency` for combined JS, parity, and concurrency checks) |
| FP-SUB-1 | Permanent public `main` commit URL building and running from its own `Dockerfile` | `Dockerfile`, `INSTALL.md`, `.github/ISSUE_TEMPLATE/audit_bug_report.yml`, `.github/labels.yml` | Verified via Docker build/start/seed/test workflow and `.github/workflows/tests.yml`; final course submission links to the graded commit SHA on public `main` |

## Document Index

| Document | Contents |
|---|---|
| [INSTALL.md](INSTALL.md) | Prerequisites, local setup, Docker build/run, migrations, seeding, tests, and troubleshooting |
| [SPEC.md](SPEC.md) | Architecture, data model, authentication/authorization, API routes, matching contract, and booking transaction |
| [Course Project Overview](final_project_spec/README.md) | Course scope, grading rubric, and milestones |
| [Course Requirements](final_project_spec/REQUIREMENTS.md) | Normative `FP-*` product and submission requirements |
| [Docker Guidelines](final_project_spec/DOCKER.md) | Course Docker build and audit workflow |
| [Peer Review Guide](final_project_spec/PEER_REVIEW.md) | Audit scope, reporting rules, and safety boundaries |
| [Audit Issue Form](.github/ISSUE_TEMPLATE/audit_bug_report.yml) & [Labels](.github/labels.yml) | Repository templates for course peer review |

## Known Limitations

- **Saved jobs** are stored per account in browser `sessionStorage` and cleared on logout.
- **Closed postings** remain visible in job lists; attempts to apply return `409`.
- **Slot attachment:** newly created employer slots attach to the employer's oldest job by ID, and any eligible `Interviewing` application for that employer may book them. Jobs with existing applications or slots cannot be deleted.
- **Calendar display:** the candidate picker displays only dates with eligible open slots; the employer calendar shows the next 14 days plus any later dates with slots and preserves a valid selected date after its last slot is removed.
- **Bookings** cannot be cancelled or rescheduled from the UI and remain attached to the application after later status changes.
- **Out of scope:** PDF resume parsing/uploads, account recovery, email verification, in-app messaging, external calendar sync, and email/push notifications.
- **Concurrency model:** SQLite serializes concurrent writers, which fits local execution and course-scale datasets.
