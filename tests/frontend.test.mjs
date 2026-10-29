import test from 'node:test';
import assert from 'node:assert/strict';
import {filterPaths,expandCommand,cleanTheme,isImage,compactEvents,workspacePath} from '../frontend/utils.js';
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
test('history replay coalesces streaming chunks without crossing tool boundaries',()=>{
  const original=[{type:'assistant_delta',text:'hello '},{type:'assistant_delta',text:'world'},{type:'assistant_end'},{type:'tool_start',id:'1'},{type:'command_output',id:'1',text:'a'},{type:'command_output',id:'1',text:'b'},{type:'command_output',id:'2',text:'c'}];
  const compacted=compactEvents(original);
  assert.equal(compacted.length,5);assert.equal(compacted[0].text,'hello world');assert.equal(compacted[3].text,'ab');assert.equal(original[0].text,'hello ');
});
test('Windows model paths share a relative editor tab without confusing sibling roots',()=>{
  assert.equal(workspacePath('E:\\Project\\src\\main.py','e:\\project'),'src/main.py');
  assert.equal(workspacePath('src/main.py','E:\\Project'),'src/main.py');
  assert.equal(workspacePath('E:\\ProjectOther\\main.py','E:\\Project'),'E:/ProjectOther/main.py');
});
