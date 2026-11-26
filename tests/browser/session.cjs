/* Use the same session CSRF contract as the shipped sign-in and portal pages. */
const assert = require('node:assert/strict');
async function postWithCsrf(context, base, route, data) {
  const tokenResponse = await context.request.get(base + '/api/auth/csrf');
  assert.equal(tokenResponse.status(), 200, await tokenResponse.text());
  const { csrfToken } = await tokenResponse.json();
  assert.ok(csrfToken);
  return context.request.post(base + route, { data, headers: { 'X-CSRF-Token': csrfToken } });
}
module.exports = { postWithCsrf };
