// Provider failures are not invalid credentials and must not revoke a valid cookie.
export function accountServiceProblem(result) {
  const error=result?.error;
  const status=Number(result?.status||error?.status||0);
  const message=[error?.message,result?.data?.message,result?.message].filter(v=>typeof v==='string').join(' ');
  if(status===402||/exceed(?:ed)?_\w+_quota/.test(message)){
    const database=/exceed(?:ed)?_db_size_quota/.test(message);
    return {status:503,code:'account_service_restricted',reason:database?'database_size_quota':'provider_restriction',
      message:database?'Cloud sign-in and data are blocked by the provider’s database storage limit.':'The cloud account service is restricted by its hosting provider.'};
  }
  if(status>=500||error?.name==='AuthRetryableFetchError'||['25006','53100','57P03','PGRST000','PGRST001','PGRST002'].includes(error?.code))return {
    status:503,code:'account_service_unavailable',reason:'provider_unavailable',message:'The cloud account service is unavailable. Please retry later; this does not mean your password is incorrect.'};
  return null;
}
