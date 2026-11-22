/* Matchwork matching contract (FP-MATCH-1), shared by the candidate and employer portals.
   Both sides call this one implementation, so a score never differs between views.

   Normalize: trim, lowercase, drop empty values, drop duplicates.
   score = 100                                   when |R| = 0
   score = floor(100 * |C ∩ R| / |R|)            otherwise                                   */
(function (root) {
  'use strict';

  function normalizeSkills(list) {
    const out = new Set();
    (list || []).forEach((s) => {
      const k = String(s == null ? '' : s).trim().toLowerCase();
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
    return normalizeSkills(candidateSkills).has(String(skill == null ? '' : skill).trim().toLowerCase());
  }

  const lc = (s) => String(s == null ? '' : s).toLowerCase();
  const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

  /* Candidate dashboard: score desc, then case-insensitive job title, then stable job id. */
  function compareJobs(a, b) {
    return (b.match - a.match) || cmp(lc(a.title), lc(b.title)) || cmp(a.seq != null ? a.seq : a.id, b.seq != null ? b.seq : b.id);
  }

  /* Employer applicants: score desc, then case-insensitive display name, then stable candidate id. */
  function compareApplicants(a, b) {
    return (b.match - a.match) || cmp(lc(a.name), lc(b.name)) || cmp(String(a.candidateId), String(b.candidateId));
  }

  root.MWMatch = Object.freeze({ normalizeSkills, matchScore, hasSkill, compareJobs, compareApplicants });
})(window);
