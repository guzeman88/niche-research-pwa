export class AccountError extends Error { constructor(message: string, public status: number) { super(message) } }
export async function accountRequest<T>(path: string, body?: unknown, options: {signal?:AbortSignal} = {}): Promise<T> {
  const timeout=AbortSignal.timeout(30000)
  const signal=options.signal?AbortSignal.any([options.signal,timeout]):timeout
  try {
  const response = await fetch(`/api/account${path}`, {
    method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: {'Content-Type':'application/json', 'X-Etgen-Request':'1'},
    body: body === undefined ? undefined : JSON.stringify(body), signal,
  })
  if (!response.headers.get('content-type')?.includes('application/json')) throw new AccountError('Account service is unavailable. Please try again.',503)
  const data = await response.json().catch(error => {if(signal.aborted)throw error;throw new AccountError('Account service returned an incomplete response. Please try again.',503)})
  if (!response.ok) throw new AccountError(data.error || 'The account request failed.', response.status)
  return data as T
  } catch(error) {
    if(signal.aborted){
      if(signal.reason?.name==='TimeoutError')throw new AccountError(body===undefined?'The account check took too long. Retry the connection.':'The account service took too long to respond.',504)
      throw signal.reason
    }
    if(error instanceof TypeError)throw new AccountError('Could not reach the account service. Check your connection.',503)
    throw error
  }
}
