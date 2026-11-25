/* Matchwork candidate prototype: shared data, matching, demo store and app shell.
   Front-end only. In the full-stack build these become API calls; the rules here
   (match score, apply-once, booking eligibility) mirror the server contract in REQUIREMENTS.md. */
(function () {
  'use strict';

  /* Served by Flask, the page loads its data from the JSON API. file:// and the
     single-file build keep the local demo store. */
  const HOSTED = !window.__MW_PAGES && /^https?:$/.test(location.protocol);
  function api(method, path, payload) {
    const xhr = new XMLHttpRequest();
    xhr.open(method, path, false);
    xhr.withCredentials = true;
    if (payload !== undefined) xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.send(payload === undefined ? null : JSON.stringify(payload));
    let data = null;
    try { data = xhr.responseText ? JSON.parse(xhr.responseText) : null; } catch (e) { data = { message: 'Unexpected response' }; }
    return { status: xhr.status, data };
  }
  let boot = null;
  if (HOSTED) {
    const me = api('GET', '/api/auth/me');
    if (!(me.status === 200 && me.data && me.data.role === 'Candidate')) location.replace('/sign-in#candidate');
    else {
      const loaded = api('GET', '/api/candidate/bootstrap');
      if (loaded.status === 200) boot = loaded.data;
      else location.replace('/sign-in#candidate');
    }
    document.addEventListener('click', (e) => {
      const a = e.target.closest && e.target.closest('a[href^="/sign-in"]');
      if (!a) return;
      e.preventDefault();
      api('POST', '/api/auth/logout');
      location.href = a.getAttribute('href');
    }, true);
  }

  /* ---------- Utilities ---------- */
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* All times are stored in UTC and shown in Pacific Time. */
  const TZ = 'America/Los_Angeles';
  const TZ_LABEL = 'Pacific Time (PT)';
  /* The demo clock: Monday, Nov 16 2026, 9:00 AM PT. The server clock replaces it when signed in. */
  let NOW = new Date(boot && boot.now ? boot.now : '2026-11-16T17:00:00Z');
  const fmt = (d, opts) => new Intl.DateTimeFormat('en-US', { timeZone: TZ, ...opts }).format(new Date(d));
  const fmtDate = (d) => fmt(d, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
  const fmtShort = (d) => fmt(d, { month: 'short', day: 'numeric' });
  const fmtTime = (d) => fmt(d, { hour: 'numeric', minute: '2-digit' });
  const fmtSlotTime = (d) => fmt(d, { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
  function fmtRange(s, e) {
    const from = fmtSlotTime(s), to = fmtSlotTime(e);
    if (from.split(' ').at(-1) !== to.split(' ').at(-1)) return `${from}–${to}`;
    const a = fmtTime(s), b = fmtTime(e);
    return `${a.slice(-2) === b.slice(-2) ? a.slice(0, -3) : a}–${b} PT`;
  }
  const dayKey = (d) => fmt(d, { year: 'numeric', month: '2-digit', day: '2-digit' });
  function ago(d) {
    const days = Math.round((NOW - new Date(d)) / 864e5);
    if (days <= 0) return 'Today';
    if (days === 1) return 'Yesterday';
    if (days < 7) return `${days} days ago`;
    if (days < 14) return '1 week ago';
    if (days < 31) return `${Math.floor(days / 7)} weeks ago`;
    if (days < 60) return "1 month ago";
    return `${Math.floor(days / 30)} months ago`;
  }

  /* ---------- Matching (FP-MATCH-1) ----------
     One implementation for both portals: /shared/match.js (window.MWMatch). */
  const { normalizeSkills, matchScore, hasSkill, compareJobs: byMatch } = window.MWMatch;

  /* ---------- Companies + jobs ----------
     Read-only job data lives in assets/jobs.json: { companies: { name: {...} }, jobs: [...] }.
     Demo jobs have short ids (g, m, tw...); real postings start with "r-" and carry a source link.
     It loads synchronously so every page renders its first frame with data (no flash between tabs).
     The single-file build inlines the same file as window.__MW_DATA.
     In the full-stack build this becomes a call to the jobs API. */
  function loadData() {
    if (window.__MW_DATA) return window.__MW_DATA;
    /* jobs.json sits next to this script, so resolve it from the script's own URL. */
    const url = new URL('jobs.json', document.currentScript.src).href;
    try {
      const xhr = new XMLHttpRequest();
      xhr.open('GET', url, false);
      xhr.send();
      if (xhr.status === 200 || (xhr.status === 0 && xhr.responseText)) return JSON.parse(xhr.responseText);
      console.error('Matchwork: could not load job data (' + xhr.status + ') from ' + url);
    } catch (e) {
      console.error('Matchwork: could not load job data from ' + url, e);
    }
    return { companies: {}, jobs: [] };
  }
  const DATA = boot ? { companies: boot.companies, jobs: boot.jobs } : (HOSTED ? { companies: {}, jobs: [] } : loadData());
  const COMPANIES = DATA.companies || {};
  const companyFor = (job) => COMPANIES[job.owner ?? job.company];
  /* Logos live on the company (tools/fetch-logos.mjs fills companies[name].logo/w/h), so every
     posting from a company shares one file. A logo set on the job itself still wins. */
  const JOBS = (DATA.jobs || []).map((j) => {
    const c = companyFor(j);
    return !j.logo && c && c.logo ? { ...j, logo: c.logo, w: c.w, h: c.h } : j;
  });

  /* Employer availability: 30-minute slots, stored in UTC. */
  const s = (id, company, isoUtc, extra) => ({ id, company, start: isoUtc, end: new Date(new Date(isoUtc).getTime() + 30 * 60e3).toISOString(), ...extra });
  const SLOTS_SEED = [
    s('hh-1', 'Harbor Health', '2026-11-05T22:00:00Z', { bookedBy: 'a3' }),
    s('m-1', 'Meta', '2026-11-24T18:00:00Z', { bookedBy: 'a1' }),
    s('m-2', 'Meta', '2026-11-24T19:00:00Z'),
    s('tw-1', 'Tidewater Labs', '2026-11-18T18:00:00Z'),
    s('tw-2', 'Tidewater Labs', '2026-11-18T18:30:00Z'),
    s('tw-3', 'Tidewater Labs', '2026-11-18T21:00:00Z', { bookedBy: 'other' }),
    s('tw-4', 'Tidewater Labs', '2026-11-18T22:30:00Z'),
    s('tw-5', 'Tidewater Labs', '2026-11-19T17:00:00Z', { race: true }),
    s('tw-6', 'Tidewater Labs', '2026-11-19T17:30:00Z'),
    s('tw-7', 'Tidewater Labs', '2026-11-19T19:00:00Z'),
    s('tw-8', 'Tidewater Labs', '2026-11-19T23:00:00Z'),
    s('tw-9', 'Tidewater Labs', '2026-11-19T23:30:00Z'),
    s('tw-10', 'Tidewater Labs', '2026-11-20T18:00:00Z'),
    s('tw-11', 'Tidewater Labs', '2026-11-20T21:30:00Z'),
    s('tw-12', 'Tidewater Labs', '2026-11-23T19:00:00Z'),
    s('tw-13', 'Tidewater Labs', '2026-11-23T19:30:00Z'),
    s('tw-14', 'Tidewater Labs', '2026-11-24T00:00:00Z'),
    s('tw-0', 'Tidewater Labs', '2026-11-13T18:00:00Z'),
  ];

  const RESUME_SEED = `John Doe
San Jose, CA

SUMMARY
Backend engineer with 4 years of experience building data-heavy services in Python and Java. I like turning slow, fragile systems into fast, boring ones.

EXPERIENCE
Software Engineer, Cascade Payments (2022 to present)
- Split a monolithic billing service into four services; p99 latency fell from 900 ms to 180 ms
- Built a ledger reconciliation job in Python and SQL that checks 3 million rows nightly
- On-call lead for the payments platform; wrote the team's incident runbooks

Software Engineer Intern, Brightline Maps (Summer 2021)
- Added caching to the tile server in Java, cutting median load time by 40%

EDUCATION
B.S. Computer Science, San Jose State University, 2021

SKILLS
Python, Java, SQL, distributed systems, React, PostgreSQL, Docker`;

  const DEFAULT_STATE = () => ({
    v: 2,
    profile: { name: 'John Doe', headline: 'Backend engineer focused on data-heavy services', location: 'San Jose, CA', email: 'john.doe@example.com',
      skills: ['Python', 'Java', 'SQL', 'Distributed Systems', 'React'], resume: RESUME_SEED, resumeUpdated: '2026-11-08T19:20:00Z', extras: false },
    saved: { g: '2026-11-14T20:00:00Z', l: '2026-11-13T18:00:00Z', pb: '2026-11-08T18:00:00Z' },
    applications: [
      { id: 'a1', jobId: 'm', status: 'Interviewing', appliedAt: '2026-11-02T18:00:00Z', slotId: 'm-1',
        events: [['Applied', '2026-11-02T18:00:00Z'], ['Moved to Interviewing', '2026-11-10T22:00:00Z'], ['Interview booked', '2026-11-11T17:30:00Z']] },
      { id: 'a2', jobId: 'tw', status: 'Interviewing', appliedAt: '2026-11-06T18:00:00Z', slotId: null,
        events: [['Applied', '2026-11-06T18:00:00Z'], ['Moved to Interviewing', '2026-11-15T00:30:00Z']] },
      { id: 'a3', jobId: 'hh', status: 'Accepted', appliedAt: '2026-10-12T18:00:00Z', slotId: 'hh-1',
        events: [['Applied', '2026-10-12T18:00:00Z'], ['Moved to Interviewing', '2026-10-30T18:00:00Z'], ['Interview booked', '2026-10-31T18:00:00Z'], ['Accepted', '2026-11-12T18:00:00Z']] },
      { id: 'a4', jobId: 'n', status: 'Rejected', appliedAt: '2026-10-16T18:00:00Z', slotId: null,
        events: [['Applied', '2026-10-16T18:00:00Z'], ['Rejected', '2026-11-04T18:00:00Z']] },
      { id: 'a5', jobId: 'kr', status: 'Pending', appliedAt: '2026-11-11T18:00:00Z', slotId: null,
        events: [['Applied', '2026-11-11T18:00:00Z']] },
    ],
    slots: SLOTS_SEED,
    notifRead: false,
  });

  /* ---------- Store ---------- */
  const KEY = 'matchwork.candidate.v1';
  const live = !!boot;
  let state;
  if (live) {
    state = boot.state;
    try {
      const saved = JSON.parse(sessionStorage.getItem('mw.saved') || '{}');
      if (saved && typeof saved === 'object') state.saved = saved;
    } catch (e) { /* keep the empty server list */ }
  } else if (!HOSTED) {
    try { state = JSON.parse(localStorage.getItem(KEY)); } catch (e) { state = null; }
    if (!state || state.v !== 2) state = DEFAULT_STATE();
  } else {
    state = { v: 2, profile: { name: '', skills: [], resume: '', headline: '', location: '', email: '', extras: false }, saved: {}, applications: [], slots: [], notifRead: false };
  }
  const listeners = new Set();
  const REV_KEY = KEY + '.rev';
  const readRev = () => { try { return localStorage.getItem(REV_KEY) || ''; } catch (e) { return ''; } };
  let loadedRev = readRev();
  function persist() {
    if (!live) {
      try { localStorage.setItem(KEY, JSON.stringify(state)); loadedRev = String(Date.now()); localStorage.setItem(REV_KEY, loadedRev); } catch (e) { /* storage unavailable: keep in memory */ }
    }
    listeners.forEach((fn) => fn(state));
  }
  function resetDemo() {
    if (live) { try { sessionStorage.removeItem('mw.saved'); } catch (e) { /* ignore */ } location.reload(); return; }
    state = DEFAULT_STATE(); persist();
  }
  function apiResult(res, fallback) {
    if (res.status >= 400 || !res.data || res.data.ok === false) return { ok: false, code: res.status || 400, message: (res.data && res.data.message) || fallback };
    return null;
  }

  function jobs() {
    const skills = state.profile.skills;
    return JOBS.map((j) => ({ ...j, tags: j.skills, match: matchScore(skills, j.skills) })).sort(byMatch);
  }
  const job = (id) => jobs().find((j) => j.id === id);
  const appForJob = (jobId) => state.applications.find((a) => a.jobId === jobId);
  const slot = (id) => state.slots.find((x) => x.id === id);
  const isSaved = (jobId) => Object.prototype.hasOwnProperty.call(state.saved, jobId);

  function toggleSave(jobId) {
    if (isSaved(jobId)) delete state.saved[jobId]; else state.saved[jobId] = new Date(NOW.getTime() + 60e3).toISOString();
    if (live) { try { sessionStorage.setItem('mw.saved', JSON.stringify(state.saved)); } catch (e) { /* ignore */ } }
    persist();
    return isSaved(jobId);
  }
  /* FP-CAN-3: one application per job, new ones start Pending. */
  function apply(jobId) {
    if (!job(jobId)) return { ok: false, code: 404, message: 'This job is no longer available' };
    if (appForJob(jobId)) return { ok: false, code: 409, message: 'You already applied to this job' };
    if (live) {
      const res = api('POST', '/api/candidate/applications', { jobId });
      const failed = apiResult(res, 'Could not apply');
      if (failed) return failed;
      state.applications.push(res.data.application);
      persist();
      return { ok: true, app: res.data.application };
    }
    const at = new Date(NOW.getTime() + 5 * 60e3).toISOString();
    const app = { id: 'a' + Date.now().toString(36), jobId, status: 'Pending', appliedAt: at, slotId: null, events: [['Applied', at]] };
    state.applications.push(app);
    persist();
    return { ok: true, app };
  }
  /* FP-SCHED-1/2: slots a given application may book. */
  function openSlotsFor(app) {
    const j = job(app.jobId);
    if (!j || app.status !== 'Interviewing' || app.slotId) return [];
    return state.slots.filter((x) => {
      const sameEmployer = live ? x.owner === j.owner : x.company === j.company;
      return sameEmployer && !x.bookedBy && new Date(x.start) > NOW;
    }).sort((a, b) => new Date(a.start) - new Date(b.start));
  }
  function book(appId, slotId) {
    if (live) {
      const res = api('POST', '/api/candidate/applications/' + encodeURIComponent(appId) + '/book', { slotId });
      const failed = apiResult(res, 'Could not book that time');
      if (failed) {
        if (failed.message === 'Slot already booked') { const taken = slot(slotId); if (taken) taken.bookedBy = 'other'; persist(); }
        return failed;
      }
      const app = state.applications.find((a) => a.id === appId);
      const sl = slot(slotId);
      if (app) Object.assign(app, res.data.application);
      if (sl) sl.bookedBy = appId;
      persist();
      return { ok: true, app, slot: sl };
    }
    const app = state.applications.find((a) => a.id === appId);
    const sl = slot(slotId);
    if (!app) return { ok: false, code: 403, message: 'You can only book interviews for your own applications' };
    if (!sl) return { ok: false, code: 404, message: 'That time is no longer offered' };
    if (sl.company !== job(app.jobId).company) return { ok: false, code: 403, message: 'That time belongs to a different employer' };
    if (app.status !== 'Interviewing') return { ok: false, code: 409, message: 'Only applications in Interviewing can book a time' };
    if (app.slotId) return { ok: false, code: 409, message: 'This application already has an interview booked' };
    if (new Date(sl.start) <= NOW) return { ok: false, code: 409, message: 'That time has already passed' };
    if (sl.bookedBy || sl.race) {
      /* Simulates losing a concurrent booking race: the slot is gone afterwards. */
      if (sl.race) { sl.bookedBy = 'other'; delete sl.race; persist(); }
      return { ok: false, code: 409, message: 'Slot already booked' };
    }
    sl.bookedBy = app.id;
    app.slotId = sl.id;
    app.events.push(['Interview booked', new Date(NOW.getTime() + 10 * 60e3).toISOString()]);
    persist();
    return { ok: true, app, slot: sl };
  }
  function updateProfile(patch) {
    if (!live) { Object.assign(state.profile, patch); persist(); return; }
    const res = api('POST', '/api/candidate/profile', patch);
    const failed = apiResult(res, 'Could not save your profile');
    if (failed) throw new Error(failed.message);
    state.profile = res.data.profile;
    persist();
  }
  function profileCompletion() {
    const p = state.profile;
    const items = [
      { label: 'Basic information', done: !!(p.name && p.name.trim() && p.location), href: 'profile#basics' },
      { label: 'Technical skills', done: normalizeSkills(p.skills).size >= 3, href: 'profile#skills' },
      { label: 'Resume', done: !!(p.resume && p.resume.trim().length > 80), href: 'profile#resume' },
      { label: 'Additional details', done: !!p.extras, href: 'profile#basics' },
    ];
    return { items, pct: Math.round((items.filter((i) => i.done).length / items.length) * 100) };
  }

  /* ---------- Shared markup ---------- */
  const ICON = {
    pin: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 21s-7-6.5-7-12a7 7 0 0 1 14 0c0 5.5-7 12-7 12z"/><circle cx="12" cy="9" r="2.5"/></svg>',
    bag: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5h6v2M3 12h18"/></svg>',
    clock: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    cal: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><rect x="4" y="5" width="16" height="16" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/></svg>',
    checkSm: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#2F6B4A" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
    flame: '<svg width="13" height="13" viewBox="0 0 24 24" fill="#3C9A57" aria-hidden="true"><path d="M12 2c1 4 6 6 6 12a6 6 0 0 1-12 0c0-3 2-5 3-6 0 2 1 3 2 3 0-4 1-6 1-9z"/></svg>',
    bookmark: '<svg width="18" height="18" viewBox="0 0 24 24" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M6 3h12v18l-6-4-6 4z"/></svg>',
    arrow: '<svg class="arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    check: '<svg class="check" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
    chev: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>',
    x: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
    lock: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
  };
  function logoHTML(j, size = '') {
    const mono = `<span class="logo-tile mono ${size}" style="color:${j.tint};background:${j.tileBg}" role="img" aria-label="${esc(j.company)} logo">${esc(j.mono)}</span>`;
    /* data-mono carries the monogram tile, swapped in by the error listener below if the file is missing. */
    return j.logo
      ? `<span class="logo-tile ${size}"><img src="${esc(j.logo)}" alt="${esc(j.company)} logo" width="${j.w}" height="${j.h}" data-mono="${esc(mono)}"></span>`
      : mono;
  }
  /* A logo that fails to load (deleted file, offline) falls back to the company monogram. */
  document.addEventListener('error', (e) => {
    const img = e.target;
    if (!(img instanceof HTMLImageElement) || !img.dataset.mono) return;
    img.parentElement.outerHTML = img.dataset.mono;
  }, true);
  function scoreHTML(m) {
    if (m >= 90) return `<span class="score hi">${ICON.flame}${m}% Match</span>`;
    if (m >= 60) return `<span class="score mid">${m}% Match</span>`;
    return `<span class="score lo">${m}% Match</span>`;
  }
  function tagsHTML(skills) {
    const mine = state.profile.skills;
    return skills.map((t) => hasSkill(mine, t)
      ? `<span class="tag match">${ICON.checkSm}${esc(t)}<span class="sr"> (matches your skills)</span></span>`
      : `<span class="tag">${esc(t)}<span class="sr"> (not in your skills)</span></span>`).join('');
  }
  const statusHTML = (st) => `<span class="status ${st.toLowerCase()}">${esc(st)}</span>`;
  const applyInner = (applied) => (applied ? `${ICON.check}<span>Applied</span>` : `<span>Apply</span>${ICON.arrow}`);
  function bodyHTML(text) {
    const out = []; let list = [];
    const flush = () => { if (list.length) { out.push(`<ul>${list.map((l) => `<li>${esc(l)}</li>`).join('')}</ul>`); list = []; } };
    String(text).split('\n').forEach((line) => {
      if (/^\s*-\s+/.test(line)) list.push(line.replace(/^\s*-\s+/, ''));
      else { flush(); if (line.trim()) out.push(`<p>${esc(line)}</p>`); }
    });
    flush();
    return out.join('');
  }

  /* Full job view, shared by Find Jobs and Saved Jobs. */
  function jobDetailHTML(j) {
    const mine = state.profile.skills;
    const have = j.skills.filter((t) => hasSkill(mine, t));
    const missing = j.skills.filter((t) => !hasSkill(mine, t));
    const app = appForJob(j.id);
    const saved = isSaved(j.id);
    const co = companyFor(j) || {};
    const summary = j.skills.length
      ? `You have <b class="num">${have.length}</b> of <b class="num">${j.skills.length}</b> required skills`
      : 'This job lists no required skills, so everyone matches';
    return `
      <div class="jd" data-id="${esc(j.id)}">
        <header class="jd-head">
          ${logoHTML(j)}
          <div class="jd-title">
            <h2 id="jd-title">${esc(j.title)}</h2>
            <div class="meta"><span class="co">${esc(j.company)}</span><span aria-hidden="true">·</span>${ICON.pin}<span>${esc(j.location)}</span><span aria-hidden="true">·</span>${ICON.bag}<span class="type">${esc(j.type)}</span></div>
            <div class="meta jd-posted">${ICON.clock}<span>Posted ${esc(ago(j.posted).toLowerCase())}</span></div>
          </div>
        </header>
        <div class="jd-actions">
          <button type="button" class="apply-btn lg${app ? ' applied' : ''}" data-act="apply" ${app ? 'aria-disabled="true"' : ''} aria-label="${app ? 'Applied to' : 'Apply to'} ${esc(j.title)} at ${esc(j.company)}">${applyInner(!!app)}</button>
          <button type="button" class="save-btn jd-save" data-act="save" aria-pressed="${saved}" aria-label="${saved ? 'Remove saved' : 'Save'} ${esc(j.title)} at ${esc(j.company)}">${ICON.bookmark}</button>
          ${app ? `<a class="link-arrow" href="applications#${esc(app.id)}">${statusHTML(app.status)}<span>View application</span>${ICON.arrow}</a>` : ''}
        </div>
        <section class="panel jd-match" aria-label="How you match">
          <div class="jd-match-top">
            <div><span class="jd-pct num">${j.match}%</span><span class="jd-pct-label">match</span></div>
            <p>${summary}</p>
          </div>
          ${j.skills.length ? `<div class="overlap" aria-hidden="true">${j.skills.map((t) => `<i class="${hasSkill(mine, t) ? 'on' : ''}"></i>`).join('')}</div>
          <div class="tags">${tagsHTML(j.skills)}</div>` : ''}
          ${missing.length ? `<p class="jd-hint">Have ${missing.map((m) => `<b>${esc(m)}</b>`).join(missing.length > 2 ? ', ' : ' or ')}? <a href="profile#skills">Add it to your skills</a> and your score updates everywhere.</p>` : ''}
        </section>
        <section class="jd-section">
          <h3>About the role</h3>
          <p class="jd-lede">${esc(j.desc)}</p>
          <div class="jd-body">${bodyHTML(j.body)}</div>
        </section>
        <section class="jd-section">
          <h3>About ${esc(j.company)}</h3>
          <p>${esc(co.about || '')}</p>
          ${co.industry ? `<div class="meta jd-co-meta"><span>${esc(co.industry)}</span>${co.size ? `<span aria-hidden="true">·</span><span>${esc(co.size)}</span>` : ''}</div>` : ''}
        </section>
        ${j.source ? `<section class="jd-section jd-source"><h3>Original posting</h3><p>Listed on ${esc(j.company)}’s careers site via ${esc(j.source.board)}. This summary may leave out details, so check the full posting before you apply.</p>
          <a class="link-arrow" href="${esc(j.source.url)}" target="_blank" rel="noopener noreferrer">View on ${esc(j.company)} careers<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 5h5v5M19 5l-8 8"/><path d="M18 14v5H5V6h5"/></svg><span class="sr"> (opens in a new tab)</span></a></section>` : ''}
      </div>`;
  }

  /* Save + Apply buttons anywhere inside `root` (rows or detail). Elements carry
     data-act and sit inside an element with data-id. */
  function wireJobActions(root, { onSaved, onApplied } = {}) {
    root.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-act="save"],[data-act="apply"]');
      if (!btn || !root.contains(btn)) return;
      e.preventDefault(); e.stopPropagation();
      const id = btn.closest('[data-id]').dataset.id;
      const j = job(id);
      if (btn.dataset.act === 'save') {
        const now = toggleSave(id);
        $$(`[data-id="${id}"] [data-act="save"]`).forEach((b) => {
          b.setAttribute('aria-pressed', String(now));
          b.setAttribute('aria-label', `${now ? 'Remove saved' : 'Save'} ${j.title} at ${j.company}`);
        });
        btn.classList.remove('pop'); void btn.offsetWidth; if (now) btn.classList.add('pop');
        toast(now ? `Saved ${j.title} at ${j.company}` : 'Removed from Saved Jobs', { undo: () => { toggleSave(id); if (onSaved) onSaved(id, !now, true); } });
        if (onSaved) onSaved(id, now);
        return;
      }
      if (btn.classList.contains('applied') || btn.classList.contains('loading')) return;
      btn.classList.add('loading');
      btn.innerHTML = '<span class="spinner" aria-hidden="true"></span><span class="sr">Submitting</span>';
      setTimeout(() => {
        const res = apply(id);
        btn.classList.remove('loading');
        if (!res.ok && res.code !== 409) { btn.innerHTML = applyInner(false); toast(res.message, { error: true }); return; }
        $$(`[data-id="${id}"] [data-act="apply"]`).forEach((b) => {
          b.classList.add('applied'); b.setAttribute('aria-disabled', 'true');
          b.setAttribute('aria-label', `Applied to ${j.title} at ${j.company}`);
          b.innerHTML = applyInner(true);
        });
        toast(res.ok ? `Application sent to ${j.company}` : res.message, { error: !res.ok });
        if (onApplied) onApplied(id, res);
      }, reduceMotion ? 0 : 700);
    });
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
      $('button', wrap).addEventListener('click', () => { if (toastUndo) toastUndo(); toastUndo = null; $('.toast', wrap).classList.remove('show'); });
    }
    const el = $('.toast', wrap);
    clearTimeout(toastTimer);
    $('.toast-msg', el).textContent = msg;
    toastUndo = undo || null;
    $('button', el).hidden = !undo;
    el.classList.toggle('error', !!error);
    el.classList.add('show');
    toastTimer = setTimeout(() => el.classList.remove('show'), error ? 4200 : 2800);
  }

  /* ---------- Popovers ---------- */
  function setupPopover(btn, pop, onOpen) {
    const close = () => { pop.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); };
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = !pop.classList.contains('open');
      $$('.popover.open').forEach((p) => p.classList.remove('open'));
      $$('[aria-expanded="true"][aria-controls]').forEach((b) => b.setAttribute('aria-expanded', 'false'));
      if (open) { pop.classList.add('open'); btn.setAttribute('aria-expanded', 'true'); if (onOpen) onOpen(); }
    });
    /* Clicks inside the popover keep it open but still bubble, so its links reach the tab router. */
    document.addEventListener('click', (e) => { if (!pop.contains(e.target)) close(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && pop.classList.contains('open')) { close(); btn.focus(); } });
    return close;
  }

  /* ---------- Sliding indicators ---------- */
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
    { key: 'dashboard', href: 'dashboard', label: 'Dashboard', icon: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9v11h14V9"/><path d="M10 20v-6h4v6"/>' },
    { key: 'jobs', href: 'jobs', label: 'Find Jobs', icon: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>' },
    { key: 'applications', href: 'applications', label: 'My Applications', icon: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/>' },
    { key: 'saved', href: 'saved', label: 'Saved Jobs', icon: '<path d="M6 3h12v18l-6-4-6 4z"/>', badge: 'saved' },
    { key: 'interviews', href: 'interviews', label: 'Interviews', icon: '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/>', badge: 'book' },
    { key: 'profile', href: 'profile', label: 'My Profile', icon: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>' },
  ];
  const initials = (name) => (String(name).trim().split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase() || '?');
  const needsBooking = () => state.applications.filter((a) => a.status === 'Interviewing' && !a.slotId);

  function renderChrome(page) {
    const sb = $('#sidebar'), tb = $('#topbar');
    if (!sb || sb.dataset.page === page) return;
    sb.dataset.page = page;
    sb.innerHTML = `
      <a href="dashboard" class="brand" aria-label="Matchwork home">
        <svg width="24" height="22" viewBox="0 0 24 22" aria-hidden="true"><circle cx="6.5" cy="5" r="4.5" fill="#1E2A24"/><circle cx="16.5" cy="6" r="4" fill="#7FAE8E"/><rect x="0" y="10" width="12" height="12" rx="4" fill="#1E2A24"/><rect x="11" y="11" width="13" height="11" rx="4" fill="#7FAE8E"/></svg>
        <span>Matchwork</span>
      </a>
      <div class="portal-label">Candidate Portal</div>
      <nav class="nav" aria-label="Candidate portal">
        <span class="nav-indicator" aria-hidden="true"></span>
        ${NAV.map((n) => `<a href="${n.href}" class="nav-item"${n.key === page ? ' aria-current="page"' : ''}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${n.icon}</svg>
          <span class="label">${n.label}</span>${n.badge ? `<span class="badge" data-badge="${n.badge}" aria-hidden="true"></span><span class="sr" data-badge-sr="${n.badge}"></span>` : ''}
        </a>`).join('')}
      </nav>
      <div class="divider"></div>
      <a href="/sign-in#candidate" class="nav-item logout">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 4H5v16h5"/><path d="M14 8l4 4-4 4"/><path d="M18 12H9"/></svg>
        <span class="label">Log Out</span>
      </a>
      <div class="sidebar-spacer"></div>
      <svg class="deco-bl" width="228" height="140" viewBox="0 0 228 140" aria-hidden="true"><path d="M0 10 C40 0 70 30 105 60 C140 90 180 110 228 140 L0 140Z" fill="#F2F3F3"/><path d="M0 70 C40 60 80 85 110 110 C125 122 140 132 150 140 L0 140Z" fill="#ECEEEE"/></svg>`;

    const params = new URLSearchParams(location.search);
    tb.innerHTML = `
      <form class="search" id="searchForm" role="search" autocomplete="off" action="jobs">
        <label class="search-field">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m20 20-4.8-4.8"/></svg>
          <span class="sr">Job title, keywords, or company</span>
          <input id="search" name="q" type="search" placeholder="Job title, keywords, or company" value="${esc(params.get('q') || '')}">
        </label>
        <span class="search-sep" aria-hidden="true"></span>
        <label class="search-field loc">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 21.5s-7-6.3-7-12a7 7 0 0 1 14 0c0 5.7-7 12-7 12z"/><circle cx="12" cy="9.5" r="2.6"/></svg>
          <span class="sr">Location</span>
          <input id="searchLoc" name="loc" type="search" placeholder="City, state, or remote" value="${esc(params.get('loc') || '')}">
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
            <a href="profile" class="menu-item" role="menuitem">My Profile</a>
            <button type="button" class="menu-item" role="menuitem" id="resetDemo">Reset demo data</button>
            <div class="menu-sep" role="separator"></div>
            <a href="/sign-in#candidate" class="menu-item danger" role="menuitem">Log Out</a>
          </div>
        </div>
      </div>`;
    fillChrome();
  }
  /* Avatar, badges and notifications from the store. */
  function fillChrome(bump) {
    const p = state.profile;
    $('#avatar').textContent = initials(p.name);
    $('#accountBtn').setAttribute('aria-label', `Account menu for ${p.name}`);
    setBadge('saved', Object.keys(state.saved).length, (n) => `, ${n} saved`, bump === 'saved');
    setBadge('book', needsBooking().length, (n) => `, ${n} to book`, bump === 'book');
    renderNotifs();
  }

  function mountShell(page, opts = {}) {
    renderChrome(page);
    /* Search: Find Jobs filters in place; other pages hand the query to Find Jobs. */
    const form = $('#searchForm');
    if (opts.onSearch) {
      let t;
      const run = () => opts.onSearch($('#search').value, $('#searchLoc').value);
      ['#search', '#searchLoc'].forEach((sel) => $(sel).addEventListener('input', () => { clearTimeout(t); t = setTimeout(run, 160); }));
      form.addEventListener('submit', (e) => { e.preventDefault(); clearTimeout(t); run(); });
    }

    setupPopover($('#bellBtn'), $('#notifPop'));
    setupPopover($('#accountBtn'), $('#accountMenu'), () => $('#accountMenu .menu-item').focus());
    $('#resetDemo').addEventListener('click', () => { resetDemo(); location.reload(); });

    const syncNav = () => moveIndicator($('.nav-indicator'), $('.nav [aria-current="page"]'));
    fillChrome();
    listeners.add(() => fillChrome());

    const fit = () => { syncNav(); if (opts.onLayout) opts.onLayout(); };
    slideNav();
    /* Page layout hooks run after the page script has finished setting up. */
    requestAnimationFrame(() => { if (opts.onLayout) opts.onLayout(); });
    requestAnimationFrame(() => requestAnimationFrame(() => document.body.classList.add('ready')));
    (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(() => requestAnimationFrame(fit));
    window.addEventListener('resize', () => requestAnimationFrame(fit));
    window.addEventListener('storage', (e) => { if (e.key === KEY) location.reload(); });
    prefetchNav();
    return { bumpBadge: (k) => fillChrome(k) };
  }

  function setBadge(key, n, srText, bump) {
    const b = $(`[data-badge="${key}"]`), sr = $(`[data-badge-sr="${key}"]`);
    if (!b) return;
    const prev = Number(b.textContent) || 0;
    b.textContent = n;
    b.classList.toggle('show', n > 0);
    sr.textContent = n ? srText(n) : '';
    if ((bump || n > prev) && n > 0 && document.body.classList.contains('ready')) { b.classList.remove('bump'); void b.offsetWidth; b.classList.add('bump'); }
  }

  function renderNotifs() {
    const items = [];
    const nb = needsBooking();
    nb.forEach((a) => { const j = job(a.jobId); items.push({ href: 'interviews#book-' + a.id, icon: 'book', title: 'Pick an interview time', text: `${j.title} at ${j.company}`, when: a.events[a.events.length - 1][1] }); });
    state.applications.filter((a) => a.slotId && new Date(slot(a.slotId).start) > NOW).sort((a, b) => new Date(slot(a.slotId).start) - new Date(slot(b.slotId).start)).forEach((a) => {
      const j = job(a.jobId), sl = slot(a.slotId);
      items.push({ href: 'interviews', icon: 'cal', title: 'Interview scheduled', text: `${j.title} at ${j.company}`, when: null, sub: `${fmtDate(sl.start)}, ${fmtTime(sl.start)} PT` });
    });
    const pop = $('#notifPop');
    pop.innerHTML = `<div class="notif-head">Notifications <button type="button" id="markRead"${state.notifRead ? ' disabled' : ''}>${state.notifRead ? 'All caught up' : 'Mark all read'}</button></div>` +
      (items.length ? items.map((n) => `<a class="notif-item" href="${n.href}"><span class="notif-icon"${n.icon === 'book' ? ' style="background:#FFF7DF"' : ''}>${n.icon === 'book'
        ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#8C6A12" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>'
        : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#6A4FC9" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><rect x="4" y="5" width="16" height="16" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/></svg>'}</span>
        <div><strong>${esc(n.title)}</strong>, ${esc(n.text)}<time>${n.sub ? esc(n.sub) : esc(ago(n.when))}</time></div></a>`).join('')
        : '<div class="notif-item">No notifications yet.</div>');
    $('#markRead').addEventListener('click', () => { state.notifRead = true; persist(); });
    $('#bellDot').classList.toggle('hide', state.notifRead || !items.length);
    $('#bellBtn').setAttribute('aria-label', `Notifications${state.notifRead || !items.length ? ', none new' : `, ${items.length} new`}`);
  }

  /* Scale the UI up on large screens so it fills the viewport like the 1456x819 design.
     Runs from <head>, before first paint, so the layout never jumps. */
  function fitScale() {
    const vw = window.innerWidth, vh = window.innerHeight;
    const z = Math.min(vw / 1456, vh / 819, 1.4);
    const ok = z > 1.03 && vw > 1180 && window.CSS && CSS.supports('zoom', '1');
    document.documentElement.style.setProperty('--mw-zoom', ok ? z.toFixed(3) : '1');
  }
  fitScale();
  window.addEventListener('resize', fitScale);

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
    try { from = sessionStorage.getItem('mw.nav'); sessionStorage.removeItem('mw.nav'); } catch (e) { /* ignore */ }
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
    try { if (c) sessionStorage.setItem('mw.nav', c.getAttribute('href')); } catch (e) { /* ignore */ }
  });

  /* True the first time a key is seen in this browser tab; used to play intro animations once. */
  function firstVisit(key) {
    try { if (sessionStorage.getItem('mw.seen.' + key)) return false; sessionStorage.setItem('mw.seen.' + key, '1'); } catch (e) { /* ignore */ }
    return true;
  }

  /* ---------- Tab router ----------
     Switching tabs swaps the page inside this document instead of loading a new one. Fonts,
     styles, job data and the store stay in memory. Every tab is still a real page with its own URL and HTML file,
     so opening, reloading or sharing a link works as before. */
  const PAGES = NAV.map((n) => n.key);
  const BUNDLE = !!window.__MW_PAGES; /* single-file build: pages come from window.__MW_PAGES */
  const BUNDLE_BASE = 'http://bundle/candidate/';
  const nativeAdd = EventTarget.prototype.addEventListener;
  const pageListeners = []; /* window/document listeners added by the current page */
  const sources = new Map();
  let prefetchScheduled = false;
  let navSeq = 0, shownSearch = location.search, lastURL = location.href;

  /* Which tab a link points to, and the URL to show for it; null for anything else. */
  function resolve(href) {
    if (BUNDLE) {
      const u = new URL(href, BUNDLE_BASE);
      const key = u.origin === 'http://bundle' && u.pathname.startsWith('/candidate/') ? u.pathname.slice(11).replace(/\.html$/, '') || 'dashboard' : null;
      if (!PAGES.includes(key)) return null;
      const p = new URLSearchParams(u.search); p.delete('page');
      return { key, url: location.pathname + '?' + ['page=' + key, p.toString()].filter(Boolean).join('&') + u.hash };
    }
    const u = new URL(href, location.href);
    const dir = location.pathname.replace(/[^/]*$/, '');
    if (u.origin !== location.origin || !u.pathname.startsWith(dir)) return null;
    const key = u.pathname.slice(dir.length).replace(/\.html$/, '');
    return PAGES.includes(key) ? { key, url: u.pathname + u.search + u.hash } : null;
  }
  function currentKey() {
    if (BUNDLE) return new URLSearchParams(location.search).get('page') || 'dashboard';
    const key = location.pathname.replace(/^.*\//, '').replace(/\.html$/, '');
    return PAGES.includes(key) ? key : 'dashboard';
  }
  function source(key) {
    if (!sources.has(key)) {
      const html = BUNDLE ? Promise.resolve(window.__MW_PAGES[key]) :
        fetch(new URL(key, location.href), { credentials: 'same-origin' })
          .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); });
      const p = html.then((text) => new DOMParser().parseFromString(text, 'text/html'));
      p.catch(() => sources.delete(key));
      sources.set(key, p);
    }
    return sources.get(key);
  }
  /* Load the other tabs' HTML once the current one is idle, so a switch never waits on the network. */
  function prefetchNav() {
    if (BUNDLE || prefetchScheduled || !/^https?:$/.test(location.protocol)) return;
    prefetchScheduled = true;
    const run = () => PAGES.forEach((k) => {
      source(k).then((doc) => prepareStyles(doc, location.href)).catch(() => {});
    });
    if (window.requestIdleCallback) requestIdleCallback(run, { timeout: 1500 }); else setTimeout(run, 300);
  }

  /* Head styles are matched by href (links) or text (inline styles): shared ones stay put. */
  const headStyles = (d) => Array.from(d.head.querySelectorAll('link[rel="stylesheet"], style'));
  const pendingStyles = new WeakMap();
  const styleKey = (el, base) => (el.tagName === 'LINK' ? 'L:' + new URL(el.getAttribute('href'), base).href : 'S:' + el.textContent);
  /* New stylesheet links are added as media="print" so they load without applying; swap() turns them on. */
  function prepareStyles(doc, base) {
    const have = new Map(headStyles(document).map((el) => [styleKey(el, location.href), el]));
    let anchor = null;
    const loads = [];
    headStyles(doc).forEach((el) => {
      const k = styleKey(el, base);
      if (have.has(k)) {
        anchor = have.get(k);
        if (pendingStyles.has(anchor)) loads.push(pendingStyles.get(anchor));
        return;
      }
      if (el.tagName !== 'LINK') return;
      const link = document.createElement('link');
      link.rel = 'stylesheet'; link.href = new URL(el.getAttribute('href'), base).href; link.media = 'print';
      link.dataset.mwMedia = el.getAttribute('media') || '';
      const loaded = new Promise((ok) => { link.onload = link.onerror = ok; setTimeout(ok, 2500); });
      pendingStyles.set(link, loaded);
      loaded.then(() => pendingStyles.delete(link));
      loads.push(loaded);
      if (anchor) anchor.after(link); else document.head.prepend(link);
      have.set(k, link); anchor = link;
    });
    return Promise.all(loads);
  }
  function applyStyles(doc, base) {
    const have = new Map(headStyles(document).map((el) => [styleKey(el, location.href), el]));
    const keep = new Set();
    let anchor = null;
    headStyles(doc).forEach((el) => {
      const k = styleKey(el, base);
      let mine = have.get(k);
      if (mine) {
        if (mine.tagName === 'LINK') { const m = mine.dataset.mwMedia != null ? mine.dataset.mwMedia : (el.getAttribute('media') || ''); if (m) mine.media = m; else mine.removeAttribute('media'); delete mine.dataset.mwMedia; }
      } else {
        mine = document.importNode(el, true);
        if (anchor) anchor.after(mine); else document.head.prepend(mine);
      }
      keep.add(mine); anchor = mine;
    });
    headStyles(document).forEach((el) => {
      if (keep.has(el)) return;
      if (el.tagName === 'LINK') el.media = 'not all';
      else el.remove();
    });
  }

  function dropPageListeners() {
    pageListeners.splice(0).forEach(([t, type, fn, opts]) => t.removeEventListener(type, fn, opts));
    listeners.clear();
  }

  /* Replace the body with the new page and run its scripts, all in one task, so no frame shows a half-built page. */
  function swap(doc, key, url, push) {
    const from = $('.nav [aria-current="page"]');
    rememberNavPosition();
    const navFocused = !!(from && document.activeElement && document.activeElement.closest && document.activeElement.closest('.sidebar'));
    if (push) history.pushState({ mw: key }, '', url);
    shownSearch = location.search;
    try { if (from) sessionStorage.setItem('mw.nav', from.getAttribute('href')); } catch (e) { /* ignore */ }
    dropPageListeners();
    applyStyles(doc, BUNDLE ? location.href : new URL(url, location.href).href);
    document.title = doc.title;
    Array.from(document.body.attributes).forEach((a) => document.body.removeAttribute(a.name));
    Array.from(doc.body.attributes).forEach((a) => document.body.setAttribute(a.name, a.value));
    const frag = document.createDocumentFragment();
    Array.from(doc.body.childNodes).forEach((n) => frag.appendChild(document.importNode(n, true)));
    /* Imported scripts never run; fresh copies run when the fragment is inserted, in page order. */
    frag.querySelectorAll('script').forEach((old) => {
      const s = document.createElement('script');
      Array.from(old.attributes).forEach((a) => s.setAttribute(a.name, a.value));
      s.textContent = old.textContent;
      old.replaceWith(s);
    });
    document.body.replaceChildren(frag);
    if (!location.hash) window.scrollTo(0, 0);
    const cur = $('.nav [aria-current="page"]');
    if (navFocused && cur) cur.focus({ preventScroll: true });
    if (from?.getAttribute('href') !== cur?.getAttribute('href') && !reduceMotion) {
      $('.main')?.animate?.([{ opacity: .96 }, { opacity: 1 }], { duration: 130, easing: 'ease-out' });
    }
  }

  async function navigate(key, url, push = true) {
    const seq = ++navSeq;
    /* Pages with unsaved edits (My Profile skills) get the same warning a real page change gives. */
    const leave = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(leave);
    if (leave.defaultPrevented && !window.confirm('Leave this page? Changes you made may not be saved.')) {
      document.documentElement.classList.remove('mw-loading');
      if (!push) history.pushState({ mw: currentKey() }, '', lastURL);
      return;
    }
    document.documentElement.classList.add('mw-loading');
    let doc, base;
    try {
      doc = await source(key);
      if (seq !== navSeq) return;
      base = BUNDLE ? location.href : new URL(url, location.href).href;
      await prepareStyles(doc, base);
    } catch (err) {
      if (seq === navSeq) location.href = url; /* fall back to a normal page load */
      return;
    } finally {
      if (seq === navSeq) document.documentElement.classList.remove('mw-loading');
    }
    if (seq !== navSeq) return;
    swap(doc, key, url, push);
  }

  function startRouter() {
    if (!BUNDLE && !PAGES.includes(location.pathname.replace(/^.*\//, '').replace(/\.html$/, ''))) return;
    /* Track the window/document listeners each page adds, so they can be removed when it is swapped out. */
    [window, document].forEach((t) => {
      t.addEventListener = function (type, fn, opts) { pageListeners.push([t, type, fn, opts]); return nativeAdd.call(this, type, fn, opts); };
    });
    ['pushState', 'replaceState'].forEach((m) => {
      const orig = history[m];
      history[m] = function () { const r = orig.apply(history, arguments); shownSearch = location.search; lastURL = location.href; return r; };
    });
    nativeAdd.call(document, 'click', (e) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = e.target.closest && e.target.closest('a[href]');
      if (!a || (a.target && a.target !== '_self') || a.hasAttribute('download')) return;
      const href = a.getAttribute('href');
      if (!href || href.startsWith('#')) return;
      if (BUNDLE && /^\/(login|sign-in)/.test(href)) { e.preventDefault(); toast('The login page is not part of this file'); return; }
      const r = resolve(href);
      if (!r) return;
      e.preventDefault();
      const here = location.pathname + location.search + location.hash;
      if (r.key === currentKey() && r.url === here) {
        navSeq++;
        document.documentElement.classList.remove('mw-loading');
        return;
      }
      navigate(r.key, r.url);
    });
    /* GET forms that point at a tab (the top-bar search on most pages). */
    nativeAdd.call(document, 'submit', (e) => {
      const f = e.target;
      if (e.defaultPrevented || !(f instanceof HTMLFormElement) || !f.getAttribute('action') || (f.method || 'get').toLowerCase() !== 'get') return;
      const p = new URLSearchParams(new FormData(f));
      Array.from(p.keys()).forEach((k) => { if (!p.get(k)) p.delete(k); });
      const r = resolve(f.getAttribute('action') + (p.toString() ? '?' + p : ''));
      if (!r) return;
      e.preventDefault();
      navigate(r.key, r.url);
    });
    nativeAdd.call(window, 'popstate', () => {
      /* Back/Forward between hash links on the same page needs no swap. */
      if (currentKey() === navKey() && location.search === shownSearch) {
        navSeq++;
        document.documentElement.classList.remove('mw-loading');
        lastURL = location.href;
        return;
      }
      navigate(currentKey(), location.pathname + location.search + location.hash, false);
    });
  }
  /* The tab the visible page belongs to (from the sidebar), which can differ from the URL mid-Back. */
  function navKey() {
    const cur = $('.nav [aria-current="page"]');
    return cur ? resolve(cur.getAttribute('href')).key : null;
  }

  /* Back/Forward restores pages from memory; only reload if data changed in the meantime. */
  window.addEventListener('pageshow', (e) => { if (e.persisted && readRev() !== loadedRev) location.reload(); });
  window.addEventListener("storage", (e) => { if (e.key === KEY && !document.getElementById("sidebar")) location.reload(); });

  /* Dead "#" links never jump. */
  document.addEventListener('click', (e) => { const a = e.target.closest('a[href="#"]'); if (a) e.preventDefault(); });

  window.MW = {
    $, $$, esc, reduceMotion, NOW, TZ, TZ_LABEL, fmt, fmtDate, fmtShort, fmtTime, fmtSlotTime, fmtRange, dayKey, ago,
    matchScore, normalizeSkills, hasSkill, byMatch, COMPANIES,
    get state() { return state; }, persist, resetDemo, onChange: (fn) => listeners.add(fn),
    jobs, job, appForJob, slot, isSaved, toggleSave, apply, openSlotsFor, book, updateProfile, profileCompletion, needsBooking,
    ICON, logoHTML, scoreHTML, tagsHTML, statusHTML, applyInner, bodyHTML, initials, jobDetailHTML, wireJobActions,
    toast, setupPopover, moveIndicator, mountShell, renderChrome, fitScale, renderNotifs, slideNav, firstVisit, prefetchNav,
    navigate: (href) => { const r = resolve(href); if (r) navigate(r.key, r.url); else location.href = href; },
  };
  /* Start now, before the page's own scripts run, so their listeners are tracked from the first page on. */
  startRouter();
})();
