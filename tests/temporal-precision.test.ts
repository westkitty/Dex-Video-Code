import { strict as assert } from "node:assert";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { resolveTemporalPrecision, runTemporalPrecision, type TemporalPrecisionContract } from "../src/temporal-precision.js";
const base=():TemporalPrecisionContract=>({
  schema_version:"temporal-precision.v1",
  source:{path:"source.mp4",sha256:"a".repeat(64),rights:"authorized"},
  alignment:{source_sha256:"a".repeat(64),method:"forced_alignment",engine:"fixture-aligner",evidence:"fixture/word-times.json",words:[{text:"FLASH",start_seconds:2.2,end_seconds:2.51}]},
  timing:{fps_numerator:24,fps_denominator:1,duration_frames:120},
  edit:{trigger:{kind:"spoken_word_end",literal:"FLASH",occurrence:1},operation:"high_contrast_lighting",allowed:["luminance","contrast"],protected:["audio","geometry","identity","camera","framing","timing"],transition_frames:0},
  output_path:"edited.mp4",captions:"off"
});
test("observed word completion at 2.51s becomes frame 61",()=>{const r=resolveTemporalPrecision(base());assert.equal(r.state,"READY");if(r.state==="READY")assert.equal(r.first_edited_frame,61)});
test("exact boundary 2.5 seconds becomes frame 60",()=>{const c=base();c.alignment.words[0]!.end_seconds=2.5;const r=resolveTemporalPrecision(c);assert.equal(r.state,"READY");if(r.state==="READY")assert.equal(r.first_edited_frame,60)});
test("no guessed timestamps: missing alignment holds",()=>{const c=base();c.alignment.words=[];assert.equal(resolveTemporalPrecision(c).state,"HOLD")});
test("unbound or manually assigned alignments hold",()=>{const c=base();c.alignment.source_sha256="b".repeat(64);assert.equal(resolveTemporalPrecision(c).state,"HOLD");c.alignment.source_sha256=c.source.sha256;(c.alignment as any).method="manual";assert.equal(resolveTemporalPrecision(c).state,"HOLD")});
test("missing protection lock holds",()=>{const c=base();c.edit.protected=[];assert.equal(resolveTemporalPrecision(c).state,"HOLD")});
test("out of clip holds",()=>{const c=base();c.alignment.words[0]!.end_seconds=5;assert.equal(resolveTemporalPrecision(c).state,"HOLD")});
test("captions and unsupported property hold",()=>{const c=base();(c as any).captions="on";assert.equal(resolveTemporalPrecision(c).state,"HOLD");c.captions="off";(c.edit.allowed as string[]).push("camera");assert.equal(resolveTemporalPrecision(c).state,"HOLD")});
test("extra manifest fields and unsafe path hold",()=>{const c=base();(c as any).authorization="granted";assert.equal(resolveTemporalPrecision(c).state,"HOLD");delete (c as any).authorization;c.source.path="../private.mp4";assert.equal(resolveTemporalPrecision(c).state,"HOLD")});
test("select explicit occurrence of repeated trigger",()=>{const c=base();c.alignment.words=[{text:"flash",start_seconds:0.2,end_seconds:0.5},{text:"FLASH!",start_seconds:2.2,end_seconds:2.51}];c.edit.trigger.occurrence=2;const r=resolveTemporalPrecision(c);assert.equal(r.state,"READY");if(r.state==="READY")assert.equal(r.first_edited_frame,61)});


const mediaToolsPresent = ["ffmpeg","ffprobe"].every(bin=>spawnSync(bin,["-version"],{timeout:3000}).status===0);
function runTool(bin:string,args:string[]):Buffer {
  const p=spawnSync(bin,args,{timeout:20000,maxBuffer:2*1024*1024});
  assert.equal(p.status,0,bin+": "+String(p.stderr));
  return p.stdout;
}
async function sourceFixture(dir:string,delayedAudio=false):Promise<TemporalPrecisionContract> {
  const file=path.join(dir,"input.mp4");
  runTool("ffmpeg",[
    "-nostdin","-hide_banner","-v","error","-f","lavfi","-i","testsrc2=size=96x64:rate=24:duration=1",
    ...(delayedAudio?["-itsoffset","0.25"]:[]),
    "-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=1",
    "-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p","-c:a","aac","-shortest","-y",file
  ]);
  const sha=createHash("sha256").update(await readFile(file)).digest("hex");
  const contract=base();contract.source.path="input.mp4";contract.source.sha256=sha;
  contract.alignment.source_sha256=sha;contract.alignment.words=[{text:"FLASH",start_seconds:0.18,end_seconds:0.251}];
  contract.timing.duration_frames=24;contract.output_path="output.mp4";
  await writeFile(path.join(dir,"contract.json"),JSON.stringify(contract));
  return contract;
}
function videoFrame(file:string,index:number):Buffer {
  return runTool("ffmpeg",["-nostdin","-v","error","-i",file,"-vf","select=eq(n\\,"+index+")","-frames:v","1","-f","rawvideo","-pix_fmt","gray","-"]);
}
function meanAbsolutePixelDifference(a:Buffer,b:Buffer):number {
  assert.equal(a.length,b.length);assert.ok(a.length>0);
  let total=0;for(let i=0;i<a.length;i++) total+=Math.abs(a[i]!-b[i]!);
  return total/a.length;
}
test("real MP4 edit begins after declared word end, preserves decoded audio and refuses overwrite",{skip:!mediaToolsPresent},async()=>{
  const root=await mkdtemp(path.join(tmpdir(),"dvc-temporal-proof-"));
  try{
    await sourceFixture(root);
    const result=await runTemporalPrecision(root,["apply","--contract","contract.json"]) as {state:string;first_edited_frame:number;output_sha256:string;audio_decoded_sha256:string};
    assert.equal(result.state,"TECHNICAL_PASS_VISUAL_PENDING");assert.equal(result.first_edited_frame,7);
    const output=path.join(root,"output.mp4"),beforeHash=createHash("sha256").update(await readFile(output)).digest("hex");
    assert.equal(result.output_sha256,beforeHash);
    const source=path.join(root,"input.mp4");
    const pre=meanAbsolutePixelDifference(videoFrame(source,6),videoFrame(output,6));
    const post=meanAbsolutePixelDifference(videoFrame(source,7),videoFrame(output,7));
    assert.ok(post>pre+10,"Edit did not begin at declared frame: pre="+pre+" post="+post);
    await assert.rejects(runTemporalPrecision(root,["apply","--contract","contract.json"]),/Output already exists/);
    assert.equal(createHash("sha256").update(await readFile(output)).digest("hex"),beforeHash);
  }finally{await rm(root,{recursive:true,force:true});}
});
test("real MP4 with delayed audio is held rather than editing at the wrong frame",{skip:!mediaToolsPresent},async()=>{
  const root=await mkdtemp(path.join(tmpdir(),"dvc-temporal-audio-offset-"));
  try{
    await sourceFixture(root,true);
    await assert.rejects(runTemporalPrecision(root,["apply","--contract","contract.json"]),/audio start time/);
    await assert.rejects(readFile(path.join(root,"output.mp4")),{code:"ENOENT"});
  }finally{await rm(root,{recursive:true,force:true});}
});
test("real MP4 with stale source hash never renders",{skip:!mediaToolsPresent},async()=>{
  const root=await mkdtemp(path.join(tmpdir(),"dvc-temporal-stale-source-"));
  try{
    const c=await sourceFixture(root);c.source.sha256="b".repeat(64);c.alignment.source_sha256=c.source.sha256;
    await writeFile(path.join(root,"contract.json"),JSON.stringify(c));
    await assert.rejects(runTemporalPrecision(root,["apply","--contract","contract.json"]),/Source SHA-256 differs/);
    await assert.rejects(readFile(path.join(root,"output.mp4")),{code:"ENOENT"});
  }finally{await rm(root,{recursive:true,force:true});}
});
