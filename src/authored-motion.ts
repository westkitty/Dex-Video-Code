export type Easing = "linear"|"smooth"|"cubic-out"|"cubic-in-out"|"anticipate"|"settle";
export interface MotionKeyframe {
  at:number; x?:number; y?:number; scale?:number; rotation?:number;
  opacity?:number; reveal?:number; easing?:Easing;
}
export interface MotionElement {
  id:string; layer:number; geometry:"circle"|"rect"|"path";
  x?:number; y?:number; radius?:number; width?:number; height?:number; corner_radius?:number;
  path?:string; fill?:string; stroke?:string; stroke_width?:number; glow?:boolean;
}
export interface MotionBeat {id:string;start:number;end:number;purpose:string;visual_state:string;}
export interface AuthoredMotionScene {
  schema_version:"authored-motion.v1"; title:string; duration_seconds:number;
  width:1280;height:720;fps:24;background:string;
  visual_sample_times:number[];
  beats:MotionBeat[];elements:MotionElement[];
  tracks:Array<{element_id:string;keyframes:MotionKeyframe[]}>;
  camera?:{keyframes:MotionKeyframe[]};
}

const easings=new Set<Easing>(["linear","smooth","cubic-out","cubic-in-out","anticipate","settle"]);
const color=/^#[0-9a-fA-F]{6}$/;
const ids=/^[a-z][a-z0-9_-]{0,47}$/;
function finite(n:unknown):n is number{return typeof n==="number"&&Number.isFinite(n);}
function validateKeyframes(value:unknown,duration:number,label:string):asserts value is MotionKeyframe[]{
  if(!Array.isArray(value)||value.length<2||value.length>64)throw new Error(`${label} needs 2–64 keyframes.`);
  let previous=-1;
  for(const frame of value){
    if(!frame||typeof frame!=="object"||!finite(frame.at)||frame.at<0||frame.at>duration||frame.at<=previous)throw new Error(`${label} keyframe times must increase within the scene duration.`);
    previous=frame.at;
    for(const key of ["x","y","scale","rotation","opacity","reveal"] as const){const n=frame[key];if(n!==undefined&&!finite(n))throw new Error(`${label} ${key} values must be finite.`);}
    if(frame.x!==undefined&&(frame.x < -1280||frame.x>2560)||frame.y!==undefined&&(frame.y < -720||frame.y>1440))throw new Error(`${label} position is outside the safe authored range.`);
    if(frame.scale!==undefined&&(frame.scale<0||frame.scale>4))throw new Error(`${label} scale must be between 0 and 4.`);
    if(frame.rotation!==undefined&&Math.abs(frame.rotation)>720)throw new Error(`${label} rotation exceeds the safe range.`);
    if(frame.opacity!==undefined&&(frame.opacity<0||frame.opacity>1)||frame.reveal!==undefined&&(frame.reveal<0||frame.reveal>1))throw new Error(`${label} opacity and reveal must be between 0 and 1.`);
    if(frame.easing!==undefined&&!easings.has(frame.easing))throw new Error(`${label} uses an unsupported easing.`);
  }
  if(value[0]!.at!==0||value[value.length-1]!.at!==duration)throw new Error(`${label} must define the full scene timeline from 0 to its end.`);
}

export function validateAuthoredMotionScene(value:unknown):asserts value is AuthoredMotionScene{
  if(!value||typeof value!=="object")throw new Error("Authored motion scene must be an object.");
  const scene=value as AuthoredMotionScene;
  if(scene.schema_version!=="authored-motion.v1"||typeof scene.title!=="string"||scene.title.length<1||scene.title.length>100)throw new Error("Unsupported or invalid authored-motion scene header.");
  if(!finite(scene.duration_seconds)||scene.duration_seconds<1||scene.duration_seconds>30||scene.width!==1280||scene.height!==720||scene.fps!==24||!color.test(scene.background))throw new Error("Authored motion scenes require 1–30 seconds, 1280x720, 24 fps and a six-digit background color.");
  if(!Array.isArray(scene.visual_sample_times)||scene.visual_sample_times.length<3||scene.visual_sample_times.length>24||scene.visual_sample_times.some((t,i)=>!finite(t)||t<0||t>=scene.duration_seconds||i>0&&t<=scene.visual_sample_times[i-1]!))throw new Error("Visual sample times must be strictly increasing and inside the scene duration.");
  if(!Array.isArray(scene.beats)||scene.beats.length<2||scene.beats.length>12)throw new Error("Scene needs 2–12 authored beats.");
  let beatEnd=0;const beatIds=new Set<string>();
  for(const beat of scene.beats){if(!ids.test(beat.id)||beatIds.has(beat.id)||!finite(beat.start)||!finite(beat.end)||beat.start!==beatEnd||beat.end<=beat.start||beat.end>scene.duration_seconds||!beat.purpose||!beat.visual_state)throw new Error("Authored beats must be unique, ordered, contiguous and cover the scene.");beatIds.add(beat.id);beatEnd=beat.end;}
  if(beatEnd!==scene.duration_seconds)throw new Error("Authored beats must cover the full scene duration.");
  if(!Array.isArray(scene.elements)||scene.elements.length<1||scene.elements.length>48)throw new Error("Scene must contain 1–48 visual elements.");
  const elementIds=new Set<string>();
  for(const el of scene.elements){
    if(!ids.test(el.id)||elementIds.has(el.id)||!Number.isInteger(el.layer)||el.layer<0||el.layer>100)throw new Error("Scene element ids and layer order must be unique and bounded.");elementIds.add(el.id);
    if(!["circle","rect","path"].includes(el.geometry))throw new Error("Scene element geometry is not supported.");
    for(const c of [el.fill,el.stroke])if(c!==undefined&&c!=="none"&&!color.test(c))throw new Error(`Scene element ${el.id} has an invalid color.`);
    if(el.geometry==="circle"&&(!finite(el.radius)||el.radius<=0||el.radius>240))throw new Error(`Scene circle ${el.id} needs a safe radius.`);
    if(el.geometry==="rect"&&(!finite(el.width)||!finite(el.height)||el.width<=0||el.height<=0||el.width>600||el.height>600||el.corner_radius!==undefined&&(!finite(el.corner_radius)||el.corner_radius<0||el.corner_radius>Math.min(el.width,el.height)/2)))throw new Error(`Scene rectangle ${el.id} needs safe dimensions.`);
    if(el.geometry==="path"&&(!el.path||el.path.length>2000||!/^[MmLlHhVvCcSsQqTtAaZz0-9.,+\-\s]+$/.test(el.path)||!/[Mm]/.test(el.path)))throw new Error(`Scene path ${el.id} contains unsupported path data.`);
    if(el.stroke_width!==undefined&&(!finite(el.stroke_width)||el.stroke_width<0||el.stroke_width>32))throw new Error(`Scene element ${el.id} has an invalid stroke width.`);
    if(el.x!==undefined&&(!finite(el.x)||Math.abs(el.x)>2560)||el.y!==undefined&&(!finite(el.y)||Math.abs(el.y)>1440))throw new Error(`Scene element ${el.id} has an invalid origin.`);
  }
  if(!Array.isArray(scene.tracks)||scene.tracks.length!==scene.elements.length)throw new Error("Every scene element must have exactly one animation track.");
  const trackIds=new Set<string>();
  for(const track of scene.tracks){if(!elementIds.has(track.element_id)||trackIds.has(track.element_id))throw new Error("Animation tracks must refer to distinct declared elements.");trackIds.add(track.element_id);validateKeyframes(track.keyframes,scene.duration_seconds,`Track ${track.element_id}`);}
  if(scene.camera)validateKeyframes(scene.camera.keyframes,scene.duration_seconds,"Camera");
}

interface Values {x:number;y:number;scale:number;rotation:number;opacity:number;reveal:number;}
const defaults:Values={x:0,y:0,scale:1,rotation:0,opacity:1,reveal:1};
function ease(t:number,kind:Easing="smooth"):number{
  const x=Math.max(0,Math.min(1,t));
  switch(kind){case "linear":return x;case "cubic-out":return 1-(1-x)**3;case "cubic-in-out":return x<.5?4*x*x*x:1-((-2*x+2)**3)/2;case "anticipate":return x*x*(2.7*x-1.7);case "settle":return 1-(1-x)**3*Math.cos(x*Math.PI*.72);default:return x*x*(3-2*x);}
}
export function sampleMotionTrack(keyframes:MotionKeyframe[],seconds:number):Values{
  const t=Math.max(0,Math.min(keyframes.at(-1)!.at,seconds));let next=keyframes.findIndex(k=>k.at>=t);if(next<=0)return {...defaults,...keyframes[Math.max(0,next)]};
  const a=keyframes[next-1]!,b=keyframes[next]!,u=ease((t-a.at)/(b.at-a.at),b.easing);const left={...defaults,...a},right={...defaults,...b};
  return {x:left.x+(right.x-left.x)*u,y:left.y+(right.y-left.y)*u,scale:left.scale+(right.scale-left.scale)*u,rotation:left.rotation+(right.rotation-left.rotation)*u,opacity:left.opacity+(right.opacity-left.opacity)*u,reveal:left.reveal+(right.reveal-left.reveal)*u};
}
const fmt=(n:number)=>Number(n.toFixed(3));
export function authoredMotionFrameSvg(scene:AuthoredMotionScene,frame:number):string{
  const t=Math.max(0,Math.min(scene.duration_seconds,frame/scene.fps));
  const trackMap=new Map(scene.tracks.map(x=>[x.element_id,x.keyframes]));
  const elements=[...scene.elements].sort((a,b)=>a.layer-b.layer||a.id.localeCompare(b.id)).map(el=>{
    const v=sampleMotionTrack(trackMap.get(el.id)!,t),opacity=fmt(v.opacity),transform=`translate(${fmt(el.x??0)} ${fmt(el.y??0)}) translate(${fmt(v.x)} ${fmt(v.y)}) rotate(${fmt(v.rotation)}) scale(${fmt(v.scale)})`;
    const makeShape=(fill:string,stroke:string,width:number)=>{
      const style=`fill="${fill}" stroke="${stroke}" stroke-width="${width}"`;
      if(el.geometry==="circle")return `<circle cx="0" cy="0" r="${el.radius}" ${style}/>`;
      if(el.geometry==="rect")return `<rect x="${-(el.width??0)/2}" y="${-(el.height??0)/2}" width="${el.width}" height="${el.height}" rx="${el.corner_radius??0}" ${style}/>`;
      const reveal=fmt(v.reveal);return `<path d="${el.path}" pathLength="100" stroke-dasharray="100" stroke-dashoffset="${fmt((1-reveal)*100)}" ${style}/>`;
    };
    const fill=el.fill??"none",stroke=el.stroke??"none",width=el.stroke_width??0;
    const glow=el.glow&&stroke!=="none"?`<g fill="none" stroke="${stroke}" stroke-linecap="round" opacity="0.12">${makeShape("none",stroke,width+12)}${makeShape("none",stroke,width+6)}</g>`:"";
    const shape=makeShape(fill,stroke,width);
    return `<g data-element="${el.id}" transform="${transform}" opacity="${opacity}">${glow}${shape}</g>`;
  }).join("");
  let camera=`<g>${elements}</g>`;
  if(scene.camera){const c=sampleMotionTrack(scene.camera.keyframes,t);camera=`<g transform="translate(${fmt(c.x+640)} ${fmt(c.y+360)}) scale(${fmt(c.scale)}) translate(-640 -360)">${elements}</g>`;}
  const defs=`<defs><radialGradient id="scene-backdrop" gradientUnits="userSpaceOnUse" cx="640" cy="360" r="680"><stop offset="0%" stop-color="#10212a"/><stop offset="55%" stop-color="${scene.background}"/><stop offset="100%" stop-color="#03060b"/></radialGradient></defs>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${scene.width}" height="${scene.height}" viewBox="0 0 ${scene.width} ${scene.height}">${defs}<rect width="${scene.width}" height="${scene.height}" fill="url(#scene-backdrop)"/>${camera}</svg>`;
}
