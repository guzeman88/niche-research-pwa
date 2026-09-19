export class AccountError extends Error { constructor(message: string, public status: number) { super(message) } }
export async function accountRequest<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/account${path}`, {
    method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: {'Content-Type':'application/json', 'X-Etgen-Request':'1'},
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(30000),
  })
  if (!response.headers.get('content-type')?.includes('application/json')) throw new AccountError('Account service is unavailable. Please try again.',503)
  const data = await response.json().catch(() => {throw new AccountError('Account service returned an incomplete response. Please try again.',503)})
  if (!response.ok) throw new AccountError(data.error || 'The account request failed.', response.status)
  return data as T
}
