import { spawnSync } from "node:child_process";
import type { Capability } from "./types.js";

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
export function planRoutes(prompt: string, capabilities = discoverCapabilities()): { selected: string; alternatives: string[]; rationale: string; requires3dRig: boolean; routes: ReturnType<typeof routesFor> } {
  const p = prompt.toLowerCase();
  const explicit3d = /\b(articulated 3d|genuine(?:ly)? 3d acting|rigged 3d|3d puppet|blender rig)\b/.test(p);
  const routes = routesFor(explicit3d, capabilities);
  const eligible = routes.filter(r => r.available && r.id !== "comfyui");
  const winner = explicit3d ? routes[0]! : (eligible[0] ?? routes.find(r => r.id === "motion-graphics")!);
  return { selected:winner.id, alternatives:routes.filter(r => r.id !== winner.id && r.id !== "comfyui").map(r=>r.id), rationale:winner.rationale, requires3dRig:winner.requires3dRig, routes };
}
function routesFor(explicit3d: boolean, caps: Capability[]) {
  const ffmpeg = caps.find(c=>c.id==="local.ffmpeg")?.state === "VERIFIED";
  const rasterizer = caps.find(c=>c.id==="local.rasterizer")?.state === "VERIFIED";
  return explicit3d ? [
    {id:"articulated-3d",score:100,selected:true,requires3dRig:true,available:false,rationale:"The brief explicitly requires articulated 3D performance; the specialist rig and contact proof are mandatory, and no live Blender adapter is enabled."},
    {id:"motion-graphics",score:10,selected:false,requires3dRig:false,available:ffmpeg && rasterizer,rationale:"Available fallback would violate the explicit performance requirement."}
  ] : [
    {id:"motion-graphics",score:90,selected:true,requires3dRig:false,available:ffmpeg && rasterizer,rationale:"Authored kinetic typography and shape animation fit an information-led graphic brief; local FFmpeg is verified and no character rig is needed."},
    {id:"illustrated-2.5d",score:65,selected:false,requires3dRig:false,available:false,rationale:"Suitable when approved source artwork exists; this job has no supplied art."},
    {id:"articulated-3d",score:30,selected:false,requires3dRig:true,available:false,rationale:"Unnecessary for this graphic brief; live native rig/render adapter is not established."},
    {id:"comfyui",score:0,selected:false,requires3dRig:false,available:false,rationale:"Excluded by policy."}
  ];
}
