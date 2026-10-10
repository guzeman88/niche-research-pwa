const http = require('node:http');
const https = require('node:https');

// Service keys may use HTTP only on the local machine during self-hosted builds.
function supabaseTransport(url) {
  if (url.username || url.password) throw new Error('Supabase credentials must be passed in headers.');
  if (url.protocol === 'https:') return https;
  if (url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) return http;
  throw new Error('Supabase requires HTTPS except for a loopback self-hosted endpoint.');
}

module.exports = { supabaseTransport };
