const { postWithCsrf } = require('./session.cjs');
/* QA3-04: real authenticated APIs -> live portal DOM, score/order and refresh. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const base=process.env.QA_BASE_URL||'http://127.0.0.1:8087';
const output=process.env.QA_OUTPUT||'output/qa3-04/authoritative-browser';
const run=Date.now().toString(36),contexts=[],results=[],pageErrors=[];
const cases=[['\u1C89','\u1C8A'],['\uA7CB','\u0264']];
let browser,cp,ep,candidate,employer,other,ids=[],apps=[];
async function post(ctx,route,data,expected=200){
 const response=await postWithCsrf(ctx, base, route, data);
 assert.equal(response.status(),expected,await response.text());return response.json();
}
async function bootstrap(ctx,role){
 const response=await ctx.request.get(base+'/api/'+role+'/bootstrap');
 assert.equal(response.status(),200);return response.json();
}
async function account(role,suffix,name){
 const ctx=await browser.newContext({viewport:{width:1440,height:1000}});
 await ctx.route('**/*',r=>new URL(r.request().url()).origin===base?r.continue():r.abort());
 ctx.on('page',page=>{page.on('dialog',dialog=>dialog.accept());page.on('pageerror',error=>pageErrors.push(error.stack));});
 // Any accidental use of the old browser calculator/comparator breaks the test.
 await ctx.addInitScript(()=>{
   let api;
   window.__legacyMatchingCalls=0;
   Object.defineProperty(window,'MWMatch',{configurable:true,get:()=>api,set(value){
     const forbidden=()=>{window.__legacyMatchingCalls++;throw new Error('Live page called legacy matching');};
     api=Object.freeze({...value,matchScore:forbidden,compareJobs:forbidden,
       compareApplicants:forbidden,normalizeSkills:forbidden,hasSkill:forbidden});
   }});
 });
 contexts.push(ctx);
 await post(ctx,'/api/auth/register',{email:'qa-authority-'+run+'-'+suffix+'@example.test',
   password:'DemoPass123!',role,name},201);
 return ctx;
}
async function visit(page,route,name){
 await page.goto(base+route,{waitUntil:'domcontentloaded'});
 await page.waitForFunction(name=>Boolean(window[name]),name);
}
async function verifyCandidate(){
 const data=await bootstrap(candidate,'candidate');
 const expected=data.jobs.filter(j=>ids.includes(j.id)).map(j=>[j.id,j.score,j.rank]);
 const actual=await cp.evaluate(ids=>MW.jobs().filter(j=>ids.includes(j.id)).map(j=>[j.id,j.match,j.rank]),ids);
 assert.deepEqual(actual,expected);
 if(new URL(cp.url()).pathname==='/candidate/jobs'){
   const rendered=await cp.locator('#list .row[data-id]').evaluateAll((nodes,ids)=>
     nodes.filter(n=>ids.includes(n.dataset.id)).map(n=>[n.dataset.id,parseInt(n.querySelector('.score').textContent)]),ids);
   assert.deepEqual(rendered,expected.map(([id,score])=>[id,score]));
 }
 return data;
}
async function verifyEmployer(jobId){
 const data=await bootstrap(employer,'employer');
 const expected=data.state.applications.filter(a=>a.jobId===jobId);
 const actual=await ep.evaluate(id=>RW.applicants(id).list.map(a=>[a.id,a.match,a.rank]),jobId);
 assert.deepEqual(actual,expected.map(a=>[a.id,a.score,a.rank]));
 const rendered=await ep.locator('#list .lrow[data-app]').evaluateAll(nodes=>
   nodes.map(n=>[n.dataset.app,parseInt(n.querySelector('.score').textContent)]));
 assert.deepEqual(rendered,expected.map(a=>[a.id,a.score]));
 return expected;
}
async function focusRefresh(page,name){
 await page.bringToFront();
 await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
 await page.waitForTimeout(80);
 assert.equal(await page.evaluate(name=>window.__legacyMatchingCalls,name),0);
}
async function check(name,fn){
 try{const detail=await fn();results.push({name,status:'passed',detail});}
 catch(error){results.push({name,status:'failed',error:error.stack,candidateURL:cp?.url(),employerURL:ep?.url(),pageErrors:[...pageErrors]});}
 console.log(results.at(-1).status.toUpperCase()+' '+name);
}
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 browser=await chromium.launch({headless:true,executablePath:process.env.QA_BROWSER||
   (process.platform==='win32'?'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe':undefined)});
 employer=await account('Employer','owner','Owner');
 candidate=await account('Candidate','candidate','SAME');
 other=await account('Candidate','other','same');
 await post(candidate,'/api/candidate/profile',{skills:[...cases.map(c=>c[0]),'Python']});
 await post(other,'/api/candidate/profile',{skills:cases.map(c=>c[1])});
 for(let index=0;index<cases.length;index++){
   const job=(await post(employer,'/api/employer/jobs',{title:'Unicode '+index+' '+run,
     body:'Authoritative Unicode scoring',skills:[cases[index][1]]},201)).job;
   ids.push(job.id);
   const own=(await post(candidate,'/api/candidate/applications',{jobId:job.id},201)).application;
   await post(other,'/api/candidate/applications',{jobId:job.id},201);
   apps.push(own.id);
 }
 const empty=(await post(employer,'/api/employer/jobs',{title:'Empty '+run,body:'Empty requirements',skills:[]},201)).job;
 ids.push(empty.id);
 cp=await candidate.newPage();ep=await employer.newPage();
 await visit(cp,'/candidate/jobs','MW');
 for(let index=0;index<cases.length;index++){
   await check('unicode-counterexample-'+index+'-api-to-both-portal-dom',async()=>{
     await visit(ep,'/recruiter/applicants?job='+ids[index],'RW');
     const data=await verifyCandidate();
     assert.equal(data.jobs.find(j=>j.id===ids[index]).score,0);
     const rows=await verifyEmployer(ids[index]);
     assert.deepEqual(rows.map(a=>a.score),[100,0]);
     assert.equal(await ep.evaluate(id=>RW.application(id).match,apps[index]),0);
     assert.equal(await cp.evaluate(()=>window.__legacyMatchingCalls),0);
     assert.equal(await ep.evaluate(()=>window.__legacyMatchingCalls),0);
   });
 }
 await check('read-only-server-preview-save-and-peer-refresh',async()=>{
   await visit(cp,'/candidate/profile#skills','MW');
   const before=(await bootstrap(candidate,'candidate')).state.profile.skills;
   let lastPreview;
   for(const [upper,lower] of cases){
     const [response]=await Promise.all([
       cp.waitForResponse(r=>r.url().endsWith('/api/candidate/matching-preview')),
       (async()=>{await cp.locator('#skillInput').fill(lower);await cp.locator('#skillInput').press('Enter');})()
     ]);
     assert.equal(response.status(),200);
     const preview=await response.json();
     lastPreview=preview;
     for(const id of ids.slice(0,2)) assert.equal(preview.jobs.find(j=>j.id===id).baselineScore,0);
   }
   assert.deepEqual((await bootstrap(candidate,'candidate')).state.profile.skills,before);
   assert.ok((await cp.locator('#impact').innerText()).includes('100%'));
   for(const id of ids.slice(0,2)) assert.equal(lastPreview.jobs.find(j=>j.id===id).score,100);
   const expectedDeltas=lastPreview.jobs.filter(j=>j.score!==j.baselineScore)
     .sort((a,b)=>Math.abs(b.score-b.baselineScore)-Math.abs(a.score-a.baselineScore)).slice(0,5)
     .map(j=>[j.title,j.baselineScore+'%',j.score+'%']);
   const renderedDeltas=await cp.locator('#impact .deltas li').evaluateAll(nodes=>nodes.map(n=>[
     n.querySelector('.t').textContent,n.querySelector('.from').textContent,
     n.querySelector('.up,.down').textContent]));
   assert.deepEqual(renderedDeltas,expectedDeltas);
   const [saved]=await Promise.all([
     cp.waitForResponse(r=>r.url().endsWith('/api/candidate/profile')&&r.request().method()==='POST'),
     cp.locator('#skSave').click()
   ]);
   assert.equal(saved.status(),200);
   await cp.evaluate(()=>{window.__sameDocument=42;MW.navigate('/candidate/jobs');});
   await cp.waitForFunction(()=>location.pathname==='/candidate/jobs' && document.querySelector('#list .row'),null,{timeout:12000});
   assert.equal(await cp.evaluate(()=>window.__sameDocument),42);
   await verifyCandidate();
   for(const id of ids.slice(0,2))assert.equal(await cp.evaluate(id=>MW.job(id).match,id),100);
   await focusRefresh(ep,'RW');
   const rows=await verifyEmployer(ids[1]);
   assert.deepEqual(rows.map(a=>a.score),[100,100]);
   return {profilePersisted:true,noPageReload:true};
 });
 await check('job-requirement-edits-refresh-current-and-other-portal',async()=>{
   await visit(ep,'/recruiter/applicants?job='+ids[0],'RW');
   for(const [skills,expected] of [[['Go'],0],[[],100]]){
     const result=await ep.evaluate(({id,skills})=>RW.updateJob(id,{skills}),{id:ids[0],skills});
     assert.equal(result.ok,true);
     const rows=await verifyEmployer(ids[0]);
     assert.deepEqual(rows.map(a=>a.score),[expected,expected]);
     await focusRefresh(cp,'MW');
     assert.equal(await cp.evaluate(id=>MW.job(id).match,ids[0]),expected);
     await verifyCandidate();
   }
 });
 await check('periodic-refresh-updates-visible-page-without-focus-or-reload',async()=>{
   await cp.bringToFront();
   assert.equal(await cp.evaluate(()=>document.hidden),false);
   await focusRefresh(cp,'MW');
   await cp.evaluate(()=>window.__periodicMarker=1);
   await post(employer,'/api/employer/jobs/'+ids[0],{skills:['never-matches']});
   await cp.waitForFunction(id=>MW.job(id).match===0,ids[0],{timeout:12000});
   assert.equal(await cp.evaluate(()=>window.__periodicMarker),1);
   await verifyCandidate();
 });
 await check('background-refresh-preserves-unsaved-skill-draft',async()=>{
   await visit(cp,'/candidate/profile#skills','MW');
   await cp.locator('#skillInput').fill('UnsavedOnly');
   await cp.locator('#skillInput').press('Enter');
   await post(employer,'/api/employer/jobs/'+ids[0],{skills:['Python']});
   assert.equal(await cp.evaluate(()=>MW.refresh()),false);
   assert.ok((await cp.locator('#skillBox').innerText()).includes('UnsavedOnly'));
   await cp.locator('#skDiscard').click();
   await focusRefresh(cp,'MW');
   assert.equal(await cp.evaluate(id=>MW.job(id).match,ids[0]),100);
   assert.ok(!(await cp.locator('#skillBox').innerText()).includes('UnsavedOnly'));
 });
 await check('dashboard-rank-and-score-refresh-without-document-reload',async()=>{
   await visit(cp,'/candidate/dashboard','MW');
   const verifyDashboard=async()=>{
     const data=await bootstrap(candidate,'candidate');
     const rendered=await cp.locator('article.job[data-id]').evaluateAll(nodes=>nodes.map(n=>[
       n.dataset.id,parseInt(n.querySelector('.score').textContent)]));
     assert.ok(rendered.length>0);
     assert.deepEqual(rendered,data.jobs.slice(0,rendered.length).map(j=>[j.id,j.score]));
   };
   await verifyDashboard();
   await cp.evaluate(()=>window.__dashboardMarker=7);
   await post(employer,'/api/employer/jobs/'+ids[0],{skills:['dashboard-missing']});
   await cp.waitForFunction(id=>MW.job(id).match===0,ids[0],{timeout:12000});
   assert.equal(await cp.evaluate(()=>window.__dashboardMarker),7);
   await verifyDashboard();
   await post(employer,'/api/employer/jobs/'+ids[0],{skills:[]});
   await focusRefresh(cp,'MW');
   await verifyDashboard();
 });
 await check('live-portals-never-call-browser-matching-under-refresh',async()=>{
   assert.equal(await cp.evaluate(()=>window.__legacyMatchingCalls),0);
   assert.equal(await ep.evaluate(()=>window.__legacyMatchingCalls),0);
   await cp.screenshot({path:path.join(output,'authoritative-profile.png'),fullPage:true});
   await ep.screenshot({path:path.join(output,'authoritative-applicants.png'),fullPage:true});
 });
})().catch(error=>results.push({name:'setup-or-runner',status:'failed',error:error.stack}))
.finally(async()=>{
 fs.mkdirSync(output,{recursive:true});
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({base,ids,apps,results},null,2));
 for(const context of contexts)await context.close();
 if(browser)await browser.close();
 process.exitCode=results.some(r=>r.status==='failed')?1:0;
});
