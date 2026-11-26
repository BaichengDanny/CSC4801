/* Matchwork employer portal: demo store, business rules and app shell.
   Front-end only. Every mutating call returns { ok, code, message } with the HTTP status the
   full-stack API must return (400 / 403 / 404 / 409), so the UI already handles the real contract.
   Live matching comes from the backend; shared/match.js projects API facts and keeps the offline demo calculator. */
(function () {
  'use strict';

  /* ---------- Demo session ----------
     login.html stores { role } on sign-in. Employer pages need role "recruiter" when served over
     http(s); file:// previews skip the check. Log Out clears the flag. */
  /* In a bundled preview, pages are supplied in window.__RW_PAGES. */
  const BUNDLE = !!window.__RW_PAGES;
  let csrfToken;
  function api(method, path, payload) {
    const xhr = new XMLHttpRequest();
    xhr.open(method, path, false);
    xhr.withCredentials = true;
    if (payload !== undefined) xhr.setRequestHeader('Content-Type', 'application/json');
    if (method === 'POST' && csrfToken) xhr.setRequestHeader('X-CSRF-Token', csrfToken);
    xhr.send(payload === undefined ? null : JSON.stringify(payload));
    let data = null;
    try { data = xhr.responseText ? JSON.parse(xhr.responseText) : null; } catch (e) { data = { message: 'Unexpected response' }; }
    /* The session ended (signed out in another tab, expired, or the demo data was reset). */
    if (xhr.status === 401 && !path.startsWith('/api/auth/')) location.replace('/sign-in#recruiter');
    return { status: xhr.status, data };
  }
  /* Where pages read their query and hash. In the bundle, if the browser refused to change the URL
     (file:// in some browsers, sandboxed previews) the router keeps the intended one in __rwLoc. */
  const loc = () => (BUNDLE && window.__rwLoc) || { search: location.search, hash: location.hash };
  const params = () => new URLSearchParams(loc().search);
  const hash = () => loc().hash.slice(1);
  /* The page's current URL, to edit and hand to history.replaceState. */
  const url = () => { const l = loc(); return new URL(location.pathname + l.search + l.hash, location.href); };
  const hosted = !BUNDLE && /^https?:$/.test(location.protocol);
  let boot = null;
  let authed = !hosted;
  if (hosted) {
    const me = api('GET', '/api/auth/me');
    authed = me.status === 200 && me.data && me.data.role === 'Employer';
    if (!authed) location.replace('/sign-in#recruiter');
    else {
      csrfToken = me.data.csrfToken;
      const loaded = api('GET', '/api/employer/bootstrap');
      if (loaded.status === 200) boot = loaded.data;
      else authed = false;
    }
    document.addEventListener('click', (e) => {
      const a = e.target.closest && e.target.closest('a[href^="/sign-in"]');
      if (!a) return;
      e.preventDefault();
      api('POST', '/api/auth/logout');
      location.href = a.getAttribute('href');
    }, true);
  }
  function hasRecruiterSession() { return authed; }

  const legacyMatch = window.MWMatch;
  const { matchScore } = legacyMatch; // Local file/demo behavior only.
  const normalizeSkills = (list) => live ? new Set(list || []) : legacyMatch.normalizeSkills(list);
  const hasSkill = (list, skill) => live ? new Set(list || []).has(skill) : legacyMatch.hasSkill(list, skill);
  const compareApplicants = (a, b) => live ? legacyMatch.byServerRank(a, b) : legacyMatch.compareApplicants(a, b);
  const skillKey = (value) => live ? String(value).trim() : String(value).trim().toLowerCase();

  /* ---------- Utilities ---------- */
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = window.MWHTML.escape;
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* All times are stored in UTC and shown in Pacific Time, like the candidate portal. */
  const TZ = 'America/Los_Angeles';
  const TZ_LABEL = 'Pacific Time (PT)';
  /* The demo clock, shared with the candidate portal. The server clock replaces it when signed in. */
  let NOW = new Date(boot && boot.now ? boot.now : '2026-11-16T17:00:00Z');
  const SLOT_MIN = 30;
  const fmt = (d, opts) => new Intl.DateTimeFormat('en-US', { timeZone: TZ, ...opts }).format(new Date(d));
  const fmtDate = (d) => fmt(d, { weekday: 'short', month: 'short', day: 'numeric' });
  const fmtLong = (d) => fmt(d, { weekday: 'long', month: 'long', day: 'numeric' });
  const fmtShort = (d) => fmt(d, { month: 'short', day: 'numeric' });
  const fmtTime = (d) => fmt(d, { hour: 'numeric', minute: '2-digit' });
  const fmtSlotTime = (d) => fmt(d, { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
  function fmtRange(s, e) {
    if (ptOffset(new Date(s)) !== ptOffset(new Date(e))) return `${fmtSlotTime(s)} – ${fmtSlotTime(e)}`;
    const a = fmtTime(s), b = fmtTime(e);
    return `${a.slice(-2) === b.slice(-2) ? a.slice(0, -3) : a} – ${b}`;
  }
  const dayKey = (d) => fmt(d, { year: 'numeric', month: '2-digit', day: '2-digit' }); /* MM/DD/YYYY in PT */
  function ago(d) {
    const mins = Math.round((NOW - new Date(d)) / 6e4);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins} min ago`;
    if (mins < 60 * 24 && dayKey(d) === dayKey(NOW)) return `${Math.round(mins / 60)} hr ago`;
    const days = Math.max(1, Math.round(mins / 1440));
    if (days === 1) return 'Yesterday';
    if (days < 7) return `${days} days ago`;
    if (days < 14) return '1 week ago';
    if (days < 31) return `${Math.floor(days / 7)} weeks ago`;
    return `${Math.floor(days / 30)} months ago`;
  }
  const offsetFormat = new Intl.DateTimeFormat('en-US', { timeZone: TZ, timeZoneName: 'shortOffset' });
  /* PT offset for a UTC instant, in minutes (PST -480, PDT -420). */
  function ptOffset(date) {
    const p = offsetFormat.formatToParts(date).find((x) => x.type === 'timeZoneName').value;
    const m = /GMT([+-])(\d+)(?::(\d+))?/.exec(p);
    return m ? (m[1] === '-' ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3] || 0)) : 0;
  }
  /* Return one exact instant, or null for a missing or repeated DST wall time. */
  function ptToUtc(ymd, h, min) {
    const [y, mo, d] = ymd.split('-').map(Number);
    const guess = Date.UTC(y, mo - 1, d, h, min);
    if (!Number.isFinite(guess) || y < 100 || y > 9999) return null;
    const offsets = new Set([-864e5, 864e5].map((delta) => ptOffset(new Date(guess + delta))));
    const matches = [...offsets].map((offset) => new Date(guess - offset * 6e4))
      .filter((date) => date.getTime() + ptOffset(date) * 6e4 === guess);
    return matches.length === 1 ? matches[0].toISOString() : null;
  }
  /* "MM/DD/YYYY" (dayKey) to "YYYY-MM-DD". */
  const ymdOf = (d) => { const [m, dd, y] = dayKey(d).split('/'); return `${y}-${m}-${dd}`; };

  /* ---------- Seed data ----------
     The signed-in employer is Tidewater Labs. One posting from another employer is kept in the
     store so ownership checks (403) have something to refuse; the UI never lists it. */
  let ME = boot ? boot.me : 'tidewater';
  const COMPANY_SEED = {
    id: ME, name: 'Tidewater Labs',
    about: 'Makes search and discovery tools for public libraries and university archives. Our small team works closely with librarians, so the people who use what we build are never far away.',
    industry: 'Software', size: '51–200 employees', location: 'Oakland, CA', website: 'tidewaterlabs.example',
    mono: 'T', tint: '#1F5FA8', tileBg: '#EAF1FA',
  };
  const CANDIDATES = [
    { id: 'c01', name: 'John Doe', headline: 'Backend engineer focused on data-heavy services', location: 'San Jose, CA', email: 'john.doe@example.com', skills: ['Python', 'Java', 'SQL', 'Distributed Systems', 'React'], tint: '#E3E2E7' },
    { id: 'c02', name: 'Alice Chen', headline: 'Full-stack engineer, Python and React', location: 'Berkeley, CA', email: 'alice.chen@example.com', skills: ['Python', 'SQL', 'React', 'AWS'], tint: '#EFEAFC' },
    { id: 'c03', name: 'Bob Smith', headline: 'Backend engineer, APIs and tooling', location: 'Oakland, CA', email: 'bob.smith@example.com', skills: ['Python', 'Go'], tint: '#E8F0EA' },
    { id: 'c04', name: 'Priya Natarajan', headline: 'Frontend engineer who cares about accessibility', location: 'San Francisco, CA', email: 'priya.n@example.com', skills: ['TypeScript', 'React', 'CSS', 'Accessibility'], tint: '#FFF4DA' },
    { id: 'c05', name: 'David Lee', headline: 'Systems programmer', location: 'Fremont, CA', email: 'david.lee@example.com', skills: ['Rust', 'Docker'], tint: '#FCE7EC' },
    { id: 'c06', name: 'Maria Garcia', headline: 'Search engineer, relevance and indexing', location: 'Oakland, CA', email: 'maria.garcia@example.com', skills: ['Java', 'Elasticsearch', 'Python', 'Kubernetes'], tint: '#E6EEF8' },
    { id: 'c07', name: 'Sam Okafor', headline: 'Data engineering student', location: 'Davis, CA', email: 'sam.okafor@example.com', skills: ['Python', 'SQL', 'Airflow'], tint: '#F1ECE4' },
    { id: 'c08', name: 'Lena Park', headline: 'Product designer, research-led', location: 'Remote', email: 'lena.park@example.com', skills: ['Figma', 'User Research', 'Prototyping'], tint: '#FDEDE3' },
    { id: 'c09', name: 'Ethan Brooks', headline: 'Senior engineer, search infrastructure', location: 'Portland, OR', email: 'ethan.brooks@example.com', skills: ['Java', 'Python', 'SQL', 'Elasticsearch', 'Distributed Systems'], tint: '#E8F0EA' },
    { id: 'c10', name: 'Noor Haddad', headline: 'Backend engineer, catalog data', location: 'Sacramento, CA', email: 'noor.haddad@example.com', skills: [' python ', 'SQL', 'sql'], tint: '#EFEAFC' },
  ];
  const J = (id, seq, title, extra) => ({ id, seq, title, owner: ME, location: 'Oakland, CA', type: 'Full-time', status: 'Active', body: '', ...extra });
  const JOBS_SEED = [
    J('tw', 1, 'Software Engineer, Search', { posted: '2026-11-04T17:00:00Z', skills: ['Java', 'Python', 'Elasticsearch', 'Distributed Systems', 'SQL'],
      desc: 'Make library catalogs and archives easier to search.',
      body: 'Improve relevance and speed for search across 40 million catalog records.\n- Build indexing pipelines in Java and Python\n- Tune Elasticsearch ranking with librarians as your users\n- Scale query serving across a small cluster' }),
    J('tw-api', 2, 'Backend Engineer, Catalog API', { location: 'Remote (US)', posted: '2026-10-28T17:00:00Z', skills: ['Python', 'SQL'],
      desc: 'Own the API that libraries use to load and update their catalogs.',
      body: '- Design versioned REST endpoints in Python\n- Keep imports of 100k-record files fast and safe\n- Write the SQL that keeps catalog data consistent' }),
    J('tw-fe', 3, 'Frontend Engineer, Discovery', { location: 'Oakland, CA (Hybrid)', posted: '2026-11-09T17:00:00Z', skills: ['TypeScript', 'React', 'CSS', 'Accessibility'],
      desc: 'Build the search pages millions of library patrons use.',
      body: '- Ship accessible search and browse pages in React\n- Work with librarians on how people actually look for books\n- Keep pages fast on old library computers' }),
    J('tw-data', 4, 'Data Engineering Intern', { type: 'Internship', posted: '2026-11-12T17:00:00Z', skills: ['Python', 'SQL', 'Airflow'],
      desc: 'Help us move nightly catalog loads onto Airflow.',
      body: '- Port cron jobs to Airflow DAGs\n- Add data quality checks to nightly loads' }),
    J('tw-des', 5, 'Product Designer', { location: 'Remote (US)', posted: '2026-11-13T17:00:00Z', skills: [],
      desc: 'Design search and archive tools with librarians and researchers.',
      body: 'We list no required skills for this role, so every applicant starts at a 100% match. Show us your process.' }),
    J('tw-sre', 6, 'Site Reliability Engineer', { posted: '2026-11-15T17:00:00Z', skills: ['Kubernetes', 'Terraform', 'Linux', 'Prometheus'],
      desc: 'Keep search fast and available for 900 library systems.',
      body: '- Run our Kubernetes clusters and on-call rotation\n- Turn manual runbooks into automation' }),
    /* Another employer's posting: ownership checks refuse every change to it. */
    { id: 'hh', seq: 90, owner: 'harbor', title: 'Platform Engineer', location: 'Seattle, WA', type: 'Full-time', status: 'Active', posted: '2026-10-01T17:00:00Z', skills: ['Go', 'Kubernetes'], desc: 'Harbor Health platform team.', body: '' },
  ];
  const at = (iso) => iso;
  const APP = (id, jobId, candidateId, status, appliedAt, slotId, events) => ({ id, jobId, candidateId, status, appliedAt, slotId: slotId || null, events: events || [['Applied', appliedAt]] });
  const APPS_SEED = [
    APP('r01', 'tw', 'c01', 'Interviewing', '2026-11-06T18:00:00Z', null, [['Applied', '2026-11-06T18:00:00Z'], ['Moved to Interviewing', '2026-11-15T00:30:00Z']]),
    APP('r02', 'tw', 'c06', 'Interviewing', '2026-11-07T19:10:00Z', null, [['Applied', '2026-11-07T19:10:00Z'], ['Moved to Interviewing', '2026-11-15T00:40:00Z']]),
    APP('r03', 'tw', 'c09', 'Interviewing', '2026-11-05T16:20:00Z', 's-01', [['Applied', '2026-11-05T16:20:00Z'], ['Moved to Interviewing', '2026-11-11T18:00:00Z'], ['Interview booked', '2026-11-12T20:15:00Z']]),
    APP('r04', 'tw', 'c02', 'Pending', '2026-11-15T21:40:00Z'),
    APP('r05', 'tw', 'c05', 'Rejected', '2026-11-08T17:30:00Z', null, [['Applied', '2026-11-08T17:30:00Z'], ['Rejected', '2026-11-10T18:00:00Z']]),
    APP('r06', 'tw-api', 'c02', 'Pending', '2026-11-16T16:48:00Z'),
    APP('r07', 'tw-api', 'c03', 'Interviewing', '2026-11-02T18:00:00Z', 's-02', [['Applied', '2026-11-02T18:00:00Z'], ['Moved to Interviewing', '2026-11-09T18:00:00Z'], ['Interview booked', '2026-11-10T17:00:00Z']]),
    APP('r08', 'tw-api', 'c05', 'Rejected', '2026-10-30T18:00:00Z', null, [['Applied', '2026-10-30T18:00:00Z'], ['Rejected', '2026-11-03T18:00:00Z']]),
    APP('r09', 'tw-api', 'c10', 'Accepted', '2026-10-29T18:00:00Z', 's-00', [['Applied', '2026-10-29T18:00:00Z'], ['Moved to Interviewing', '2026-11-03T18:00:00Z'], ['Interview booked', '2026-11-04T18:00:00Z'], ['Accepted', '2026-11-12T18:00:00Z']]),
    APP('r10', 'tw-api', 'c07', 'Pending', '2026-11-14T18:00:00Z'),
    APP('r11', 'tw-fe', 'c04', 'Interviewing', '2026-11-09T22:00:00Z', 's-03', [['Applied', '2026-11-09T22:00:00Z'], ['Moved to Interviewing', '2026-11-12T18:00:00Z'], ['Interview booked', '2026-11-13T17:00:00Z']]),
    APP('r12', 'tw-fe', 'c02', 'Pending', '2026-11-13T18:00:00Z'),
    APP('r13', 'tw-data', 'c07', 'Pending', '2026-11-13T19:00:00Z'),
    APP('r14', 'tw-data', 'c10', 'Pending', '2026-11-16T15:30:00Z'),
    APP('r15', 'tw-des', 'c08', 'Pending', '2026-11-14T20:00:00Z'),
    APP('r16', 'tw-des', 'c03', 'Pending', '2026-11-15T17:00:00Z'),
    APP('x01', 'hh', 'c02', 'Pending', '2026-10-05T18:00:00Z'),
  ];
  const SL = (id, startIso, bookedBy, owner) => ({ id, owner: owner || ME, start: startIso, end: new Date(new Date(startIso).getTime() + SLOT_MIN * 6e4).toISOString(), bookedBy: bookedBy || null });
  const SLOTS_SEED = [
    SL('s-00', '2026-11-10T19:00:00Z', 'r09'),
    SL('s-p1', '2026-11-13T18:00:00Z'),
    SL('s-01', '2026-11-16T18:00:00Z', 'r03'),
    SL('s-02', '2026-11-16T22:00:00Z', 'r07'),
    SL('s-04', '2026-11-18T18:00:00Z'),
    SL('s-05', '2026-11-18T18:30:00Z'),
    SL('s-03', '2026-11-18T19:00:00Z', 'r11'),
    SL('s-06', '2026-11-18T21:00:00Z'),
    SL('s-07', '2026-11-19T17:00:00Z'),
    SL('s-08', '2026-11-19T17:30:00Z'),
    SL('s-09', '2026-11-19T23:00:00Z'),
    SL('s-10', '2026-11-20T18:00:00Z'),
    SL('s-11', '2026-11-20T21:30:00Z'),
    SL('s-12', '2026-11-23T19:00:00Z'),
    SL('h-01', '2026-11-19T18:00:00Z', null, 'harbor'),
  ];
  const DEFAULT_STATE = () => JSON.parse(JSON.stringify({
    v: 1, company: COMPANY_SEED, candidates: CANDIDATES, jobs: JOBS_SEED, applications: APPS_SEED, slots: SLOTS_SEED,
    notifRead: false, clock: 0,
  }));

  /* ---------- Store ---------- */
  const KEY = 'matchwork.recruiter.v1';
  const live = !!boot;
  let state;
  if (live) state = boot.state;
  else if (!hosted) {
    try { state = JSON.parse(localStorage.getItem(KEY)); } catch (e) { state = null; }
    if (!state || state.v !== 1) state = DEFAULT_STATE();
  } else {
    state = { v: 1, company: { id: '', name: '', about: '', industry: '', size: '', location: '', website: '', mono: '?', tint: '#1F5FA8', tileBg: '#EAF1FA' }, candidates: [], jobs: [], applications: [], slots: [], notifRead: false, clock: 0 };
  }
  const listeners = new Set();
  function persist() {
    if (!live) { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* storage unavailable: keep in memory */ } }
    listeners.forEach((fn) => { try { fn(state); } catch (err) { console.error(err); } });
  }
  let lastSnapshot = live ? JSON.stringify(boot.state) : '';
  function acceptSnapshot(data) {
    lastSnapshot = JSON.stringify(data.state);
    const notifRead = state.notifRead;
    Object.assign(state, data.state, { notifRead });
    NOW.setTime(new Date(data.now).getTime());
    persist();
  }
  function refresh(force = false) {
    if (!live) return false;
    if (!force) {
      const leave = new Event('beforeunload', { cancelable: true });
      window.dispatchEvent(leave);
      if (leave.defaultPrevented) return false;
    }
    const res = api('GET', '/api/employer/bootstrap');
    if (res.status === 401 || res.status === 403) { location.replace('/sign-in#recruiter'); return false; }
    const error = failed(res, 'Could not refresh applicant results');
    if (error) throw new Error(error.message);
    const previousTime = NOW.getTime();
    NOW.setTime(new Date(res.data.now).getTime());
    if (lastSnapshot === JSON.stringify(res.data.state)) {
      const expired = state.slots.some(slot => new Date(slot.start).getTime() > previousTime && new Date(slot.start) <= NOW);
      if (expired) persist();
      return expired;
    }
    acceptSnapshot(res.data);
    return true;
  }
  function resetDemo() {
    if (live) { location.reload(); return; }
    state = DEFAULT_STATE(); persist();
  }
  const failed = (res, fallback) => (res.status >= 400 || !res.data || res.data.ok === false)
    ? fail(res.status || 400, (res.data && res.data.message) || fallback, res.data || {}) : null;
  /* The demo clock stands still, so each change gets the next minute after NOW to keep histories in order. */
  const stamp = () => new Date(NOW.getTime() + (++state.clock) * 6e4).toISOString();

  const fail = (code, message, extra) => ({ ok: false, code, message, ...extra });

  /* ---------- Reads (scoped to the signed-in employer) ---------- */
  const company = () => state.company;
  const candidate = (id) => state.candidates.find((c) => c.id === id);
  const ownJobs = () => state.jobs.filter((j) => j.owner === ME);
  const findJob = (id) => state.jobs.find((j) => j.id === id);
  const appsFor = (jobId) => state.applications.filter((a) => a.jobId === jobId);
  const slot = (id) => state.slots.find((s) => s.id === id);
  const ownSlots = () => state.slots.filter((s) => s.owner === ME).sort((a, b) => new Date(a.start) - new Date(b.start));
  const ownApps = () => { const ids = new Set(ownJobs().map((j) => j.id)); return state.applications.filter((a) => ids.has(a.jobId)); };

  function jobs() {
    return ownJobs().map((j) => {
      const apps = appsFor(j.id);
      return { ...j, apps: apps.length, interviewing: apps.filter((a) => a.status === 'Interviewing').length, pending: apps.filter((a) => a.status === 'Pending').length };
    }).sort((a, b) => new Date(b.posted) - new Date(a.posted) || a.seq - b.seq);
  }
  const job = (id) => jobs().find((j) => j.id === id) || null;

  /* An application with its candidate, job, booked slot and score: the row the applicant views show. */
  function view(a) {
    const j = findJob(a.jobId), c = candidate(a.candidateId);
    return { ...a, job: j, cand: c, name: c.name, match: live ? legacyMatch.fromServer([a])[0].match : matchScore(c.skills, j.skills), slot: a.slotId ? slot(a.slotId) : null };
  }
  /* FP-EMP-3: applicants for one owned job, highest score first, ties by name then candidate id. */
  function applicants(jobId) {
    const j = findJob(jobId);
    if (!j) return fail(404, 'That job no longer exists');
    if (j.owner !== ME) return fail(403, 'You can only view applicants for your own jobs');
    return { ok: true, list: appsFor(jobId).map(view).sort(compareApplicants) };
  }
  const allApplicants = () => ownApps().map(view).sort(compareApplicants);
  const application = (id) => { const a = state.applications.find((x) => x.id === id); return a && findJob(a.jobId).owner === ME ? view(a) : null; };
  const awaitingBooking = () => ownApps().filter((a) => a.status === 'Interviewing' && !a.slotId).map(view);
  const openSlots = () => ownSlots().filter((s) => !s.bookedBy && new Date(s.start) > NOW);

  /* ---------- Writes ---------- */
  const JOB_TYPES = ['Full-time', 'Part-time', 'Contract', 'Internship'];
  /* Required skills keep the employer's spelling, minus blanks and case-insensitive duplicates. */
  function cleanSkills(list) {
    if (live) return (list || []).map(s => String(s).trim()).filter(Boolean);
    const seen = new Set(), out = [];
    (list || []).forEach((s) => { const t = String(s == null ? '' : s).trim().replace(/\s+/g, ' '); const k = t.toLowerCase(); if (t && !seen.has(k)) { seen.add(k); out.push(t); } });
    return out;
  }
  function validateJob(d) {
    const errors = {};
    if (!String(d.title || '').trim()) errors.title = 'Enter a job title.';
    else if (String(d.title).trim().length > 90) errors.title = 'Keep the title under 90 characters.';
    if (!String(d.desc || '').trim()) errors.desc = 'Enter a description so candidates know what the job is.';
    if (d.type && !JOB_TYPES.includes(d.type)) errors.type = 'Choose a job type.';
    if (d.status && !['Active', 'Closed'].includes(d.status)) errors.status = 'Choose Active or Closed.';
    return errors;
  }
  /* A blank location stays blank. Cards from the server show "Not listed" for it, with
     locationSet: false, and that placeholder must not be saved back as a real place. */
  const placeOf = (d) => (d.locationSet === false && d.location === 'Not listed' ? '' : String(d.location || '').trim());
  const pickJob = (d) => ({
    title: String(d.title || '').trim(), location: placeOf(d), type: d.type || 'Full-time',
    desc: String(d.desc || '').trim(), body: String(d.body || '').replace(/\s+$/, ''), skills: cleanSkills(d.skills), status: d.status || 'Active',
  });
  /* FP-EMP-2 */
  function createJob(d) {
    const errors = validateJob(d);
    if (Object.keys(errors).length) return fail(400, 'Fix the highlighted fields', { errors });
    if (live) {
      const res = api('POST', '/api/employer/jobs', pickJob(d));
      const error = failed(res, 'Could not create the job');
      if (error) return error;
      acceptSnapshot(res.data.snapshot);
      return { ok: true, job: res.data.job };
    }
    const seq = Math.max(0, ...state.jobs.map((j) => j.seq || 0)) + 1;
    const j = { id: 'j' + Date.now().toString(36), seq, owner: ME, posted: stamp(), ...pickJob(d) };
    state.jobs.push(j); persist();
    return { ok: true, job: j };
  }
  function updateJob(id, d) {
    const j = findJob(id);
    if (!j) return fail(404, 'That job no longer exists');
    if (j.owner !== ME) return fail(403, 'You can only edit your own jobs');
    const merged = { ...j, ...d };
    if (live) {
      const errors = validateJob(merged);
      if (Object.keys(errors).length) return fail(400, 'Fix the highlighted fields', { errors });
      const res = api('POST', '/api/employer/jobs/' + encodeURIComponent(id), pickJob(merged));
      const error = failed(res, 'Could not update the job');
      if (error) return error;
      acceptSnapshot(res.data.snapshot);
      return { ok: true, job: res.data.job };
    }
    const errors = validateJob(merged);
    if (Object.keys(errors).length) return fail(400, 'Fix the highlighted fields', { errors });
    Object.assign(j, pickJob(merged)); persist();
    return { ok: true, job: j };
  }
  /* Jobs with dependents (applications, or slots tied to it) refuse deletion with 409 and change nothing. */
  function deleteBlockers(id) {
    const apps = appsFor(id).length, slots = state.slots.filter((s) => s.jobId === id).length;
    return { apps, slots, blocked: apps > 0 || slots > 0 };
  }
  /* Name what actually blocks deletion. New interview slots attach to the oldest job. */
  function deleteBlockedText(b) {
    const parts = [];
    if (b.apps) parts.push(`${b.apps} application${b.apps === 1 ? '' : 's'}`);
    if (b.slots) parts.push(`${b.slots} interview slot${b.slots === 1 ? '' : 's'}`);
    return `It still has ${parts.join(' and ')}. `
      + (b.slots ? 'Interview slots you add are kept on your oldest job. ' : '')
      + 'Close the posting to stop new applications.';
  }
  function deleteJob(id) {
    const j = findJob(id);
    if (!j) return fail(404, 'That job no longer exists');
    if (j.owner !== ME) return fail(403, 'You can only delete your own jobs');
    if (live) {
      const res = api('POST', '/api/employer/jobs/' + encodeURIComponent(id) + '/delete');
      const error = failed(res, 'Could not delete the job');
      if (error) return error;
      acceptSnapshot(res.data.snapshot);
      return { ok: true, job: j };
    }
    const b = deleteBlockers(id);
    if (b.blocked) return fail(409, `“${j.title}” can't be deleted. ${deleteBlockedText(b)}`);
    state.jobs = state.jobs.filter((x) => x.id !== id); persist();
    return { ok: true, job: j };
  }

  const STATUSES = ['Pending', 'Interviewing', 'Rejected', 'Accepted'];
  /* FP-EMP-3: only the owning employer sets status, and only to one of the four values. */
  function setStatus(appId, status) {
    const a = state.applications.find((x) => x.id === appId);
    if (!a) return fail(404, 'That application no longer exists');
    if (findJob(a.jobId).owner !== ME) return fail(403, 'Only the employer who owns this job can change its status');
    if (!STATUSES.includes(status)) return fail(400, 'Status must be Pending, Interviewing, Rejected or Accepted');
    if (a.status === status) return { ok: true, app: view(a), unchanged: true };
    if (live) {
      const res = api('POST', '/api/employer/applications/' + encodeURIComponent(appId) + '/status', { status });
      const error = failed(res, 'Could not update the status');
      if (error) return error;
      const prev = a.status;
      acceptSnapshot(res.data.snapshot);
      return { ok: true, app: application(appId), prev };
    }
    const prev = a.status;
    a.status = status;
    a.events.push([status === 'Interviewing' ? 'Moved to Interviewing' : status === 'Pending' ? 'Moved back to Pending' : status, stamp()]);
    persist();
    return { ok: true, app: view(a), prev };
  }

  /* FP-SCHED-1: future, exactly 30 minutes, one owner, no overlap with the owner's other slots. */
  function createSlot(startIso, endIso) {
    if (!startIso || !endIso) return fail(400, 'Choose a time that occurs once in Pacific Time');
    const s = new Date(startIso), e = new Date(endIso);
    if (isNaN(s) || isNaN(e)) return fail(400, 'Enter a valid start and end time');
    if (e <= s) return fail(400, 'The end time must be after the start time');
    if (e - s !== SLOT_MIN * 6e4) return fail(400, 'Interview slots must be exactly 30 minutes');
    if (s <= NOW) return fail(400, 'Slots must start in the future');
    const clash = ownSlots().find((x) => new Date(x.start) < e && new Date(x.end) > s);
    if (clash) return fail(409, `That overlaps your ${fmtTime(clash.start)} slot`);
    if (live) {
      const res = api('POST', '/api/employer/slots', { start: s.toISOString(), end: e.toISOString() });
      const error = failed(res, 'Could not add that time');
      if (error) return error;
      state.slots.push(res.data.slot); persist();
      return { ok: true, slot: res.data.slot };
    }
    const sl = { id: 's' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5), owner: ME, start: s.toISOString(), end: e.toISOString(), bookedBy: null };
    state.slots.push(sl); persist();
    return { ok: true, slot: sl };
  }
  function deleteSlot(id) {
    const sl = slot(id);
    if (!sl) return fail(404, 'That slot no longer exists');
    if (sl.owner !== ME) return fail(403, 'You can only delete your own slots');
    if (live && !sl.bookedBy) {
      const res = api('POST', '/api/employer/slots/' + encodeURIComponent(id) + '/delete');
      const error = failed(res, 'Could not delete that time');
      if (error) return error;
      state.slots = state.slots.filter((item) => item.id !== id);
      persist();
      return { ok: true, slot: sl };
    }
    if (sl.bookedBy) {
      const a = application(sl.bookedBy);
      return fail(409, `${a ? a.name + ' booked' : 'A candidate booked'} this time, so it can't be deleted`);
    }
    state.slots = state.slots.filter((x) => x.id !== id); persist();
    return { ok: true, slot: sl };
  }

  /* FP-EMP-1 */
  const SIZES = ['1–10 employees', '11–50 employees', '51–200 employees', '201–1,000 employees', '1,001–10,000 employees', '10,000+ employees'];
  function updateCompany(d) {
    const errors = {};
    const name = String(d.name == null ? state.company.name : d.name).trim();
    const about = String(d.about == null ? state.company.about : d.about).trim();
    if (!name) errors.name = 'Enter your company name.';
    else if (name.length > 80) errors.name = 'Keep the name under 80 characters.';
    if (!about) errors.about = 'Enter a short description of your company.';
    else if (about.length > 800) errors.about = 'Keep the description under 800 characters.';
    if (Object.keys(errors).length) return fail(400, 'Fix the highlighted fields', { errors });
    if (live) {
      const res = api('POST', '/api/employer/company', { ...d, name, about });
      const error = failed(res, 'Could not save the company');
      if (error) return error;
      state.company = res.data.company;
      persist();
      return { ok: true, company: state.company };
    }
    const next = { ...state.company, ...d, name, about };
    ['industry', 'location', 'website'].forEach((k) => { next[k] = String(next[k] || '').trim(); });
    next.mono = (name.match(/[A-Za-z0-9]/) || ['?'])[0].toUpperCase();
    state.company = next; persist();
    return { ok: true, company: next };
  }

  /* ---------- Shared markup ---------- */
  const ICON = {
    pin: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 21s-7-6.5-7-12a7 7 0 0 1 14 0c0 5.5-7 12-7 12z"/><circle cx="12" cy="9" r="2.5"/></svg>',
    bag: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5h6v2M3 12h18"/></svg>',
    clock: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    cal: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><rect x="4" y="5" width="16" height="16" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/></svg>',
    checkSm: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#2F6B4A" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
    flame: '<svg width="13" height="13" viewBox="0 0 24 24" fill="#3C9A57" aria-hidden="true"><path d="M12 2c1 4 6 6 6 12a6 6 0 0 1-12 0c0-3 2-5 3-6 0 2 1 3 2 3 0-4 1-6 1-9z"/></svg>',
    arrow: '<svg class="arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    chev: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>',
    plus: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
    x: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
    lock: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
    edit: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/><path d="m13.5 6.5 4 4"/></svg>',
    trash: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>',
    mail: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7 8 6 8-6"/></svg>',
    globe: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9s1-6.5 3.5-9z"/></svg>',
    users: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.3c2.1.7 3.5 2.8 3.5 5.7"/></svg>',
  };
  function logoHTML(size = '') {
    const c = state.company;
    return `<span class="logo-tile mono ${size}" style="color:${esc(c.tint)};background:${esc(c.tileBg)}" role="img" aria-label="${esc(c.name)} logo">${esc(c.mono)}</span>`;
  }
  const initials = (name) => (String(name).trim().split(/\s+/).map((w) => (w.match(/[\p{L}\p{N}]/u) || [''])[0]).join('').slice(0, 2).toUpperCase() || '?');
  const avatarHTML = (c, cls = '') => `<span class="person-av ${cls}" style="background:${esc(c.tint)}" aria-hidden="true">${esc(initials(c.name))}</span>`;
  function scoreHTML(m) {
    if (m >= 90) return `<span class="score hi">${ICON.flame}${m}% Match</span>`;
    if (m >= 60) return `<span class="score mid">${m}% Match</span>`;
    return `<span class="score lo">${m}% Match</span>`;
  }
  const statusHTML = (st) => `<span class="status ${esc(String(st).toLowerCase())}">${esc(st)}</span>`;
  /* Candidate skills, with the ones this job requires marked. */
  function candTagsHTML(c, j, max) {
    const req = normalizeSkills(j.skills);
    const list = cleanSkills(c.skills);
    list.sort((a, b) => Number(req.has(live ? b : b.toLowerCase())) - Number(req.has(live ? a : a.toLowerCase())));
    const shown = max ? list.slice(0, max) : list, extra = list.length - shown.length;
    return shown.map((s) => req.has(live ? s : s.toLowerCase())
      ? `<span class="tag match">${ICON.checkSm}${esc(s)}<span class="sr"> (required)</span></span>`
      : `<span class="tag">${esc(s)}</span>`).join('') + (extra > 0 ? `<span class="tag" title="${esc(list.slice(max).join(', '))}">+${extra}</span>` : '');
  }
  function bodyHTML(text) {
    const out = []; let list = [];
    const flush = () => { if (list.length) { out.push(`<ul>${list.map((l) => `<li>${esc(l)}</li>`).join('')}</ul>`); list = []; } };
    String(text || '').split('\n').forEach((line) => {
      if (/^\s*-\s+/.test(line)) list.push(line.replace(/^\s*-\s+/, ''));
      else { flush(); if (line.trim()) out.push(`<p>${esc(line)}</p>`); }
    });
    flush();
    return out.join('');
  }
  /* Where an application's interview stands, for table cells. */
  /* "Today, 10:00 AM" / "Wed, 11:00 AM" this week / "Nov 4" further out: short enough for a table cell. */
  function whenShort(iso) {
    const days = Math.round((new Date(ymdOf(iso)) - new Date(ymdOf(NOW))) / 864e5);
    if (days === 0) return `Today, ${fmtTime(iso)} PT`;
    if (days === 1) return `Tomorrow, ${fmtTime(iso)} PT`;
    if (days > 1 && days < 7) return `${fmt(iso, { weekday: 'short' })}, ${fmtTime(iso)} PT`;
    return fmtShort(iso);
  }
  function ivCellHTML(a) {
    if (a.slot) {
      const past = new Date(a.slot.start) < NOW;
      return `<span class="ivcell${past ? ' past' : ''}" title="${esc(fmtDate(a.slot.start))}, ${esc(fmtRange(a.slot.start, a.slot.end))} PT">${ICON.cal}<span>${past ? 'Held ' + esc(fmtShort(a.slot.start)) : esc(whenShort(a.slot.start))}</span></span>`;
    }
    if (a.status === 'Interviewing') return `<span class="ivcell todo">${ICON.clock}<span>Waiting to book</span></span>`;
    return '<span class="ivcell none"><span>Not scheduled</span></span>';
  }

  /* ---------- Toast ---------- */
  let toastTimer, toastUndo = null;
  function toast(msg, { undo, error } = {}) {
    let wrap = $('.toast-wrap');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = 'toast-wrap';
      wrap.setAttribute('aria-live', 'polite');
      wrap.innerHTML = '<div class="toast" role="status"><span class="toast-msg"></span><button type="button" hidden>Undo</button></div>';
      document.body.appendChild(wrap);
      $('button', wrap).addEventListener('click', () => { const fn = toastUndo; toastUndo = null; $('.toast', wrap).classList.remove('show'); if (fn) fn(); });
    }
    const el = $('.toast', wrap);
    clearTimeout(toastTimer);
    $('.toast-msg', el).textContent = msg;
    toastUndo = undo || null;
    $('button', el).hidden = !undo;
    el.classList.toggle('error', !!error);
    el.classList.remove('show'); void el.offsetWidth; el.classList.add('show');
    toastTimer = setTimeout(() => el.classList.remove('show'), error ? 4600 : undo ? 4200 : 2800);
  }

  /* ---------- Popovers ---------- */
  function closePopovers() {
    $$('.popover.open').forEach((p) => p.classList.remove('open'));
    $$('[aria-expanded="true"][aria-controls]').forEach((b) => b.setAttribute('aria-expanded', 'false'));
  }
  function setupPopover(btn, pop, onOpen) {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = !pop.classList.contains('open');
      closePopovers();
      if (open) { pop.classList.add('open'); btn.setAttribute('aria-expanded', 'true'); if (onOpen) onOpen(); }
    });
  }
  document.addEventListener('click', (e) => { if (!e.target.closest('.popover')) closePopovers(); });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const btn = $('[aria-expanded="true"][aria-controls]');
    if (!btn) return;
    closePopovers(); btn.focus();
  });

  function moveIndicator(indicator, target, horizontal) {
    if (!indicator || !target) { if (indicator) indicator.style.opacity = '0'; return; }
    indicator.style.opacity = '1';
    if (horizontal) {
      indicator.style.width = target.offsetWidth + 'px';
      indicator.style.height = target.offsetHeight + 'px';
      indicator.style.transform = `translate(${target.offsetLeft}px, ${target.offsetTop}px)`;
    } else {
      indicator.style.height = target.offsetHeight + 'px';
      indicator.style.transform = `translateY(${target.offsetTop}px)`;
    }
  }

  /* ---------- Shell ---------- */
  const NAV = [
    { key: 'dashboard', label: 'Dashboard', icon: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9v11h14V9"/><path d="M10 20v-6h4v6"/>' },
    { key: 'jobs', label: 'My Jobs', icon: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5h6v2M3 12.5h18"/>', badge: 'jobs' },
    { key: 'applicants', label: 'Applicants', icon: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.3c2.1.7 3.5 2.8 3.5 5.7"/>', badge: 'pending' },
    { key: 'interviews', label: 'Interviews', icon: '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/>', badge: 'waiting' },
    { key: 'company', label: 'Company Profile', icon: '<path d="M4 21V5a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v16"/><path d="M15 10h4a1 1 0 0 1 1 1v10"/><path d="M8 8h3M8 12h3M8 16h3M3 21h18"/>' },
  ];
  const BADGE_SR = { jobs: (n) => `, ${n} active`, pending: (n) => `, ${n} pending review`, waiting: (n) => `, ${n} waiting to book` };

  function renderChrome(page) {
    const sb = $('#sidebar'), tb = $('#topbar');
    if (!sb || !tb) return;
    sb.innerHTML = `
      <a href="dashboard" class="brand" aria-label="Matchwork home">
        <svg width="24" height="22" viewBox="0 0 24 22" aria-hidden="true"><circle cx="6.5" cy="5" r="4.5" fill="#1E2A24"/><circle cx="16.5" cy="6" r="4" fill="#7FAE8E"/><rect x="0" y="10" width="12" height="12" rx="4" fill="#1E2A24"/><rect x="11" y="11" width="13" height="11" rx="4" fill="#7FAE8E"/></svg>
        <span>Matchwork</span>
      </a>
      <div class="portal-label">Employer Portal</div>
      <nav class="nav" aria-label="Employer portal">
        <span class="nav-indicator" aria-hidden="true"></span>
        ${NAV.map((n) => `<a href="${n.key}" class="nav-item"${n.key === page ? ' aria-current="page"' : ''}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${n.icon}</svg>
          <span class="label">${n.label}</span>${n.badge ? `<span class="badge" data-badge="${n.badge}" aria-hidden="true"></span><span class="sr" data-badge-sr="${n.badge}"></span>` : ''}
        </a>`).join('')}
      </nav>
      <div class="divider"></div>
      <a href="/sign-in#recruiter" class="nav-item logout">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 4H5v16h5"/><path d="M14 8l4 4-4 4"/><path d="M18 12H9"/></svg>
        <span class="label">Log Out</span>
      </a>
      <div class="sidebar-spacer"></div>
      <svg class="deco-bl" width="228" height="140" viewBox="0 0 228 140" aria-hidden="true"><path d="M0 10 C40 0 70 30 105 60 C140 90 180 110 228 140 L0 140Z" fill="#F2F3F3"/><path d="M0 70 C40 60 80 85 110 110 C125 122 140 132 150 140 L0 140Z" fill="#ECEEEE"/><rect x="123" y="33" width="14" height="14" transform="rotate(45 130 40)" fill="#EDEFEE"/></svg>`;

    const q = params().get('q') || '';
    tb.innerHTML = `
      <form class="search" id="searchForm" role="search" autocomplete="off" action="applicants">
        <label class="search-field">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m20 20-4.8-4.8"/></svg>
          <span class="sr">Search applicants by name, skill or job</span>
          <input id="search" name="q" type="search" placeholder="Search applicants, skills or jobs…" value="${esc(q)}" enterkeyhint="search">
        </label>
        <button type="submit" class="search-btn">Search</button>
      </form>
      <div class="topbar-right">
        <div class="bell-wrap">
          <button type="button" class="icon-btn" id="bellBtn" aria-haspopup="true" aria-expanded="false" aria-controls="notifPop">
            <svg class="bell" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#202124" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>
            <span class="dot" id="bellDot"></span>
          </button>
          <div class="popover notif" id="notifPop" role="dialog" aria-label="Notifications"></div>
        </div>
        <div class="account">
          <button type="button" class="account-btn" id="accountBtn" aria-haspopup="menu" aria-expanded="false" aria-controls="accountMenu">
            <span class="avatar" id="avatar"></span>
            <svg class="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#202124" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
          </button>
          <div class="popover" id="accountMenu" role="menu" aria-label="Account">
            <a href="company" class="menu-item" role="menuitem">Company Profile</a>
            ${live ? '' : '<button type="button" class="menu-item" role="menuitem" id="resetDemo">Reset demo data</button>'}
            <div class="menu-sep" role="separator"></div>
            <a href="/sign-in#recruiter" class="menu-item danger" role="menuitem">Log Out</a>
          </div>
        </div>
      </div>`;
    fillChrome();
  }

  function setBadge(key, n) {
    const b = $(`[data-badge="${key}"]`), sr = $(`[data-badge-sr="${key}"]`);
    if (!b) return;
    const prev = Number(b.textContent) || 0;
    b.textContent = n;
    b.classList.toggle('show', n > 0);
    sr.textContent = n ? BADGE_SR[key](n) : '';
    if (n !== prev && n > 0 && document.body.classList.contains('ready') && !reduceMotion) { b.classList.remove('bump'); void b.offsetWidth; b.classList.add('bump'); }
  }
  function fillChrome() {
    const c = state.company;
    const av = $('#avatar');
    if (!av) return;
    av.textContent = initials(c.name);
    $('#accountBtn').setAttribute('aria-label', `Account menu for ${c.name}`);
    setBadge('jobs', ownJobs().filter((j) => j.status === 'Active').length);
    setBadge('pending', ownApps().filter((a) => a.status === 'Pending').length);
    setBadge('waiting', awaitingBooking().length);
    renderNotifs();
  }
  function notifications() {
    const items = [];
    ownApps().filter((a) => a.status === 'Pending' && NOW - new Date(a.appliedAt) < 3 * 864e5 && new Date(a.appliedAt) <= NOW).map(view)
      .sort((a, b) => new Date(b.appliedAt) - new Date(a.appliedAt))
      .forEach((a) => items.push({ href: `applicants?job=${encodeURIComponent(a.jobId)}#${a.id}`, kind: 'app', title: 'New applicant', text: `${a.name} applied to ${a.job.title}`, when: ago(a.appliedAt) }));
    ownApps().filter((a) => a.slotId && new Date(slot(a.slotId).start) > NOW).map(view)
      .sort((a, b) => new Date(a.slot.start) - new Date(b.slot.start))
      .forEach((a) => items.push({ href: 'interviews', kind: 'iv', title: 'Interview booked', text: `${a.name}, ${a.job.title}`, when: `${fmtDate(a.slot.start)} · ${fmtTime(a.slot.start)} PT` }));
    return items;
  }
  function renderNotifs() {
    const pop = $('#notifPop');
    if (!pop) return;
    const items = notifications();
    /* On the served site, "Mark all read" remembers which notifications were seen, so a new
       one shows as unread again. The server always sends notifRead: false. */
    const fingerprint = items.map((n) => `${n.title}|${n.text}|${n.when}`).join('\n');
    const NOTIF_KEY = 'rw.notifSeen.' + ME;
    if (live) { try { state.notifRead = !!items.length && localStorage.getItem(NOTIF_KEY) === fingerprint; } catch (e) { /* keep in memory */ } }
    pop.innerHTML = `<div class="notif-head">Notifications <button type="button" id="markRead"${state.notifRead || !items.length ? ' disabled' : ''}>${state.notifRead || !items.length ? 'All caught up' : 'Mark all read'}</button></div>` +
      (items.length ? items.slice(0, 6).map((n) => `<a href="${esc(n.href)}" class="notif-item">
        ${n.kind === 'app'
          ? '<span class="notif-icon" style="background:var(--green-100)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1F4D34" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/></svg></span>'
          : '<span class="notif-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#5B3FC4" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><rect x="4" y="5" width="16" height="16" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/></svg></span>'}
        <div><strong>${esc(n.title)}</strong>, ${esc(n.text)}<time>${esc(n.when)}</time></div></a>`).join('')
        : '<div class="notif-item">No notifications yet.</div>');
    $('#markRead').addEventListener('click', (e) => {
      e.stopPropagation();
      if (live) { try { localStorage.setItem(NOTIF_KEY, fingerprint); } catch (err) { /* keep in memory */ } }
      state.notifRead = true; persist();
    });
    $('#bellDot').classList.toggle('hide', state.notifRead || !items.length);
    $('#bellBtn').setAttribute('aria-label', `Notifications${state.notifRead || !items.length ? ', none new' : `, ${items.length} new`}`);
  }

  let navSlideFrom = null;

  function rememberNavPosition() {
    const indicator = $('.nav-indicator');
    if (reduceMotion || !indicator) return;
    const transform = getComputedStyle(indicator).transform;
    navSlideFrom = transform === 'none' ? null : new DOMMatrixReadOnly(transform).m42;
  }

  /* Start from the visible highlight position, even if the previous slide is still running. */
  function slideNav() {
    const ind = $('.nav-indicator'), cur = $('.nav [aria-current="page"]');
    if (!ind || !cur) return;
    let from = null;
    try { from = sessionStorage.getItem('rw.nav'); sessionStorage.removeItem('rw.nav'); } catch (e) { /* ignore */ }
    const prev = from ? $$('.nav .nav-item').find((a) => a.getAttribute('href') === from) : null;
    const start = navSlideFrom ?? prev?.offsetTop;
    navSlideFrom = null;
    moveIndicator(ind, cur);
    if (!reduceMotion && ind.animate && start != null && Math.abs(start - cur.offsetTop) > 0.5) {
      ind.animate([{ transform: `translateY(${start}px)` }, { transform: ind.style.transform }],
        { duration: 250, easing: 'cubic-bezier(.32,.72,.28,1)' });
    }
  }
  window.addEventListener('pagehide', () => {
    const c = $('.nav [aria-current="page"]');
    try { if (c) sessionStorage.setItem('rw.nav', c.getAttribute('href')); } catch (e) { /* ignore */ }
  });

  /* Scale the UI up on large screens toward the 1456x819 design, like the candidate pages. */
  function fitScale() {
    const vw = window.innerWidth, vh = window.innerHeight;
    const z = Math.min(vw / 1456, vh / 819, 1.4);
    const ok = z > 1.03 && vw > 1180 && window.CSS && CSS.supports('zoom', '1');
    document.documentElement.style.setProperty('--mw-zoom', ok ? z.toFixed(3) : '1');
  }
  fitScale();
  window.addEventListener('resize', fitScale);

  function mountShell(page, opts = {}) {
    if (!$('#notifPop')) renderChrome(page);
    const form = $('#searchForm');
    if (opts.onSearch) {
      let t;
      const run = () => opts.onSearch($('#search').value.trim());
      $('#search').addEventListener('input', () => { clearTimeout(t); t = setTimeout(run, 140); });
      form.addEventListener('submit', (e) => { e.preventDefault(); clearTimeout(t); run(); });
    }
    setupPopover($('#bellBtn'), $('#notifPop'));
    setupPopover($('#accountBtn'), $('#accountMenu'), () => $('#accountMenu .menu-item').focus());
    const reset = $('#resetDemo');
    if (reset) reset.addEventListener('click', () => { resetDemo(); location.reload(); });
    listeners.add(fillChrome);
    const fit = () => { moveIndicator($('.nav-indicator'), $('.nav [aria-current="page"]')); if (opts.onLayout) opts.onLayout(); };
    slideNav();
    requestAnimationFrame(() => { if (opts.onLayout) opts.onLayout(); });
    requestAnimationFrame(() => requestAnimationFrame(() => document.body.classList.add('ready')));
    (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(() => requestAnimationFrame(fit));
    window.addEventListener('resize', () => requestAnimationFrame(fit));
    /* Another tab changed the demo data: re-render from the new copy. */
    window.addEventListener('storage', (e) => { if (e.key === KEY) location.reload(); });
    window.addEventListener('pageshow', (e) => { if (e.persisted) location.reload(); });
  }

  /* Cross-page view transitions (shell.css) are skipped when the page is hidden or already shown;
     that is expected, so their promises shouldn't surface as errors. */
  ['pagereveal', 'pageswap'].forEach((type) => window.addEventListener(type, (e) => {
    const vt = e.viewTransition;
    if (vt) [vt.ready, vt.finished, vt.updateCallbackDone].forEach((p) => p && p.catch(() => {}));
  }));

  /* ---------- Single-file router ----------
     In the bundle, tab links become ?page=<tab>&<params>#<hash> on the same file. The loader
     re-renders the page from window.__RW_PAGES, which also clears this page's window listeners. */
  if (BUNDLE) {
    const PAGE_KEYS = NAV.map((n) => n.key);
    const resolve = (href) => {
      const u = new URL(href, 'http://bundle/recruiter/' + (params().get('page') || 'dashboard'));
      if (u.origin !== 'http://bundle' || !u.pathname.startsWith('/recruiter/')) return null;
      const key = u.pathname.slice(11).replace(/\.html$/, '') || 'dashboard';
      if (!PAGE_KEYS.includes(key)) return null;
      const p = new URLSearchParams(u.search); p.delete('page');
      return { key, url: location.pathname + '?' + ['page=' + key, p.toString()].filter(Boolean).join('&') + u.hash };
    };
    const go = (r, push) => {
      /* Unsaved edits get the same warning a real page change gives. */
      const leave = new Event('beforeunload', { cancelable: true });
      window.dispatchEvent(leave);
      if (leave.defaultPrevented && !window.confirm('Leave this page? Changes you made may not be saved.')) return;
      const cur = $('.nav [aria-current="page"]');
      try { if (cur) sessionStorage.setItem('rw.nav', cur.getAttribute('href')); } catch (e) { /* ignore */ }
      if (push) {
        const want = new URL(r.url, location.href);
        try { history.pushState({ rw: r.key }, '', want); } catch (e) { /* URL can't change here */ }
        window.__rwLoc = location.search === want.search && location.hash === want.hash ? null : { search: want.search, hash: want.hash };
      } else window.__rwLoc = null;
      window.__rwRender(r.key);
    };
    document.addEventListener('click', (e) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = e.target.closest && e.target.closest('a[href]');
      if (!a || (a.target && a.target !== '_self')) return;
      const href = a.getAttribute('href');
      if (!href || href.startsWith('#') || /^(mailto|https?):/.test(href)) return;
      if (/^\/(login|sign-in)/.test(href)) { e.preventDefault(); toast('The sign-in page is not part of this file'); return; }
      const r = resolve(href);
      if (!r) return;
      e.preventDefault();
      go(r, true);
    });
    document.addEventListener('submit', (e) => {
      const f = e.target;
      if (e.defaultPrevented || !(f instanceof HTMLFormElement) || !f.getAttribute('action')) return;
      const p = new URLSearchParams(new FormData(f));
      Array.from(p.keys()).forEach((k) => { if (!p.get(k)) p.delete(k); });
      const r = resolve(f.getAttribute('action') + (p.toString() ? '?' + p : ''));
      if (!r) return;
      e.preventDefault();
      go(r, true);
    });
    window.addEventListener('popstate', () => go({ key: new URLSearchParams(location.search).get('page') || 'dashboard' }, false));
    /* Page scripts keep the URL in step with replaceState; mirror that into __rwLoc when it can't. */
    /* history outlives each re-render, so wrap it only once. */
    if (!history.__rwReplace) {
      history.__rwReplace = history.replaceState;
      history.replaceState = function (st, t, to) {
        const r = history.__rwReplace.apply(history, arguments);
        if (window.__rwLoc && to) { const u = new URL(to, location.href); window.__rwLoc = { search: u.search, hash: u.hash }; }
        return r;
      };
    }
  }

  /* Dead "#" links never jump. */
  document.addEventListener('click', (e) => { const a = e.target.closest && e.target.closest('a[href="#"]'); if (a) e.preventDefault(); });

  function startTabRouter() {
    const pages = NAV.map((item) => item.key);
    const directory = new URL('./', location.href);
    const current = new URL(location.href);
    const extension = current.pathname.endsWith('.html') ? '.html' : '';
    const cache = new Map();
    const pageListeners = [];
    let visibleURL = current.href;
    let navigation = 0;

    function resolve(href) {
      const target = new URL(href, location.href);
      if (target.origin !== directory.origin || !target.pathname.startsWith(directory.pathname)) return null;
      const key = target.pathname.slice(directory.pathname.length).replace(/\.html$/, '');
      return pages.includes(key) ? { key, target } : null;
    }
    if (!resolve(current)) return;
    const replaceState = history.replaceState.bind(history);
    history.replaceState = (...args) => {
      replaceState(...args);
      visibleURL = location.href;
    };

    async function fetchText(url) {
      const response = await fetch(url, { credentials: 'same-origin' });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.text();
    }

    function loadPage(key) {
      if (!cache.has(key)) {
        const url = new URL(key + extension, directory);
        const load = fetchText(url).then(async (html) => {
          const page = new DOMParser().parseFromString(html, 'text/html');
          if (!page.querySelector('.app #topbar')) throw new Error('Expected a recruiter page');
          const scripts = await Promise.all(Array.from(page.body.querySelectorAll('script'), async (script) => {
            const src = script.getAttribute('src');
            if (!src) return script.textContent;
            const asset = new URL(src, url);
            if (asset.href !== new URL('assets/dashboard.js', directory).href) throw new Error('Unexpected page script');
            return fetchText(asset);
          }));
          return { page, scripts };
        });
        cache.set(key, load);
        load.catch(() => cache.delete(key));
      }
      return cache.get(key);
    }

    function renderPage({ page, scripts }, target, push) {
      const focusedInNav = document.activeElement?.closest('.nav');
      const previous = $('.nav [aria-current="page"]')?.getAttribute('href');
      rememberNavPosition();
      try { if (previous) sessionStorage.setItem('rw.nav', previous); } catch (e) { /* storage unavailable */ }
      if (push) history.pushState(null, '', target);
      pageListeners.splice(0).forEach(([owner, type, fn, options]) => owner.removeEventListener(type, fn, options));
      listeners.clear();
      document.title = page.title;
      document.head.querySelectorAll('style').forEach((style) => style.remove());
      page.head.querySelectorAll('style').forEach((style) => document.head.append(document.importNode(style, true)));

      const body = document.importNode(page.body, true);
      body.querySelectorAll('script').forEach((old, index) => {
        const script = document.createElement('script');
        script.textContent = scripts[index];
        old.replaceWith(script);
      });
      document.body.className = page.body.className;
      document.body.replaceChildren(...body.childNodes);
      visibleURL = location.href;
      const active = $('.nav [aria-current="page"]');
      if (focusedInNav) active?.focus({ preventScroll: true });
      if (previous !== active?.getAttribute('href') && !reduceMotion) {
        $('.main')?.animate?.([{ opacity: .96 }, { opacity: 1 }], { duration: 130, easing: 'ease-out' });
      }
    }

    async function navigate({ key, target }, push) {
      const sequence = ++navigation;
      if (!hasRecruiterSession()) {
        location.replace('/sign-in#recruiter');
        return;
      }
      const leave = new Event('beforeunload', { cancelable: true });
      window.dispatchEvent(leave);
      if (leave.defaultPrevented && !window.confirm('Leave this page? Changes you made may not be saved.')) {
        if (!push) history.pushState(null, '', visibleURL);
        return;
      }
      try {
        const page = await loadPage(key);
        if (live) refresh(true);
        if (sequence === navigation) renderPage(page, target, push);
      } catch (error) {
        if (sequence === navigation) {
          if (push) location.assign(target);
          else location.reload();
        }
      }
    }

    document.addEventListener('click', (event) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = event.target.closest?.('a[href]');
      if (!link || (link.target && link.target !== '_self') || link.hasAttribute('download')) return;
      const href = link.getAttribute('href');
      if (!href || href.startsWith('#')) return;
      const route = resolve(href);
      if (!route) return;
      event.preventDefault();
      if (route.target.href !== location.href) navigate(route, true);
      else navigation++;
    });

    document.addEventListener('submit', (event) => {
      const form = event.target;
      if (event.defaultPrevented || form.method !== 'get' || !form.getAttribute('action')) return;
      const route = resolve(form.action);
      if (!route) return;
      event.preventDefault();
      const query = new URLSearchParams(new FormData(form));
      route.target.search = new URLSearchParams(Array.from(query).filter(([, value]) => value !== ''));
      navigate(route, true);
    });

    window.addEventListener('popstate', () => {
      const route = resolve(location.href);
      if (!route) return;
      const visible = new URL(visibleURL);
      if (visible.pathname === location.pathname && visible.search === location.search) {
        navigation++;
        visibleURL = location.href;
        return;
      }
      navigate(route, false);
    });

    // Future window and document listeners belong to the current page.
    [window, document].forEach((owner) => {
      const add = owner.addEventListener.bind(owner);
      owner.addEventListener = (type, fn, options) => {
        pageListeners.push([owner, type, fn, options]);
        add(type, fn, options);
      };
    });
    const prefetch = () => pages.forEach((key) => loadPage(key).catch(() => {}));
    if (window.requestIdleCallback) requestIdleCallback(prefetch, { timeout: 1500 });
    else setTimeout(prefetch, 300);
  }

  if (live) {
    const update = () => { try { refresh(); } catch (error) { console.warn('Applicant refresh failed', error); } };
    window.addEventListener('focus', update);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) update(); });
    setInterval(() => { if (!document.hidden) update(); }, 5000);
  }

  window.RW = {
    $, $$, esc, reduceMotion, params, hash, url, NOW, TZ, TZ_LABEL, SLOT_MIN, fmt, fmtDate, fmtLong, fmtShort, fmtTime, fmtSlotTime, fmtRange, dayKey, ymdOf, ptToUtc, ago,
    matchScore, normalizeSkills, hasSkill, cleanSkills, skillKey, refresh, live,
    get state() { return state; }, persist, resetDemo, onChange: (fn) => listeners.add(fn),
    company, candidate, jobs, job, applicants, allApplicants, application, awaitingBooking, ownSlots, openSlots, slot, view,
    JOB_TYPES, STATUSES, SIZES, createJob, updateJob, deleteJob, deleteBlockers, deleteBlockedText, pickJob, setStatus, createSlot, deleteSlot, updateCompany,
    ICON, logoHTML, avatarHTML, initials, scoreHTML, statusHTML, candTagsHTML, bodyHTML, ivCellHTML, whenShort,
    toast, setupPopover, closePopovers, moveIndicator, renderChrome, mountShell, notifications,
  };
  if (hosted && hasRecruiterSession()) startTabRouter();
})();
