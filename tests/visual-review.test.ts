import test from "node:test";
import assert from "node:assert/strict";
import {mkdtemp,rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import path from "node:path";
import {makeJob} from "../src/job.js";
import {defaultVisualSampleTimes,extractVisualSamples} from "../src/visual-review.js";

test("circle-square evidence samples target the required action moments",()=>{const job=makeJob("Create a 12-second motion graphic where one luminous circle smoothly morphs into one square, centered and stationary, with no text or subtitles.");assert.deepEqual(defaultVisualSampleTimes(job),[.5,3.5,5,6.5,8.5,11.5]);});
test("generic sample times are sorted, unique and inside the declared duration",()=>{const job=makeJob("Create a 1-second motion graphic showing a circle transforming without text");const t=defaultVisualSampleTimes(job);assert.deepEqual(t,[.25,.5,.75]);assert.ok(t.every(x=>x>0&&x<job.brief.duration_seconds));});
test("sample extraction fails closed until technical verification",async()=>{const root=await mkdtemp(path.join(tmpdir(),"dvc-visual-")),job=makeJob("Create a 1-second motion graphic showing a circle transforming without text");try{await assert.rejects(extractVisualSamples(job,root),/technically verified MP4 master/);}finally{await rm(root,{recursive:true,force:true});}});
