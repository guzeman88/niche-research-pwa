export class ValidationError extends Error { status = 400; }
import { createCipheriv, createDecipheriv, createHash, randomBytes } from 'node:crypto';

export const hash = value => createHash('sha256').update(value).digest('hex');
export function seal(value, secret, context = '') {
  const key = Buffer.from(secret || '', 'base64');
  if (key.length !== 32) throw new ValidationError('Account encryption is not configured');
  const iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', key, iv);
  cipher.setAAD(Buffer.from(context));
  const body = Buffer.concat([cipher.update(JSON.stringify(value), 'utf8'), cipher.final()]);
  return Buffer.concat([iv, cipher.getAuthTag(), body]).toString('base64url');
}
export function unseal(value, secret, context = '') {
  const bytes = Buffer.from(value, 'base64url');
  const decipher = createDecipheriv('aes-256-gcm', Buffer.from(secret, 'base64'), bytes.subarray(0, 12));
  decipher.setAAD(Buffer.from(context)); decipher.setAuthTag(bytes.subarray(12, 28));
  return JSON.parse(Buffer.concat([decipher.update(bytes.subarray(28)), decipher.final()]).toString('utf8'));
}
export function trustedMutation(request, origin) {
  return request.headers.get('origin') === origin && request.headers.get('x-etgen-request') === '1'
    && request.headers.get('content-type')?.split(';')[0] === 'application/json';
}
export function validatePassword(value) {
  if (typeof value !== 'string' || value.length < 12 || value.length > 128) {
    throw new ValidationError('Use a password between 12 and 128 characters.');
  }
  return value;
}
export function validateProfile(value) {
  const allowed = ['display_name', 'business_name', 'timezone', 'currency'];
  if (!value || Object.keys(value).some(key => !allowed.includes(key))) throw new ValidationError('Invalid profile fields.');
  if (typeof value.display_name !== 'string' || !value.display_name.trim() || value.display_name.length > 80) throw new ValidationError('Enter a display name of 1–80 characters.');
  if (typeof value.business_name !== 'string' || value.business_name.length > 120) throw new ValidationError('Business name must be 120 characters or fewer.');
  try { new Intl.DateTimeFormat('en', {timeZone:value.timezone}).format(); } catch { throw new ValidationError('Choose a valid time zone.'); }
  if (!['USD','CAD','GBP','EUR','AUD'].includes(value.currency)) throw new ValidationError('Choose a supported currency.');
  return {...value, display_name:value.display_name.trim(), business_name:value.business_name.trim(), updated_at:new Date().toISOString()};
}
export function validateWorkspace(payload) {
  const keys = ['stores','store-workspace','user-keywords','user-scan-batches'].map(k => `niche-research-pwa:${k}:v1`);
  if (!payload || typeof payload !== 'object' || Array.isArray(payload) || Object.keys(payload).some(key => !keys.includes(key))) throw new ValidationError('Invalid workspace sections.');
  if (Buffer.byteLength(JSON.stringify(payload)) > 4 * 1024 * 1024) throw new ValidationError('Workspace exceeds 4 MB. Download a backup and reduce embedded image sizes.');
  return payload;
}

export function sessionCookie(id, origin, clear = false) {
  const secure = origin.startsWith('https:');
  return `${secure ? '__Host-etgen-session' : 'etgen-session'}=${id}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${clear ? 0 : 604800}${secure ? '; Secure' : ''}`;
}
export function readSessionCookie(request, origin) {
  const name = origin.startsWith('https:') ? '__Host-etgen-session' : 'etgen-session';
  return (request.headers.get('cookie') || '').split(';').map(s => s.trim()).find(s => s.startsWith(name + '='))?.slice(name.length + 1) || '';
}
