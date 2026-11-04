import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import type { CreativeJob } from "./types.js";

export interface ProbeStream { codec_type:string;codec_name?:string;width?:number;height?:number;r_frame_rate?:string;avg_frame_rate?:string; }
export interface ProbeData {format?:{duration?:string;format_name?:string};streams?:ProbeStream[];}
export function assessMedia(job:CreativeJob,probe:ProbeData,sha:string,byteCount:number,decodeExit:number|null):{passes:boolean;failures:string[]} {
  const failures:string[]=[];const streams=probe.streams??[];const video=streams.find(s=>s.codec_type==="video"), audio=streams.some(s=>s.codec_type==="audio"), subs=streams.some(s=>s.codec_type==="subtitle");
  const actualDuration=Number(probe.format?.duration);const tolerance=Math.max(.1,job.brief.duration_seconds*.005);
  if(!Number.isFinite(actualDuration)||Math.abs(actualDuration-job.brief.duration_seconds)>tolerance)failures.push(`duration mismatch (expected ${job.brief.duration_seconds}s ±${tolerance.toFixed(2)}s; got ${probe.format?.duration??"unknown"})`);
  if(job.brief.deliverable_type==="video"&&(!video||audio))failures.push("video deliverable must contain video and no undeclared audio stream");
  if(job.brief.deliverable_type==="audio"&&(!audio||video))failures.push("audio deliverable must contain audio and no video stream");
  if(video&&(video.width!==job.render_plan.width||video.height!==job.render_plan.height))failures.push(`dimension mismatch (expected ${job.render_plan.width}x${job.render_plan.height})`);
  if(video&&video.width&&video.height){const [rw,rh]=job.brief.aspect_ratio.split(":").map(Number);if(!Number.isFinite(rw/rh)||Math.abs(video.width/video.height-rw/rh)>.01)failures.push(`aspect ratio mismatch (expected ${job.brief.aspect_ratio})`);}
  if(video&&video.codec_name!=="h264")failures.push(`video codec mismatch (expected h264, got ${video.codec_name??"unknown"})`);
  if(video){const fps=video.avg_frame_rate??video.r_frame_rate;const [n,d]=String(fps).split("/").map(Number);const actual=n/d;if(!Number.isFinite(actual)||Math.abs(actual-job.render_plan.fps)>.01)failures.push(`frame rate mismatch (expected ${job.render_plan.fps}, got ${fps})`);}
  if(!probe.format?.format_name?.split(",").includes("mp4"))failures.push("container mismatch (expected MP4)");
  if(job.brief.captions==="off"&&subs)failures.push("subtitle stream present while captions are off");
  if(decodeExit!==0)failures.push("full media decode failed");
  if(!job.artifacts[0]?.sha256)failures.push("artifact SHA-256 is missing from manifest");else if(job.artifacts[0].sha256!==sha)failures.push("artifact SHA-256 differs from manifest");
  if(byteCount<=0)failures.push("artifact is empty");return {passes:failures.length===0,failures};
}
export async function verifyMedia(job:CreativeJob,file:string):Promise<{bytes:number;sha256:string;probe:ProbeData;full_decode:"PASS"|"FAIL";failures:string[];state:"TECHNICAL_PASS_VISUAL_PENDING"|"FAILED"}> {
  const bytes=await readFile(file),sha=createHash("sha256").update(bytes).digest("hex");
  const p=spawnSync("ffprobe",["-v","error","-show_entries","format=duration,size,format_name:stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate","-of","json",file],{encoding:"utf8",timeout:10000});
  if(p.status!==0)throw new Error(`ffprobe failed: ${p.stderr||p.error?.message||p.status}`);
  const probe=JSON.parse(p.stdout) as ProbeData;
  const d=spawnSync("ffmpeg",["-v","error","-nostdin","-i",file,"-f","null","-"],{encoding:"utf8",timeout:120000});
  const assessed=assessMedia(job,probe,sha,bytes.length,d.status);
  return {bytes:bytes.length,sha256:sha,probe,full_decode:d.status===0?"PASS":"FAIL",failures:assessed.failures,state:assessed.passes?"TECHNICAL_PASS_VISUAL_PENDING":"FAILED"};
}
