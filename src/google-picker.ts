import {randomBytes,timingSafeEqual} from "node:crypto";
import {createServer} from "node:http";
import {spawn} from "node:child_process";

export interface DrivePickerOptions {apiKey:string;projectNumber:string;expectedFolderId:string;accessToken:string;timeoutMs?:number;openBrowser?:(url:string)=>Promise<void>;}
const safeJson=(value:string)=>JSON.stringify(value).replaceAll("<","\\u003c").replaceAll(">","\\u003e").replaceAll("&","\\u0026");
export async function selectDriveFolderWithPicker(options:DrivePickerOptions):Promise<string>{
  if(!options.apiKey.trim()||!/^[0-9]{4,20}$/.test(options.projectNumber)||!options.expectedFolderId.trim())throw new Error("Google Picker API key, Cloud project number, and configured folder are required for drive.file access.");
  const nonce=randomBytes(24).toString("base64url");let resolve!:(id:string)=>void,reject!:(e:Error)=>void;const selected=new Promise<string>((a,b)=>{resolve=a;reject=b;});
  const server=createServer((req,res)=>{const u=new URL(req.url??"/","http://127.0.0.1"),state=u.searchParams.get("state")??"",expected=Buffer.from(nonce),actual=Buffer.from(state);if(actual.length!==expected.length||!timingSafeEqual(actual,expected)){res.writeHead(403).end("Invalid local selection session.");return;}
    if(req.method==="GET"&&u.pathname==="/picker"){const html=`<!doctype html><meta charset="utf-8"><title>Choose delivery folder</title><p id="status">Choose the configured private Drive folder in the picker.</p><script src="https://apis.google.com/js/api.js"></script><script>
const token=${safeJson(options.accessToken)},apiKey=${safeJson(options.apiKey)},appId=${safeJson(options.projectNumber)},state=${safeJson(nonce)};
function report(path,id){return fetch(path+'?state='+encodeURIComponent(state),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});}
gapi.load('picker',{callback:()=>{const view=new google.picker.DocsView(google.picker.ViewId.FOLDERS).setIncludeFolders(true).setSelectFolderEnabled(true);const picker=new google.picker.PickerBuilder().setAppId(appId).setDeveloperKey(apiKey).setOAuthToken(token).setTitle('Select your configured delivery folder').addView(view).setCallback(async data=>{if(data.action===google.picker.Action.PICKED){const id=data.docs?.[0]?.id;if(id){document.getElementById('status').textContent='Selection received. You may close this window.';await report('/selected',id);}}else if(data.action===google.picker.Action.CANCEL){await report('/cancel','');}}).build();picker.setVisible(true);}});
</script>`;res.writeHead(200,{"Content-Type":"text/html; charset=utf-8","Cache-Control":"no-store","Referrer-Policy":"no-referrer"}).end(html);return;}
    if(req.method==="POST"&&(u.pathname==="/selected"||u.pathname==="/cancel")){let body="";req.on("data",chunk=>{body+=String(chunk);if(body.length>2048)req.destroy();});req.on("end",()=>{let id="";try{id=(JSON.parse(body) as {id?:string}).id??"";}catch{}res.writeHead(200,{"Content-Type":"text/plain","Cache-Control":"no-store"}).end("Selection received. You may close this window.");if(u.pathname==="/cancel")reject(new Error("Drive folder selection was canceled; no refresh credential was saved."));else if(/^[A-Za-z0-9_-]{5,200}$/.test(id))resolve(id);else reject(new Error("Google Picker returned an invalid folder selection."));});return;}
    res.writeHead(404).end();
  });
  await new Promise<void>((resolveListen,rejectListen)=>{server.once("error",rejectListen);server.listen(0,"127.0.0.1",()=>resolveListen());});const address=server.address();if(!address||typeof address==="string"){server.close();throw new Error("Could not open the local Google Picker listener.");}
  let timer:NodeJS.Timeout;const timeout=new Promise<never>((_,rej)=>{timer=setTimeout(()=>rej(new Error("Google Drive folder selection timed out; no refresh credential was saved.")),options.timeoutMs??5*60_000);});
  const result=Promise.race([selected,timeout]).then(value=>({ok:true as const,value}),error=>({ok:false as const,error}));
  try{const url=`http://127.0.0.1:${address.port}/picker?state=${encodeURIComponent(nonce)}`;if(options.openBrowser)await options.openBrowser(url);else{const child=spawn("open",[url],{stdio:"ignore",detached:true});child.unref();}const outcome=await result;if(!outcome.ok)throw outcome.error;return outcome.value;}finally{clearTimeout(timer!);server.close();}
}
