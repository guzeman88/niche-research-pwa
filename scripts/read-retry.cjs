const {setTimeout: delay}=require('node:timers/promises');

// Only idempotent snapshot reads use this helper. Validation and authorization
// failures remain immediate failures; exhausted transient errors remain errors.
async function readWithRetry(read, {sleep=delay}={}) {
  for(let attempt=0;attempt<3;attempt++) {
    try {return await read();}
    catch(error) {
      const transient=[429,500,502,503,504].includes(error.statusCode)
        || ['ETIMEDOUT','ECONNRESET','EAI_AGAIN','ENETUNREACH','EPIPE'].includes(error.code);
      if(!transient||attempt===2)throw error;
      await sleep(1000*2**attempt);
    }
  }
}
module.exports={readWithRetry};
