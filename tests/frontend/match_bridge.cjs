/* Execute the actual browser implementation without copying its algorithm. */
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const sandbox = {window:{}};
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'../../shared/match.js'),'utf8'),sandbox);
const match=sandbox.window.MWMatch;
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const output={
  scores:input.cases.map(c=>match.matchScore(c.candidate,c.required)),
  jobs:input.jobGroups.map(group=>group.slice().sort(match.compareJobs).map(j=>j.id)),
  applicants:input.applicantGroups.map(group=>group.slice().sort(match.compareApplicants).map(a=>a.candidateId))
};
process.stdout.write(JSON.stringify(output));
