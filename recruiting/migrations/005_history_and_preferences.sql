-- One row per status change, so application history shows real dates for every step.
CREATE TABLE application_events (
    id INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id),
    status TEXT NOT NULL CHECK(status IN ('Pending','Interviewing','Rejected','Accepted')),
    created_at INTEGER NOT NULL
);
CREATE INDEX application_events_application ON application_events(application_id, created_at, id);
-- When the booking was made; 0 for bookings created before this migration.
ALTER TABLE bookings ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0;
-- When the resume was last saved; 0 means never.
ALTER TABLE candidate_profiles ADD COLUMN resume_updated_at INTEGER NOT NULL DEFAULT 0;
-- Work preferences from the profile form. An empty job type means none were saved.
ALTER TABLE candidate_profiles ADD COLUMN pref_job_type TEXT NOT NULL DEFAULT ''
    CHECK(pref_job_type IN ('', 'Full-time', 'Contract', 'Any'));
ALTER TABLE candidate_profiles ADD COLUMN pref_remote INTEGER NOT NULL DEFAULT 0 CHECK(pref_remote IN (0, 1));
