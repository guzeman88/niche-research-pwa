// Local adapter for the same account handler deployed as a Netlify Function.
import {createServer} from 'node:http';
import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
for (const name of ['../.env.local','../../.env.local']) {
  const path = fileURLToPath(new URL(name,import.meta.url));
  if (existsSync(path)) process.loadEnvFile(path);
}
process.env.APP_ORIGIN = process.env.AUTH_DEV_ORIGIN || 'http://127.0.0.1:5173';
const {default:handler} = await import('../netlify/functions/account.mjs');
createServer(async (req,res) => {
  try {
    const chunks=[];let bytes=0;
    for await (const chunk of req) {bytes+=chunk.length;if(bytes>5*1024*1024){res.writeHead(413);res.end();return}chunks.push(chunk)}
    const request=new Request(`http://127.0.0.1:8890${req.url}`,{method:req.method,headers:req.headers,body:['GET','HEAD'].includes(req.method)?undefined:Buffer.concat(chunks)});
    const result=await handler(request,{ip:req.socket.remoteAddress});
    const headers=Object.fromEntries(result.headers);
    const cookies=result.headers.getSetCookie();if(cookies.length)headers['set-cookie']=cookies;
    res.writeHead(result.status,headers);res.end(Buffer.from(await result.arrayBuffer()));
  } catch {res.writeHead(500);res.end('{"error":"Local account service failed."}');}
}).listen(8890,'127.0.0.1',()=>console.log('Account service listening on 127.0.0.1:8890'));
