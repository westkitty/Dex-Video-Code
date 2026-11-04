import { spawnSync } from "node:child_process";
import type { Capability } from "./types.js";
import { planCreativeJob } from "./job.js";

function probe(command: string): { version?: string; found: boolean; reason: string } {
  const r = spawnSync(command, ["-version"], { encoding: "utf8", timeout: 3000 });
  if (r.error) return { found: false, reason: `Not callable: ${r.error.message}` };
  if (r.status !== 0) return { found: false, reason: `Probe exited ${r.status}` };
  return { found: true, version: (r.stdout || r.stderr).split("\n")[0] ?? "version unknown", reason: "Read-only version probe passed." };
}
export function discoverCapabilities(): Capability[] {
  const ffmpeg = probe("ffmpeg");
  const node = process.version;
  const rasterizerCommand = process.platform === "darwin" ? "sips" : "magick";
  const rasterizerProbe = spawnSync(rasterizerCommand, ["--version"], {encoding:"utf8", timeout:3000});
  const rasterizerFound = process.platform === "darwin" ? !rasterizerProbe.error : rasterizerProbe.status === 0;
  return [
    { id:"local.ffmpeg", state:ffmpeg.found?"VERIFIED":"UNAVAILABLE", host:"observed local host", command:"ffmpeg", version:ffmpeg.version, reason:ffmpeg.reason, cost:"none", privacy:"local" },
    { id:"local.rasterizer", state:rasterizerFound?"VERIFIED":"UNAVAILABLE", host:"observed local host", command:rasterizerCommand, version:rasterizerFound?(rasterizerProbe.stdout||rasterizerProbe.stderr).split("\n")[0]:undefined, reason:rasterizerFound?"Read-only frame rasterizer probe passed.":`Frame rasterizer not callable: ${rasterizerProbe.error?.message??"probe failed"}`, cost:"none", privacy:"local" },
    { id:"local.node", state:"VERIFIED", host:"observed local host", command:"node", version:node, reason:"Current process runtime.", cost:"none", privacy:"local" },
    { id:"remotion", state:"AVAILABLE_UNPROVEN", host:"not probed", reason:"Repository source lead only; no installed runnable project was established for this coordinator.", cost:"unknown", privacy:"local" },
    { id:"hyperframes", state:"AVAILABLE_UNPROVEN", host:"remote host not invoked by local doctor", reason:"Historical Big Mac proof exists; this local probe did not validate the live worker.", cost:"unknown", privacy:"local" },
    { id:"code-video-blender", state:"DORMANT", host:"specialist route", reason:"3D-only route; never required by ordinary motion design.", cost:"unknown", privacy:"local" },
    { id:"manual-art-import", state:"AVAILABLE_UNPROVEN", host:"operator", reason:"Manual authorized asset handoff; no asset imported for this probe.", cost:"none", privacy:"manual" },
    { id:"comfyui", state:"EXCLUDED", host:"none", reason:"Explicitly excluded by product contract.", cost:"none", privacy:"local" }
  ];
}
export function planRoutes(prompt: string, capabilities = discoverCapabilities()): { selected: string; alternatives: string[]; rationale: string; requires3dRig: boolean; routes: Array<{id:string;score:number;selected:boolean;requires3dRig:boolean;available:boolean;rationale:string}> } {
  const job=planCreativeJob(prompt,capabilities);const id=job.route_decision.selected;const requires3dRig=job.creative_intent.proof_requirements.includes("native articulated rig");const route={id,score:100,selected:true,requires3dRig,available:job.route_decision.status==="READY",rationale:job.route_decision.reason};
  return {selected:id,alternatives:[],rationale:job.route_decision.reason,requires3dRig,routes:[route]};
}
