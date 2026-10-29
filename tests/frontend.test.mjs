import test from 'node:test';
import assert from 'node:assert/strict';
import {filterPaths,expandCommand,cleanTheme,isImage} from '../frontend/utils.js';
test('quick-open ranks basename matches and limits results',()=>{
  assert.deepEqual(filterPaths(['deep/main.py','main.py','main/tests.py','other.py'],'main',2),['main.py','deep/main.py']);
});
test('slash commands preserve the user addition',()=>{
  assert.match(expandCommand('/fix only the empty-list case'),/最小修改/);
  assert.match(expandCommand('/fix only the empty-list case'),/only the empty-list case$/);
  assert.equal(expandCommand('/not-a-command text'),'/not-a-command text');
});
test('untrusted theme values cannot become CSS or HTML',()=>{
  assert.equal(cleanTheme('dark'),'dark');assert.equal(cleanTheme('<script>'),'light');
  assert.equal(isImage('a.PnG'),true);assert.equal(isImage('main.py'),false);
});
