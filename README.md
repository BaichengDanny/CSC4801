# Matchwork

A local recruiting platform where candidates discover roles by skill match,
employers manage applicants, and interview slots are reserved safely under
concurrent use. Built for CSC4801 with Flask and SQLite.

The browser UI is the static Matchwork site: sign-in and account creation on
one page, a candidate dashboard, and an employer dashboard. Flask serves those
pages and a JSON API. The earlier Jinja screens have been removed.

## Quick start

See [INSTALL.md](INSTALL.md) for Python and Docker setup, migrations, seed/reset,
configuration, tests, and browser smoke steps. With Python 3.12 and dependencies
installed:

```sh
python -m flask --app recruiting init-db
python -m flask --app recruiting seed --yes
python -m recruiting
```

Open http://127.0.0.1:8080. Run the required unit suite with
`python -m pytest tests/unit -q`, or the full suite including the synchronized
booking race with `python -m pytest -q`.

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

The seed also loads the 39 Matchwork catalog postings from `candidate/assets/jobs.json`. Each of those companies has its own demo employer. The email is the company name in lowercase, with spaces turned into hyphens, at `@example.test` — for example `google@example.test`. The password is the same demo password.

## Architecture

- `recruiting/__init__.py`: application factory, security headers, JSON errors.
- `auth.py`, `api.py`, `pages.py`: sessions, the JSON API, and the Matchwork pages.
- `accounts.py`, `jobs.py`, `scheduling.py`: authorization and business services.
- `matching.py` and `shared/match.js`: the same deterministic skill-overlap score.
- `db.py`, `migrations/`: SQLite connections, transactions, versioned schema.
- `candidate/`, `recruiter/`, `shared/`, `login.html`: the pages a browser actually loads.
- `seed.py`: explicit synthetic reset/seed CLI, including the Matchwork job catalog.
- `tests/unit/`: required business and HTTP-boundary tests with isolated databases.
- `tests/integration/`: two independent SQLite connections racing for one slot.

Booking uses `BEGIN IMMEDIATE` and unique constraints on both slot and application.
Resume text is private to its owner and never contributes to matching scores.
Times are stored in UTC and displayed in Pacific Time (`America/Los_Angeles`).
Server sessions are revocable on logout. Creating an account is on the sign-in
page; there is no password-recovery flow.

## Requirement–test mapping

Tests listed below are team-owned behavior assertions, replacing starter `pass`
functions. Paths below are relative to `tests/unit/` unless stated otherwise.
Non-functional rows identify verification steps; external course actions remain
team responsibilities, not claims of automated completion.

| Requirement | Implementation | Named tests / verification evidence |
|---|---|---|
| FP-ARCH-1 | `recruiting/__init__.py`, `db.py`, `pages.py`, `api.py`, Dockerfile | `test_web.py::test_candidate_and_employer_api_browser_workflow`; `test_api.py::test_sign_in_page_and_static_files_are_served`; clean Docker workflow in INSTALL.md |
| FP-AUTH-1 | `accounts.py`, `auth.py`, `api.py`, `login.html` | `test_auth.py::test_registration_login_and_salted_hashes`, `test_invalid_registration`, `test_duplicate_and_invalid_login`; `test_web.py::test_registration_and_session_lifecycle`; `test_api.py::test_api_login_role_and_logout`, `test_api_register_starts_a_session` |
| FP-AUTH-2 | `accounts.py` | `test_auth.py::test_registration_login_and_salted_hashes` |
| FP-AUTH-3 | `accounts.py`, `jobs.py`, `scheduling.py`, `auth.py` | `test_workflows.py::test_wrong_roles_ownership_and_missing_objects`; `test_web.py::test_auth_errors_and_role_boundaries`, `test_other_employer_cannot_manage_a_job`; `test_regressions.py::test_oversized_path_id_is_not_found`, `test_forbidden_scheduling_requests_are_403_before_bad_input` |
| FP-CAN-1 | `accounts.py`, `api.py`, `candidate/profile.html` | `test_auth.py::test_profile_skills_and_private_resume`; `test_web.py::test_resume_stays_private_and_user_text_is_json` |
| FP-CAN-2 | `jobs.py`, `candidate/dashboard.html` | `test_workflows.py::test_recommendations_fields_all_jobs_and_tie_breakers` |
| FP-CAN-3 | `jobs.py`, `candidate/applications.html` | `test_workflows.py::test_applications_pending_duplicate_owner_and_statuses`; `test_web.py::test_malformed_booking_and_other_application_access` |
| FP-EMP-1 | `accounts.py`, `recruiter/` company screens | `test_auth.py::test_company_profile` |
| FP-EMP-2 | `jobs.py`, `api.py`, recruiter job screens | `test_workflows.py::test_job_crud_validation_and_dependent_deletion`, `test_wrong_roles_ownership_and_missing_objects`; `test_scheduling.py::test_slot_ownership_and_job_dependency`; `test_api.py::test_invalid_job_create_and_edit_leave_listing_unchanged` |
| FP-EMP-3 | `jobs.py`, `recruiter/applicants.html` | `test_workflows.py::test_applicants_fields_and_both_tie_breakers`, `test_applications_pending_duplicate_owner_and_statuses`; `test_scheduling.py::test_booking_visible_preserved_and_deletion_rejected` |
| FP-MATCH-1 | `matching.py`, `shared/match.js`, `jobs.py` | `test_matching.py::test_score_examples_normalization_and_floor`, `test_skill_normalization`; `test_workflows.py::test_recommendations_fields_all_jobs_and_tie_breakers`, `test_applicants_fields_and_both_tie_breakers` |
| FP-MATCH-2 | Not implemented | N/A — optional AI enhancement |
| FP-SCHED-1 | `scheduling.py`, `api.py`, `recruiter/interviews.html` | `test_scheduling.py::test_create_slot_timezone_and_delete`, `test_invalid_slots`; `test_regressions.py::test_slot_requires_a_renderable_utc_time`; `test_booking_visible_preserved_and_deletion_rejected`, `test_slot_ownership_and_job_dependency`; `test_api.py::test_slot_api_requires_explicit_timezone_and_preserves_far_future_slot` |
| FP-SCHED-2 | `scheduling.py`, `present.py`, `candidate/assets/matchwork.js` | `test_scheduling.py::test_booking_visible_preserved_and_deletion_rejected`, `test_ineligible_bookings_leave_no_partial_changes`, `test_same_employer_cross_job_and_one_booking_per_application`; `test_api.py::test_candidate_bootstrap_distinguishes_same_name_employers` |
| FP-SCHED-3 | `db.py`, `scheduling.py`, migration constraints | `test_scheduling.py::test_booking_conflict_contract`; `tests/integration/test_concurrency.py::test_two_candidates_race_for_one_slot` |
| FP-SEC-1 | Account/job/scheduling ownership checks | `test_auth.py::test_profile_skills_and_private_resume`; `test_workflows.py::test_wrong_roles_ownership_and_missing_objects`; `test_scheduling.py::test_ineligible_bookings_leave_no_partial_changes`; direct-request tests in `test_web.py` |
| FP-SEC-2 | Parameterized service queries | `test_security.py::test_sql_metacharacters_remain_bound_values` records bound login parameters and verifies malicious job text persists as data |
| FP-SEC-3 | JSON responses, page escaping, CSP | `test_web.py::test_resume_stays_private_and_user_text_is_json` returns script text as JSON data and keeps it out of another user's bootstrap and the static page |
| FP-SEC-4 | `tests/conftest.py`, `.env.example`, ignore files | Temporary database per test; no external-service test code; source/secret review before submission |
| FP-PROC-1 | SPEC.md and this mapping | Maintain specification alongside behavior; team members must review and explain submitted code |
| FP-DOC-1 | INSTALL.md, Dockerfile, CLI | Execute the documented clean-checkout build/start/migrate/seed/test flow |
| FP-DOC-2 | README.md | This table covers every normative requirement ID; document index and demo credentials above/below |
| FP-DOC-3 | `seed.py` | `test_seed.py::test_seed_is_repeatable_and_covers_requirements`, `test_reset_invalidates_existing_sessions_and_requires_confirmation` |
| FP-TEST-1 | `tests/`, `.github/workflows/tests.yml` | `python -m pytest tests/unit -q`; full suite also includes the real concurrency check |
| FP-SUB-1 | Dockerfile, INSTALL.md, GitHub audit templates | Clean container verification; team must publish repository and submit the exact permanent `main` commit URL before the course deadline |

## Documents and team handoff

- [AGENTS.md](AGENTS.md): working rules, milestones, current verification status.
- [Verification record](docs/verification.md): local tests, Docker checks, browser checks, and review fixes.
- [SPEC.md](SPEC.md): architecture, data model, routes, matching, scheduling, security.
- [INSTALL.md](INSTALL.md): setup, commands, reset, and smoke checks.
- [Implementation plan](docs/superpowers/plans/2026-11-14-recruiting-platform.md).
- [Course specification](final_project_spec/README.md) and [peer-audit rules](final_project_spec/PEER_REVIEW.md).
- `.github/ISSUE_TEMPLATE/audit_bug_report.yml` and `.github/labels.yml`: supplied
  audit form and label definitions. Import labels into the target repository as
  part of the team's authorized GitHub setup.

Team roster and contribution attribution must be completed by the students before
submission. Every member must understand and be able to modify the implementation.

## Known limitations

This version targets local/course use. It has no optional AI, PDF upload, email
verification, password recovery, notifications, booking cancellation, or hosted
deployment. SQLite serializes writers and is intended for small workloads.
The employer calendar shows the next 14 days plus farther dates with future slots.
Empty required skills intentionally score 100 under the course formula.
Employers cannot read raw resumes. Saved jobs live in the browser's
session storage. A new employer slot is attached to that employer's oldest job.
Closed jobs stay in the candidate list, and a new application to one is rejected.
The month grid on the interview page is a display of days that already have
slots; booking uses those existing slots.

The repository's public visibility, imported GitHub labels, hosted CI results,
permanent graded commit, and course submission require separate team actions.
