const KEY = 'etgen:operator-connection'
export interface OperatorConnection { url: string; token: string }

export function readConnection(): OperatorConnection {
  try { return JSON.parse(sessionStorage.getItem(KEY) || 'null') || {url: '', token: ''} }
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
}

export function clearConnection() { sessionStorage.removeItem(KEY) }

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
    signal: AbortSignal.timeout(20000),
  })
  if (!response.ok) throw new Error(response.status === 401
    ? 'The backend rejected the connection. Check your operator token.' : `Backend request failed (${response.status}).`)
  return response.json() as Promise<T>
}
