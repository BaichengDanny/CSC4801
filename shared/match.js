/* Matchwork matching contract (FP-MATCH-1), shared by the candidate and employer portals.
   Both sides call this one implementation, so a score never differs between views.

   Normalize: trim, lowercase, drop empty values, drop duplicates.
   score = 100                                   when |R| = 0
   score = floor(100 * |C ∩ R| / |R|)            otherwise                                   */
(function (root) {
  'use strict';

  // Match Python's explicit whitespace set, including BOM, NEL and U+001C–1F.
  const edgeWhitespace = /^[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000\uFEFF]+|[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000\uFEFF]+$/g;
  const cleanSkill = (value) => String(value == null ? '' : value).replace(edgeWhitespace, '').toLowerCase();

  function normalizeSkills(list) {
    const out = new Set();
    (list || []).forEach((s) => {
      const k = cleanSkill(s);
      if (k) out.add(k);
    });
    return out;
  }

  function matchScore(candidateSkills, requiredSkills) {
    const C = normalizeSkills(candidateSkills);
    const R = normalizeSkills(requiredSkills);
    if (R.size === 0) return 100;
    let hit = 0;
    R.forEach((s) => { if (C.has(s)) hit++; });
    return Math.floor((100 * hit) / R.size);
  }

  function hasSkill(candidateSkills, skill) {
    return normalizeSkills(candidateSkills).has(cleanSkill(skill));
  }

  const lc = (s) => String(s == null ? '' : s).toLowerCase();
  // JS's UTF-16 ordering differs from Python for supplementary characters.
  function cmp(a, b) {
    const left = Array.from(String(a)), right = Array.from(String(b));
    for (let index = 0; index < Math.min(left.length, right.length); index++) {
      const difference = left[index].codePointAt(0) - right[index].codePointAt(0);
      if (difference) return difference;
    }
    return left.length - right.length;
  }
  /* Integer ids compare numerically so "10" sorts after "2", matching the database. */
  function cmpId(a, b) {
    const as = String(a), bs = String(b);
    if (/^\d+$/.test(as) && /^\d+$/.test(bs)) return as.length - bs.length || cmp(as, bs);
    return cmp(as, bs);
  }

  /* Candidate dashboard: score desc, then case-insensitive job title, then stable job id. */
  function compareJobs(a, b) {
    return (b.match - a.match) || cmp(lc(a.title), lc(b.title)) || cmpId(a.id, b.id);
  }

  /* Employer applicants: score desc, then case-insensitive display name, then stable candidate id. */
  function compareApplicants(a, b) {
    return (b.match - a.match) || cmp(lc(a.name), lc(b.name)) || cmpId(a.candidateId, b.candidateId);
  }

  // Live portals consume API facts; these functions never normalize or score.
  function byServerRank(a, b) {
    if (!Number.isInteger(a.rank) || a.rank < 0 || !Number.isInteger(b.rank) || b.rank < 0)
      throw new Error('Missing authoritative API rank');
    return a.rank - b.rank;
  }
  function fromServer(rows) {
    return rows.map((row) => {
      if (!Number.isInteger(row.score) || row.score < 0 || row.score > 100 ||
          !Number.isInteger(row.rank) || row.rank < 0)
        throw new Error('Missing authoritative API score or rank');
      return { ...row, match: row.score };
    }).sort(byServerRank);
  }

  root.MWMatch = Object.freeze({ fromServer, byServerRank, normalizeSkills, matchScore, hasSkill, compareJobs, compareApplicants });
})(window);
