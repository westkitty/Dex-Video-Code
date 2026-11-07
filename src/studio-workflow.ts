import {randomUUID} from "node:crypto";
import {spawnSync} from "node:child_process";
import {createInterface} from "node:readline/promises";
import {stdin,stdout} from "node:process";
import {mkdir,readdir,readFile,realpath,writeFile,lstat} from "node:fs/promises";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {assertNoSymlinks,ensureDirectoriesNoSymlink} from "./paths.js";
import {safeRelative,validateJob,normalizeJob} from "./job.js";

const cliPath=fileURLToPath(new URL("./cli.js",import.meta.url));
const run=(root:string,args:string[])=>spawnSync(process.execPath,[cliPath,...args],{cwd:root,encoding:"utf8",timeout:600_000,maxBuffer:4*1024*1024,windowsHide:true});
const errorTail=(value:string)=>value.trim().split("\n").slice(-3).join(" ").slice(-500);
function arg(args:string[],name:string){const index=args.indexOf(name);return index<0?undefined:args[index+1];}
function sessionPath(jobRoot:string){return path.join(jobRoot,"studio-session.json");}
async function saveSession(file:string,value:unknown){await writeFile(file,JSON.stringify(value,null,2)+"\n",{mode:0o600});}
async function readJob(root:string,value:string){const relative=safeRelative(value),absolute=path.resolve(root,relative);if(!absolute.startsWith(root+path.sep))throw new Error("Job manifest must remain inside the current workspace.");await assertNoSymlinks(root,relative);const job=normalizeJob(JSON.parse(await readFile(absolute,"utf8")));validateJob(job);return {job,relative,absolute,jobRoot:path.dirname(absolute)};}
function invoke(root:string,args:string[]){const result=run(root,args);if(result.error||result.status!==0)throw new Error(errorTail(result.stderr||result.stdout)||`Director ${args[0]} failed.`);return result.stdout;}
function openVideo(file:string){if(process.platform!=="darwin")return false;const result=spawnSync("open",["-a","QuickTime Player",file],{encoding:"utf8",timeout:5000,windowsHide:true});return !result.error&&result.status===0;}

/** Low-interruption local flow. Only the existing allowlisted Director commands execute production. */
export async function runStudioWorkflow(rootInput:string,args:string[]):Promise<unknown>{
  const root=await realpath(rootInput);const [action,...rest]=args;
  if(action==="make"){
    const prompt=arg(rest,"--input");if(!prompt?.trim())throw new Error("Use `director studio make --input \"your film brief\"`.");
    const scene=arg(rest,"--scene"),noOpen=rest.includes("--no-open");const id=randomUUID();const dir=`runs/studio/${id}`;await ensureDirectoriesNoSymlink(root,dir);
    const manifestRelative=`${dir}/job.json`,sessionFile=path.join(root,dir,"studio-session.json");
    invoke(root,["plan","--input",prompt,"--out",manifestRelative,...(scene?["--scene",scene]:[])]);
    const initial={schema_version:"studio-session.v1",session_id:id,manifest_path:manifestRelative,source_prompt:prompt,state:"PLANNED",output_class:"MASTER",delivery:"NOT_REQUESTED",artistic_review:"PENDING_HUMAN_REVIEW",created_at:new Date().toISOString()};await saveSession(sessionFile,initial);
    const {job}=await readJob(root,manifestRelative);
    if(job.route_decision.status!=="READY") {const blocked={...initial,state:"BLOCKED",reason:job.route_decision.reason,updated_at:new Date().toISOString()};await saveSession(sessionFile,blocked);return {session_id:id,state:"BLOCKED",reason:job.route_decision.reason,manifest:manifestRelative};}
    try{
      await saveSession(sessionFile,{...initial,state:"RUNNING",updated_at:new Date().toISOString()});
      invoke(root,["produce","--job",manifestRelative]);
      const verified=JSON.parse(invoke(root,["verify","--job",manifestRelative]));
      const verification=JSON.parse(invoke(root,["status","--job",manifestRelative]));
      const checked=verification.verification;
      if(!checked||job.artifacts[0]?.sha256!==checked.sha256||checked.sha256!==verified.sha256||!Number.isSafeInteger(verified.bytes)||verified.bytes<=0||verification.state!=="TECHNICAL_PASS_VISUAL_PENDING")throw new Error("Technical verification did not reach a verified master state.");
      invoke(root,["visual-samples","--job",manifestRelative]);
      const artifactRelative=`${path.posix.dirname(manifestRelative)}/${job.artifacts[0]!.path}`;safeRelative(artifactRelative);await assertNoSymlinks(root,artifactRelative);
      const artifact=path.resolve(root,artifactRelative);if(!artifact.startsWith(root+path.sep))throw new Error("Verified master escaped the workspace.");
      const opened=!noOpen&&openVideo(artifact);
      const completed={...initial,state:"TECHNICALLY_VERIFIED",master_path:artifactRelative,sha256:checked.sha256,bytes:verified.bytes,verified_at:checked.verified_at,visual_review:"PENDING_VISUAL_REVIEW",artistic_review:"PENDING_HUMAN_REVIEW",playback_opened:opened,updated_at:new Date().toISOString()};await saveSession(sessionFile,completed);
      return {session_id:id,state:completed.state,master:artifactRelative,bytes:completed.bytes,sha256:completed.sha256,playback_opened:opened,artistic_review:completed.artistic_review,next:"Use `director studio watch --job "+manifestRelative+"` to reopen, or `director studio review --job "+manifestRelative+" --decision approve|revise` after watching."};
    }catch(error){const failed={...initial,state:"FAILED",error:errorTail(error instanceof Error?error.message:String(error)),updated_at:new Date().toISOString()};await saveSession(sessionFile,failed);throw new Error(`${failed.error} Job state and original files are preserved at ${manifestRelative}.`);}
  }
  if(action==="history"){
    const base=path.join(root,"runs","studio");try{const baseStat=await lstat(base);if(baseStat.isSymbolicLink()||!baseStat.isDirectory())throw new Error("Studio history directory is unsafe.");}catch(e){if((e as NodeJS.ErrnoException).code==="ENOENT")return [];throw e;}
    const entries=await readdir(base,{withFileTypes:true}),history=[];
    for(const entry of entries){if(!entry.isDirectory()||entry.isSymbolicLink())continue;const rel=`runs/studio/${entry.name}/studio-session.json`;try{await assertNoSymlinks(root,rel);history.push(JSON.parse(await readFile(path.join(root,rel),"utf8")));}catch(e){if((e as NodeJS.ErrnoException).code!=="ENOENT")throw e;}}
    return history.sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at))).map(s=>({session_id:s.session_id,state:s.state,manifest:s.manifest_path,master:s.master_path??null,artistic_review:s.artistic_review,delivery:s.delivery}));
  }
  if(action==="watch"){
    const manifestArg=arg(rest,"--job"),noOpen=rest.includes("--no-open");if(!manifestArg)throw new Error("Use `director studio watch --job <manifest>`.");const {job,relative,jobRoot}=await readJob(root,manifestArg);invoke(root,["verify","--job",relative]);const status=JSON.parse(invoke(root,["status","--job",relative]));if(status.state!=="TECHNICAL_PASS_VISUAL_PENDING")throw new Error("This job has no technically verified master to watch.");const artifact=job.artifacts[0];if(!artifact)throw new Error("This job has no master declaration.");await assertNoSymlinks(jobRoot,artifact.path);const file=path.resolve(jobRoot,artifact.path);if(!file.startsWith(jobRoot+path.sep))throw new Error("Master path escapes its job directory.");const opened=!noOpen&&openVideo(file);return {job_id:job.job_id,state:"TECHNICALLY_VERIFIED",path:path.relative(root,file),sha256:status.verification.sha256,playback_opened:opened,artistic_review:"PENDING_HUMAN_REVIEW"};
  }
  if(action==="review"){
    if(!stdin.isTTY||!stdout.isTTY)throw new Error("Human review requires an interactive terminal; no approval was recorded.");
    const manifestArg=arg(rest,"--job"),decision=arg(rest,"--decision");if(!manifestArg||!(["approve","revise"] as string[]).includes(decision??""))throw new Error("Use `director studio review --job <manifest> --decision approve|revise`.");
    const {job,relative,jobRoot}=await readJob(root,manifestArg);invoke(root,["verify","--job",relative]);const statusPath=path.join(jobRoot,"job-state.json"),state=JSON.parse(await readFile(statusPath,"utf8"));if(state.state!=="TECHNICAL_PASS_VISUAL_PENDING")throw new Error("Only a technically verified master can be reviewed.");const artifact=job.artifacts[0];if(!artifact)throw new Error("Job has no master.");const file=path.resolve(jobRoot,artifact.path);await assertNoSymlinks(jobRoot,artifact.path);if(!openVideo(file))throw new Error("Could not open the verified master for review; no approval was recorded.");
    const rl=createInterface({input:stdin,output:stdout});try{
      const watched=await rl.question("After watching the master, have you reviewed it? Type YES to continue: ");if(watched.trim()!=="YES")throw new Error("Review was not confirmed; no approval was recorded.");
      if(decision==="approve")state.human_review={state:"USER_APPROVED",actor:"INTERACTIVE_USER_ASSERTION",job_id:job.job_id,master_sha256:state.verification.sha256,recorded_at:new Date().toISOString()};
      else {const note=(await rl.question("Describe the requested revision: ")).trim();if(!note)throw new Error("Revision request was empty; no change was recorded.");state.human_review={state:"REVISION_REQUESTED",actor:"INTERACTIVE_USER_ASSERTION",job_id:job.job_id,master_sha256:state.verification.sha256,note,recorded_at:new Date().toISOString()};}
      await writeFile(statusPath,JSON.stringify(state,null,2)+"\n");return state.human_review;
    }finally{rl.close();}
  }
  throw new Error("Use `director studio make`, `history`, `watch`, or `review`.");
}
