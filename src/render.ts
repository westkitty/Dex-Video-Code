import { mkdir, writeFile, link, unlink, readFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import { createHash, randomUUID } from "node:crypto";
import type { CreativeJob } from "./types.js";
import { safeRelative } from "./job.js";
import { assertNoSymlinks, ensureDirectoriesNoSymlink } from "./paths.js";
import { circleSquareContour } from "./morph.js";
export { assertNoSymlinks } from "./paths.js";
const xml=(s:string)=>s.replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&apos;"}[c]!));
export function frameSvg(job:CreativeJob,frame:number):string {
  const {width:W,height:H,palette}=job.render_plan; const [bg,accent,highlight]=palette;
  const t=frame/job.render_plan.fps, duration=job.brief.duration_seconds, progress=Math.min(1,t/duration);
  const x=(W*(.18+.64*progress)).toFixed(1), y=(H*(.56-.26*Math.sin(progress*Math.PI))).toFixed(1);
  const unit=Math.min(W,H);const size=Math.round(unit*(.04+.12*progress));
  const shapeMarkup=(shape:"circle"|"square"|"triangle"|"signal",fill:string,stroke:string,opacity:number,rotation:number,scale:number)=>{
    const common=`fill="${fill}" stroke="${stroke}" stroke-width="5" opacity="${opacity.toFixed(3)}" transform="translate(${x} ${y}) rotate(${rotation.toFixed(1)}) scale(${scale.toFixed(3)})"`;
    if(shape==="circle")return `<circle cx="0" cy="0" r="${Math.round(size/2)}" ${common}/>`;
    if(shape==="square")return `<rect x="${-size/2}" y="${-size/2}" width="${size}" height="${size}" ${common}/>`;
    if(shape==="triangle")return `<polygon points="0,${-size/2} ${size/2},${size/2} ${-size/2},${size/2}" ${common}/>`;
    return `<circle cx="0" cy="0" r="${Math.max(3,Math.round(size/5))}" ${common}/>`;
  };
  let geometry:string;
  if(job.render_plan.shape_transform_mode==="continuous_circle_square_v1"){
    const contour=circleSquareContour(t,W,H,duration);
    geometry=`<path d="${contour.path}" fill="none" stroke="url(#morph-edge)" stroke-width="5" stroke-linejoin="miter" stroke-miterlimit="2"/>`;
  }else if(job.render_plan.kind==="shape_transformation"){
    const from=job.render_plan.source_shape??job.render_plan.shape;const to=job.render_plan.shape;const scale=Math.max(.2,Math.min(1.4,.45+progress));
    geometry=from===to?shapeMarkup(to,"none",accent,1,0,scale):shapeMarkup(from,"none",accent,1-progress,0,1)+shapeMarkup(to,"none",highlight,progress,progress*15,1);
  }else if(job.render_plan.kind==="shape_rotation"){
    geometry=shapeMarkup(job.render_plan.shape,"none",highlight,1,progress*360,1);
  }else{
    const trail=job.render_plan.shape==="signal"?`<path d="M ${W*.15} ${H*.62} Q ${W*.44} ${H*.85} ${x} ${y}" fill="none" stroke="${accent}" stroke-width="4"/>`:"";
    geometry=trail+shapeMarkup(job.render_plan.shape,job.render_plan.shape==="signal"?highlight:"none",accent,1,0,1);
  }
  const title=job.render_plan.title_text&&!job.creative_intent.text_policy.toString().includes("no_text")?`<text x="${W*.08}" y="${H*.18}" fill="${highlight}" font-family="Arial,sans-serif" font-size="${Math.round(H*.06)}">${xml(job.render_plan.title_text)}</text>`:"";
  const morphDefs=job.render_plan.shape_transform_mode==="continuous_circle_square_v1"?`<defs><radialGradient id="morph-background"><stop offset="0%" stop-color="#101c27"/><stop offset="100%" stop-color="${bg}"/></radialGradient><linearGradient id="morph-edge" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="${accent}"/><stop offset="100%" stop-color="${highlight}"/></linearGradient></defs>`:"";
  const background=job.render_plan.shape_transform_mode==="continuous_circle_square_v1"?`<rect width="${W}" height="${H}" fill="url(#morph-background)"/>`:`<rect width="${W}" height="${H}" fill="${bg}"/>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${xml(job.creative_intent.subject)}">${morphDefs}${background}${title}${geometry}</svg>`;
}
function run(command:string,args:string,timeout:number,onPid?:(pid:number|null)=>Promise<void>):Promise<void>{return new Promise((resolve,reject)=>{const p=spawn(command,args.split("\u0000"),{stdio:"ignore"});const timer=setTimeout(()=>{p.kill("SIGTERM");setTimeout(()=>p.kill("SIGKILL"),3000);},timeout);void onPid?.(p.pid??null);p.on("error",e=>{clearTimeout(timer);reject(e)});p.on("close",async code=>{clearTimeout(timer);await onPid?.(null);code===0?resolve():reject(new Error(`${command} exited ${code??"without status"}`));});});}
export async function finalizeNoClobber(temp:string,final:string):Promise<void>{await link(temp,final);await unlink(temp);}
export async function renderMotionGraphic(job:CreativeJob, root:string, onEncoderPid?:(pid:number|null)=>Promise<void>):Promise<{path:string;sha256:string;bytes:number;frames:number;duration:number}> {
  if(job.route_decision.status!=="READY"||job.route_decision.selected!=="motion-graphics")throw new Error("Only a READY motion-graphics plan can be rendered.");
  if(job.render_plan.kind==="none"||job.brief.captions!=="off"||job.brief.format!=="mp4")throw new Error("Plan does not match the local motion-graphics adapter.");
  if(job.render_plan.width!==1280||job.render_plan.height!==720||job.render_plan.fps!==24||job.brief.duration_seconds<1||job.brief.duration_seconds>30)throw new Error("Local adapter supports 1280x720, 24 fps and 1–30 seconds.");
  const [ratioW,ratioH]=job.brief.aspect_ratio.split(":").map(Number);if(!Number.isFinite(ratioW/ratioH)||Math.abs(ratioW/ratioH-job.render_plan.width/job.render_plan.height)>.01)throw new Error("Brief aspect ratio does not match the local renderer dimensions.");
  const outRel=safeRelative(job.artifacts[0]?.path??"");if(!outRel.endsWith(".mp4"))throw new Error("Expected declared MP4 output path.");
  const output=path.resolve(root,outRel);if(!output.startsWith(path.resolve(root)+path.sep))throw new Error("Output path escapes job root.");
  const parent=path.dirname(outRel);await ensureDirectoriesNoSymlink(root,parent==="."?"":parent);await assertNoSymlinks(root,outRel);
  const frameDir=path.join(path.dirname(output),`.frames-${randomUUID()}`);await mkdir(frameDir,{recursive:false});
  const temp=path.join(path.dirname(output),`.${path.basename(output)}.${randomUUID()}.tmp.mp4`);
  const total=job.brief.duration_seconds*job.render_plan.fps;
  try {
    for(let i=0;i<total;i++)await writeFile(path.join(frameDir,`frame-${String(i).padStart(5,"0")}.svg`),frameSvg(job,i),{flag:"wx"});
    const raster=process.platform==="darwin"?"sips":"magick";
    const convert=async(i:number)=>{const src=path.join(frameDir,`frame-${String(i).padStart(5,"0")}.svg`),dst=path.join(frameDir,`frame-${String(i).padStart(5,"0")}.png`);if(process.platform==="darwin")await run(raster,`-s\u0000format\u0000png\u0000${src}\u0000--out\u0000${dst}`,15000);else await run(raster,`${src}\u0000${dst}`,15000);};
    for(let i=0;i<total;i++)await convert(i);
    await run("ffmpeg",`-hide_banner\u0000-loglevel\u0000error\u0000-nostdin\u0000-framerate\u0000${job.render_plan.fps}\u0000-i\u0000${path.join(frameDir,"frame-%05d.png")}\u0000-t\u0000${job.brief.duration_seconds}\u0000-an\u0000-c:v\u0000libx264\u0000-preset\u0000ultrafast\u0000-crf\u000019\u0000-pix_fmt\u0000yuv420p\u0000-movflags\u0000+faststart\u0000${temp}`,240000,onEncoderPid);
    await finalizeNoClobber(temp,output);
    const bytes=await readFile(output);return {path:outRel,sha256:createHash("sha256").update(bytes).digest("hex"),bytes:bytes.length,frames:total,duration:job.brief.duration_seconds};
  } finally {
    await unlink(temp).catch(()=>{});const {rm}=await import("node:fs/promises");await rm(frameDir,{recursive:true,force:true});
  }
}
