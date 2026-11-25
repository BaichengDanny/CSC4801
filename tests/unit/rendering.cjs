const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..', '..');

function loadPortal(file, name) {
  // Load the shipped renderer without starting a browser or fetching assets.
  const window = new EventTarget();
  window.matchMedia = () => ({ matches: false });
  window.__MW_DATA = { jobs: [], companies: {} };
  const document = new EventTarget();
  document.documentElement = { style: { setProperty() {} } };
  const location = new URL('file:///matchwork-test.html');
  const context = vm.createContext({ window, document, location, EventTarget });
  for (const asset of ['shared/match.js', file]) {
    vm.runInContext(fs.readFileSync(path.join(root, asset), 'utf8'), context, { filename: asset });
  }
  return window[name];
}

const text = '<script>alert(1)</script>';
const escaped = '&lt;script&gt;alert(1)&lt;/script&gt;';
for (const [file, name] of [
  ['candidate/assets/matchwork.js', 'MW'],
  ['recruiter/assets/recruiter.js', 'RW'],
]) {
  const renderer = loadPortal(file, name);
  assert.equal(renderer.bodyHTML(text), `<p>${escaped}</p>`, `${name} job body`);
  assert.equal(renderer.bodyHTML(`- ${text}`), `<ul><li>${escaped}</li></ul>`, `${name} job bullet`);
  assert.equal(renderer.esc(text), escaped, `${name} user text`);
  assert.equal(renderer.esc(`A & B "'`), 'A &amp; B &quot;&#39;', `${name} attribute text`);
}
