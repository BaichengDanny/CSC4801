/* Employer dashboard: everything on it comes from the shared store in recruiter.js. */
(function () {
  'use strict';
  const { $, $$, esc, ICON, reduceMotion } = RW;

  RW.mountShell('dashboard', { onLayout: () => fitRows() });

  const CHEV = '<svg class="row-chev" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>';
  const enter = (i) => (reduceMotion ? '' : ` enter" style="animation-delay:${i * 50}ms`);
  const WEEK = 7 * 864e5;

  /* ---------- Welcome + stats ---------- */
  function renderWelcome(animate) {
    const c = RW.company(), jobs = RW.jobs(), apps = RW.allApplicants();
    $('#welcome-title').textContent = c.name;
    const h = Number(RW.fmt(RW.NOW, { hour: 'numeric', hourCycle: 'h23' }));
    $('#greeting').textContent = h < 12 ? 'Good morning,' : h < 18 ? 'Good afternoon,' : 'Good evening,';
    const fresh = jobs.filter((j) => RW.NOW - new Date(j.posted) < WEEK && new Date(j.posted) <= RW.NOW).length;
    const delta = $('#stDelta');
    delta.hidden = !fresh; delta.textContent = `+${fresh} this week`;
    const counts = { stJobs: jobs.length, stApps: apps.length, stIv: apps.filter((a) => a.status === 'Interviewing').length, stAcc: apps.filter((a) => a.status === 'Accepted').length };
    Object.entries(counts).forEach(([id, n]) => countTo($('#' + id), n, animate));
  }
  function countTo(el, end, animate) {
    const from = Number(el.textContent) || 0;
    if (!animate || reduceMotion || from === end) { el.textContent = end; return; }
    const t0 = performance.now(), dur = 700;
    const tick = (t) => { const p = Math.min(1, (t - t0) / dur); el.textContent = Math.round(from + (end - from) * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  }

  /* ---------- Recent applicants: the last two weeks, best match first ---------- */
  function renderApplicants(animate) {
    const recent = RW.allApplicants().filter((a) => RW.NOW - new Date(a.appliedAt) < 2 * WEEK).slice(0, 6);
    $('#applicants').innerHTML = recent.length ? recent.map((a, i) => {
      const shown = RW.candTagsHTML(a.cand, a.job, 2);
      return `<a href="applicants?job=${encodeURIComponent(a.jobId)}#${esc(a.id)}" class="row app-row${animate ? enter(i) : ''}" aria-label="${esc(a.name)}, ${esc(a.job.title)}, ${a.match}% match, ${esc(a.status)}">
        ${RW.avatarHTML(a.cand)}
        <span class="who"><b>${esc(a.name)}</b><span>${esc(a.job.title)}</span></span>
        <span class="tags">${shown}</span>
        ${RW.scoreHTML(a.match)}
        ${RW.statusHTML(a.status)}
        ${CHEV}
      </a>`;
    }).join('') : '<div class="empty">No new applicants in the last two weeks.</div>';
  }

  /* ---------- Job postings: active jobs, newest first ---------- */
  function renderPostings(animate) {
    const list = RW.jobs().filter((j) => j.status === 'Active');
    $('#postings').innerHTML = list.length ? list.map((j, i) => `<div class="row job-row${animate ? enter(i + 2) : ''}">
      ${RW.logoHTML('sm')}
      <div style="min-width:0">
        <h3><a href="jobs?id=${encodeURIComponent(j.id)}">${esc(j.title)}</a></h3>
        <div class="meta"><span class="type">${esc(j.type)}</span><span aria-hidden="true">·</span><span>${esc(j.location)}</span></div>
      </div>
      <div class="count"><b>${j.apps}</b><span>Applications</span></div>
      <div class="count"><b>${j.interviewing}</b><span>Interviewing</span></div>
      ${RW.statusHTML(j.status)}
      <div class="more-wrap">
        <button type="button" class="more-btn" aria-label="More actions for ${esc(j.title)}" aria-haspopup="menu" aria-expanded="false" aria-controls="jm${i}">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>
        </button>
        <div class="popover" id="jm${i}" role="menu" aria-label="${esc(j.title)} actions">
          <a href="applicants?job=${encodeURIComponent(j.id)}" class="menu-item" role="menuitem">View applicants</a>
          <a href="jobs?id=${encodeURIComponent(j.id)}&amp;edit=1" class="menu-item" role="menuitem">Edit posting</a>
          <div class="menu-sep" role="separator"></div>
          <a href="jobs?id=${encodeURIComponent(j.id)}&amp;delete=1" class="menu-item danger" role="menuitem">Delete posting</a>
        </div>
      </div>
    </div>`).join('') : '<div class="empty">No active jobs. <a href="jobs?new=1" style="color:var(--green-700);font-weight:600">Post a job</a></div>';
    $$('#postings .more-btn').forEach((b) => RW.setupPopover(b, document.getElementById(b.getAttribute('aria-controls'))));
  }

  /* ---------- Upcoming interviews: today in the panel, the rest of the week below ---------- */
  function renderInterviews() {
    const today = RW.ymdOf(RW.NOW);
    const upcoming = RW.ownSlots().filter((s) => s.bookedBy && new Date(s.end) > RW.NOW).map((s) => ({ s, a: RW.application(s.bookedBy) })).filter((x) => x.a);
    const todays = upcoming.filter((x) => RW.ymdOf(x.s.start) === today);
    $('#ivToday').innerHTML = todays.length ? todays.map(({ s, a }) => `<a href="applicants?job=${encodeURIComponent(a.jobId)}#${esc(a.id)}" class="iv-slot">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
        <span><b>${esc(RW.fmtRange(s.start, s.end))} PT</b><span>${esc(a.name)} · ${esc(a.job.title)}</span></span>
        ${CHEV}
      </a>`).join('') : '<p class="iv-none">No interviews today.</p>';
    const weekEnd = RW.NOW.getTime() + WEEK;
    const later = upcoming.filter((x) => RW.ymdOf(x.s.start) !== today && new Date(x.s.start) < weekEnd);
    const waiting = RW.awaitingBooking().length;
    $('#ivLater').innerHTML = later.length
      ? `<b>${later.length} more</b> this week · next ${esc(RW.fmt(later[0].s.start, { weekday: 'short' }))}, ${esc(RW.fmtTime(later[0].s.start))} PT`
      : waiting ? `<b>${waiting}</b> applicant${waiting === 1 ? '' : 's'} still choosing a time` : 'Nothing else booked this week.';
  }

  /* ---------- Pipeline: one bar per status, across every job ---------- */
  function renderPipeline() {
    const apps = RW.allApplicants();
    const P = [['Pending', '#C9CED2'], ['Interviewing', '#A893F0'], ['Accepted', '#4E9A68'], ['Rejected', '#F28B8B']].map(([label, color]) => ({ label, color, n: apps.filter((a) => a.status === label).length }));
    const max = Math.max(1, ...P.map((p) => p.n));
    const el = $('#pipeline');
    const prev = new Map($$('.pipe-bar i', el).map((i) => [i.dataset.k, i.style.width]));
    el.innerHTML = P.map((p) => `<a class="pipe-row" href="applicants?status=${p.label}" style="text-decoration:none">
        <span>${esc(p.label)}</span>
        <span class="pipe-bar"><i data-k="${p.label}" style="background:${p.color};width:${prev.get(p.label) || 0}" data-w="${(p.n / max) * 100}"></i></span>
        <b>${p.n}</b>
      </a>`).join('');
    requestAnimationFrame(() => requestAnimationFrame(() => $$('.pipe-bar i', el).forEach((i) => { i.style.width = i.dataset.w + '%'; })));
  }

  /* Desktop layout fits the viewport: drop trailing rows that would be cut off, never show half a row. */
  function fitRows() {
    $$('.rows').forEach((r) => {
      const kids = [...r.children];
      kids.forEach((c) => { c.hidden = false; });
      if (getComputedStyle(r).overflowY !== 'hidden' || kids.length < 2) return;
      const overflows = () => { const v = kids.filter((c) => !c.hidden).pop(); return v.offsetTop - r.offsetTop + v.offsetHeight > r.clientHeight + 1; };
      for (let i = kids.length - 1; i > 0 && overflows(); i--) kids[i].hidden = true;
    });
  }

  function renderAll(animate) {
    renderWelcome(animate);
    renderApplicants(animate);
    renderPostings(animate);
    renderInterviews();
    renderPipeline();
    fitRows();
  }
  renderAll(true);
  RW.onChange(() => renderAll(false));
  if (document.fonts) document.fonts.ready.then(fitRows);
})();
