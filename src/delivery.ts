import { createHash } from "node:crypto";
import { chmod, copyFile, mkdtemp, open, rm, stat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { CreativeJob } from "./types.js";

export type DeliveryState = "NOT_REQUESTED"|"PENDING"|"UPLOADING"|"RETRYABLE"|"BLOCKED_AUTH"|"FAILED"|"DELIVERED_UNVERIFIED"|"DELIVERED_VERIFIED";
export interface DeliveryReceipt {
  schema_version: 1; state: DeliveryState; job_id: string; source_path: string;
  source_sha256: string; source_md5: string; source_bytes: number; provider: "google-drive";
  parent_id: string; file_id?: string; file_name: string; mime_type: "video/mp4";
  provider_md5?: string; readback?: "drive-md5-checksum"; web_view_link?: string;
  idempotency_key: string; private: boolean; created_at: string; verified_at?: string;
  error?: string;
}
export interface DriveFile {
  id?: string; name?: string; mimeType?: string; parents?: string[]; size?: string;
  md5Checksum?: string; webViewLink?: string; permissions?: Array<{type?:string}>;
  appProperties?: Record<string,string>;
}
export type FetchLike = (input: string|URL, init?: RequestInit) => Promise<Response>;
const API="https://www.googleapis.com/drive/v3";
const UPLOAD="https://www.googleapis.com/upload/drive/v3";
const FIELDS="id,name,mimeType,parents,size,md5Checksum,webViewLink,permissions(type),appProperties";
const RETRYABLE=new Set([408,429,500,502,503,504]);

export class DeliveryError extends Error {
  constructor(message:string,readonly state:DeliveryState){super(message);this.name="DeliveryError";}
}
async function fail(response:Response):Promise<never> {
  if(response.status===401)throw new DeliveryError("Google Drive rejected authorization (HTTP 401).","BLOCKED_AUTH");
  if(response.status===403){let reasons:string[]=[];try{const body=await response.clone().json() as {error?:{errors?:Array<{reason?:string}>}};reasons=(body.error?.errors??[]).map(e=>e.reason??"");}catch{/* Keep the provider response body private. */}
    if(reasons.some(r=>r==="userRateLimitExceeded"||r==="rateLimitExceeded"))throw new DeliveryError("Google Drive rate limit reached; bounded retry is safe.","RETRYABLE");
    if(reasons.includes("storageQuotaExceeded"))throw new DeliveryError("Google Drive storage quota is exceeded.","FAILED");
    throw new DeliveryError("Google Drive rejected authorization or destination access (HTTP 403).","BLOCKED_AUTH");
  }
  if(RETRYABLE.has(response.status))throw new DeliveryError(`Google Drive temporarily unavailable (HTTP ${response.status}); retry is safe.`,"RETRYABLE");
  throw new DeliveryError(`Google Drive request failed (HTTP ${response.status}).`,"FAILED");
}
function validId(v:string|undefined,label:string):string { if(!v||!/^[A-Za-z0-9_-]{5,200}$/.test(v))throw new DeliveryError(`${label} is missing or invalid.`,"FAILED");return v; }
function safeName(v:string):string { const s=path.basename(v).replace(/[^A-Za-z0-9._-]+/g,"-").replace(/^-+|-+$/g,"").slice(0,100);return (s||"video").replace(/\.mp4$/i,""); }
function responseJson<T>(r:Response):Promise<T>{return r.json() as Promise<T>;}

export interface DriveConfig { accessToken:string|(()=>Promise<string>); folderId:string; invalidateAccessToken?:()=>void; }
export class GoogleDriveDeliveryAdapter {
  constructor(private readonly config:DriveConfig,private readonly fetcher:FetchLike=fetch,private readonly pause=(ms:number)=>new Promise<void>(r=>setTimeout(r,ms))) {
    validId(config.folderId,"DEX_DRIVE_FOLDER_ID");
  }
  private async headers(extra:Record<string,string>={}):Promise<HeadersInit>{const token=typeof this.config.accessToken==="string"?this.config.accessToken:await this.config.accessToken();if(!token)throw new DeliveryError("Google Drive authorization is not configured.","BLOCKED_AUTH");return {Authorization:`Bearer ${token}`,...extra};}
  private async request(url:string,init:RequestInit,retryNetwork=true):Promise<Response>{
    for(let attempt=0;;attempt++){
      let r:Response;try{r=await this.fetcher(url,init);}catch{if(!retryNetwork||attempt>=3)throw new DeliveryError("Google Drive connection failed; delivery can be retried safely.","RETRYABLE");await this.pause(250*2**attempt);continue;}
      if(r.status===401&&typeof this.config.accessToken==="function"&&attempt===0){this.config.invalidateAccessToken?.();const headers=new Headers(init.headers);headers.set("Authorization",`Bearer ${await this.config.accessToken()}`);init={...init,headers};continue;}
      if(RETRYABLE.has(r.status)&&attempt<3){await this.pause(250*2**attempt);continue;}
      if(r.status===403){try{await fail(r);}catch(e){if(e instanceof DeliveryError&&e.state==="RETRYABLE"&&attempt<3){await this.pause(250*2**attempt);continue;}throw e;}}
      if(!r.ok&&r.status!==308)await fail(r);return r;
    }
  }
  private async getFile(fileId:string):Promise<DriveFile>{
    const u=`${API}/files/${encodeURIComponent(fileId)}?fields=${encodeURIComponent(FIELDS)}`;
    return responseJson<DriveFile>(await this.request(u,{headers:await this.headers()}));
  }
  private async findByKey(key:string):Promise<DriveFile|undefined>{
    const q=`'${this.config.folderId}' in parents and appProperties has { key='dexDeliveryKey' and value='${key}' } and trashed=false`;
    const u=`${API}/files?${new URLSearchParams({q,fields:`files(${FIELDS})`,pageSize:"10",supportsAllDrives:"true",includeItemsFromAllDrives:"true"})}`;
    const result=await responseJson<{files?:DriveFile[]}>(await this.request(u,{headers:await this.headers()}));
    if((result.files?.length??0)>1)throw new DeliveryError("Multiple Drive files carry this delivery key; refusing to choose or duplicate.","FAILED");return result.files?.[0];
  }
  private async ensurePrivateFolder():Promise<void>{
    const folder=await this.getFile(this.config.folderId);
    if(folder.mimeType!=="application/vnd.google-apps.folder")throw new DeliveryError("Configured Drive destination is not a folder.","FAILED");
    if(folder.permissions?.some(p=>p.type==="anyone"))throw new DeliveryError("Configured Drive folder grants public link access; upload blocked.","FAILED");
    if(!folder.permissions)throw new DeliveryError("Drive did not return destination permissions; privacy could not be verified.","FAILED");
  }
  private validateFile(file:DriveFile,expected:{key:string;name:string;bytes:number;md5:string}):{verified:boolean;reason?:string}{
    if(!file.id||file.parents?.length!==1||file.parents[0]!==this.config.folderId)throw new DeliveryError("Drive file parent does not match the authorized destination folder.","FAILED");
    if(file.mimeType!=="video/mp4"||file.name!==expected.name||Number(file.size)!==expected.bytes)throw new DeliveryError("Drive file metadata does not match the original MP4 master.","FAILED");
    if(file.appProperties?.dexDeliveryKey!==expected.key)throw new DeliveryError("Drive idempotency identity does not match this master.","FAILED");
    if(!file.permissions)throw new DeliveryError("Drive did not return file permissions; privacy could not be verified.","FAILED");
    if(file.permissions.some(p=>p.type==="anyone"))throw new DeliveryError("Drive file has public link access; delivery blocked.","FAILED");
    if(file.md5Checksum&&file.md5Checksum.toLowerCase()!==expected.md5)throw new DeliveryError("Google Drive checksum differs from the original master.","FAILED");
    return file.md5Checksum?{verified:true}:{verified:false,reason:"Drive did not provide a comparable content checksum."};
  }
  private async uploadResumable(filePath:string,bytes:number,name:string,key:string):Promise<DriveFile>{
    const metadata={name,mimeType:"video/mp4",parents:[this.config.folderId],appProperties:{dexDeliveryKey:key}};
    const init=await this.request(`${UPLOAD}/files?uploadType=resumable&fields=${encodeURIComponent(FIELDS)}`,{method:"POST",headers:await this.headers({"Content-Type":"application/json; charset=UTF-8","X-Upload-Content-Type":"video/mp4","X-Upload-Content-Length":String(bytes)}),body:JSON.stringify(metadata)});
    const loc=init.headers.get("location");if(!loc)throw new DeliveryError("Drive omitted the resumable upload session; no upload was confirmed.","RETRYABLE");
    let session:URL;try{session=new URL(loc);}catch{throw new DeliveryError("Drive returned an invalid resumable session; upload stopped.","FAILED");}
    if(session.protocol!=="https:"||!session.hostname.endsWith(".googleapis.com"))throw new DeliveryError("Drive returned an unexpected upload host; upload stopped.","FAILED");
    const chunkSize=8*1024*1024,handle=await open(filePath,"r");let offset=0,noProgress=0;
    try{while(offset<bytes){const length=Math.min(chunkSize,bytes-offset),buf=Buffer.allocUnsafe(length);const {bytesRead}=await handle.read(buf,0,length,offset);if(bytesRead!==length)throw new DeliveryError("Master changed or ended during upload.","FAILED");let response:Response;
        try{response=await this.request(session.toString(),{method:"PUT",headers:{"Content-Length":String(length),"Content-Range":`bytes ${offset}-${offset+length-1}/${bytes}`,"Content-Type":"video/mp4"},body:buf},false);}
        catch(e){if(!(e instanceof DeliveryError)||e.state!=="RETRYABLE")throw e;const status=await this.request(session.toString(),{method:"PUT",headers:{"Content-Length":"0","Content-Range":`bytes */${bytes}`}});if(status.status===200||status.status===201)return responseJson<DriveFile>(status);if(status.status!==308)throw e;const range=status.headers.get("range");const next=range?Number(range.match(/-(\d+)$/)?.[1]??-1)+1:0;if(next<=offset){if(++noProgress>3)throw new DeliveryError("Drive upload made no progress after reconciliation.","RETRYABLE");}else noProgress=0;offset=next;continue;}
        if(response.status===200||response.status===201)return responseJson<DriveFile>(response);
        const range=response.headers.get("range");const next=range?Number(range.match(/-(\d+)$/)?.[1]??-1)+1:0;if(next<=offset){if(++noProgress>3)throw new DeliveryError("Drive upload made no progress after repeated resume responses.","RETRYABLE");}else noProgress=0;offset=next;
      }
    }finally{await handle.close();}
    throw new DeliveryError("Drive upload ended without a completed file response.","RETRYABLE");
  }
  async deliver(job:CreativeJob,filePath:string,verifiedSha:string,sourceRelativePath=path.basename(filePath)):Promise<DeliveryReceipt>{
    await this.ensurePrivateFolder();
    // Upload a private snapshot, not a path reopened after hashing. This closes the
    // time-of-check/time-of-use gap if a producer or external process changes the master.
    const snapshotDir=await mkdtemp(path.join(os.tmpdir(),"dex-video-drive-"));
    const snapshot=path.join(snapshotDir,"verified-master.mp4");
    try{
      await copyFile(filePath,snapshot);await chmod(snapshot,0o600);
      const f=await open(snapshot,"r"),h256=createHash("sha256"),hmd5=createHash("md5");let bytes=0;const start=await stat(snapshot);
      try{for await(const chunk of f.createReadStream({autoClose:false})){h256.update(chunk);hmd5.update(chunk);bytes+=chunk.length;}}finally{await f.close();}
      const sha=h256.digest("hex"),md5=hmd5.digest("hex");if(bytes!==start.size||sha!==verifiedSha)throw new DeliveryError("Master changed after verification; refusing upload.","FAILED");
      const key=createHash("sha256").update(`${job.job_id}\0${sha}`).digest("hex");const filename=`${safeName(path.basename(filePath))}-${safeName(job.job_id)}-${sha.slice(0,12)}.mp4`;
      const expected={key,name:filename,bytes,md5};let remote=await this.findByKey(key);if(remote){const status=this.validateFile(remote,expected);return this.receipt(job,sourceRelativePath,sha,md5,bytes,key,filename,remote,status.verified);}
      const remoteCreated=await this.uploadResumable(snapshot,bytes,filename,key);remote=await this.getFile(validId(remoteCreated.id,"Drive file id"));
      const status=this.validateFile(remote,expected);return this.receipt(job,sourceRelativePath,sha,md5,bytes,key,filename,remote,status.verified,status.reason);
    }finally{await rm(snapshotDir,{recursive:true,force:true});}
  }
  private receipt(job:CreativeJob,sourcePath:string,sha:string,md5:string,bytes:number,key:string,name:string,file:DriveFile,verified:boolean,reason?:string):DeliveryReceipt{
    const base:DeliveryReceipt={schema_version:1,state:verified?"DELIVERED_VERIFIED":"DELIVERED_UNVERIFIED",job_id:job.job_id,source_path:sourcePath,source_sha256:sha,source_md5:md5,source_bytes:bytes,provider:"google-drive",parent_id:this.config.folderId,file_id:file.id,file_name:name,mime_type:"video/mp4",...(file.md5Checksum?{provider_md5:file.md5Checksum,readback:"drive-md5-checksum" as const}:{}),idempotency_key:key,private:true,created_at:new Date().toISOString(),...(verified?{verified_at:new Date().toISOString()}:{}),...(!verified?{error:reason??"No comparable remote checksum was available."}:{})};
    if(verified&&file.webViewLink&&/^https:\/\/drive\.google\.com\//.test(file.webViewLink))base.web_view_link=file.webViewLink;
    if(verified&&!base.web_view_link){base.state="DELIVERED_UNVERIFIED";delete base.verified_at;base.error="Verified bytes and private parent, but Drive returned no usable viewing link.";}
    return base;
  }
}

export function driveConfigFromEnv(env:NodeJS.ProcessEnv=process.env):DriveConfig{
  const accessToken=env.DEX_DRIVE_ACCESS_TOKEN?.trim(),folderId=env.DEX_DRIVE_FOLDER_ID?.trim();
  if(!accessToken)throw new DeliveryError("Google Drive authorization is not configured (DEX_DRIVE_ACCESS_TOKEN).","BLOCKED_AUTH");
  if(!folderId)throw new DeliveryError("Private Google Drive destination is not configured (DEX_DRIVE_FOLDER_ID).","BLOCKED_AUTH");
  return {accessToken,folderId};
}
