import { Ajv2020 } from "ajv/dist/2020.js";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import type { CreativeJob } from "./types.js";
const schemaPath = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../schemas/creative-job.v1.schema.json");
const schema = JSON.parse(readFileSync(schemaPath,"utf8"));
const validate = new Ajv2020({allErrors:true,strict:false}).compile(schema);
export function validateJob(value: unknown): asserts value is CreativeJob {
  if (!validate(value)) throw new Error(`Invalid CreativeJob v1: ${JSON.stringify(validate.errors)}`);
  const job=value as CreativeJob;
  for (const artifact of job.artifacts) safeRelative(artifact.path);
  if (job.route_decision.selected.toLowerCase().includes("comfy")) throw new Error("Excluded route cannot be selected.");
  for (const step of job.execution_plan) {
    if (!["motion-graphics-local"].includes(step.adapter)) throw new Error(`Adapter is not allowlisted: ${step.adapter}`);
    if (step.timeout_seconds > 300) throw new Error("Execution timeout exceeds 300 second policy ceiling.");
  }
}
export function safeRelative(value:string): string {
  if (!value || path.isAbsolute(value) || value.includes("\\") || value.split("/").some(s=>s===".."||s==="")) throw new Error(`Unsafe or non-relative project path: ${value}`);
  return value;
}
export function makeJob(prompt:string):CreativeJob {
  const plan= (awaitlessRoutes(prompt));
  const id=`dv_${Date.now().toString(36)}-${Math.random().toString(36).slice(2,10)}`;
  const duration=16;
  const isBlocked=plan.selected==="articulated-3d";
  return {schema_version:"1.0",job_id:id,source_prompt:prompt,brief:{deliverable_type:"video",format:"mp4",aspect_ratio:"16:9",duration_seconds:duration,tone:"quietly hopeful, precise",exclusions:["no narration","no subtitles","no captions","no new voice or music"],captions:"off"},route_decision:{selected:plan.selected,alternatives:plan.alternatives,reason:plan.rationale,evidence:["local FFmpeg version probe","prompt classification"]},shots_or_beats:[{start:0,end:4,purpose:"Establish an isolated signal",visual_state:"A dim field and one drifting point"},{start:4,end:10,purpose:"Build motion and anticipation",visual_state:"The point traces a path through measured rings"},{start:10,end:16,purpose:"Resolve into a clear visual payoff",visual_state:"The path closes into a bright connected mark and title"}],assets:[],execution_plan:isBlocked?[]:[{operation:"render-original-motion-graphic",adapter:"motion-graphics-local",approval:"not_required",timeout_seconds:240}],artifacts:[{role:"master",format:"video/mp4",path:`outputs/${id}/master.mp4`}],proof:{technical_status:isBlocked?"BLOCKED_ARTISTIC_CONSTRAINT":"PENDING",artistic_status:"PENDING_HUMAN_REVIEW",evidence:isBlocked?["Explicit articulated 3D requirement; native rig/render adapter unavailable."]:[]}};
}
function awaitlessRoutes(prompt:string){
  const p=prompt.toLowerCase();
  if(/articulated 3d|genuinely 3d acting|rigged 3d|3d puppet/.test(p)) return {selected:"articulated-3d",alternatives:["motion-graphics"],rationale:"Explicit 3D acting requirement; this route is blocked until native rig/render capability is verified."};
  return {selected:"motion-graphics",alternatives:["illustrated-2.5d","articulated-3d"],rationale:"Original kinetic typography and shape animation fit the brief without imposing character or 3D production."};
}
