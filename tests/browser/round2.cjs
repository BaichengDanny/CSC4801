const { postWithCsrf } = require('./session.cjs');
/* Round-2 regression: identical display names are not employer identities.
   Uses an independent headless browser and new synthetic accounts on a local app. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const base = process.env.QA_BASE_URL || 'http://127.0.0.1:8084';
const output = process.env.QA_OUTPUT || 'output/qa-round2/browser';
const results = [];
const contexts = [];
const run = Date.now().toString(36);
let browser;
async function post(context, route, data, expected = 200) {
  const response = await postWithCsrf(context, base, route, data);
  assert.equal(response.status(), expected, await response.text());
  return response.json();
}
async function account(role, suffix) {
  const context = await browser.newContext();
  await context.route('**/*', route =>
    new URL(route.request().url()).origin === base ? route.continue() : route.abort());
  contexts.push(context);
  await post(context, '/api/auth/register', {
    email: 'qa-r2-' + run + '-' + suffix + '@example.test',
    password: 'DemoPass123!', role, name: 'Round 2 ' + suffix
  }, 201);
  return context;
}
async function check(name, action) {
  try { const detail = await action(); results.push({name,status:'passed',detail}); }
  catch (error) {results.push({name,status:'failed',error:error.stack});}
  console.log(results.at(-1).status.toUpperCase() + ' ' + name);
}
(async () => {
  fs.mkdirSync(output, {recursive:true});
  browser = await chromium.launch({
    executablePath:process.env.QA_BROWSER || (process.platform === 'win32' ? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' : undefined),
    headless:true
  });
  const a = await account('Employer','owner-a'), b = await account('Employer','owner-b');
  const c = await account('Candidate','candidate');
  const company = 'Same display company ' + run;
  await post(a,'/api/employer/company',{name:company,about:'OWNER_A_DESCRIPTION'});
  await post(b,'/api/employer/company',{name:company,about:'OWNER_B_DESCRIPTION'});
  const ja = (await post(a,'/api/employer/jobs',{title:'Round2 owner A',body:'Role A',skills:[]},201)).job;
  const jb = (await post(b,'/api/employer/jobs',{title:'Round2 owner B',body:'Role B',skills:[]},201)).job;
  const app = (await post(c,'/api/candidate/applications',{jobId:ja.id},201)).application;
  await post(a,'/api/employer/applications/'+app.id+'/status',{status:'Interviewing'});
  const start = new Date(); start.setUTCDate(start.getUTCDate()+2); start.setUTCHours(18,0,0,0);
  const end = new Date(start.getTime()+1800000);
  const input = {start:start.toISOString(),end:end.toISOString()};
  const sa = (await post(a,'/api/employer/slots',input,201)).slot;
  const sb = (await post(b,'/api/employer/slots',input,201)).slot;
  const page = await c.newPage();
  await page.goto(base+'/candidate/interviews',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>Boolean(window.MW));
  await check('same-name-employers-have-distinct-bookable-slots',async()=>{
    const actual = await page.evaluate(id => {
      const app = MW.state.applications.find(x=>x.id===id);
      return MW.openSlotsFor(app).map(s=>s.id);
    },app.id);
    assert.deepEqual(actual,[sa.id]);
    assert.equal(await page.locator('#book-'+app.id+' [data-slot="'+sb.id+'"]').count(),0);
    await post(c,'/api/candidate/applications/'+app.id+'/book',{slotId:sb.id},403);
    await page.locator('#book-'+app.id+' label.slot[data-slot="'+sa.id+'"]').click();
    const [response] = await Promise.all([
      page.waitForResponse(r=>r.url().endsWith('/applications/'+app.id+'/book')),
      page.locator('[data-confirm="'+app.id+'"]').click()
    ]);
    assert.equal(response.status(),200);
    await page.screenshot({path:path.join(output,'distinct-employer-booking.png'),fullPage:true});
    return {jobA:ja.id,jobB:jb.id,slotA:sa.id,slotB:sb.id};
  });
  await check('same-name-company-details-follow-job-owner',async()=>{
    await page.goto(base+'/candidate/jobs?id='+ja.id,{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>Boolean(window.MW));
    const text = await page.locator('body').innerText();
    assert.ok(text.includes('OWNER_A_DESCRIPTION'),text.slice(-900));
    assert.ok(!text.includes('OWNER_B_DESCRIPTION'));
    await page.goto(base+'/candidate/jobs?id='+jb.id,{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>Boolean(window.MW));
    assert.ok((await page.locator('body').innerText()).includes('OWNER_B_DESCRIPTION'));
    return {company};
  });
})().catch(error=>{
  results.push({name:'setup-or-runner',status:'failed',error:error.stack});
}).finally(async()=>{
  fs.mkdirSync(output,{recursive:true});
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({base,results},null,2));
  for(const context of contexts) await context.close();
  if(browser) await browser.close();
  process.exitCode = results.some(r=>r.status==='failed') ? 1 : 0;
});
