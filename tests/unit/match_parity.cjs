// Compare shared/match.js with the Python results passed on stdin by test_audit_fixes.py.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const window = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', '..', 'shared', 'match.js'), 'utf8'), { window });
const { normalizeSkills, matchScore } = window.MWMatch;
const { cases, expected } = JSON.parse(fs.readFileSync(0, 'utf8'));
cases.forEach(([candidate, required], i) => {
  assert.deepEqual([...normalizeSkills(candidate)].sort(), expected[i].normalized, `normalize case ${i}`);
  assert.equal(matchScore(candidate, required), expected[i].score, `score case ${i}`);
});
