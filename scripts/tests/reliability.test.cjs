const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const {validateStoreIdeas} = require('../snapshot-contract.cjs');

function loadModule(file) {
  const source = fs.readFileSync(path.join(__dirname, '../../src/lib', file), 'utf8');
  const compiled = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const result = {exports:{}};
  new Function('exports','module',compiled)(result.exports,result);
  return result.exports;
}
const backups = loadModule('workspaceBackup.ts');
function storage(initial={}) {
  const rows = new Map(Object.entries(initial));
  return {getItem:key=>rows.get(key)??null,setItem:(key,value)=>rows.set(key,value),removeItem:key=>rows.delete(key)};
}

test('malformed recommendations cannot reach a release', () => {
  assert.throws(()=>validateStoreIdeas([{id:'bad',name:'Bad',profitScore:80,profitabilityEvidence:[]}]), /evidence/);
  validateStoreIdeas([]);
});
test('backup merge preserves local conflicts and adds incoming work', () => {
  const key='niche-research-pwa:stores:v1';
  const local=storage({[key]:JSON.stringify([{slug:'a',name:'Current',niche:'mugs'}])});
  const incoming=backups.parseBackup(JSON.stringify({schema_version:1,created_at:'2026-09-08',data:{[key]:[
    {slug:'a',name:'Older',niche:'mugs'},{slug:'b',name:'Second',niche:'art'}]}}));
  const preview=backups.previewMerge(incoming,local);
  assert.equal(preview.added,1);assert.equal(preview.conflicts,1);
  assert.equal(preview.data[key][0].name,'Current');
  assert.equal(JSON.parse(local.getItem(key)).length,1);
});
test('backup never includes connection credentials', () => {
  const local=storage({'etgen:operator-connection':'secret'});
  assert.deepEqual(backups.readBackup(local).data,{});
  assert.throws(()=>backups.parseBackup(JSON.stringify({schema_version:1,created_at:'x',data:{'etgen:operator-connection':'secret'}})), /unsupported/);
});
test('invalid backup is rejected before any writes', () => {
  assert.throws(()=>backups.parseBackup('{"schema_version":2}'), /version 1/);
  assert.throws(()=>backups.parseBackup('{"schema_version":1,"created_at":"x","data":{"niche-research-pwa:store-workspace:v1":{"__proto__":{}}}}'), /identifier/);
});
