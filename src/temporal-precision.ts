/** A separately admitted, narrow temporal edit. Never elevates a CreativeJob route. */
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { link, mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { assertNoSymlinks } from "./paths.js";
import { safeRelative } from "./job.js";

export type TemporalPrecisionContract = {
  schema_version: "temporal-precision.v1";
  source: { path: string; sha256: string; rights: "authorized" };
  alignment: {
    source_sha256: string;
    method: "forced_alignment";
    engine: string;
    evidence: string;
    words: { text: string; start_seconds: number; end_seconds: number }[];
  };
  timing: { fps_numerator: number; fps_denominator: number; duration_frames: number };
  edit: {
    trigger: { kind: "spoken_word_end"; literal: string; occurrence: number };
    operation: "high_contrast_lighting";
    allowed: ("luminance" | "contrast")[];
    protected: ("audio" | "geometry" | "identity" | "camera" | "framing" | "timing")[];
    transition_frames: 0;
  };
  output_path: string;
  captions: "off";
};
export type TemporalResolution =
  | { state: "READY"; trigger_end_seconds: number; first_edited_frame: number; word: string; evidence: string }
  | { state: "HOLD"; reasons: string[] };

const shaPattern = /^[a-f0-9]{64}$/;
const protections = ["audio", "geometry", "identity", "camera", "framing", "timing"];
const exactKeys = (v: unknown, keys: string[]): boolean => !!v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).sort().join("|") === [...keys].sort().join("|");
const object = (v: unknown): Record<string, any> => v && typeof v === "object" && !Array.isArray(v) ? v as Record<string, any> : {};
const integer = (v: unknown, min: number, max: number) => Number.isSafeInteger(v) && (v as number) >= min && (v as number) <= max;
const finite = (v: unknown) => typeof v === "number" && Number.isFinite(v);
const simple = (v: unknown) => typeof v === "string" && v.length > 0 && v.length <= 512 && !/[\r\n\x00]/.test(v);
const wordKey = (v: string) => v.normalize("NFKC").toLocaleLowerCase("en-US").replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");

/** Resolve from source-bound word alignment, never from the user's guessed timestamp. */
export function resolveTemporalPrecision(value: unknown): TemporalResolution {
  const c = object(value), s = object(c.source), a = object(c.alignment), t = object(c.timing), e = object(c.edit), tr = object(e.trigger);
  const reasons: string[] = [];
  if (!exactKeys(c,["schema_version","source","alignment","timing","edit","output_path","captions"]) || c.schema_version !== "temporal-precision.v1") reasons.push("Unsupported temporal contract schema/fields");
  if (!exactKeys(s,["path","sha256","rights"]) || !simple(s.path) || !shaPattern.test(s.sha256) || s.rights !== "authorized") reasons.push("Invalid source identity or rights");
  if (!exactKeys(a,["source_sha256","method","engine","evidence","words"]) || a.source_sha256 !== s.sha256 || a.method !== "forced_alignment" || !simple(a.engine) || !simple(a.evidence) || !Array.isArray(a.words) || a.words.length < 1 || a.words.length > 10000) reasons.push("Missing source-bound forced alignment evidence");
  if (!exactKeys(t,["fps_numerator","fps_denominator","duration_frames"]) || !integer(t.fps_numerator,1,120000) || !integer(t.fps_denominator,1,1001) || !integer(t.duration_frames,1,3600)) reasons.push("Invalid frame timebase/duration");
  if (!exactKeys(e,["trigger","operation","allowed","protected","transition_frames"]) || e.operation !== "high_contrast_lighting" || e.transition_frames !== 0 || !Array.isArray(e.allowed) || e.allowed.length !== 2 || !["luminance","contrast"].every(x=>e.allowed.includes(x)) || !Array.isArray(e.protected) || e.protected.length !== protections.length || !protections.every(x=>e.protected.includes(x))) reasons.push("Edit exceeds locked lighting-only properties");
  if (!exactKeys(tr,["kind","literal","occurrence"]) || tr.kind !== "spoken_word_end" || !simple(tr.literal) || !wordKey(String(tr.literal ?? "")) || !integer(tr.occurrence,1,10000)) reasons.push("Invalid spoken-word trigger");
  if (c.captions !== "off") reasons.push("Captions must be off");
  try { safeRelative(s.path); safeRelative(c.output_path); if (s.path === c.output_path) reasons.push("Source cannot equal output"); } catch { reasons.push("Source/output path is not safely relative"); }
  const fps = t.fps_numerator / t.fps_denominator;
  if (Number.isFinite(fps) && (fps < 1 || fps > 120 || t.duration_frames/fps > 30)) reasons.push("Temporal adapter is limited to 30 seconds at 1-120 fps");
  let lastEnd = -1;
  const matches: {text:string;start_seconds:number;end_seconds:number}[] = [];
  for (const w of Array.isArray(a.words) ? a.words : []) {
    if (!exactKeys(w,["text","start_seconds","end_seconds"]) || !simple(w.text) || !finite(w.start_seconds) || !finite(w.end_seconds) || w.start_seconds < 0 || w.end_seconds <= w.start_seconds || w.start_seconds < lastEnd - 1e-6 || w.end_seconds > t.duration_frames/fps + 1e-3) { reasons.push("Invalid/overlapping alignment word timings"); break; }
    lastEnd=w.end_seconds;
    if (wordKey(w.text) === wordKey(String(tr.literal ?? ""))) matches.push(w);
  }
  if (!reasons.length && matches.length < tr.occurrence) reasons.push("Requested spoken-word occurrence not present in evidence");
  if (reasons.length) return {state:"HOLD",reasons:[...new Set(reasons)]};
  const selected=matches[tr.occurrence-1]!;
  const frame=Math.ceil(selected.end_seconds * fps - 1e-9);
  if (!integer(frame,0,t.duration_frames-1)) return {state:"HOLD",reasons:["Spoken-word completion occurs outside editable frames"]};
  return {state:"READY",trigger_end_seconds:selected.end_seconds,first_edited_frame:frame,word:selected.text,evidence:a.evidence};
}

async function fileSha256(file:string):Promise<string> {
  const h=createHash("sha256");for await (const chunk of createReadStream(file))h.update(chunk);return h.digest("hex");
}
function command(bin:string,args:string[],maxMs=30000):string {
  const r=spawnSync(bin,args,{encoding:"utf8",timeout:maxMs,maxBuffer:4*1024*1024});
  if(r.error||r.status!==0)throw new Error(`${bin} failed: ${String(r.error??r.stderr).slice(0,800)}`);
  return r.stdout;
}
type Stream = {codec_type:string;codec_name:string;width?:number;height?:number;r_frame_rate?:string;avg_frame_rate?:string;nb_read_frames?:string};
function probe(file:string):{streams:Stream[];format:{duration?:string;format_name?:string}}{
  return JSON.parse(command("ffprobe",["-v","error","-count_frames","-show_entries","stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,nb_read_frames:format=duration,format_name","-of","json",file],30000));
}
function audioHash(file:string):string {
  const result=command("ffmpeg",["-nostdin","-v","error","-i",file,"-map","0:a:0","-vn","-c:a","pcm_s16le","-f","hash","-hash","SHA256","-"],30000);
  const match=result.match(/SHA256=([a-f0-9]{64})/i);if(!match)throw new Error("Could not hash decoded audio");return match[1]!.toLowerCase();
}
/** Explicit subcommand: separate from CreativeJob production and never dispatches its renderer. */
export async function runTemporalPrecision(root:string,args:string[]):Promise<unknown> {
  const mode=args[0],index=args.indexOf("--contract"),contractName=index>=0?args[index+1]:undefined;
  if(!["resolve","apply"].includes(mode) || !contractName)throw new Error("Usage: director temporal resolve|apply --contract <relative.json>");
  const contractRel=safeRelative(contractName);
  await assertNoSymlinks(root,contractRel);
  const contract=JSON.parse(await readFile(path.join(root,contractRel),"utf8"));
  const result=resolveTemporalPrecision(contract);
  if(mode==="resolve")return result;
  if(result.state!=="READY")throw new Error(`Temporal edit HOLD: ${result.reasons.join("; ")}`);
  const c=contract as TemporalPrecisionContract;
  const input=path.resolve(root,safeRelative(c.source.path)),output=path.resolve(root,safeRelative(c.output_path));
  await assertNoSymlinks(root,c.source.path);await assertNoSymlinks(root,c.output_path);
  if(input===output)throw new Error("Cannot overwrite source");
  if(!input.toLowerCase().endsWith(".mp4") || !output.toLowerCase().endsWith(".mp4"))throw new Error("Temporal adapter requires MP4 paths");
  if((await stat(input)).size<100)throw new Error("Source is empty or invalid");
  if(await fileSha256(input)!==c.source.sha256)throw new Error("Source SHA-256 differs from alignment-bound contract");
  const before=probe(input),vs=before.streams.filter(s=>s.codec_type==="video"),as=before.streams.filter(s=>s.codec_type==="audio");
  if(before.streams.length!==2 || vs.length!==1 || as.length!==1 || vs[0]!.codec_name!=="h264" || !["aac"].includes(as[0]!.codec_name) || !before.format.format_name?.includes("mp4"))throw new Error("Only source MP4 with one H.264 video and one AAC audio stream is admitted");
  const fps=`${c.timing.fps_numerator}/${c.timing.fps_denominator}`;
  if(vs[0]!.r_frame_rate!==fps || vs[0]!.avg_frame_rate!==fps || Number(vs[0]!.nb_read_frames)!==c.timing.duration_frames)throw new Error("Source frame count or CFR timebase disagrees with contract");
  const originalAudio=audioHash(input);
  const tempDir=await mkdtemp(path.join(path.dirname(output),".temporal-"));
  const temp=path.join(tempDir,"candidate.mp4");
  try {
    // Frame-indexed enable avoids rounding at timestamp boundaries. No scaling,
    // cropping, overlays, audio filters, text, or subtitle mapping is allowed.
    const filter=`eq=contrast=1.75:brightness=0.02:enable='gte(n\\,${result.first_edited_frame})'`;
    command("ffmpeg",["-nostdin","-hide_banner","-loglevel","error","-i",input,"-map","0:v:0","-map","0:a:0","-vf",filter,"-c:v","libx264","-preset","medium","-crf","18","-bf","0","-pix_fmt","yuv420p","-c:a","copy","-sn","-dn","-movflags","+faststart","-f","mp4",temp],60000);
    const after=probe(temp),outV=after.streams.filter(s=>s.codec_type==="video");
    if(after.streams.length!==2 || outV.length!==1 || after.streams.filter(s=>s.codec_type==="audio").length!==1 || outV[0]!.r_frame_rate!==fps || outV[0]!.avg_frame_rate!==fps || Number(outV[0]!.nb_read_frames)!==c.timing.duration_frames || outV[0]!.width!==vs[0]!.width || outV[0]!.height!==vs[0]!.height)throw new Error("Output frame, geometry or stream verification failed");
    if(audioHash(temp)!==originalAudio)throw new Error("Decoded audio differs; output rejected");
    command("ffmpeg",["-nostdin","-v","error","-i",temp,"-f","null","-"],30000);
    if(await fileSha256(input)!==c.source.sha256)throw new Error("Source changed during production");
    await link(temp,output); // create-if-absent; never replace output
    return {state:"TECHNICAL_PASS_VISUAL_PENDING",source_sha256:c.source.sha256,output_sha256:await fileSha256(output),first_edited_frame:result.first_edited_frame,trigger_end_seconds:result.trigger_end_seconds,audio_decoded_sha256:originalAudio,visual_review:"PENDING_HUMAN_REVIEW",speech_alignment:"EXTERNAL_CLAIM_NOT_INDEPENDENTLY_VERIFIED",note:"Exact frame filter and decoded audio verified. External forced alignment is source-bound metadata, not independently verified speech recognition; identity, scene geometry and camera require human visual review"};
  } finally {await rm(tempDir,{recursive:true,force:true});}
}
