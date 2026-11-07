import {createHash} from "node:crypto";

export type WorkerOperation="health"|"submit-approved-job"|"status"|"read-receipt";
export interface WorkerRequest {schema_version:"blender-worker-request.v1";request_id:string;operation:WorkerOperation;job_id?:string;approved_contract_id?:string;contract_sha256?:string;render_quality?:"interaction"|"preview";frame_start?:number;frame_end?:number;director_commit?:string;}
export type WorkerJobState="QUEUED"|"RUNNING"|"SUCCEEDED"|"FAILED"|"UNCERTAIN_INTERRUPTED";
export interface WorkerIdentity {worker_id:string;hostname:string;platform:string;arch:string;blender_version:string;worker_script_sha256:string;policy_version:string;observed_at:string;}
export interface WorkerReceipt {schema_version:"blender-worker-receipt.v1";job_id:string;request_id:string;state:"SUCCEEDED";worker:WorkerIdentity;contract_id:string;contract_sha256:string;output_relative_path:string;output_sha256:string;output_bytes:number;render_quality:"interaction"|"preview";frame_start:number;frame_end:number;video:{codec:"h264";width:number;height:number;fps:24;frame_count:number;audio:false;subtitles:false};evidence_scope:"WORKER_RECEIPT_REQUIRES_DIRECTOR_READBACK";}
export type WorkerResponse=
 | {schema_version:"blender-worker-response.v1";request_id:string;operation:"health";state:"READY"|"BLOCKED";worker:WorkerIdentity;admitted:boolean;reason?:string}
 | {schema_version:"blender-worker-response.v1";request_id:string;operation:"submit-approved-job"|"status";job_id:string;state:WorkerJobState;worker:WorkerIdentity;reason?:string}
 | {schema_version:"blender-worker-response.v1";request_id:string;operation:"read-receipt";job_id:string;state:"SUCCEEDED";worker:WorkerIdentity;receipt:WorkerReceipt};

const exact=(value:Record<string,unknown>,keys:string[])=>Object.keys(value).every(k=>keys.includes(k))&&keys.every(k=>Object.hasOwn(value,k));
const id=(value:unknown)=>typeof value==="string"&&/^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(value);
const hash=(value:unknown)=>typeof value==="string"&&/^[a-f0-9]{64}$/i.test(value);
const iso=(value:unknown)=>typeof value==="string"&&Number.isFinite(Date.parse(value));
const identityKeys=["worker_id","hostname","platform","arch","blender_version","worker_script_sha256","policy_version","observed_at"];
function validateIdentity(value:unknown):asserts value is WorkerIdentity{
  if(!value||typeof value!=="object")throw new Error("Worker identity is missing.");const x=value as Record<string,unknown>;
  if(!exact(x,identityKeys)||identityKeys.slice(0,7).some(k=>!id(x[k]))||!hash(x.worker_script_sha256)||!iso(x.observed_at))throw new Error("Worker identity is malformed.");
}
export function validateWorkerRequest(value:unknown):asserts value is WorkerRequest{
  if(!value||typeof value!=="object")throw new Error("Worker request must be an object.");const x=value as Record<string,unknown>;
  if(x.schema_version!=="blender-worker-request.v1"||!id(x.request_id)||!(["health","submit-approved-job","status","read-receipt"] as unknown[]).includes(x.operation))throw new Error("Worker request header is invalid.");
  const operation=x.operation;
  if(operation==="health"){if(!exact(x,["schema_version","request_id","operation"]))throw new Error("Health request contains unsupported fields.");return;}
  if(operation==="submit-approved-job"){
    if(!exact(x,["schema_version","request_id","operation","job_id","approved_contract_id","contract_sha256","render_quality","frame_start","frame_end","director_commit"])||!id(x.job_id)||!id(x.approved_contract_id)||!hash(x.contract_sha256)||!(["interaction","preview"] as unknown[]).includes(x.render_quality)||!Number.isInteger(x.frame_start)||!Number.isInteger(x.frame_end)||Number(x.frame_start)<1||Number(x.frame_end)>144||Number(x.frame_start)>Number(x.frame_end)||Number(x.frame_end)-Number(x.frame_start)+1>48||typeof x.director_commit!=="string"||!/^[a-f0-9]{40}$/i.test(x.director_commit))throw new Error("Approved-job request is outside the bounded contract.");
    return;
  }
  if(!exact(x,["schema_version","request_id","operation","job_id"])||!id(x.job_id))throw new Error("Job lookup request is malformed.");
}

export function validateWorkerResponse(value:unknown,request:WorkerRequest):asserts value is WorkerResponse{
  validateWorkerRequest(request);if(!value||typeof value!=="object")throw new Error("Worker response must be an object.");const x=value as Record<string,unknown>;
  if(x.schema_version!=="blender-worker-response.v1"||x.request_id!==request.request_id||x.operation!==request.operation)throw new Error("Worker response does not match the request identity.");
  validateIdentity(x.worker);
  if(request.operation==="health"){
    if(!exact(x,["schema_version","request_id","operation","state","worker","admitted",...(Object.hasOwn(x,"reason")?["reason"]:[])])||!(["READY","BLOCKED"] as unknown[]).includes(x.state)||typeof x.admitted!=="boolean"||x.admitted!==(x.state==="READY"))throw new Error("Worker health response is invalid.");return;
  }
  if(x.job_id!==request.job_id||!(["QUEUED","RUNNING","SUCCEEDED","FAILED","UNCERTAIN_INTERRUPTED"] as unknown[]).includes(x.state))throw new Error("Worker job response does not match the requested job.");
  if(request.operation==="read-receipt"){
    const r=x.receipt as Record<string,unknown>|undefined;
    const receiptKeys=["schema_version","job_id","request_id","state","worker","contract_id","contract_sha256","output_relative_path","output_sha256","output_bytes","render_quality","frame_start","frame_end","video","evidence_scope"];
    const video=r?.video as Record<string,unknown>|undefined;
    if(!exact(x,["schema_version","request_id","operation","job_id","state","worker","receipt"])||x.state!=="SUCCEEDED"||!r||!exact(r,receiptKeys)||r.schema_version!=="blender-worker-receipt.v1"||r.job_id!==request.job_id||r.request_id!==request.request_id||JSON.stringify(r.worker)!==JSON.stringify(x.worker)||!id(r.contract_id)||!hash(r.contract_sha256)||!hash(r.output_sha256)||!Number.isSafeInteger(r.output_bytes)||Number(r.output_bytes)<=0||typeof r.output_relative_path!=="string"||r.output_relative_path.startsWith("/")||r.output_relative_path.split(/[\\/]/).some(p=>p===".."||p==="."||p==="")||!(["interaction","preview"] as unknown[]).includes(r.render_quality)||!Number.isInteger(r.frame_start)||!Number.isInteger(r.frame_end)||Number(r.frame_start)<1||Number(r.frame_end)>144||Number(r.frame_end)-Number(r.frame_start)+1>48||!video||!exact(video,["codec","width","height","fps","frame_count","audio","subtitles"])||video.codec!=="h264"||video.width!==320&&video.width!==640||video.height!==180&&video.height!==360||(video.width===320?video.height!==180:video.height!==360)||video.fps!==24||video.frame_count!==Number(r.frame_end)-Number(r.frame_start)+1||video.audio!==false||video.subtitles!==false||r.evidence_scope!=="WORKER_RECEIPT_REQUIRES_DIRECTOR_READBACK")throw new Error("Worker receipt is incomplete or unsafe.");
    if(request.operation==="read-receipt"&&request.job_id!==r.job_id)throw new Error("Receipt job identity mismatch.");return;
  }
  const allowed=["schema_version","request_id","operation","job_id","state","worker",...(Object.hasOwn(x,"reason")?["reason"]:[])];if(!exact(x,allowed))throw new Error("Worker status response contains unsupported fields.");
}

export interface WorkerTransport {request(request:WorkerRequest):Promise<unknown>;}
/** No production transport is wired until an authenticated restricted worker is available. */
export class BlockedWorkerTransport implements WorkerTransport {async request(_request:WorkerRequest):Promise<unknown>{throw new Error("BLOCKED_WORKER_TRANSPORT: no authenticated restricted Blender endpoint is configured.");}}

/** Deterministic fixture only; its receipts are never production evidence. */
export class DeterministicTestWorker implements WorkerTransport{
  readonly identity:WorkerIdentity={worker_id:"test-worker",hostname:"fixture",platform:"test",arch:"none",blender_version:"fixture",worker_script_sha256:createHash("sha256").update("fixture-worker").digest("hex"),policy_version:"fixture-policy-v1",observed_at:"2026-01-01T00:00:00.000Z"};
  private readonly jobs=new Map<string,{request:WorkerRequest;state:WorkerJobState;receipt?:WorkerReceipt}>();
  async request(request:WorkerRequest):Promise<unknown>{
    validateWorkerRequest(request);
    if(request.operation==="health")return {schema_version:"blender-worker-response.v1",request_id:request.request_id,operation:"health",state:"BLOCKED",worker:this.identity,admitted:false,reason:"TEST_FIXTURE_ONLY; no Blender execution occurred."};
    if(request.operation==="submit-approved-job"){
      const prior=this.jobs.get(request.job_id!);if(prior)return {schema_version:"blender-worker-response.v1",request_id:request.request_id,operation:request.operation,job_id:request.job_id,state:prior.state,worker:this.identity};
      this.jobs.set(request.job_id!,{request,state:"QUEUED"});return {schema_version:"blender-worker-response.v1",request_id:request.request_id,operation:request.operation,job_id:request.job_id,state:"QUEUED",worker:this.identity};
    }
    const prior=this.jobs.get(request.job_id!);if(!prior)return {schema_version:"blender-worker-response.v1",request_id:request.request_id,operation:request.operation,job_id:request.job_id,state:"FAILED",worker:this.identity,reason:"Unknown fixture job."};
    if(request.operation==="status")return {schema_version:"blender-worker-response.v1",request_id:request.request_id,operation:request.operation,job_id:request.job_id,state:prior.state,worker:this.identity};
    if(!prior.receipt)throw new Error("TEST_FIXTURE_ONLY: no synthetic receipt was configured.");return {schema_version:"blender-worker-response.v1",request_id:request.request_id,operation:request.operation,job_id:request.job_id,state:"SUCCEEDED",worker:this.identity,receipt:prior.receipt};
  }
  setFixtureReceipt(jobId:string,requestId:string,receipt:Omit<WorkerReceipt,"schema_version"|"job_id"|"request_id"|"worker"|"evidence_scope">){
    const job=this.jobs.get(jobId);if(!job)throw new Error("Unknown fixture job.");job.state="SUCCEEDED";job.receipt={schema_version:"blender-worker-receipt.v1",job_id:jobId,request_id:requestId,worker:this.identity,evidence_scope:"WORKER_RECEIPT_REQUIRES_DIRECTOR_READBACK",...receipt};
  }
}

export async function submitAndReconcile(transport:WorkerTransport,request:WorkerRequest):Promise<WorkerResponse>{
  validateWorkerRequest(request);const raw=await transport.request(request);validateWorkerResponse(raw,request);
  if(request.operation!=="submit-approved-job")return raw;
  const statusRequest:WorkerRequest={schema_version:"blender-worker-request.v1",request_id:request.request_id,operation:"status",job_id:request.job_id};const status=await transport.request(statusRequest);validateWorkerResponse(status,statusRequest);
  if(status.state!=="SUCCEEDED")return status;
  const receiptRequest:WorkerRequest={schema_version:"blender-worker-request.v1",request_id:request.request_id,operation:"read-receipt",job_id:request.job_id};const receipt=await transport.request(receiptRequest);validateWorkerResponse(receipt,receiptRequest);const result=receipt as Extract<WorkerResponse,{operation:"read-receipt"}>;if(result.receipt.contract_id!==request.approved_contract_id||result.receipt.contract_sha256!==request.contract_sha256||result.receipt.render_quality!==request.render_quality||result.receipt.frame_start!==request.frame_start||result.receipt.frame_end!==request.frame_end||JSON.stringify(result.worker)!==JSON.stringify((raw as {worker:WorkerIdentity}).worker))throw new Error("Worker receipt does not reconcile to the approved submission.");return result;
}
