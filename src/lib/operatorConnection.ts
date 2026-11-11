const KEY = 'etgen:operator-connection'
const LOCAL_KEY = 'etgen:local-validation-address'
const DISCONNECTED_KEY = 'etgen:operator-disconnected'
export interface OperatorConnection { url: string; token: string }

function localValidationPage() {
  return ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname) && ['/validation', '/selling'].includes(location.pathname)
}

function loopbackOrigin(value: string) {
  try {const url = new URL(value); return url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) && url.origin === value}
  catch {return false}
}

export function readConnection(): OperatorConnection {
  try {
    const connection = JSON.parse(sessionStorage.getItem(KEY) || 'null')
    if (connection) return connection
    // Account refresh still clears every operator token. Retain only an explicit
    // loopback address for the standalone local validation page, never credentials.
    const local = sessionStorage.getItem(LOCAL_KEY) || ''
    const installed = localValidationPage() && location.port === '5175' && sessionStorage.getItem(DISCONNECTED_KEY) !== '1'
    return {url: localValidationPage() && loopbackOrigin(local) ? local : installed ? 'http://127.0.0.1:18020' : '', token: ''}
  }
  catch { return {url: '', token: ''} }
}

export function saveConnection(connection: OperatorConnection) {
  const url = new URL(connection.url)
  if (url.username || url.password || url.search || url.hash || !['', '/'].includes(url.pathname)) {
    throw new Error('Enter the backend origin, without a path or credentials.')
  }
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname))) {
    throw new Error('Use HTTPS for a remote backend.')
  }
  sessionStorage.setItem(KEY, JSON.stringify({url: url.origin, token: connection.token.trim()}))
  sessionStorage.removeItem(DISCONNECTED_KEY)
  if (localValidationPage() && loopbackOrigin(url.origin)) sessionStorage.setItem(LOCAL_KEY, url.origin)
  else sessionStorage.removeItem(LOCAL_KEY)
}

export function clearConnection(removeLocalAddress = false) {
  sessionStorage.removeItem(KEY)
  if (removeLocalAddress) {sessionStorage.removeItem(LOCAL_KEY); sessionStorage.setItem(DISCONNECTED_KEY, '1')}
}

export function operatorHeaders(url: string): Record<string, string> {
  const connection = readConnection()
  return connection.url === url && connection.token ? {Authorization: `Bearer ${connection.token}`} : {}
}

export async function operatorRequest<T>(path: string, body?: unknown): Promise<T> {
  const {url} = readConnection()
  if (!url) throw new Error('Connect to your backend first.')
  const response = await fetch(`${url}${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {'Content-Type': 'application/json', ...operatorHeaders(url)},
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(path.startsWith('/api/production') ? 120000 : 20000),
  }).catch((error: unknown) => {
    if (localValidationPage() && location.port === '5175' && loopbackOrigin(url)) {
      throw new Error('EtGen’s local service is unavailable. Open EtGen from its launcher, then retry the connection.')
    }
    throw error
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({})) as {detail?: unknown}
    throw new Error(response.status === 401 ? 'The backend rejected the connection. Check your operator token.'
      : typeof detail.detail === 'string' ? detail.detail : `Backend request failed (${response.status}).`)
  }
  return response.json() as Promise<T>
}
