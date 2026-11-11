const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function fixture() {
  const storage = new Map();
  const location = {hostname: '127.0.0.1', pathname: '/validation'};
  const context = {exports: {}, URL, location, sessionStorage: {
    getItem: key => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: key => storage.delete(key),
  }};
  const source = ts.transpileModule(fs.readFileSync('src/lib/operatorConnection.ts', 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020},
  }).outputText;
  vm.runInNewContext(source, context);
  return {api: context.exports, location, storage};
}

test('local validation survives account credential clearing without retaining a token', () => {
  const {api, location} = fixture();
  api.saveConnection({url: 'http://127.0.0.1:18020', token: 'fixture-token'});
  api.clearConnection();
  assert.equal(api.readConnection().url, 'http://127.0.0.1:18020');
  assert.equal(api.readConnection().token, '');
  location.pathname = '/evidence';
  assert.equal(api.readConnection().url, '');
  location.pathname = '/validation'; location.hostname = 'example.com';
  assert.equal(api.readConnection().url, '');
});

test('remote credentials and explicit disconnect never use the retained local address', () => {
  const {api, storage} = fixture();
  api.saveConnection({url: 'http://127.0.0.1:18020', token: ''});
  api.saveConnection({url: 'https://private.example.com', token: 'remote-fixture-token'});
  api.clearConnection();
  assert.equal(api.readConnection().url, '');
  assert.ok(![...storage.values()].some(value => value.includes('remote-fixture-token')));
  api.saveConnection({url: 'http://127.0.0.1:18020', token: ''});
  api.clearConnection(true);
  assert.equal(api.readConnection().url, '');
});

test('fresh installed local pages connect automatically without storing credentials', () => {
  const {api,location,storage}=fixture();location.port='5175';
  assert.equal(api.readConnection().url,'http://127.0.0.1:18020');
  assert.equal(api.readConnection().token,'');assert.equal(storage.size,0);
  location.pathname='/selling';assert.equal(api.readConnection().url,'http://127.0.0.1:18020');
  location.pathname='/evidence';assert.equal(api.readConnection().url,'');
  location.pathname='/validation';location.port='4173';assert.equal(api.readConnection().url,'');
  location.port='5175';location.hostname='public.example';assert.equal(api.readConnection().url,'');
});

test('installed defaults preserve explicit connections and respect explicit disconnect', () => {
  const {api,location}=fixture();location.port='5175';
  api.saveConnection({url:'https://private.example.com',token:'explicit-token'});
  assert.equal(api.readConnection().url,'https://private.example.com');
  api.clearConnection(true);assert.equal(api.readConnection().url,'');
  api.saveConnection({url:'http://127.0.0.1:18020',token:''});
  assert.equal(api.readConnection().url,'http://127.0.0.1:18020');
});
