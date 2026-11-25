# Local verification record

Verified on **2026-11-14**, Asia/Shanghai. Source is on the local
`codex/recruiting-platform` branch and remains uncommitted. This record does not
claim a published submission, a hosted CI run, or a graded commit.

## Automated checks

| Check | Result |
|---|---|
| Python 3.12.11: `.venv/bin/python -m pytest tests/unit -q` | 48 passed |
| Python 3.12.11: `.venv/bin/python -m pytest -q` | 49 passed |
| Final image: `docker run --rm common-ground-csc4801 python -m pytest -q` | 49 passed, no warnings |
| README requirement mapping | All 25 normative requirement IDs present |
| Local Markdown references | All referenced local documents resolve |
| Whitespace validation | `git diff --check` passes |

The optional integration test uses a synchronization barrier and two independent
SQLite connections. Exactly one candidate succeeds, the other receives
`409 / Slot already booked`, and one booking remains in the database.

Tests were written and observed failing before each implementation batch. The
starter `pass` functions have been replaced. A SQL binding test fixture was
corrected to reflect the documented lowercase login normalization; it still
asserts that the malicious value appears in bound parameters, never SQL text.

## Independent review and regressions

A separate read-only reviewer ran the then-current 42-test suite and examined the
implementation against the course requirements. The following findings were
reproduced with failing regressions and fixed in `tests/unit/test_regressions.py`:

- Oversized URL IDs now yield 404, including numeric paths longer than Python's
  integer-conversion limit. A bounded URL converter prevents database overflow.
- Non-ASCII CSRF values now yield 400 rather than raising a comparison exception.
- NUL-containing text fields now yield 400 and preserve the existing records.
- Offset timestamps that normalize outside the representable UTC range are
  rejected before a slot can be persisted.

The reviewer rated the last finding lower priority because normal browser inputs
cannot supply timezone offsets. It was addressed because the documented service
interface could otherwise persist a slot that crashes subsequent rendering.
No reported findings remain deferred. Review fixes were verified with failing
regressions followed by focused passing runs and the full 49-test suite.

## Browser checks

Checked the real local Waitress server, with synthetic demo users:

- Candidate login, ranked dashboard, profile display/save, and logout.
- Candidate interview booking and its confirmation.
- Employer ranked applicant view showing the same reservation.
- Employer changing the application to Accepted while the booking remains reserved.
- Employer schedule showing the booked slot as reserved with no delete action.
- Dashboard, profile, and schedule responsive layouts at a 390px viewport; document
  width equals viewport width. Employer tables scroll within their own container.
- Desktop layout at 1280px; screenshot saved locally to
  `output/screenshots/dashboard-desktop.jpg` (ignored generated output).

The schedule initially overflowed on mobile. The grid's intrinsic minimum width
and absolutely positioned screen-reader text were corrected; browser measurements
then confirmed 390px document width at 390px viewport width. Viewport overrides
were reset. Fresh demo data was restored after workflow testing, and the candidate
dashboard is available in the preview.

## Docker verification

Built `common-ground-csc4801` from the repository Dockerfile with the documented
`python:3.12.11-slim-bookworm` base image and locked dependencies. The build context
excludes the host virtual environment, local database, secrets, and generated
outputs. No extra runtime images are required.

A task-specific container and fresh named volume were used to:

1. Start the image as its non-root user and apply migrations.
2. Repeat `init-db` successfully without resetting data.
3. Run `seed --yes` inside the running container.
4. Verify live HTTP `/health`, login, ranked dashboard, and application pages.
5. Recreate the container with the same volume and verify five users, four jobs,
   and two applied migrations remain; wait for HTTP readiness before probing.
6. Run the complete test suite in a separate disposable container: 49 passed.

An initial pytest cache permission warning was fixed by assigning the application
working directory to its non-root runtime user. The final container suite has no
warnings. Docker Desktop's credential helper stalled the first public image fetch;
a task-local empty client configuration successfully fetched the same public base
image without changing the user's Docker settings.

## Remaining external delivery steps

- Team review of implementation and roster/contribution details.
- Commit/push and public repository availability when authorized.
- Import the supplied GitHub audit labels.
- Observe GitHub Actions running on the published source.
- Freeze/fix according to course dates and submit the permanent graded `main`
  commit URL. Repeat the documented clean-checkout verification at that commit.
