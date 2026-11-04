import { Ajv2020 } from "ajv/dist/2020.js";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import type { CreativeJob, Capability } from "./types.js";
import { discoverCapabilities } from "./capabilities.js";
const schemaPath = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../schemas/creative-job.v1.1.schema.json");
const validateSchema = new Ajv2020({allErrors:true,strict:false}).compile(JSON.parse(readFileSync(schemaPath,"utf8")));
export function safeRelative(value:string): string {
  if (!value || path.isAbsolute(value) || value.includes("\\") || value.split("/").some(s=>s===".."||s===""||s===".")) throw new Error(`Unsafe or non-relative project path: ${value}`);
  return value;
}
export function validateJob(value: unknown): asserts value is CreativeJob {
  if (!validateSchema(value)) throw new Error(`Invalid CreativeJob v1.1: ${JSON.stringify(validateSchema.errors)}`);
  const job=value as CreativeJob;
  for (const artifact of job.artifacts) safeRelative(artifact.path);
  if (job.route_decision.selected.toLowerCase().includes("comfy")) throw new Error("Excluded route cannot be selected.");
  for (const step of job.execution_plan) {
    if (step.adapter!=="motion-graphics-local" || step.operation!=="render-original-motion-graphic") throw new Error(`Operation/adapter is not allowlisted: ${step.operation}/${step.adapter}`);
    if (step.approval!=="not_required") throw new Error("User-editable approval fields cannot authorize production. Required approval must be recorded outside the job manifest.");
    if (step.timeout_seconds > 300) throw new Error("Execution timeout exceeds 300 second policy ceiling.");
  }
  const expected=planCreativeJob(job.source_prompt);
  const same=(a:unknown,b:unknown)=>JSON.stringify(a)===JSON.stringify(b);
  if(!same(job.brief,expected.brief)||!same(job.creative_intent,expected.creative_intent)||!same(job.render_plan,expected.render_plan)||!same(job.shots_or_beats,expected.shots_or_beats)||!same(job.execution_plan,expected.execution_plan)||job.route_decision.selected!==expected.route_decision.selected||job.route_decision.status!==expected.route_decision.status||job.route_decision.reason!==expected.route_decision.reason||job.artifacts.length!==1||job.artifacts[0]?.format!==expected.artifacts[0]?.format||job.artifacts[0]?.role!=="master"||job.route_decision.status==="READY"&&job.assets.length>0)throw new Error("Creative plan fields do not match source_prompt and current capability; re-plan before execution.");
}
export function normalizeJob(value: unknown): CreativeJob {
  if ((value as {schema_version?:string})?.schema_version === "1.1") { validateJob(value); return value as CreativeJob; }
  const old=value as Record<string,any>;
  if(old?.schema_version!=="1.0"||!old.brief||!old.route_decision) throw new Error("Unsupported CreativeJob schema version.");
  const upgraded=planCreativeJob(String(old.source_prompt??""));
  upgraded.job_id=String(old.job_id??upgraded.job_id);
  upgraded.artifacts=Array.isArray(old.artifacts)?old.artifacts:upgraded.artifacts;
  upgraded.assets=Array.isArray(old.assets)?old.assets:[];
  return upgraded;
}
export function planCreativeJob(prompt:string, capabilities:Capability[]=discoverCapabilities()):CreativeJob {
  const p=prompt.trim(), low=p.toLowerCase();
  const durationWords:Record<string,number>={one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10,eleven:11,twelve:12,thirteen:13,fourteen:14,fifteen:15,sixteen:16,seventeen:17,eighteen:18,nineteen:19,twenty:20,twentyone:21,twentytwo:22,twentythree:23,twentyfour:24,twentyfive:25,twentysix:26,twentyseven:27,twentyeight:28,twentynine:29,thirty:30};
  const durationNumberWords="one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty(?:[- ]?(?:one|two|three|four|five|six|seven|eight|nine))?|thirty";
  const dur=p.match(new RegExp(`\\b(\\d+(?:\\.\\d+)?|${durationNumberWords})\\s*-?\\s*(?:seconds?|secs?|s)\\b`,"i"));
  const duration=dur?Number(dur[1])||durationWords[dur[1].toLowerCase().replace(/[- ]/g,"")]||0:0;
  const aspect=p.match(/\b(\d+)\s*:\s*(\d+)\b/);
  const aspectRatio=aspect?`${aspect[1]}:${aspect[2]}`:"16:9";
  const requestedFormat=(p.match(/\b(mp4|webm|mov|gif)\b/i)?.[1]??"").toLowerCase();
  const positiveAudioPrompt=low.replace(/\b(no|without|exclude|omit|avoid)\b[^,.;]*/gi,"");
  const audioOnly=/\baudio[- ]only\b|\bonly audio\b/.test(low)||(!/\bvideo\b/.test(low)&&/\b(audio|song|soundtrack|dialogue|narration)\b/.test(positiveAudioPrompt));
  const imageOnly=/\b(still image|single image|image|poster|illustration|photograph|photo)\b/.test(low)&&!(/\bvideo\b/.test(low)&&/\b(?:insert|use|show|include)\b/.test(low));
  const document=/\b(document|written report|script only|write a script|screenplay)\b/.test(low);
  const deliverable=audioOnly?"audio":imageOnly?"image":document?"document":/\b(scene|project file)\b/.test(low)?"scene":"video";
  const outputFormat=deliverable==="video"?(requestedFormat||"mp4"):deliverable==="audio"?"audio/unknown":"unknown";
  const extension=requestedFormat||"mp4";
  const is3d=/\b(3d|three[- ]dimensional)\b/.test(low);
  const requires3dRig=is3d&&/\b(articulated|rigged|puppet|character|characters|person|people|human|fight|combat|acting|performance)\b/.test(low);
  const is2d=/\b(2d|two[- ]dimensional)\b/.test(low);
  const noText=/\b(without text|no text|text[- ]free|no titles|no words on screen)\b/.test(low);
  const captionsOff=/\b(no captions|no subtitles|captions off|subtitles off)\b/.test(low);
  const captionsRequested=/\b(captions|subtitles)\b/.test(low)&&!captionsOff;
  const subject=(/\bbetween\s+two\s+animated characters\b/i.test(p)?"two animated characters":p.match(/\b(?:featuring|about|of|showing)\s+([^,.;]+?)(?=\s+(?:in|under|at|without|with|for|over)\b|[,.;]|$)/i)?.[1]??p).trim();
  const setting=(/\bunderwater\b/i.test(p)?"underwater":p.match(/\b(?:in|under|at|inside|within)\s+(?:the\s+)?([^,.;]+?)(?=\s+(?:without|with|for|over|while)\b|[,.;]|$)/i)?.[1]??"").trim();
  const actions=[...new Set((low.match(/\b(?:talking|fighting|sword fight|running|dancing|transforming|exploring|floating|swimming|growing|falling|walking|explaining)\b/g)??[]))];
  const graphicIntent=/\b(motion graphic|geometric|shape animation|kinetic typography)\b/i.test(p);
  const abstractGeometry=/\b(circle|square|triangle|shape|geometry|geometric|signal|pattern|line|cycle|orbit)\b/i.test(p);
  const audioRequested=/\b(dialogue|talking|spoken|narration|voice|soundtrack|music|song|audio)\b/i.test(positiveAudioPrompt);
  const assetConstraints=p.split(/[,;.]/).map(s=>s.trim()).filter(s=>/\b(reference|attached|asset|identity|canon|same character|continuity|match|keep .*same)\b/i.test(s));
  const unsupportedReason=deliverable==="audio"||audioRequested?"No authorized audio production adapter is verified; audio cannot be silently replaced with a silent video.":deliverable==="image"?"No authorized still-image production adapter is verified.":deliverable==="document"?"No document production adapter is configured.":captionsRequested?"Captions/subtitles were requested but the local adapter does not implement caption tracks.":requestedFormat&&requestedFormat!=="mp4"?`Requested ${requestedFormat} format is not supported by the local renderer.`:assetConstraints.length?"The brief has asset, identity or continuity constraints, but no authorized source asset was supplied to this adapter.":requires3dRig?"Explicit 3D character performance requires a verified native rig, mesh and performance/contact proof; none is available.":is3d?"A 3D render adapter is not currently verified; this brief cannot be substituted with 2D graphics.":/\b(animated story|story|cinematic|character|characters|jellyfish|underwater|forest|fight|sword)\b/i.test(p)?"The local adapter only produces authored geometric motion graphics; it cannot represent this narrative subject/action truthfully.":!graphicIntent||!abstractGeometry?"The verified adapter only represents abstract geometric motion graphics; this brief does not specify a supported geometric concept.":"";
  const caps=(id:string)=>capabilities.find(c=>c.id===id)?.state==="VERIFIED";
  const supported=deliverable==="video"&&!is3d&&!unsupportedReason&&caps("local.ffmpeg")&&caps("local.rasterizer")&&duration>=1&&duration<=30&&aspectRatio==="16:9";
  const reason=supported?"Local authored geometric motion graphics can execute this constrained visual brief.":unsupportedReason||(!dur?"Duration was not specified; provide a duration before production.":duration>30?"The verified local motion-graphics adapter supports at most 30 seconds.":aspectRatio!=="16:9"?"The verified local adapter supports 16:9 output only.":"Required local FFmpeg/rasterizer capability is not verified.");
  const status=supported?"READY":unsupportedReason?"BLOCKED":!dur?"NEEDS_CLARIFICATION":"BLOCKED";
  const title=noText?undefined:(p.match(/\b(?:titled|title:?)\s+[“\"]?([^”\".]+?)[”\"]?(?:\s|$)/i)?.[1]??undefined);
  const shape=/\bsquare\b/i.test(p)?"square":/\btriangle\b/i.test(p)?"triangle":/\bcircle\b/i.test(p)?"circle":"signal";
  const sourceShape=/\bcircle\b.*\b(?:into|becomes?)\b.*\bsquare\b/i.test(p)?"circle":/\bsquare\b.*\b(?:into|becomes?)\b.*\bcircle\b/i.test(p)?"square":undefined;
  const kind=supported?(/\b(transform|transforming|growing|shrinking)\b/i.test(p)?"shape_transformation":/\brotat(?:e|es|ing|ion)\b/i.test(p)?"shape_rotation":"signal_path"):"none";
  const selected=supported?"motion-graphics":requires3dRig?"articulated-3d":is3d?"3d-render":deliverable==="audio"?"audio-production":deliverable==="image"?"still-image":deliverable==="document"?"document-production":/\b(story|cinematic|character|jellyfish|underwater|forest|fight|sword)\b/i.test(p)?"illustrated-animation":"motion-graphics";
  const beats=supported?[{start:0,end:duration*.35,purpose:"Establish the requested graphic subject",visual_state:`A geometric composition representing ${subject}`},{start:duration*.35,end:duration*.75,purpose:actions[0]??"Develop the visual",visual_state:`${subject}${setting?` in ${setting}`:""} changes through authored geometric motion`},{start:duration*.75,end:duration,purpose:"Resolve the composition",visual_state:`A clear visual resolution for ${subject}`}]:[];
  return {schema_version:"1.1",job_id:`dv_${Date.now().toString(36)}-${Math.random().toString(36).slice(2,10)}`,source_prompt:p,brief:{deliverable_type:deliverable,format:outputFormat,aspect_ratio:aspectRatio,duration_seconds:duration,tone:(p.match(/\b(cinematic|quiet|hopeful|playful|dramatic|documentary|surreal|gentle)\b/i)?.[1]??"unspecified"),exclusions:[...(noText?["no on-screen text"]:[]),...(captionsOff?["no captions","no subtitles"]:[])],captions:captionsRequested?"on":"off"},creative_intent:{subject,setting,actions,purpose:/\b(explain|explainer|teach|story|narrative)\b/i.test(p)?"story or explanatory purpose requested":"unspecified",style:(p.match(/\b(animated|cinematic|minimal|flat|hand-drawn|documentary|3d|2d)\b/i)?.[1]??"unspecified"),audio:audioOnly?`audio only; ${/\btwo people\b/i.test(p)?"two-person":"unspecified-person-count"} dialogue requested`:audioRequested?"audio requested":"not specified",technique:requires3dRig?"3D character performance required":is3d?"3D visual technique requested":is2d?"2D animation required":deliverable==="audio"?"audio production requested":deliverable==="image"?"still-image production requested":/\banimated\b/i.test(p)?"animation requested":"geometric motion graphics",text_policy:noText?"no_text":/\b(title|text|words|typography)\b/i.test(p)?"text_allowed":"unspecified",proof_requirements:requires3dRig?["native articulated rig","mesh identity","performance/contact proof"]:is3d?["native 3D render proof"]:[],requested_constraints:assetConstraints,uncertainties:!dur?["No duration specified; production needs clarification."]:[]},route_decision:{selected,status,alternatives:[],reason,evidence:[...capabilities.filter(c=>c.id.startsWith("local.")).map(c=>`${c.id}: ${c.state}`)]},render_plan:{kind,shape,...(sourceShape?{source_shape:sourceShape}:{}),palette:["#080d15","#76dbc4","#e1f7b7"],fps:24,width:1280,height:720,...(title?{title_text:title}:{})},shots_or_beats:beats,assets:[],execution_plan:supported?[{operation:"render-original-motion-graphic",adapter:"motion-graphics-local",approval:"not_required",timeout_seconds:240}]:[],artifacts:[{role:"master",format:deliverable==="video"?`video/${extension}`:"unknown",path:`outputs/${p.slice(0,24).toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"")||"job"}-${Date.now().toString(36)}/master.${extension}`}],proof:{technical_status:supported?"PENDING":"BLOCKED",artistic_status:"PENDING_HUMAN_REVIEW",evidence:[]}};
}
export function makeJob(prompt:string):CreativeJob { return planCreativeJob(prompt); }
