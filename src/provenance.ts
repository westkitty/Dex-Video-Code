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

export async function verifyAssetProvenance(root:string,input:AssetProvenanceInput):Promise<AssetProvenanceReceipt>{
  if(!/^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(input.asset_id))throw new Error("Asset id is invalid.");
  safeRelative(input.path);if(!/^[a-f0-9]{64}$/i.test(input.sha256))throw new Error("Asset SHA-256 must be 64 hexadecimal characters.");
  if(!input.source.trim()||!input.rights_basis.trim())throw new Error("Asset source and rights basis are required.");
  if(input.rights_status!=="USER_ASSERTED_VERIFIED"||input.consent_status==="unknown"||input.allowed_uses.length===0)throw new Error("Asset rights, consent or allowed use is unverified; asset use is blocked.");
  const uses=new Set(input.allowed_uses);if(uses.size!==input.allowed_uses.length||[...uses].some(v=>!v.trim()))throw new Error("Asset allowed uses must be nonempty and unique.");
  await assertNoSymlinks(root,input.path);const full=path.resolve(root,input.path);if(!full.startsWith(path.resolve(root)+path.sep))throw new Error("Asset path escapes its project root.");
  const handle=await open(full,"r");const digest=createHash("sha256");let bytes=0;
  try{for await(const chunk of handle.createReadStream({autoClose:false})){digest.update(chunk);bytes+=chunk.length;}}finally{await handle.close();}
  if(digest.digest("hex")!==input.sha256.toLowerCase())throw new Error("Asset bytes do not match the declared SHA-256.");
  return {...input,sha256:input.sha256.toLowerCase(),allowed_uses:[...input.allowed_uses],checked_at:new Date().toISOString(),bytes,evidence_scope:"LOCAL_BYTES_ONLY",authorization_state:"NOT_ESTABLISHED_BY_THIS_CHECK"};
}
