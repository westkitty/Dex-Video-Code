export interface MorphContour {
  progress:number;
  formation:number;
  center:{x:number;y:number};
  points:Array<{x:number;y:number}>;
  path:string;
}

const clamp=(v:number)=>Math.max(0,Math.min(1,v));
const smooth=(v:number)=>{const t=clamp(v);return t*t*(3-2*t);};
const easeOut=(v:number)=>{const t=clamp(v);return 1-(1-t)**3;};

/** A single sampled contour: circle -> radial interpolation -> exact square. */
export function circleSquareContour(seconds:number,width=1280,height=720,duration=12,segments=256):MorphContour {
  if(!Number.isFinite(seconds)||!Number.isFinite(width)||!Number.isFinite(height)||!Number.isFinite(duration)||duration<=0||segments<32||segments%4!==0)throw new Error("Invalid circle-square contour parameters.");
  const t=clamp(seconds/duration),formationEnd=.25,morphEnd=2/3;
  const formation=easeOut(t/formationEnd);
  const progress=smooth((t-formationEnd)/(morphEnd-formationEnd));
  const half=Math.min(width,height)*.22*formation,center={x:width/2,y:height/2};
  const points=Array.from({length:segments},(_,i)=>{
    const a=2*Math.PI*i/segments,c=Math.cos(a),s=Math.sin(a);
    const circle=half,square=half/Math.max(Math.abs(c),Math.abs(s));
    const radius=circle+(square-circle)*progress;
    return {x:center.x+radius*c,y:center.y+radius*s};
  });
  const path=`M ${points.map(p=>`${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(" L ")} Z`;
  return {progress,formation,center,points,path};
}
