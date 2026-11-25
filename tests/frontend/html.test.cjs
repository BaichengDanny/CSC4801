const {test} = require('node:test');
const assert = require('node:assert/strict');
const {escape} = require('../../shared/html.js');
const examples = [
  ['script-tag', '<script>alert(1)</script>', '&lt;script&gt;alert(1)&lt;/script&gt;'],
  ['event-attribute', '<img src=x onerror="alert(1)">', '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;'],
  ['attribute-breakout', '\'" autofocus onfocus="alert(1)', '&#39;&quot; autofocus onfocus=&quot;alert(1)'],
  ['all-delimiters', '&<>"\'', '&amp;&lt;&gt;&quot;&#39;'],
  ['entity-is-text', '&lt;script&gt;', '&amp;lt;script&amp;gt;'],
  ['unicode-and-lines', '中文\nPython', '中文\nPython'],
  ['null-is-empty', null, ''],
  ['number-is-text', 42, '42']
];
for (const [name,input,expected] of examples) {
  test('product escape: '+name, () => {
    const actual = escape(input);
    assert.equal(actual, expected);
    assert.ok(!actual.includes('<') && !actual.includes('>'));
    assert.ok(!actual.includes('"') && !actual.includes("'"));
  });
}
test('a quoted attribute and text node retain a single template boundary', () => {
  const untrusted = '"><svg onload=alert(1)><!--';
  const actual = '<span title="' + escape(untrusted) + '">' + escape(untrusted) + '</span>';
  assert.equal(actual,
    '<span title="&quot;&gt;&lt;svg onload=alert(1)&gt;&lt;!--">&quot;&gt;&lt;svg onload=alert(1)&gt;&lt;!--</span>');
});
