import type {CreativeJob} from "./types.js";
import {discoverCapabilities} from "./capabilities.js";

export type RegistryStatus="VERIFIED_LIVE"|"HISTORICAL_ONLY"|"INSTALLED_UNPROVEN"|"BLOCKED"|"DORMANT"|"UNKNOWN"|"EXCLUDED";
export interface CapabilityRecord {
  id:string;status:RegistryStatus;observed_at:string;host:string;adapter:string;
  operations:string[];inputs:string[];outputs:string[];constraints:string[];
  cost:"none"|"unknown";privacy:"local"|"private-provider"|"manual";
  proof:string[];reason:string;
}
export interface VerifiedJobEvidence {job_id:string;sha256:string;verified_at:string;host:string;}

export function capabilityRegistry(evidence?:VerifiedJobEvidence):CapabilityRecord[]{
  const observed=new Date().toISOString(),local=discoverCapabilities(),has=(id:string)=>local.find(c=>c.id===id)?.state==="VERIFIED";
  const installed=has("local.ffmpeg")&&has("local.rasterizer");
  const localStatus:RegistryStatus=evidence&&installed?"VERIFIED_LIVE":installed?"INSTALLED_UNPROVEN":"BLOCKED";
  const record=(r:Omit<CapabilityRecord,"observed_at">):CapabilityRecord=>({...r,observed_at:observed});
  return [
    record({id:"local.motion-graphics",status:localStatus,host:evidence?.host??"this local process",adapter:"motion-graphics-local",operations:["render-original-motion-graphic"],inputs:["confined CreativeJob v1.1", "no external assets"],outputs:["video/mp4 H.264"],constraints:["16:9","1280x720","24 fps","1–30 seconds","captions off","no audio"],cost:"none",privacy:"local",proof:evidence?[`Verified job ${evidence.job_id}`,`Master SHA-256 ${evidence.sha256}`,`Verified ${evidence.verified_at}`]:[],reason:evidence?"A current local master passed full technical verification.":"Required tools are installed, but this snapshot has no bound verified output."}),
    record({id:"hyperframes.controller",status:"HISTORICAL_ONLY",host:"Big Mac via DEX//REACH",adapter:"separate HyperFrames controller",operations:[],inputs:["prepared local project slug only"],outputs:["video/mp4"],constraints:["historical controller contract: health/submit/status; max 30 seconds","no current process operation is exposed to this director"],cost:"unknown",privacy:"local",proof:["Historical Pilot A/controller receipt in OPERATIONAL_STATE.md"],reason:"A fresh DEX node/tool inventory was available, but no HyperFrames process operation was exposed; no render was submitted."}),
    record({id:"remotion.editorial",status:"UNKNOWN",host:"unverified",adapter:"none",operations:[],inputs:[],outputs:[],constraints:["No installed runnable project or license evidence"],cost:"unknown",privacy:"local",proof:[],reason:"No current executable capability evidence."}),
    record({id:"native.articulated-3d",status:"BLOCKED",host:"Big Mac specialist Blender worker",adapter:"examples/p7/second_light.py (specialist-only)",operations:[],inputs:["narrow p7.performance.v1 contract"],outputs:["specialist-rendered H.264; not director-dispatched"],constraints:["one authored Sentinel performance is proven outside the director","no authorized typed worker dispatch or receipt reconciliation is exposed to the director","not a general multi-character or arbitrary-scene route"],cost:"none",privacy:"local",proof:["P7.3 THE SECOND LIGHT specialist render and technical verification recorded in OPERATIONAL_STATE.md"],reason:"A bounded standalone Sentinel performance now renders and verifies on Big Mac, but the director cannot safely dispatch to that worker or reconcile its output. Native 3D job admission remains blocked."}),
    record({id:"audio.production",status:"BLOCKED",host:"unverified",adapter:"none",operations:[],inputs:[],outputs:[],constraints:["No verified audio route"],cost:"unknown",privacy:"local",proof:[],reason:"Audio production is unavailable."}),
    record({id:"assets.authorized-import",status:"BLOCKED",host:"operator source handoff",adapter:"none",operations:[],inputs:[],outputs:[],constraints:["No source pixels or rights record supplied to the director"],cost:"none",privacy:"manual",proof:[],reason:"Reference-sensitive work remains blocked until authorized, verified assets are present."}),
    record({id:"comfyui",status:"EXCLUDED",host:"none",adapter:"none",operations:[],inputs:[],outputs:[],constraints:["Product exclusion"],cost:"none",privacy:"local",proof:[],reason:"Explicitly excluded by repository policy."})
  ];
}

export interface RouteAdmission {job_id:string;selected:string|null;decision:"ADMITTED"|"BLOCKED"|"NEEDS_CLARIFICATION";candidates:Array<{id:string;status:RegistryStatus;selected:boolean;reason:string}>;}
export function routeAdmission(job:CreativeJob,registry=capabilityRegistry()):RouteAdmission{
  const local=registry.find(r=>r.id==="local.motion-graphics")!,canUse=job.route_decision.status==="READY"&&local.status!=="BLOCKED"&&local.status!=="EXCLUDED";
  const blocked=registry.filter(r=>r.id!=="local.motion-graphics"&&r.status!=="EXCLUDED").map(r=>({id:r.id,status:r.status,selected:false,reason:r.reason}));
  return {job_id:job.job_id,selected:canUse?"local.motion-graphics":null,decision:job.route_decision.status==="READY"?canUse?"ADMITTED":"BLOCKED":job.route_decision.status,candidates:[{id:local.id,status:local.status,selected:canUse,reason:canUse?"This job satisfies the local adapter's declared constraints.":"The local adapter does not satisfy this job's route contract."},...blocked]};
}
