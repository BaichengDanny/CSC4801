# Matchwork

## Project Overview

Matchwork is a locally runnable recruiting platform built for CSC4801. Candidates discover jobs by skill match, employers manage their postings and applicants, and both sides share an interview scheduling workflow.

The application uses Flask, SQLite, and a browser interface built with HTML, CSS, and JavaScript. Flask serves both the pages and the JSON API. No cloud account, paid API, or Node.js build step is needed to run the application. The whole site runs on your own computer from one Docker image.

| Role | What you can do |
|---|---|
| `Candidate` | Register and sign in, maintain a skills profile and a private plain-text resume, browse ranked jobs, save jobs in the browser, apply, track application status, and book an offered interview. |
| `Employer` | Maintain a company profile, create and edit postings, close or reopen jobs, delete jobs without dependents, review ranked applicants, change application status, and manage 30-minute interview slots. |

Accounts have exactly one of the two roles: `Candidate` or `Employer`. Both roles use the same [sign-in page](http://127.0.0.1:8080/sign-in).

## Team Members

| Name | Student ID |
|---|---|
| Baicheng Chen | 123090015 |
| Yuyang Qin | 122090433 |
| Xuanxue Zheng | 123090886 |

## Architecture Summary

Flask serves the HTML, CSS, and JavaScript pages and exposes a JSON API under `/api`. The server checks permissions and enforces application and booking rules. SQLite stores accounts, skills, jobs, applications, and bookings in a persistent file.

Waitress serves the app. The root `Dockerfile` packages the server and test runtime in one image named `matchwork`. Local startup uses no Node.js build step, hosted database, or paid service.

| Location | Responsibility |
|---|---|
| `login.html`, `candidate/`, `recruiter/`, `shared/` | Sign-in, the two portals, and shared browser helpers. |
| `recruiting/__init__.py`, `recruiting/pages.py`, `recruiting/api.py`, `recruiting/present.py` | App setup, page delivery, JSON endpoints, and response fields. |
| `recruiting/auth.py`, `recruiting/accounts.py` | Session and CSRF checks, account management, and profile permissions. |
| `recruiting/jobs.py`, `recruiting/matching.py`, `recruiting/scheduling.py` | Job and application rules, shared scoring, and booking. |
| `recruiting/db.py`, `recruiting/migrations/`, `recruiting/seed.py` | SQLite transactions, schema versions, and demo reset. |
| `tests/unit/`, `tests/frontend/`, `tests/integration/` | Service and API units, JavaScript checks, and a two-connection booking race. |

Both portals use the scores and order returned by the Python matching service. It measures the percentage of required skills a candidate has, rounds down, and uses title or display name and stable IDs to break ties. Skills are normalized before scoring. The service does not read resumes for matching. Saved skill and job edits return fresh scores. Other open pages refresh on focus or during periodic checks while they are visible.

Booking uses a SQLite write transaction and unique constraints on the slot and application IDs. See [SPEC.md](SPEC.md) for the data model and rules.

## Quick Start

### Docker

From the repository root, build the image and start a container with a named volume for SQLite.

```sh
docker build -t matchwork .
docker volume create matchwork-data
docker run -d --name matchwork -p 127.0.0.1:8080:8080 \
  -v matchwork-data:/app/data matchwork
```

Startup applies pending migrations. Once the [health endpoint](http://127.0.0.1:8080/health) returns `{"status":"ok"}`, run the seed command on a fresh or disposable demo volume.

```sh
docker exec matchwork python -m flask --app recruiting seed --yes
```

Open [Matchwork](http://127.0.0.1:8080/sign-in) and sign in with a demo account. Reusing the volume preserves the database when the container is recreated. Running the seed again resets that database and invalidates existing sessions.

### Local Python

Activate a Python 3.12 virtual environment first. See [Dependency Installation](INSTALL.md#dependency-installation) for macOS, Linux, and Windows commands.

```sh
python -m pip install -r requirements.txt
python -m flask --app recruiting init-db
python -m flask --app recruiting seed --yes
python -m recruiting
```

The default local database is `instance/recruiting.sqlite3`. [INSTALL.md](INSTALL.md) covers environment settings, migrations, tests, and troubleshooting.

## Demo Accounts

These synthetic accounts all use the local demo password `DemoPass123!`.

| Email | Role | Seeded data |
|---|---|---|
| `alex@example.test` | Candidate | Python and SQL. Backend Engineer is `Interviewing`; Data Analyst is `Pending`. |
| `blair@example.test` | Candidate | Python. Backend Engineer is `Interviewing`; Systems Engineer is `Rejected`. |
| `casey@example.test` | Candidate | Rust. Graduate Programme is `Accepted`. |
| `north@example.test` | Employer | Northstar Studio owns Backend Engineer and Data Analyst and has three open slots. |
| `field@example.test` | Employer | Fieldwork Labs owns Systems Engineer and Graduate Programme and has one open slot. |

Backend Engineer requires Python and SQL, so Alex scores 100, Blair 50, and Casey 0. Graduate Programme has an empty required-skills list and scores 100 for each candidate. Alex and Blair can book the same Northstar slot until one of them reserves it.

The seed also loads 39 catalog jobs from 26 companies in `candidate/assets/jobs.json`. Each catalog company gets a demo employer account. Its email is the lowercase company name with runs of non-alphanumeric characters replaced by hyphens, followed by `@example.test`. For example, `google@example.test` uses the same demo password.

## Running Unit Tests

```sh
python -m pytest tests/unit -q
```

The unit suite runs without prompts and exits with a nonzero status on failure. It needs Python 3.12, the pinned dependencies, and Node.js for the renderer checks. In Docker, use `docker exec matchwork python -m pytest tests/unit -q`.

Run `python -m pytest -q` to include the synchronized booking race. `python tests/run_units.py --include-concurrency` also runs the JavaScript units and the API-to-frontend matching checks. On `35773f9`, 138 Python tests passed locally and in Docker. The retest also passed 15 JavaScript units, 1,243 matching cases, eight ordering groups, and 22 browser checks on both Chrome and Chromium. Setup and acceptance commands are in [INSTALL.md](INSTALL.md#running-unit-tests).

## Requirement–Test Mapping

Python test files in the table are under `tests/unit/` unless a full path is shown. The requirement IDs refer to the [course requirements](final_project_spec/REQUIREMENTS.md).

| Requirement ID | Behavior to verify | Implementation file(s) | Unit test(s) / verification evidence |
|---|---|---|---|
| FP-ARCH-1 | Browser UI, server-side rules, persistent relational storage | `recruiting/pages.py`, `recruiting/api.py`, `recruiting/db.py`, `Dockerfile`, `recruiting/__init__.py` | `test_api.py::test_sign_in_page_and_static_files_are_served`; `test_web.py::test_candidate_and_employer_api_browser_workflow`; clean Docker build and volume persistence check; `test_api.py::test_candidate_and_employer_api_workflow`; `test_audit_fixes.py::test_deeply_nested_json_is_a_client_error` |
| FP-AUTH-1 | Two roles, unique email, register, log in and out | `recruiting/accounts.py`, `recruiting/auth.py`, `login.html`, `recruiting/api.py` | `test_web.py::test_registration_and_session_lifecycle`; `test_auth.py::test_duplicate_and_invalid_login`; `test_entry_boundaries.py::test_register_and_login_reject_roles_without_writes`; `test_auth.py::test_registration_login_and_salted_hashes`; `test_auth.py::test_invalid_registration`; `test_api.py::test_api_login_role_and_logout`; `test_api.py::test_api_register_starts_a_session`; `test_entry_boundaries.py::test_credentials_type_length_and_email_boundaries`; `test_entry_boundaries.py::test_rotated_and_expired_sessions_cannot_be_reused`; `test_regressions.py::test_non_ascii_login_is_rejected_without_crashing` |
| FP-AUTH-2 | Store salted password hashes and keep credentials private | `recruiting/accounts.py`, `recruiting/api.py`, `recruiting/present.py` | `test_auth.py::test_registration_login_and_salted_hashes`; `test_api.py::test_api_register_starts_a_session` |
| FP-AUTH-3 | Server checks session, role, and ownership with 401, 403, and 404 responses | `recruiting/accounts.py`, `recruiting/auth.py`, `recruiting/api.py`, `recruiting/jobs.py`, `recruiting/scheduling.py` | `test_web.py::test_auth_errors_and_role_boundaries`; `test_workflows.py::test_wrong_roles_ownership_and_missing_objects`; `test_round2_contracts.py::test_role_owner_matrix_with_direct_requests`; `test_web.py::test_other_employer_cannot_manage_a_job`; `test_regressions.py::test_oversized_path_id_is_not_found`; `test_regressions.py::test_forbidden_scheduling_requests_are_403_before_bad_input`; `test_security.py::test_csrf_token_rotates_after_login`; `test_security.py::test_account_creation_and_login_require_csrf`; `test_security.py::test_bodyless_writes_require_this_sessions_csrf_token` |
| FP-CAN-1 | Candidates edit their own profile and skills. Resume reads and writes are owner-only. | `recruiting/accounts.py`, `recruiting/api.py`, `candidate/profile.html` | `test_auth.py::test_profile_skills_and_private_resume`; `test_web.py::test_direct_resume_requires_candidate_ownership`; `test_web.py::test_profile_edit_preserves_resume_saved_since_profile_was_read`; `test_audit_fixes.py::test_work_preferences_are_saved_and_validated`; `test_web.py::test_resume_stays_private_and_user_text_is_json`; `test_round2_contracts.py::test_failed_writes_leave_all_related_and_unrelated_rows`; `test_web.py::test_direct_resume_returns_404_when_owners_profile_is_missing`; `test_regressions.py::test_nul_text_is_rejected_without_partial_changes`; `test_audit_fixes.py::test_application_history_and_resume_dates_are_real` |
| FP-CAN-2 | Show all current jobs with score, title, company, required skills, and description | `recruiting/jobs.py`, `recruiting/present.py`, `candidate/dashboard.html`, `shared/match.js` | `test_workflows.py::test_recommendations_fields_all_jobs_and_tie_breakers`; `test_api.py::test_candidate_and_employer_api_workflow`; `test_round2_contracts.py::test_both_views_recompute_oracle_and_stable_ties`; `test_authoritative_matching.py::test_preview_is_read_only_and_uses_the_course_formula` |
| FP-CAN-3 | Apply once per job. Each new application starts `Pending` and belongs to its candidate. | `recruiting/jobs.py`, `recruiting/api.py`, `candidate/applications.html` | `test_workflows.py::test_applications_pending_duplicate_owner_and_statuses`; `test_web.py::test_malformed_booking_and_other_application_access`; `test_audit_fixes.py::test_legacy_application_history_does_not_invent_dates`; `test_round2_contracts.py::test_json_resource_id_does_not_coerce_or_crash`; `test_audit_fixes.py::test_application_history_and_resume_dates_are_real` |
| FP-EMP-1 | View and edit the employer's company profile | `recruiting/accounts.py`, `recruiting/api.py`, `recruiter/company.html`, `recruiter/` | `test_auth.py::test_company_profile`; `test_round2_contracts.py::test_same_name_companies_remain_distinct_in_candidate_api`; `test_api.py::test_api_register_starts_a_session` |
| FP-EMP-2 | Manage owned jobs and reject invalid writes or deletion with dependents | `recruiting/jobs.py`, `recruiting/api.py`, `recruiter/jobs.html` | `test_workflows.py::test_job_crud_validation_and_dependent_deletion`; `test_web.py::test_other_employer_cannot_manage_a_job`; `test_api.py::test_invalid_job_create_and_edit_leave_listing_unchanged`; `test_scheduling.py::test_slot_ownership_and_job_dependency`; `test_audit_fixes.py::test_job_cards_say_whether_a_location_was_entered`; `test_workflows.py::test_wrong_roles_ownership_and_missing_objects`; `test_acceptance_regressions.py::test_rejected_job_creation_preserves_database`; `test_acceptance_regressions.py::test_rejected_job_edit_preserves_all_fields`; `test_round2_contracts.py::test_failed_writes_leave_all_related_and_unrelated_rows`; `test_audit_fixes.py::test_page_scripts_show_server_scores_real_days_and_real_blockers` |
| FP-EMP-3 | Rank owned applicants and show identity, skills, score, status, and booking. The owner controls status changes. | `recruiting/jobs.py`, `recruiting/api.py`, `recruiter/applicants.html` | `test_workflows.py::test_applicants_fields_and_both_tie_breakers`; `test_workflows.py::test_applications_pending_duplicate_owner_and_statuses`; `test_scheduling.py::test_booking_visible_preserved_and_deletion_rejected`; `test_authoritative_matching.py::test_status_response_keeps_score_and_rank`; `test_round2_contracts.py::test_both_views_recompute_oracle_and_stable_ties`; `test_authoritative_matching.py::test_preview_and_ranked_results_keep_role_and_owner_boundaries`; `test_audit_fixes.py::test_api_sends_the_server_match_score_to_both_portals` |
| FP-MATCH-1 | Verify four score examples, normalization, integer rounding, tie-breakers, and identical results in both portals | `recruiting/matching.py`, `recruiting/jobs.py`, `recruiting/api.py`, `shared/match.js`, `recruiting/present.py` | `test_matching.py::test_score_examples_normalization_and_floor`; `test_workflows.py::test_recommendations_fields_all_jobs_and_tie_breakers`; `test_workflows.py::test_applicants_fields_and_both_tie_breakers`; `test_round2_contracts.py::test_both_views_recompute_oracle_and_stable_ties`; `test_authoritative_matching.py::test_unicode_scores_and_order_flow_through_real_api`; `tests/acceptance/matching_parity.py`; `test_matching.py::test_skill_normalization`; `test_round2_contracts.py::test_independent_golden_scores`; `test_round2_contracts.py::test_seeded_score_oracle_and_metamorphic_relations`; `test_entry_boundaries.py::test_unicode_edge_whitespace_persists_and_matches_both_services`; `tests/frontend/matching.test.cjs`; `test_authoritative_matching.py::test_api_title_ties_and_large_ids_are_authoritative`; `tests/frontend/server.test.cjs`; `tests/browser/authoritative.cjs`; `test_seed.py::test_seed_is_repeatable_and_covers_requirements`; `test_audit_fixes.py::test_api_sends_the_server_match_score_to_both_portals`; `test_audit_fixes.py::test_match_js_normalizes_exactly_like_python`; `test_audit_fixes.py::test_page_scripts_show_server_scores_real_days_and_real_blockers` |
| FP-MATCH-2 | Optional AI enhancement | N/A | N/A |
| FP-SCHED-1 | Future 30-minute availability with explicit time zones. Booked slots stay unavailable and cannot be deleted. | `recruiting/scheduling.py`, `recruiting/api.py`, `recruiter/interviews.html` | `test_scheduling.py::test_create_slot_timezone_and_delete`; `test_scheduling.py::test_invalid_slots`; `test_scheduling.py::test_booking_visible_preserved_and_deletion_rejected`; `test_api.py::test_slot_api_requires_explicit_timezone_and_preserves_far_future_slot`; `test_regressions.py::test_interview_calendar_preserves_selected_day_after_last_slot_is_deleted`; `test_regressions.py::test_slot_requires_a_renderable_utc_time`; `test_scheduling.py::test_slot_ownership_and_job_dependency`; `test_acceptance_regressions.py::test_slot_api_requires_explicit_timezone`; `test_acceptance_regressions.py::test_unrenderable_slot_is_rejected_without_server_error`; `test_round2_contracts.py::test_time_boundaries_offsets_and_failed_state`; `test_round2_contracts.py::test_booked_slot_is_redacted_and_unavailable_to_other_candidate`; `test_entry_boundaries.py::test_generated_future_slots_and_offsets_have_exact_utc` |
| FP-SCHED-2 | Check all booking conditions, preserve bookings through status changes, and show them to both parties | `recruiting/scheduling.py`, `recruiting/api.py`, `candidate/interviews.html`, `recruiting/present.py` | `test_scheduling.py::test_ineligible_bookings_leave_no_partial_changes`; `test_scheduling.py::test_same_employer_cross_job_and_one_booking_per_application`; `test_scheduling.py::test_booking_visible_preserved_and_deletion_rejected`; `test_api.py::test_candidate_schedule_contains_only_own_bookings_and_eligible_open_slots`; `test_round2_contracts.py::test_booking_state_machine_and_exact_future_boundary`; `test_entry_boundaries.py::test_seeded_application_booking_operation_model`; `test_scheduling.py::test_booking_checks_application_eligibility_before_reading_slot`; `test_scheduling.py::test_expired_slot_does_not_report_booking_state`; `test_api.py::test_candidate_bootstrap_distinguishes_same_name_employers` |
| FP-SCHED-3 | A same-slot race creates one booking and returns 409 `Slot already booked` to the other candidate | `recruiting/scheduling.py`, `recruiting/db.py`, `recruiting/migrations/001_initial.sql` | `test_scheduling.py::test_booking_conflict_contract`; `test_round2_contracts.py::test_storage_contention_is_distinct_and_transaction_recovers`; `tests/integration/test_concurrency.py::test_two_candidates_race_for_one_slot` |
| FP-SEC-1 | Direct requests enforce resume, application, job, applicant, and booking ownership | `recruiting/accounts.py`, `recruiting/api.py`, `recruiting/jobs.py`, `recruiting/scheduling.py` | `test_web.py::test_direct_resume_requires_candidate_ownership`; `test_round2_contracts.py::test_role_owner_matrix_with_direct_requests`; `test_scheduling.py::test_booking_checks_application_eligibility_before_reading_slot`; `test_auth.py::test_profile_skills_and_private_resume`; `test_workflows.py::test_wrong_roles_ownership_and_missing_objects`; `test_scheduling.py::test_ineligible_bookings_leave_no_partial_changes`; `test_regressions.py::test_forbidden_scheduling_requests_are_403_before_bad_input`; `test_api.py::test_candidate_schedule_contains_only_own_bookings_and_eligible_open_slots`; `test_security.py::test_bodyless_writes_require_this_sessions_csrf_token`; `test_web.py::test_malformed_booking_and_other_application_access`; `test_web.py::test_other_employer_cannot_manage_a_job`; `test_audit_fixes.py::test_body_record_ids_must_be_whole_numbers` |
| FP-SEC-2 | SQL metacharacters stay bound as data | `recruiting/accounts.py`, `recruiting/jobs.py`, `recruiting/scheduling.py` | `test_security.py::test_sql_metacharacters_remain_bound_values` |
| FP-SEC-3 | Escape user-supplied text before rendering HTML | `shared/html.js`, `candidate/assets/matchwork.js`, `recruiter/assets/recruiter.js`, `recruiting/__init__.py` | `test_security.py::test_matchwork_renders_script_text_as_escaped_html`; `test_web.py::test_resume_stays_private_and_user_text_is_json`; `tests/frontend/html.test.cjs`; `tests/browser/acceptance.cjs` |
| FP-SEC-4 | Placeholder configuration, synthetic fixtures, and isolated databases | `.env.example`, `.gitignore`, `.dockerignore`, `tests/conftest.py` | Temporary SQLite fixture per test. The Python suite passed inside Docker with `--network none`.; `tests/conftest.py` |
| FP-PROC-1 | Keep the specification consistent with the implementation | `SPEC.md`, `README.md` | Check the schema, route permissions, matching, and booking transaction against the source. |
| FP-DOC-1 | Reproduce setup, migrations, seed, startup, and tests | `INSTALL.md`, `Dockerfile` | The clean Docker build, startup, migrations, seed, and tests passed at `35773f9`. |
| FP-DOC-2 | Provide demo accounts, setup links, and requirement coverage | `README.md` | Compare this mapping with the IDs in `final_project_spec/REQUIREMENTS.md`. |
| FP-DOC-3 | Reset and load repeatable demo data with one command | `recruiting/seed.py` | `test_seed.py::test_seed_is_repeatable_and_covers_requirements`; `test_seed.py::test_reset_invalidates_existing_sessions_and_requires_confirmation`; `test_audit_fixes.py::test_seeded_interviews_are_in_pacific_business_hours` |
| FP-TEST-1 | Run the required unit suite noninteractively with real service assertions | `tests/`, `.github/workflows/tests.yml`, `tests/unit/` | `python -m pytest tests/unit -q`; `python tests/run_units.py --include-concurrency` for the wider checks |
| FP-SUB-1 | Submit the exact public `main` commit that builds and runs from its Dockerfile | `Dockerfile`, `INSTALL.md`, `.github/ISSUE_TEMPLATE/audit_bug_report.yml`, `.github/labels.yml` | Docker was verified at `35773f9` on `platform-draft`. The course submission must link to the final commit on public `main`. |

## Document Index

| Document | Contents |
|---|---|
| [INSTALL.md](INSTALL.md) | Local setup, Docker, migrations, demo reset, and verification commands |
| [SPEC.md](SPEC.md) | Data model, permissions, API, matching, and the booking transaction |
| [Course project overview](final_project_spec/README.md) | Project scope, grading, and submission milestones |
| [Course requirements](final_project_spec/REQUIREMENTS.md) | Graded behavior and submission rules |
| [Docker rules](final_project_spec/DOCKER.md) | Course build and runtime requirements |
| [Peer review](final_project_spec/PEER_REVIEW.md) | Audit scope, reporting rules, and acceptable evidence |
| [Audit issue form](.github/ISSUE_TEMPLATE/audit_bug_report.yml) and [label definitions](.github/labels.yml) | Repository files for course peer review |

## Known Limitations

- Saved jobs are stored per account in the current browser tab and cleared at logout.
- Closed postings stay in the list. Attempts to apply return `409`.
- The employer's oldest job holds its new slots. Any eligible application to that employer may use those slots. Jobs with slots or applications cannot be deleted.
- The candidate picker shows only days with eligible open times. The employer calendar includes the next 14 days, later dates with slots, and a valid selected date after its last slot is removed.
- Booked slots cannot be cancelled or rescheduled through the UI. The slot remains on the application after a status change.
- Resume input is plain text. Account recovery, email verification, chat, calendar integration, and email or push delivery are outside this scope.
- SQLite allows one writer at a time. The app targets local use and course-sized datasets.
