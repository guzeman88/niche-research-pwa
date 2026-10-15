const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

const { outputText } = ts.transpileModule(fs.readFileSync(require.resolve('../../src/lib/keywordRights.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
});
const context = { exports: {} };
vm.runInNewContext(outputText, context);
const matches = keyword => Array.from(context.exports.keywordRightsMatches(keyword), row => ({ ...row }));

test('flags the names missed by the existing candidate screen', () => {
  for (const keyword of ['ted baker london shirt', 'ted baker dress shirt', 'ted baker shirts men']) {
    assert.deepEqual(matches(keyword), [{ term: 'Ted Baker', kind: 'brand name' }]);
  }
  assert.deepEqual(matches('baker mayfield shirt'), [{ term: 'Baker Mayfield', kind: 'public figure or fan name' }]);
});

test('recognizes case, accents, punctuation, plurals and possessives', () => {
  for (const keyword of ['POKÉMON mug', 'pokemon mug', '#Pokémon-shirt']) {
    assert.equal(matches(keyword)[0]?.term, 'Pokémon');
  }
  assert.equal(matches('Spider-Man print')[0]?.term, 'Spider-Man');
  assert.equal(matches('Taylor Swift’s lyrics')[0]?.term, 'Taylor Swift');
  assert.equal(matches('Disney-inspired artwork')[0]?.term, 'Disney');
  assert.equal(matches('Nike shoes')[0]?.term, 'Nike');
});

test('does not flag ordinary professions, customer names or partial word matches', () => {
  for (const keyword of ['baker shirt', 'teacher mug', 'basketball goodie bags', 'rolling teacher tote bag',
    'personalized mug for Jorge', 'marvellous garden print', 'Stanleyville map', '']) {
    assert.deepEqual(matches(keyword), [], keyword);
  }
});

test('keeps multiple reasons and flags fan-work wording without declaring infringement', () => {
  const result = matches('Star Wars fan art');
  assert.deepEqual(result.map(row => row.term), ['Star Wars', 'Fan art']);
  assert.equal('blocked' in result[0], false);
  assert.equal('cleared' in result[0], false);
});
