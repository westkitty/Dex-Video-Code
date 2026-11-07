import {createHash} from "node:crypto";
import {open} from "node:fs/promises";
import path from "node:path";
import {assertNoSymlinks} from "./paths.js";
import {safeRelative} from "./job.js";

export type AssetRightsStatus="USER_ASSERTED_VERIFIED"|"UNVERIFIED"|"BLOCKED";
export interface AssetProvenanceInput {
  asset_id:string;path:string;sha256:string;source:string;
  rights_status:AssetRightsStatus;rights_basis:string;consent_status:"user_asserted_verified"|"not_required"|"unknown";
  allowed_uses:string[];attribution?:string;
}
export interface AssetProvenanceReceipt extends AssetProvenanceInput {checked_at:string;bytes:number;evidence_scope:"LOCAL_BYTES_ONLY";authorization_state:"NOT_ESTABLISHED_BY_THIS_CHECK";}

export interface AssetApprovalEvent {
  event_id:string;state:"APPROVED"|"REJECTED"|"SUPERSEDED";actor:"USER_ASSERTED";
  recorded_at:string;allowed_uses:string[];supersedes_event_id?:string;
}
export interface AssetTransformation {
  tool:string;version:string;parameters_sha256:string;input_sha256:string;output_sha256:string;
  output_path:string;
}
export interface AssetProvenanceV2 extends AssetProvenanceInput {
  source_revision:string;license:string;approval:AssetApprovalEvent;
  category:"approved_reference"|"experimental"|"rejected";
  dependency_ids:string[];continuity_group?:string;transformations:AssetTransformation[];
}
export interface AssetManifestV2 {schema_version:"asset-provenance.v2";assets:AssetProvenanceV2[];}

function sha256File(pathname:string):Promise<{sha256:string;bytes:number}>{
  return new Promise(async(resolve,reject)=>{
    const digest=createHash("sha256");let bytes=0;
    try{const handle=await open(pathname,"r");const stream=handle.createReadStream({autoClose:false});
      stream.on("data",(chunk:Buffer|string)=>{const buffer=Buffer.isBuffer(chunk)?chunk:Buffer.from(chunk);digest.update(buffer);bytes+=buffer.length;});
      stream.on("error",async e=>{await handle.close().catch(()=>{});reject(e);});
      stream.on("end",async()=>{await handle.close();resolve({sha256:digest.digest("hex"),bytes});});
    }catch(e){reject(e);}
  });
}

async function verifyLocalFile(root:string,relativePath:string,expectedHash:string){
  safeRelative(relativePath);if(!/^[a-f0-9]{64}$/i.test(expectedHash))throw new Error("Asset SHA-256 must be 64 hexadecimal characters.");
  await assertNoSymlinks(root,relativePath);const full=path.resolve(root,relativePath);if(!full.startsWith(path.resolve(root)+path.sep))throw new Error("Asset path escapes its project root.");
  const actual=await sha256File(full);if(actual.sha256!==expectedHash.toLowerCase())throw new Error("Asset bytes do not match the declared SHA-256.");return actual;
}

export async function verifyAssetProvenance(root:string,input:AssetProvenanceInput):Promise<AssetProvenanceReceipt>{
  if(!/^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(input.asset_id))throw new Error("Asset id is invalid.");
  if(!input.source.trim()||!input.rights_basis.trim())throw new Error("Asset source and rights basis are required.");
  if(input.rights_status!=="USER_ASSERTED_VERIFIED"||input.consent_status==="unknown"||input.allowed_uses.length===0)throw new Error("Asset rights, consent or allowed use is unverified; asset use is blocked.");
  const uses=new Set(input.allowed_uses);if(uses.size!==input.allowed_uses.length||[...uses].some(v=>!v.trim()))throw new Error("Asset allowed uses must be nonempty and unique.");
  const actual=await verifyLocalFile(root,input.path,input.sha256);
  return {...input,sha256:input.sha256.toLowerCase(),allowed_uses:[...input.allowed_uses],checked_at:new Date().toISOString(),bytes:actual.bytes,evidence_scope:"LOCAL_BYTES_ONLY",authorization_state:"NOT_ESTABLISHED_BY_THIS_CHECK"};
}

/** Checks declared provenance and exact local dependency/transform bytes. User assertions remain assertions. */
export async function verifyAssetManifest(root:string,manifest:AssetManifestV2){
  if(!manifest||manifest.schema_version!=="asset-provenance.v2"||!Array.isArray(manifest.assets)||Object.keys(manifest).some(k=>!['schema_version','assets'].includes(k)))throw new Error("Expected strict asset-provenance.v2 with an assets array.");
  const assetKeys=new Set(['asset_id','path','sha256','source','source_revision','license','rights_status','rights_basis','consent_status','allowed_uses','attribution','category','approval','dependency_ids','continuity_group','transformations']);
  const ids=new Set<string>();for(const asset of manifest.assets){if(!asset||typeof asset!=='object'||Object.keys(asset).some(k=>!assetKeys.has(k)))throw new Error("Asset entry has unsupported fields.");if(ids.has(asset.asset_id))throw new Error("Asset ids must be unique within the manifest.");ids.add(asset.asset_id);}
  const receipts=[];
  for(const asset of manifest.assets){
    const base=await verifyAssetProvenance(root,asset);
    if(!asset.source_revision.trim()||!asset.license.trim())throw new Error(`Asset ${asset.asset_id} needs a source revision and license declaration.`);
    if(!asset.approval||Object.keys(asset.approval).some(k=>!['event_id','state','actor','recorded_at','allowed_uses','supersedes_event_id'].includes(k))||!/^[-A-Za-z0-9._]{1,100}$/.test(asset.approval.event_id)||asset.approval.actor!=="USER_ASSERTED"||!Number.isFinite(Date.parse(asset.approval.recorded_at))||!Array.isArray(asset.approval.allowed_uses)||asset.approval.allowed_uses.length===0)throw new Error(`Asset ${asset.asset_id} needs a complete user-asserted approval event.`);
    if(asset.approval.state!=="APPROVED"||asset.category!=="approved_reference")throw new Error(`Asset ${asset.asset_id} is rejected, experimental or lacks current approval.`);
    if(asset.approval.allowed_uses.some(use=>!asset.allowed_uses.includes(use)))throw new Error(`Asset ${asset.asset_id} approval exceeds its declared allowed-use scope.`);
    if(!Array.isArray(asset.dependency_ids)||new Set(asset.dependency_ids).size!==asset.dependency_ids.length||asset.dependency_ids.some(id=>!ids.has(id)||id===asset.asset_id))throw new Error(`Asset ${asset.asset_id} has an unknown, repeated or self-referential dependency.`);
    if(asset.continuity_group!==undefined&&!/^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(asset.continuity_group))throw new Error(`Asset ${asset.asset_id} continuity group is invalid.`);
    if(!Array.isArray(asset.transformations))throw new Error(`Asset ${asset.asset_id} transformations must be an array.`);
    let previous=asset.sha256.toLowerCase();const transforms=[];
    for(const transform of asset.transformations){
      if(!transform||Object.keys(transform).some(k=>!['tool','version','parameters_sha256','input_sha256','output_sha256','output_path'].includes(k))||!transform.tool.trim()||!transform.version.trim()||!/^([a-f0-9]{64})$/i.test(transform.parameters_sha256)||transform.input_sha256.toLowerCase()!==previous)throw new Error(`Asset ${asset.asset_id} transformation lineage is invalid.`);
      const output=await verifyLocalFile(root,transform.output_path,transform.output_sha256);
      transforms.push({...transform,input_sha256:transform.input_sha256.toLowerCase(),output_sha256:output.sha256,output_bytes:output.bytes});previous=output.sha256;
    }
    receipts.push({...base,source_revision:asset.source_revision,license:asset.license,category:asset.category,approval:{...asset.approval,scope:"USER_ASSERTED_NOT_CRYPTOGRAPHICALLY_VERIFIED"},dependency_ids:[...asset.dependency_ids],...(asset.continuity_group?{continuity_group:asset.continuity_group}:{}),transformations:transforms,production_admission:"NOT_GRANTED_BY_PROVENANCE_CHECK" as const});
  }
  return {schema_version:"asset-provenance-receipt.v2" as const,checked_at:new Date().toISOString(),evidence_scope:"LOCAL_BYTES_AND_DECLARED_LINEAGE_ONLY" as const,assets:receipts};
}
