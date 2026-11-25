const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const pagePath = path.join(__dirname, '..', '..', 'recruiter', 'interviews.html');
const html = fs.readFileSync(pagePath, 'utf8');
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
const today = '2026-11-25';
const later = '2026-12-16';

function renderSelection(day, slots) {
  const nodes = new Map();
  function $(selector) {
    if (!nodes.has(selector)) {
      nodes.set(selector, { addEventListener() {}, scrollIntoView() {} });
    }
    return nodes.get(selector);
  }

  const RW = {
    $, $$: () => [], esc: String, ICON: {},
    NOW: new Date(`${today}T18:00:00Z`),
    params: () => new URLSearchParams(day === null ? {} : { day }),
    ymdOf: (date) => new Date(date).toISOString().slice(0, 10),
    ptToUtc: (date, hour, minute) => new Date(`${date}T00:00:00Z`).setUTCHours(hour, minute),
    fmt: () => '', fmtLong: () => '', fmtTime: () => '', fmtSlotTime: () => '',
    ownSlots: () => slots, openSlots: () => slots, awaitingBooking: () => [],
    mountShell() {},
  };

  vm.runInNewContext(script, { RW }, { filename: pagePath });
  const selected = $('#days').innerHTML.match(/data-day="([^"]+)" aria-pressed="true"/);
  return { selectedDay: selected?.[1], manualDate: $('#mDate').value };
}

const slot = { id: '1', start: `${later}T18:00:00Z`, bookedBy: null };
assert.deepEqual(renderSelection(later, [slot]), { selectedDay: later, manualDate: later });
assert.deepEqual(renderSelection(later, []), { selectedDay: later, manualDate: later },
  'Reloading after deleting the last slot should preserve the selected date');

for (const day of [null, '2026-11-24', '2026-12-32', '2027-02-29', '2026-12-1']) {
  assert.deepEqual(renderSelection(day, []), { selectedDay: today, manualDate: today }, String(day));
}
