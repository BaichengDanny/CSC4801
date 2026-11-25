const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const base=process.env.QA_BASE_URL||'http://127.0.0.1:8085';
const output=process.env.QA_OUTPUT||'output/qa-supplement/browser-normalization';
const results=[],contexts=[]; const run=Date.now().toString(36);
let browser,details={};
async function post(ctx,route,data,expected=200){
  const res=await ctx.request.post(base+route,{data});
  assert.equal(res.status(),expected,await res.text()); return res.json();
}
async function account(role,suffix){
  const ctx=await browser.newContext({viewport:{width:1440,height:1000}}); contexts.push(ctx);
  await ctx.route('**/*',r=>new URL(r.request().url()).origin===base?r.continue():r.abort());
  const email='qa-normalization-'+run+'-'+suffix+'@example.test';
  await post(ctx,'/api/auth/register',{email,password:'DemoPass123!',role,name:'Normalization '+suffix},201);
  return {ctx,email};
}
async function check(name,fn){
  try{await fn();results.push({name,status:'passed'});}
  catch(error){results.push({name,status:'failed',error:error.stack});}
  console.log(results.at(-1).status.toUpperCase()+' '+name);
}
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 browser=await chromium.launch({executablePath:process.env.QA_BROWSER||
   (process.platform === 'win32' ? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' : undefined),headless:true});
 const e=await account('Employer','employer'), c=await account('Candidate','candidate');
 const job=(await post(e.ctx,'/api/employer/jobs',
   {title:'BOM score '+run,body:'Normalization contract',skills:['Python','SQL','Rust']},201)).job;
 const profile=(await post(c.ctx,'/api/candidate/profile',{skills:['\uFEFFPython']})).profile;
 const application=(await post(c.ctx,'/api/candidate/applications',{jobId:job.id},201)).application;
 const candidate=await c.ctx.newPage(),employer=await e.ctx.newPage();
 await candidate.goto(base+'/candidate/jobs?id='+job.id,{waitUntil:'domcontentloaded'});
 await candidate.waitForFunction(()=>Boolean(window.MW));
 await employer.goto(base+'/recruiter/applicants?job='+job.id,{waitUntil:'domcontentloaded'});
 await employer.waitForFunction(()=>Boolean(window.RW));
 const candidateScore=await candidate.evaluate(id=>MW.job(id).match,job.id);
 const employerScore=await employer.evaluate(id=>RW.application(id).match,application.id);
 details={candidateEmail:c.email,employerEmail:e.email,jobId:job.id,applicationId:application.id,
   apiSkills:profile.skills,candidateScore,employerScore};
 await check('feff-api-to-both-visible-portals',async()=>{
   assert.deepEqual(profile.skills,['python']);
   assert.equal(candidateScore,33); assert.equal(employerScore,33);
   assert.ok((await candidate.locator('body').innerText()).includes('33%'));
   assert.ok((await employer.locator('body').innerText()).includes('33%'));
   await candidate.screenshot({path:path.join(output,'feff-candidate.png'),fullPage:true});
 });
 await check('actual-portals-use-tested-escape-function',async()=>{
   for(const [page,globalName] of [[candidate,'MW'],[employer,'RW']]){
     assert.equal(await page.evaluate(name=>window[name].esc===window.MWHTML.escape,globalName),true);
     assert.equal(await page.evaluate(name=>window[name].esc('<script>alert(1)</script>'),globalName),
       '&lt;script&gt;alert(1)&lt;/script&gt;');
   }
 });
 const jHigh=(await post(e.ctx,'/api/employer/jobs',
   {title:'\u{10000}',body:'higher code point',skills:['python','sql','rust']},201)).job;
 const jLow=(await post(e.ctx,'/api/employer/jobs',
   {title:'\uE000',body:'lower code point',skills:['python','sql','rust']},201)).job;
 await candidate.goto(base+'/candidate/jobs',{waitUntil:'domcontentloaded'});
 await candidate.waitForFunction(()=>Boolean(window.MW));
 await check('unicode-title-order-through-api-and-rendered-list',async()=>{
   const ids=[jLow.id,jHigh.id];
   const actual=await candidate.evaluate(ids=>MW.jobs().filter(j=>ids.includes(j.id)).map(j=>j.id),ids);
   const rendered=await candidate.locator('[data-id]').evaluateAll((nodes,ids)=>
     [...new Set(nodes.map(n=>n.dataset.id).filter(id=>ids.includes(id)))],ids);
   assert.deepEqual(actual,ids); assert.deepEqual(rendered,ids);
 });
})().catch(error=>results.push({name:'setup-or-runner',status:'failed',error:error.stack}))
.finally(async()=>{
 fs.mkdirSync(output,{recursive:true});
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({base,details,results},null,2));
 for(const ctx of contexts) await ctx.close(); if(browser) await browser.close();
 process.exitCode=results.some(r=>r.status==='failed')?1:0;
});
