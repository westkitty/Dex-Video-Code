import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { mkdtemp, mkdir, symlink, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { makeJob, validateJob } from "../src/job.js";
import { planRoutes, discoverCapabilities } from "../src/capabilities.js";
import { assertNoSymlinks } from "../src/render.js";

test("motion graphics route does not require a 3D rig",()=>{const p=planRoutes("A 20 second motion graphic explaining a quiet signal.");assert.equal(p.selected,"motion-graphics");assert.equal(p.requires3dRig,false);assert.equal(p.routes.some(r=>r.id==="comfyui"&&r.available),false);assert.equal(p.alternatives.includes("comfyui"),false);});
test("explicit articulated 3D remains a hard gated route",()=>{const p=planRoutes("Create genuinely 3D acting with articulated 3D characters.");assert.equal(p.selected,"articulated-3d");assert.equal(p.requires3dRig,true);assert.equal(p.routes[0]?.available,false);const j=makeJob("Create genuinely 3D acting with an articulated 3D puppet.");assert.equal(j.execution_plan.length,0);assert.equal(j.proof.technical_status,"BLOCKED_ARTISTIC_CONSTRAINT");});
test("schema validates a planned job and denies traversal",()=>{const j=makeJob("Make a motion graphic about a signal.");validateJob(j);j.artifacts[0]!.path="../../private.mp4";assert.throws(()=>validateJob(j),/Unsafe/);});
test("ComfyUI is excluded and never selected",()=>{const caps=discoverCapabilities();assert.equal(caps.find(c=>c.id==="comfyui")?.state,"EXCLUDED");assert.notEqual(planRoutes("motion graphic").selected,"comfyui");});
test("unknown execution adapters are rejected",()=>{const j=makeJob("A graphic");j.execution_plan[0]!.adapter="shell";assert.throws(()=>validateJob(j),/not allowlisted/);});

test("safe motion-graphics job fixture validates",()=>{const p=fileURLToPath(new URL("../../examples/fixtures/motion-graphics.job.v1.json",import.meta.url));const fixture=JSON.parse(readFileSync(p,"utf8"));validateJob(fixture);});

test("output confinement rejects a symlink escape",async()=>{const root=await mkdtemp(path.join(tmpdir(),"dvc-test-"));const outside=await mkdtemp(path.join(tmpdir(),"dvc-outside-"));try{await symlink(outside,path.join(root,"link"));await assert.rejects(assertNoSymlinks(root,"link/private.mp4"),/symlink/);}finally{await rm(root,{recursive:true,force:true});await rm(outside,{recursive:true,force:true});}});

test("unavailable tools remain visible but unavailable in a mock capability snapshot",()=>{const unavailable=[{id:"local.ffmpeg",state:"UNAVAILABLE",host:"mock",reason:"missing",cost:"none",privacy:"local"},{id:"local.rasterizer",state:"UNAVAILABLE",host:"mock",reason:"missing",cost:"none",privacy:"local"}] as const;const p=planRoutes("A motion graphic",unavailable as never);assert.equal(p.selected,"motion-graphics");assert.equal(p.routes[0]?.available,false);});
