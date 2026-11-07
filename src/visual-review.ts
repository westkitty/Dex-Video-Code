import {createHash} from "node:crypto";
import {mkdir,readFile,writeFile} from "node:fs/promises";
import {spawnSync} from "node:child_process";
import path from "node:path";
import type {CreativeJob} from "./types.js";
import {assertNoSymlinks,ensureDirectoriesNoSymlink} from "./paths.js";
import {safeRelative} from "./job.js";
import {verifyMedia} from "./verification.js";

export interface VisualSample {seconds:number;path:string;bytes:number;sha256:string;}
export interface VisualEvidence {schema_version:"visual-evidence.v1";job_id:string;source_path:string;source_sha256:string;state:"PENDING_VISUAL_REVIEW";samples:VisualSample[];created_at:string;}
const morphTimes=(duration:number)=>[.5,3.5,5,6.5,8.5,duration-.5];
export function defaultVisualSampleTimes(job:CreativeJob):number[]{
  if(job.authored_motion)return [...job.authored_motion.visual_sample_times];
  const duration=job.brief.duration_seconds;if(duration<=0)return [];
  const candidates=job.render_plan.shape_transform_mode==="continuous_circle_square_v1"?morphTimes(duration):[.5,duration*.25,duration*.5,duration*.75,duration-.5];
  return [...new Set(candidates.filter(t=>Number.isFinite(t)&&t>0&&t<duration).map(t=>Math.round(t*1000)/1000))].sort((a,b)=>a-b);
}
function safeComponent(v:string){return v.replace(/[^A-Za-z0-9._-]+/g,"-").slice(0,80)||"job";}
export async function extractVisualSamples(job:CreativeJob,jobRoot:string):Promise<VisualEvidence>{
  const artifact=job.artifacts[0];if(!artifact||artifact.format!=="video/mp4"||job.proof.technical_status!=="TECHNICAL_PASS_VISUAL_PENDING")throw new Error("Visual evidence requires a technically verified MP4 master.");
  safeRelative(artifact.path);await assertNoSymlinks(jobRoot,artifact.path);const source=path.resolve(jobRoot,artifact.path);if(!source.startsWith(path.resolve(jobRoot)+path.sep))throw new Error("Master path escapes its job directory.");
  const checked=await verifyMedia(job,source);if(checked.state!=="TECHNICAL_PASS_VISUAL_PENDING")throw new Error("Master changed or failed verification; visual samples were not created.");
  const sampleTimes=defaultVisualSampleTimes(job),sampleSet=createHash("sha256").update(JSON.stringify(sampleTimes)).digest("hex").slice(0,8);const relativeDir=`visual-evidence/${safeComponent(job.job_id)}-${checked.sha256.slice(0,12)}-${sampleSet}`;await ensureDirectoriesNoSymlink(jobRoot,"visual-evidence");await assertNoSymlinks(jobRoot,relativeDir);const outputDir=path.resolve(jobRoot,relativeDir);await mkdir(outputDir,{recursive:false});
  const samples:VisualSample[]=[];
  for(const [index,seconds] of sampleTimes.entries()){
    const filename=`frame-${String(index+1).padStart(2,"0")}-${seconds.toFixed(3)}s.png`,relativePath=`${relativeDir}/${filename}`,out=path.join(outputDir,filename);
    const p=spawnSync("ffmpeg",["-hide_banner","-loglevel","error","-nostdin","-n","-ss",seconds.toFixed(3),"-i",source,"-frames:v","1","-f","image2",out],{encoding:"utf8",timeout:20000,maxBuffer:1024*1024});
    if(p.status!==0)throw new Error(`Encoded-frame extraction failed at ${seconds.toFixed(3)}s.`);
    await assertNoSymlinks(jobRoot,relativePath);const bytes=await readFile(out);samples.push({seconds,path:relativePath,bytes:bytes.length,sha256:createHash("sha256").update(bytes).digest("hex")});
  }
  const evidence:VisualEvidence={schema_version:"visual-evidence.v1",job_id:job.job_id,source_path:artifact.path,source_sha256:checked.sha256,state:"PENDING_VISUAL_REVIEW",samples,created_at:new Date().toISOString()};
  await writeFile(path.join(outputDir,"evidence.json"),JSON.stringify(evidence,null,2)+"\n",{flag:"wx"});return evidence;
}
