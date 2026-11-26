CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('Candidate','Employer')),
    display_name TEXT NOT NULL CHECK(length(trim(display_name)) > 0)
);
CREATE TABLE candidate_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    resume TEXT NOT NULL DEFAULT ''
);
CREATE TABLE candidate_skills (
    candidate_id INTEGER NOT NULL REFERENCES candidate_profiles(user_id) ON DELETE CASCADE,
    skill TEXT NOT NULL,
    PRIMARY KEY(candidate_id, skill)
);
CREATE TABLE companies (
    employer_id INTEGER PRIMARY KEY REFERENCES users(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    employer_id INTEGER NOT NULL REFERENCES companies(employer_id),
    title TEXT NOT NULL CHECK(length(trim(title)) > 0),
    description TEXT NOT NULL CHECK(length(trim(description)) > 0)
);
CREATE TABLE job_skills (
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    skill TEXT NOT NULL,
    PRIMARY KEY(job_id, skill)
);
CREATE TABLE applications (
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER NOT NULL REFERENCES candidate_profiles(user_id),
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending','Interviewing','Rejected','Accepted')),
    UNIQUE(candidate_id, job_id)
);
CREATE TABLE slots (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    starts_at INTEGER NOT NULL,
    ends_at INTEGER NOT NULL CHECK(ends_at - starts_at = 1800)
);
CREATE TABLE bookings (
    id INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL UNIQUE REFERENCES applications(id),
    slot_id INTEGER NOT NULL UNIQUE REFERENCES slots(id)
);
CREATE INDEX jobs_employer ON jobs(employer_id);
CREATE INDEX applications_job ON applications(job_id);
CREATE INDEX slots_job ON slots(job_id);
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO metadata VALUES ('session_generation', lower(hex(randomblob(24))));
