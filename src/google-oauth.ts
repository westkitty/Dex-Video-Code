import {createHash,randomBytes,timingSafeEqual} from "node:crypto";
import {createServer} from "node:http";
import {spawn} from "node:child_process";
import type {SecretStore} from "./keychain.js";

export const DRIVE_UPLOAD_SCOPE="https://www.googleapis.com/auth/drive.file";
const TOKEN_ENDPOINT="https://oauth2.googleapis.com/token";
interface SavedCredential {refresh_token:string;scope:string;}
export interface AccessToken {value:string;expiresAt:number;}
export interface OAuthOptions {clientId:string;store:SecretStore;fetcher?:typeof fetch;openBrowser?:(url:string)=>Promise<void>;now?:()=>number;beforeSaveRefreshCredential?:(accessToken:string)=>Promise<void>;}
export interface Pkce {verifier:string;challenge:string;state:string;}
export function createPkce():Pkce {const verifier=randomBytes(48).toString("base64url");return {verifier,challenge:createHash("sha256").update(verifier).digest("base64url"),state:randomBytes(32).toString("base64url")};}
export function authorizationUrl(clientId:string,redirectUri:string,pkce:Pkce):string {
  const u=new URL("https://accounts.google.com/o/oauth2/v2/auth");
  for(const [k,v] of Object.entries({client_id:clientId,redirect_uri:redirectUri,response_type:"code",scope:DRIVE_UPLOAD_SCOPE,code_challenge:pkce.challenge,code_challenge_method:"S256",state:pkce.state,access_type:"offline",prompt:"consent"}))u.searchParams.set(k,v);
  return u.toString();
}
function safeOAuthError(body:unknown):string {const e=body as {error?:string};return e?.error==="invalid_grant"?"Google authorization expired or was revoked; sign in again with director auth-google.":"Google OAuth request failed; provider details and credentials were withheld.";}
function tokenHasRequiredScope(scope:string|undefined):boolean{const granted=(scope??"").split(/\s+/).filter(Boolean);return granted.length===1&&granted[0]===DRIVE_UPLOAD_SCOPE;}
async function parseToken(response:Response):Promise<{access_token?:string;refresh_token?:string;expires_in?:number;scope?:string;error?:string}>{try{return await response.json() as {access_token?:string;refresh_token?:string;expires_in?:number;scope?:string;error?:string};}catch{return {};}}

export class GoogleDesktopOAuth {
  private readonly fetcher:typeof fetch;
  private cached?:AccessToken;
  constructor(private readonly options:OAuthOptions){this.fetcher=options.fetcher??fetch;if(!options.clientId.trim())throw new Error("Google Desktop OAuth client ID is not configured; run director auth-google --client-id <ID>.");}
  private now():number{return this.options.now?.()??Date.now();}
  async authorize(timeoutMs=5*60_000):Promise<void>{
    const pkce=createPkce();let code="",oauthFailure="";const server=createServer((req,res)=>{
      const target=new URL(req.url??"/","http://127.0.0.1");if(target.pathname!=="/oauth2callback"){res.writeHead(404).end();return;}
      const got=target.searchParams.get("state")??"";const expected=Buffer.from(pkce.state),actual=Buffer.from(got);if(actual.length!==expected.length||!timingSafeEqual(actual,expected)){res.writeHead(400,{"Content-Type":"text/plain"}).end("Authorization state mismatch. You can close this window.");return;}
      const providerError=target.searchParams.get("error");if(providerError){oauthFailure=providerError;res.writeHead(400,{"Content-Type":"text/plain"}).end("Google authorization was not completed. You can close this window.");return;}
      code=target.searchParams.get("code")??"";res.writeHead(code?200:400,{"Content-Type":"text/plain; charset=utf-8"}).end(code?"Dex Video Code authorization complete. You may close this window.":"Authorization code missing. You may close this window.");
    });
    await new Promise<void>((resolve,reject)=>{server.once("error",reject);server.listen(0,"127.0.0.1",()=>resolve());});
    const address=server.address();if(!address||typeof address==="string"){server.close();throw new Error("Could not establish the Google OAuth loopback listener.");}
    const redirectUri=`http://127.0.0.1:${address.port}/oauth2callback`;let timeout:NodeJS.Timeout;const abort=new Promise<never>((_,reject)=>{timeout=setTimeout(()=>reject(new Error("Google sign-in timed out; no credential was changed.")),timeoutMs);});
    try{
      const callback=new Promise<string>((resolve,reject)=>{const poll=setInterval(()=>{if(code){clearInterval(poll);resolve(code);}else if(oauthFailure){clearInterval(poll);reject(new Error("Google sign-in was declined or not completed; no credential was changed."));}},50);server.on("close",()=>{clearInterval(poll);reject(new Error("Google sign-in was interrupted; no credential was changed."));});});
      const url=authorizationUrl(this.options.clientId,redirectUri,pkce);
      if(this.options.openBrowser)await this.options.openBrowser(url);else {const child=spawn("open",[url],{stdio:"ignore",detached:true});child.unref();}
      const authCode=await Promise.race([callback,abort]);
      const response=await this.fetcher(TOKEN_ENDPOINT,{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:new URLSearchParams({client_id:this.options.clientId,code:authCode,code_verifier:pkce.verifier,redirect_uri:redirectUri,grant_type:"authorization_code"})});
      const token=await parseToken(response);if(!response.ok||!token.access_token)throw new Error(safeOAuthError(token));if(!tokenHasRequiredScope(token.scope))throw new Error("Google did not grant the required drive.file upload scope; no credential was saved.");
      let refresh=token.refresh_token;if(!refresh){const previous=await this.options.store.get();if(previous)refresh=(JSON.parse(previous) as SavedCredential).refresh_token;}
      if(!refresh)throw new Error("Google did not issue offline refresh authorization. Sign-in was not saved; retry after approving offline access.");
      await this.options.beforeSaveRefreshCredential?.(token.access_token);
      await this.options.store.set(JSON.stringify({refresh_token:refresh,scope:token.scope!} satisfies SavedCredential));this.cached={value:token.access_token,expiresAt:this.now()+Math.max(60,token.expires_in??3600)*1000};
    } finally {clearTimeout(timeout!);server.close();}
  }
  async accessToken():Promise<string>{if(this.cached&&this.cached.expiresAt-this.now()>60_000)return this.cached.value;const raw=await this.options.store.get();if(!raw)throw new Error("Google Drive is not authorized; run director auth-google.");let saved:SavedCredential;try{saved=JSON.parse(raw) as SavedCredential;}catch{throw new Error("Stored Google authorization is invalid; run director auth-google.");}if(!saved.refresh_token||!tokenHasRequiredScope(saved.scope))throw new Error("Stored Google authorization lacks the drive.file scope; run director auth-google.");
    const response=await this.fetcher(TOKEN_ENDPOINT,{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:new URLSearchParams({client_id:this.options.clientId,refresh_token:saved.refresh_token,grant_type:"refresh_token"})});const token=await parseToken(response);if(!response.ok||!token.access_token){this.cached=undefined;if(token.error==="invalid_grant")await this.options.store.delete();throw new Error(safeOAuthError(token));}if(token.scope&&!tokenHasRequiredScope(token.scope))throw new Error("Renewed Google authorization lacks the required drive.file scope; run director auth-google.");this.cached={value:token.access_token,expiresAt:this.now()+Math.max(60,token.expires_in??3600)*1000};return this.cached.value;
  }
  invalidate():void{this.cached=undefined;}
}

export async function verifyDriveDestinationAccess(accessToken:string,folderId:string,fetcher:typeof fetch=fetch):Promise<{folderId:string;private:boolean;mimeType:string}>{
  const query=new URLSearchParams({fields:"id,mimeType,permissions(type)",supportsAllDrives:"true"});let response:Response;
  try{response=await fetcher(`https://www.googleapis.com/drive/v3/files/${encodeURIComponent(folderId)}?${query}`,{headers:{Authorization:`Bearer ${accessToken}`}});}catch{throw new Error("Could not verify the configured Drive folder. No upload was attempted.");}
  if(!response.ok)throw new Error(response.status===401?"Google authorization was rejected while checking the folder; run director auth-google.":response.status===403||response.status===404?"The drive.file authorization cannot access the configured folder (or the folder is unavailable). No upload was attempted.":"Google Drive folder access check failed. No upload was attempted.");
  let file:{id?:string;mimeType?:string;permissions?:Array<{type?:string}>};try{file=await response.json() as typeof file;}catch{throw new Error("Google Drive returned unreadable folder metadata. No upload was attempted.");}
  if(file.id!==folderId||file.mimeType!=="application/vnd.google-apps.folder")throw new Error("Configured Drive destination is not the expected folder.");if(!file.permissions||file.permissions.some(p=>p.type==="anyone"))throw new Error("Drive folder privacy could not be verified or grants public access.");return {folderId,private:true,mimeType:file.mimeType};
}
