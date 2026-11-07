import test from "node:test";
import assert from "node:assert/strict";
import {capabilityRegistry,routeAdmission} from "../src/capability-registry.js";
import {makeJob} from "../src/job.js";
import {mkdtemp,readFile,rm,writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import path from "node:path";
import {spawnSync} from "node:child_process";
import {fileURLToPath} from "node:url";

test("registry keeps unproven or historical workers from gaining a route admission",()=>{
  const r=capabilityRegistry();assert.equal(r.find(x=>x.id==="hyperframes.controller")?.status,"HISTORICAL_ONLY");assert.deepEqual(r.find(x=>x.id==="hyperframes.controller")?.operations,[]);assert.equal(r.find(x=>x.id==="comfyui")?.status,"EXCLUDED");
  const blocked=routeAdmission(makeJob("Create a 40-second cinematic 3D sword fight between two animated characters"),r);assert.equal(blocked.selected,null);assert.equal(blocked.decision,"BLOCKED");
});
test("standalone P7.3 proof does not unlock director 3D without typed dispatch",()=>{
  const registry=capabilityRegistry(),threeD=registry.find(x=>x.id==="native.articulated-3d")!;
  assert.equal(threeD.status,"BLOCKED");assert.deepEqual(threeD.operations,[]);
  assert.match(threeD.reason,/cannot safely dispatch/i);
  assert.match(threeD.constraints.join(" "),/not a general multi-character/i);
  const job=makeJob("Create a 6-second 3D character performance with a mechanical Sentinel.");
  const admission=routeAdmission(job,registry);assert.equal(admission.decision,"BLOCKED");assert.equal(admission.selected,null);
});
test("a verified local job binds proof to its job id, hash and observation",()=>{
  const when="2026-11-07T00:00:00.000Z",r=capabilityRegistry({job_id:"job-safe",sha256:"a".repeat(64),verified_at:when,host:"local test host"});const local=r.find(x=>x.id==="local.motion-graphics")!;assert.equal(local.status,"VERIFIED_LIVE");assert.ok(local.proof.includes(`Master SHA-256 ${"a".repeat(64)}`));assert.ok(local.proof.includes(`Verified ${when}`));
});
test("ready local jobs admit only the matching bounded adapter",()=>{const job=makeJob("Create a 12-second geometric motion graphic showing a circle transforming without text");const admission=routeAdmission(job);assert.equal(admission.decision,"ADMITTED");assert.equal(admission.selected,"local.motion-graphics");assert.equal(admission.candidates.filter(c=>c.selected).length,1);assert.equal(admission.candidates.some(c=>c.id==="hyperframes.controller"&&c.selected),false);});
test("stored plans remain inspectable but production re-probes current tools",async()=>{const root=await mkdtemp(path.join(tmpdir(),"dvc-registry-admission-"));try{const job=makeJob("Create a 1-second motion graphic showing a transforming circle without text");await writeFile(path.join(root,"job.json"),JSON.stringify(job));const cli=fileURLToPath(new URL("../src/cli.js",import.meta.url));const p=spawnSync(process.execPath,[cli,"produce","--job","job.json"],{cwd:root,encoding:"utf8",timeout:15000,env:{...process.env,PATH:"/nonexistent"}});assert.notEqual(p.status,0);assert.match(p.stderr,/Current local render capability is unavailable/);await assert.rejects(readFile(path.join(root,"job-state.json")),{code:"ENOENT"});}finally{await rm(root,{recursive:true,force:true});}});
