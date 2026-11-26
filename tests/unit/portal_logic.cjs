// Page-script logic behind audit defects 1, 6, and 10, run against the shipped portal scripts.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..', '..');

function loadPortal(file, name, role, bootstrap) {
  const window = new EventTarget();
  window.matchMedia = () => ({ matches: false });
  const document = new EventTarget();
  document.documentElement = { style: { setProperty() {} } };
  const location = new URL('http://matchwork.test');
  const store = () => {
    const data = new Map();
    return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, String(value)), removeItem: (key) => data.delete(key) };
  };
  const responses = new Map([
    ['/api/auth/me', { id: 1, role, csrfToken: 'fixture-token' }],
    ['/api/candidate/bootstrap', bootstrap],
    ['/api/employer/bootstrap', bootstrap],
  ]);
  class XMLHttpRequest {
    open(method, url) {
      assert.equal(method, 'GET');
      this.url = url;
    }

    send() {
      assert.ok(responses.has(this.url), this.url);
      this.status = 200;
      this.responseText = JSON.stringify(responses.get(this.url));
    }
  }
  const context = vm.createContext({
    window, document, location, EventTarget, XMLHttpRequest, URL,
    localStorage: store(), sessionStorage: store(), setInterval() {},
  });
  for (const asset of ['shared/html.js', 'shared/match.js', file]) {
    vm.runInContext(fs.readFileSync(path.join(root, asset), 'utf8'), context, { filename: asset });
  }
  return window[name];
}

// Defect 1: hosted pages show the backend's scores and ranks.
const now = '2026-11-16T17:00:00Z';
const job = (id, title, skills, score, rank) => ({ id, seq: Number(id), title, company: 'Acme', owner: '1', skills, score, rank });
const jobs = [job('1', 'Alpha', ['nothing-matches'], 77, 1), job('2', 'Beta', ['x'], 12, 2), job('3', 'Gamma', [], 100, 0)];
const MW = loadPortal('candidate/assets/matchwork.js', 'MW', 'Candidate', {
  now, companies: {}, jobs, state: { profile: { skills: [] }, saved: {}, slots: [], applications: [] },
});
assert.deepEqual(Array.from(MW.jobs(), (job) => [job.title, job.match]), [['Gamma', 100], ['Alpha', 77], ['Beta', 12]]);

const RW = loadPortal('recruiter/assets/recruiter.js', 'RW', 'Employer', {
  now, me: '1', state: {
    jobs, slots: [], company: { name: 'Acme' },
    candidates: [{ id: '1', name: 'Alex', skills: [] }],
    applications: [{ id: '1', candidateId: '1', jobId: '1', score: 7, rank: 0 }],
  },
});
assert.equal(RW.application('1').match, 7, 'employer rows show the server score');

// Defect 10: "Today" and "Tomorrow" follow Pacific calendar days. The demo clock is
// Monday 16 Nov 2026, 9:00 AM PT.
assert.equal(MW.relativeDay('2026-11-16T23:00:00Z'), 'Today');
assert.equal(MW.relativeDay('2026-11-17T07:30:00Z'), 'Today', '11:30 PM PT the same day');
assert.equal(MW.relativeDay('2026-11-17T09:00:00Z'), 'Tomorrow', '1:00 AM PT the next day');
assert.equal(MW.relativeDay('2026-11-19T18:00:00Z'), 'In 3 days');

// Defect 10: a blank location is saved blank, and the "Not listed" placeholder is never saved.
const base = { title: 'T', desc: 'D', body: '', skills: [] };
assert.equal(RW.pickJob({ ...base, location: '' }).location, '');
assert.equal(RW.pickJob({ ...base, location: 'Not listed', locationSet: false }).location, '');
assert.equal(RW.pickJob({ ...base, location: ' Austin, TX ', locationSet: false }).location, 'Austin, TX');
assert.equal(RW.pickJob({ ...base, location: 'Not listed', locationSet: true }).location, 'Not listed');

// Defect 6: the delete-blocked message names what actually blocks deletion.
const slotOnly = RW.deleteBlockedText({ apps: 0, slots: 1, blocked: true });
assert.match(slotOnly, /1 interview slot\b/);
assert.doesNotMatch(slotOnly, /0 application/);
assert.match(RW.deleteBlockedText({ apps: 2, slots: 0, blocked: true }), /2 applications\b/);
assert.match(RW.deleteBlockedText({ apps: 1, slots: 3, blocked: true }), /1 application and 3 interview slots/);
