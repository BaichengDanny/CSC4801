const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const context={window:{}};
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'../../shared/match.js'),'utf8'),context);
const data=JSON.parse(fs.readFileSync(0,'utf8'));
const project=groups=>groups.map(rows=>context.window.MWMatch.fromServer(rows).map(r=>({
 id:r.id,match:r.match,rank:r.rank,candidateId:r.candidateId
})));
process.stdout.write(JSON.stringify({candidate:project(data.candidate),employer:project(data.employer),
 jobs:project(data.jobs),applicants:project(data.applicants)}));
