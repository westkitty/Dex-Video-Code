import { mkdir, writeFile, access } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import { createHash } from "node:crypto";
import { lstat, readFile } from "node:fs/promises";
import type { CreativeJob } from "./types.js";
const W=1280,H=720,FPS=24;
function frameSvg(i:number,total:number):string {
 const t=i/FPS;
 const ease=(x:number)=>x*x*(3-2*x);
 const pulse=Math.sin(t*2.2)*0.5+0.5;
 const cx=300+680*ease(Math.min(1,t/11)); const cy=390-210*Math.sin(Math.PI*Math.min(1,t/11));
 const reveal=(a:number,b:number)=>Math.max(0,Math.min(1,(t-a)/(b-a)));
 const subtitleOpacity=reveal(3,4)*(1-reveal(10.3,11.2));
 const titleA=reveal(0.5,1.2), titleB=reveal(4.2,5.0), titleC=reveal(10.7,11.8);
 const line=(t>2.2)?`<path d="M 300 390 Q 510 590 620 310 T ${cx.toFixed(1)} ${cy.toFixed(1)}" fill="none" stroke="#82e6cf" stroke-width="3" stroke-opacity="${(0.25+0.45*pulse).toFixed(2)}"/>`:"";
 const circles=[0,1,2,3].map(k=>{const r=55+k*44+12*pulse;return `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r.toFixed(1)}" fill="none" stroke="#82e6cf" stroke-width="1" stroke-opacity="${(0.21-k*0.035).toFixed(2)}"/>`;}).join("");
 const glow=`<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${(22+8*pulse).toFixed(1)}" fill="#a6ffe8" opacity="0.13"/><circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="8" fill="#d3fff3"/>`;
 const opacity=(n:number)=>Math.max(0,Math.min(1,n)).toFixed(3);
 return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><defs><radialGradient id="bg"><stop stop-color="#172b34"/><stop offset="1" stop-color="#080d15"/></radialGradient><linearGradient id="accent"><stop stop-color="#76dbc4"/><stop offset="1" stop-color="#e1f7b7"/></linearGradient></defs><rect width="1280" height="720" fill="url(#bg)"/><path d="M0 570H1280" stroke="#ffffff" stroke-opacity=".07"/><text x="92" y="92" fill="#9db9bc" font-family="Arial,sans-serif" font-size="16" letter-spacing="4">FIELD NOTE 01 · SIGNAL</text><text x="92" y="178" fill="#f2f4ed" font-family="Arial,sans-serif" font-size="53" font-weight="600" opacity="${opacity(titleA)}">Somewhere, a signal</text><text x="92" y="239" fill="#f2f4ed" font-family="Arial,sans-serif" font-size="53" font-weight="600" opacity="${opacity(titleB)}">is looking for a way through.</text>${line}${circles}${glow}<text x="92" y="632" fill="#b4c5c3" font-family="Arial,sans-serif" font-size="20" opacity="${opacity(subtitleOpacity)}">A quiet pattern becomes a path.</text><g opacity="${opacity(titleC)}"><rect x="92" y="580" width="1096" height="1" fill="url(#accent)"/><text x="92" y="638" fill="#e1f7b7" font-family="Arial,sans-serif" font-size="28" letter-spacing="5">FOUND · AND ANSWERED</text><text x="1188" y="638" fill="#9db9bc" font-family="Arial,sans-serif" font-size="15" text-anchor="end">${String(i+1).padStart(3,"0")} / ${total}</text></g></svg>`;
}
export async function assertNoSymlinks(root:string, relative:string):Promise<void>{
 let current=path.resolve(root); const boundary=path.resolve(root);
 for(const part of relative.split("/")){ current=path.join(current,part); try{const st=await lstat(current);if(st.isSymbolicLink())throw new Error(`Refusing symlink in output path: ${part}`);if(!current.startsWith(boundary+path.sep))throw new Error("Output path escapes job root.");}catch(e){if((e as NodeJS.ErrnoException).code==="ENOENT")continue;throw e;} }
}
export async function renderMotionGraphic(job:CreativeJob, root:string, onEncoderPid?:(pid:number|null)=>Promise<void>):Promise<{path:string;sha256:string;bytes:number;frames:number;duration:number}> {
 if(job.route_decision.selected!=="motion-graphics") throw new Error(`No production adapter for selected route ${job.route_decision.selected}`);
 if(job.brief.captions!=="off") throw new Error("This adapter only supports captions off.");
 const outRel=job.artifacts[0]?.path;
 if(!outRel||!outRel.endsWith(".mp4")) throw new Error("Expected declared MP4 output path.");
 const output=path.resolve(root,outRel); if(!output.startsWith(path.resolve(root)+path.sep)) throw new Error("Output path escapes job root."); await assertNoSymlinks(root,outRel);
 await access(output).then(()=>{throw new Error(`Refusing to overwrite existing output: ${outRel}`)}).catch(e=>{if((e as NodeJS.ErrnoException).code!=="ENOENT") throw e;});
 const frameDir=path.join(path.dirname(output),"frames-svg"); const pngDir=path.join(path.dirname(output),"frames-png"); await assertNoSymlinks(root,path.relative(root,frameDir)); await assertNoSymlinks(root,path.relative(root,pngDir)); await mkdir(frameDir,{recursive:true}); await mkdir(pngDir,{recursive:true}); await mkdir(path.dirname(output),{recursive:true});
 const duration=job.brief.duration_seconds; if(duration<15||duration>30) throw new Error("Pilot A adapter accepts 15–30 second durations only.");
 const frames=duration*FPS;
 for(let i=0;i<frames;i++) await writeFile(path.join(frameDir,`frame-${String(i).padStart(5,"0")}.svg`),frameSvg(i,frames));
 const convert=(input:string,outputPng:string)=>new Promise<void>((resolve,reject)=>{const command=process.platform==="darwin"?"/usr/bin/sips":"magick";const args=process.platform==="darwin"?["-s","format","png",input,"--out",outputPng]:[input,outputPng];const p=spawn(command,args,{stdio:"ignore"});const timer=setTimeout(()=>{p.kill("SIGTERM");reject(new Error("Frame rasterization exceeded 15 second timeout"));},15000);p.on("error",e=>{clearTimeout(timer);reject(e)});p.on("close",code=>{clearTimeout(timer);code===0?resolve():reject(new Error(`Frame rasterizer exited ${code}`));});});
 let next=0; const workers=Array.from({length:3},async()=>{while(true){const i=next++;if(i>=frames)return;await convert(path.join(frameDir,`frame-${String(i).padStart(5,"0")}.svg`),path.join(pngDir,`frame-${String(i).padStart(5,"0")}.png`));}});await Promise.all(workers);
 await new Promise<void>((resolve,reject)=>{const p=spawn("ffmpeg",["-hide_banner","-loglevel","error","-y","-framerate",String(FPS),"-i",path.join(pngDir,"frame-%05d.png"),"-t",String(duration),"-an","-c:v","libx264","-preset","ultrafast","-crf","19","-pix_fmt","yuv420p","-movflags","+faststart",output],{stdio:"ignore"});const timer=setTimeout(()=>{p.kill("SIGTERM");reject(new Error("FFmpeg render exceeded 240 second timeout"));},240000);p.on("error",e=>{clearTimeout(timer);reject(e)});void onEncoderPid?.(p.pid??null);p.on("close",async code=>{clearTimeout(timer);await onEncoderPid?.(null);code===0?resolve():reject(new Error(`FFmpeg exited ${code}`));});});
 const bytes=await readFile(output); return {path:outRel,sha256:createHash("sha256").update(bytes).digest("hex"),bytes:bytes.length,frames,duration};
}
