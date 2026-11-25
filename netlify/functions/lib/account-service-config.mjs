// A dedicated account project must never inherit a research-project credential.
export function accountServiceConfig(env) {
  const dedicated=['ACCOUNT_SUPABASE_URL','ACCOUNT_SUPABASE_ANON_KEY','ACCOUNT_SUPABASE_SERVICE_ROLE_KEY'].some(key=>Boolean(env[key]));
  const prefix=dedicated?'ACCOUNT_':'';
  return {
    dedicated,
    url:env[prefix+'SUPABASE_URL'],
    anonKey:env[prefix+'SUPABASE_ANON_KEY'],
    serviceKey:env[prefix+'SUPABASE_SERVICE_ROLE_KEY'],
  };
}
