const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { supabaseTransport } = require('../supabase-transport.cjs');

test('local self-hosted snapshot request carries headers over loopback HTTP', async () => {
  const server = http.createServer((req, res) => {
    assert.equal(req.headers.apikey, 'synthetic-service-key');
    res.setHeader('Content-Type', 'application/json');
    res.end('[{"keyword":"preserved research"}]');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const url = new URL(`http://127.0.0.1:${server.address().port}/rest/v1/keyword_seeds`);
    const body = await new Promise((resolve, reject) => {
      supabaseTransport(url).get(url, {headers: {apikey: 'synthetic-service-key'}}, response => {
        let text = ''; response.on('data', chunk => text += chunk);
        response.on('end', () => resolve(JSON.parse(text)));
      }).on('error', reject);
    });
    assert.deepEqual(body, [{keyword: 'preserved research'}]);
  } finally { await new Promise(resolve => server.close(resolve)); }
});

test('remote plaintext and lookalike loopback URLs cannot receive service keys', () => {
  for (const url of ['http://example.com', 'http://192.168.1.5', 'http://127.0.0.1.example.com', 'ftp://localhost']) {
    assert.throws(() => supabaseTransport(new URL(url)), /requires HTTPS/);
  }
  assert.throws(() => supabaseTransport(new URL('https://user:password@example.com')), /headers/);
});
