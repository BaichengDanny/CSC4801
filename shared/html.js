/* Escape untrusted text for HTML text and quoted-attribute contexts.
   URL validation and trusted HTML templates are separate responsibilities. */
(function (root) {
  'use strict';
  function escape(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (character) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[character]));
  }
  const api = Object.freeze({escape});
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.MWHTML = api;
})(typeof window !== 'undefined' ? window : null);
