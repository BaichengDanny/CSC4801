const { postWithCsrf } = require('./session.cjs');
/* Local browser acceptance checks. Requires Playwright and an installed Chromium browser.
   See Browser acceptance in INSTALL.md for setup and QA_BASE_URL. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const base = process.env.QA_BASE_URL || 'http://127.0.0.1:8081';
const output = process.env.QA_OUTPUT || 'output/qa/browser';
const password = 'DemoPass123!';
const runId = Date.now().toString(36);
const results = [];
const contexts = [];
const dialogs = [];
let browser;
let candidatePage;
let employerPage;

async function check(name, action) {
  try {
    const detail = await action();
    results.push({ name, status: 'passed', detail: detail || null });
    console.log('PASS ' + name);
  } catch (error) {
    results.push({ name, status: 'failed', error: error.stack });
    console.log('FAIL ' + name + ': ' + error.message);
  }
}

async function newContext() {
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  // Exercise the local application without depending on external font servers.
  await context.route('**/*', route => {
    const host = new URL(route.request().url()).hostname;
    return ['127.0.0.1', 'localhost'].includes(host) ? route.continue() : route.abort();
  });
  context.on('page', page => page.on('dialog', async dialog => {
    dialogs.push(dialog.message());
    await dialog.dismiss();
  }));
  contexts.push(context);
  return context;
}

async function register(context, role, suffix, name) {
  const response = await postWithCsrf(context, base, '/api/auth/register',
    {email: 'qa-' + runId + '-' + suffix + '@example.test', password, role, name});
  assert.equal(response.status(), 201, await response.text());
}

async function navigate(page, route, globalName) {
  await page.goto(base + route, {waitUntil: 'domcontentloaded'});
  await page.waitForFunction(name => Boolean(window[name]), globalName);
}

async function post(context, route, data, expected = 200) {
  const response = await postWithCsrf(context, base, route, data);
  assert.equal(response.status(), expected, await response.text());
  return response.json();
}

async function main() {
  fs.mkdirSync(output, {recursive: true});
  browser = await chromium.launch({
    executablePath: process.env.QA_BROWSER || (process.platform === 'win32' ? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' : undefined),
    headless: true
  });

  await check('browser-signup-and-session', async () => {
    const context = await newContext();
    candidatePage = await context.newPage();
    await candidatePage.goto(base + '/sign-in', {waitUntil: 'domcontentloaded'});
    await candidatePage.locator('#signup-link').click();
    await candidatePage.locator('#name').fill('QA Candidate');
    await candidatePage.locator('#email').fill('qa-' + runId + '-candidate@example.test');
    await candidatePage.locator('#password').fill(password);
    await candidatePage.locator('#submit-btn').click();
    await candidatePage.waitForURL('**/candidate/dashboard');
    await candidatePage.waitForFunction(() => Boolean(window.MW));
    const response = await context.request.get(base + '/api/auth/me');
    assert.equal((await response.json()).role, 'Candidate');
    await candidatePage.screenshot({path: path.join(output, 'candidate-dashboard.png'), fullPage: true});
  });

  await check('full-publish-apply-interview-booking-flow', async () => {
    assert.ok(candidatePage, 'Signup must finish first');
    const context = await newContext();
    await register(context, 'Employer', 'employer', 'QA Employer');
    employerPage = await context.newPage();
    await navigate(employerPage, '/recruiter/jobs?new=1', 'RW');
    await employerPage.locator('#fTitle').fill('QA workflow engineer ' + runId);
    await employerPage.locator('#fDesc').fill('Verify the complete recruiting workflow');
    await employerPage.locator('#fBody').fill('Build reliable Python services.');
    await employerPage.locator('#fSkill').fill('Python');
    await employerPage.locator('#fSkill').press('Enter');
    const [created] = await Promise.all([
      employerPage.waitForResponse(response =>
        response.url().endsWith('/api/employer/jobs') && response.request().method() === 'POST'),
      employerPage.locator('#saveJob').click()
    ]);
    assert.equal(created.status(), 201);
    const jobId = (await created.json()).job.id;

    await post(candidatePage.context(), '/api/candidate/profile', {skills: ['Python']});
    await navigate(candidatePage, '/candidate/jobs?id=' + jobId, 'MW');
    const [applied] = await Promise.all([
      candidatePage.waitForResponse(response =>
        response.url().endsWith('/api/candidate/applications') && response.request().method() === 'POST'),
      candidatePage.locator('[data-id="' + jobId + '"] [data-act="apply"]').first().click()
    ]);
    assert.equal(applied.status(), 201);
    const application = (await applied.json()).application;
    assert.equal(application.status, 'Pending');

    await navigate(employerPage, '/recruiter/applicants?job=' + jobId, 'RW');
    const [statusResponse] = await Promise.all([
      employerPage.waitForResponse(response =>
        response.url().endsWith('/applications/' + application.id + '/status')),
      employerPage.locator('.status-grid button[data-v="Interviewing"]').click()
    ]);
    assert.equal(statusResponse.status(), 200);

    await navigate(employerPage, '/recruiter/interviews', 'RW');
    await employerPage.locator('#days .day').nth(1).click();
    const [slotReply] = await Promise.all([
      employerPage.waitForResponse(response =>
        response.url().endsWith('/api/employer/slots') && response.request().method() === 'POST'),
      employerPage.locator('#times button.t[aria-label^="Add a slot"]').first().click()
    ]);
    assert.equal(slotReply.status(), 201, await slotReply.text());
    const slot = (await slotReply.json()).slot;

    await navigate(candidatePage, '/candidate/interviews', 'MW');
    await candidatePage.locator('#book-' + application.id + ' label.slot[data-slot="' + slot.id + '"]').click();
    assert.ok(await candidatePage.locator('input[name="slot-' + application.id + '"][value="' + slot.id + '"]').isChecked());
    const [bookingResponse] = await Promise.all([
      candidatePage.waitForResponse(response =>
        response.url().endsWith('/applications/' + application.id + '/book')),
      candidatePage.locator('[data-confirm="' + application.id + '"]').click()
    ]);
    assert.equal(bookingResponse.status(), 200);
    await candidatePage.reload({waitUntil: 'domcontentloaded'});
    await candidatePage.waitForFunction(() => Boolean(window.MW));
    const candidateBooking = await candidatePage.evaluate(id =>
      window.MW.state.applications.find(item => item.id === id), application.id);
    assert.equal(candidateBooking.slotId, slot.id);
    assert.ok(await candidatePage.getByText('Tomorrow', {exact:true}).count());

    await navigate(employerPage, '/recruiter/applicants?job=' + jobId, 'RW');
    const employerBooking = await employerPage.evaluate(id => window.RW.application(id), application.id);
    assert.equal(employerBooking.slot.id, slot.id);
    await employerPage.locator('.status-grid button[data-v="Accepted"]').click();
    await candidatePage.reload({waitUntil: 'domcontentloaded'});
    await candidatePage.waitForFunction(() => Boolean(window.MW));
    const afterDecision = await candidatePage.evaluate(id =>
      window.MW.state.applications.find(item => item.id === id), application.id);
    assert.equal(afterDecision.status, 'Accepted');
    assert.equal(afterDecision.slotId, slot.id);
    await post(context, '/api/employer/slots/' + slot.id + '/delete', {}, 409);
    await candidatePage.screenshot({path: path.join(output, 'booking-confirmed.png'), fullPage: true});
    return {jobId, applicationId: application.id, slotId: slot.id, utc: slot.start};
  });

  await check('frontend-matching-formula-normalization-and-ties', async () => {
    await navigate(candidatePage, '/candidate/dashboard', 'MW');
    const examples = [
      [['Python', 'SQL'], ['Python', 'SQL'], 100],
      [['Python'], ['Python', 'SQL'], 50],
      [['Rust'], ['Python', 'SQL'], 0],
      [[], [], 100],
      [[' PYTHON ', 'python', '', 'SQL'], [' python', 'SQL ', 'sql', ''], 100],
      [['Python'], ['python', 'sql', 'rust'], 33]
    ];
    for (const [candidate, required, expected] of examples) {
      assert.equal(await candidatePage.evaluate(args => window.MWMatch.matchScore(...args),
        [candidate, required]), expected);
    }
    const ordering = await candidatePage.evaluate(() => ({
      jobs: [{id:'10',seq:10,title:'ALPHA',match:50}, {id:'2',seq:2,title:'alpha',match:50}]
        .sort(window.MWMatch.compareJobs).map(item=>item.id),
      applicants: [{candidateId:'10',name:'ALEX',match:50}, {candidateId:'2',name:'alex',match:50}]
        .sort(window.MWMatch.compareApplicants).map(item=>item.candidateId)
    }));
    assert.deepEqual(ordering.jobs, ['2', '10']);
    assert.deepEqual(ordering.applicants, ['2', '10']);
  });

  await check('rendered-xss-and-profile-persistence', async () => {
    assert.equal(await candidatePage.evaluate(() => MW.esc === MWHTML.escape), true);
    assert.equal(await employerPage.evaluate(() => RW.esc === MWHTML.escape), true);
    const payload = '<script>alert(1)</script>';
    const imagePayload = '<img src=x onerror="window.__qaXss=1">';
    const privateResume = 'QA_PRIVATE_RESUME_' + runId + payload + imagePayload;
    await post(candidatePage.context(), '/api/candidate/profile',
      {name: payload, resume: privateResume, skills: ['Python', payload]});
    await navigate(candidatePage, '/candidate/profile', 'MW');
    assert.equal(await candidatePage.evaluate(() => window.__qaXss), undefined);
    assert.ok((await candidatePage.locator('#resumeText').textContent()).includes(payload));
    assert.equal(await candidatePage.locator('#resumeText script, #resumeText img').count(), 0);
    await candidatePage.locator('#editBasics').click();
    await candidatePage.locator('#fName').fill('QA Profile Saved');
    await candidatePage.getByRole('button', {name:'Save profile', exact:true}).click();
    await candidatePage.reload({waitUntil:'domcontentloaded'});
    await candidatePage.waitForFunction(() => Boolean(window.MW));
    assert.equal(await candidatePage.evaluate(() => window.MW.state.profile.name), 'QA Profile Saved');

    const context = await newContext();
    await register(context, 'Employer', 'xss-employer', 'QA XSS Employer');
    await post(context, '/api/employer/company', {name: payload, about: imagePayload});
    const job = (await post(context, '/api/employer/jobs',
      {title: payload, body: imagePayload, skills: [payload]}, 201)).job;
    await navigate(candidatePage, '/candidate/jobs?id=' + job.id, 'MW');
    assert.equal(await candidatePage.evaluate(() => window.__qaXss), undefined);
    assert.equal(await candidatePage.locator('img[src="x"]').count(), 0);
    const other = await newContext();
    await register(other, 'Candidate', 'privacy', 'QA Other Candidate');
    assert.ok(!(await (await other.request.get(base + '/api/candidate/bootstrap')).text()).includes(privateResume));
    assert.ok(!(await (await context.request.get(base + '/api/employer/bootstrap')).text()).includes(privateResume));
    assert.deepEqual(dialogs, []);
    await candidatePage.screenshot({path:path.join(output,'escaped-user-text.png'),fullPage:true});
  });

  await check('closed-job-rejection-does-not-claim-application', async () => {
    const job = (await post(employerPage.context(), '/api/employer/jobs',
      {title: 'Closed role ' + runId, body: 'This role is closed', skills: [], status: 'Closed'}, 201)).job;
    await navigate(candidatePage, '/candidate/jobs?id=' + job.id, 'MW');
    const button = candidatePage.locator('[data-id="' + job.id + '"] [data-act="apply"]').first();
    const [response] = await Promise.all([
      candidatePage.waitForResponse(r => r.url().endsWith('/api/candidate/applications') && r.request().method() === 'POST'),
      button.click()
    ]);
    assert.equal(response.status(), 409);
    await candidatePage.waitForTimeout(150);
    assert.equal(await candidatePage.evaluate(id => Boolean(MW.appForJob(id)), job.id), false);
    assert.equal(await button.getAttribute('aria-disabled'), null);
    assert.doesNotMatch(await button.innerText(), /Applied/);
    const applications = await (await candidatePage.context().request.get(base + '/api/candidate/bootstrap')).json();
    assert.equal(applications.state.applications.some(a => a.jobId === job.id), false);
  });

  await check('far-future-slot-delete-keeps-selected-calendar-day', async () => {
    await navigate(employerPage, '/recruiter/interviews', 'RW');
    const start = new Date(); start.setUTCDate(start.getUTCDate() + 40); start.setUTCHours(18, 0, 0, 0);
    const slot = (await post(employerPage.context(), '/api/employer/slots',
      {start: start.toISOString(), end: new Date(start.getTime() + 1800000).toISOString()}, 201)).slot;
    const day = await employerPage.evaluate(start => RW.ymdOf(new Date(start)), start.toISOString());
    await navigate(employerPage, '/recruiter/interviews?day=' + day, 'RW');
    assert.equal(await employerPage.locator('#days [aria-pressed="true"]').getAttribute('data-day'), day);
    const [response] = await Promise.all([
      employerPage.waitForResponse(r => r.url().endsWith('/slots/' + slot.id + '/delete')),
      employerPage.locator('#times button[data-slot="' + slot.id + '"]').click()
    ]);
    assert.equal(response.status(), 200);
    await employerPage.reload({waitUntil: 'domcontentloaded'});
    await employerPage.waitForFunction(() => Boolean(window.RW));
    assert.equal(await employerPage.locator('#days [aria-pressed="true"]').getAttribute('data-day'), day);
    assert.equal(await employerPage.locator('#mDate').inputValue(), day);
    assert.equal(await employerPage.evaluate(id => RW.state.slots.some(s => s.id === id), slot.id), false);
  });

  await check('pacific-time-roundtrip-on-daylight-saving-transition', async () => {
    await navigate(employerPage, '/recruiter/interviews', 'RW');
    const values = await employerPage.evaluate(() => [
      window.RW.ptToUtc('2027-03-14', 9, 0),
      window.RW.ptToUtc('2027-11-07', 9, 0)
    ]);
    assert.deepEqual(values, ['2027-03-14T16:00:00.000Z','2027-11-07T17:00:00.000Z']);
    const invalidTimes = await employerPage.evaluate(() => [
      window.RW.ptToUtc('2027-03-14', 2, 30),
      window.RW.ptToUtc('2027-11-07', 1, 30)
    ]);
    assert.deepEqual(invalidTimes, [null, null], 'Reject skipped and repeated wall times');
    for (const [date, start, end] of [
      ['2027-03-14', '02:00', '02:30'], ['2027-11-07', '01:00', '01:30']
    ]) {
      await employerPage.locator('#mDate').fill(date);
      await employerPage.locator('#mStart').fill(start);
      await employerPage.locator('#mEnd').fill(end);
      await employerPage.locator('#manual button[type=submit]').click();
      assert.match(await employerPage.locator('#mErr').innerText(), /occurs once in Pacific Time/);
    }
  });

  await check('mobile-pages-fit-390px-viewport', async () => {
    const measured=[];
    for (const [page, route, globalName] of [
      [candidatePage,'/candidate/profile','MW'],
      [employerPage,'/recruiter/applicants','RW']
    ]) {
      await page.setViewportSize({width:390,height:844});
      await navigate(page,route,globalName);
      const width=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
      measured.push({route,...width});
      await page.screenshot({path:path.join(output,globalName+'-mobile.png'),fullPage:true});
      assert.ok(width.document <= width.viewport + 1, JSON.stringify({route,...width}));
    }
    return measured;
  });

  await check('logout-revokes-api-access', async () => {
    const context = candidatePage.context();
    await post(context, '/api/auth/logout', {});
    assert.equal((await context.request.get(base+'/api/candidate/bootstrap')).status(),401);
    await candidatePage.goto(base+'/candidate/profile',{waitUntil:'domcontentloaded'});
    await candidatePage.waitForURL('**/sign-in#candidate');
  });

  for (const context of contexts) await context.close();
  await browser.close();
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({base,runId,results},null,2));
  console.log(JSON.stringify(results.map(({name,status})=>({name,status})),null,2));
  if (results.some(result=>result.status==='failed')) process.exitCode=1;
}

main().catch(async error=>{
  console.error(error);
  if(browser) await browser.close();
  process.exitCode=1;
});
