const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/mobile-navigation.js', 'utf8');
for (const isMobile of [true, false]) {
  let focused = false;
  const handlers = {};
  const media = { matches: isMobile, addEventListener: (name, fn) => { handlers.change = fn; } };
  const sidebar = { hidden: false };
  const toggle = { setAttribute: (name, value) => { toggle[name] = value; }, focus: () => { focused = true; }, addEventListener: (name, fn) => { handlers[name] = fn; } };
  const navigation = { querySelector: selector => selector === 'button' ? toggle : sidebar, addEventListener: (name, fn) => { handlers[name] = fn; } };
  vm.runInNewContext(source, { document: { querySelector: () => navigation }, window: { matchMedia: () => media } });
  assert.equal(sidebar.hidden, isMobile);
  assert.equal(toggle['aria-expanded'], String(!isMobile));
  if (isMobile) { handlers.click(); assert.equal(sidebar.hidden, false); }
  handlers.keydown({ key: 'Escape' });
  assert.equal(sidebar.hidden, isMobile);
  assert.equal(focused, isMobile);
  media.matches = !isMobile;
  handlers.change();
  assert.equal(sidebar.hidden, !isMobile);
}
vm.runInNewContext(source, { document: { querySelector: () => null } });
console.log('Mobile navigation: collapse, toggle, Escape focus, resize and public pages passed.');
