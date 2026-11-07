import type {CreativeJob} from "./types.js";

export type ContractStage="ESTABLISH"|"TRANSFORM"|"RESOLVE";
export interface CreativeContract {
  contract_version:"creative-contract.v1";
  job_id:string;
  source_prompt:string;
  admission:{state:CreativeJob["route_decision"]["status"];route:string;reason:string};
  subject:{description:string;identity:"ONE_CONTINUOUS_OBJECT"|"SAME_AUTHORED_PRODUCT"|"UNSPECIFIED";actions:string[]};
  temporal_contract:Array<{stage:ContractStage;start_seconds:number;end_seconds:number;purpose:string;visual_state:string}>;
  source_beats:CreativeJob["shots_or_beats"];
  camera:{motion:"FIXED"|"AUTHORED_TIMELINE"|"UNSPECIFIED";centroid:"FIXED_FRAME_CENTER"|"AUTHORED_COMPOSITION"|"UNSPECIFIED";framing:string};
  visual_style:{description:string;palette:string[]};
  authored_motion_scene?:CreativeJob["authored_motion"];
  exclusions:{explicit:string[];text_policy:CreativeJob["creative_intent"]["text_policy"];audio_policy:string};
  proof:{technical_status:string;visual_review:"PENDING_VISUAL_REVIEW";human_acceptance:"PENDING_HUMAN_REVIEW";technical_obligations:string[];visual_obligations:string[]};
}

const rounded=(n:number)=>Math.round(n*1000)/1000;

/** Compile only source-backed job facts and explicit route invariants; never infer approval or capability. */
export function compileCreativeContract(job:CreativeJob):CreativeContract {
  const morph=job.render_plan.shape_transform_mode==="continuous_circle_square_v1";
  const authored=job.authored_motion;
  const duration=job.brief.duration_seconds;
  const temporal_contract:CreativeContract["temporal_contract"]=authored?authored.beats.map((beat,i)=>({stage:i===0?"ESTABLISH":i===authored.beats.length-1?"RESOLVE":"TRANSFORM",start_seconds:beat.start,end_seconds:beat.end,purpose:beat.purpose,visual_state:beat.visual_state})):morph?[
    {stage:"ESTABLISH",start_seconds:0,end_seconds:rounded(duration*.25),purpose:"Establish the circle as one centered object.",visual_state:"A single closed circular contour becomes clearly visible without changing its center."},
    {stage:"TRANSFORM",start_seconds:rounded(duration*.25),end_seconds:rounded(duration*2/3),purpose:"Morph the same object from circle to square.",visual_state:"The one closed contour changes continuously; do not overlay, fade between, or translate separate shapes."},
    {stage:"RESOLVE",start_seconds:rounded(duration*2/3),end_seconds:duration,purpose:"Hold the resolved square.",visual_state:"The final square stays centered and stationary through the end."}
  ]:job.shots_or_beats.map((beat,i)=>({stage:i===0?"ESTABLISH":i===job.shots_or_beats.length-1?"RESOLVE":"TRANSFORM",start_seconds:beat.start,end_seconds:beat.end,purpose:beat.purpose,visual_state:beat.visual_state}));
  const technical_obligations=authored?[
    "Verify the original authored-scene master against its declared duration, dimensions, frame rate, streams, full decode and SHA-256.",
    "Confirm the commercial is silent and has no subtitle stream."
  ]:morph?[
    "Verify the original encoded master against its declared duration, dimensions, frame rate, streams, full decode and SHA-256.",
    "Confirm the video has no audio or subtitle stream."
  ]:["Verify the original encoded master against the declared technical requirements."];
  const visual_obligations=authored?[
    `Inspect encoded frames at authored times ${authored.visual_sample_times.join(", ")} seconds.`,
    `Review the authored sequence: ${authored.beats.map(beat=>`${beat.purpose} ${beat.visual_state}`).join("; ")}.`,
    ...(authored.groups?.length?[`Check continuity across ${authored.groups.length} nested transform groups and their independently animated parts.`]:[]),
    "Check clipping, unintended text, audio and subtitles on the encoded master."
  ]:morph?[
    "Inspect encoded frames at 0.5, 3.5, 5.0, 6.5, 8.5 and 11.5 seconds.",
    "Confirm a single contour changes geometry, with no independent destination shape or opacity crossfade.",
    "Confirm the centroid remains fixed and the terminal square holds without clipping."
  ]:["Inspect representative encoded frames against the source brief and recorded beat map."];
  return {
    contract_version:"creative-contract.v1",job_id:job.job_id,source_prompt:job.source_prompt,
    admission:{state:job.route_decision.status,route:job.route_decision.selected,reason:job.route_decision.reason},
    subject:{description:job.creative_intent.subject,identity:morph?"ONE_CONTINUOUS_OBJECT":authored?"SAME_AUTHORED_PRODUCT":"UNSPECIFIED",actions:authored?authored.beats.map(beat=>beat.purpose):[...job.creative_intent.actions]},
    temporal_contract,source_beats:job.shots_or_beats.map(b=>({...b})),
    camera:{motion:authored?"AUTHORED_TIMELINE":morph?"FIXED":"UNSPECIFIED",centroid:authored?"AUTHORED_COMPOSITION":morph?"FIXED_FRAME_CENTER":"UNSPECIFIED",framing:authored?"1280x720 with bounded authored camera motion.":morph?"Centered in the 16:9 frame.":"Unspecified by the supported contract."},
    visual_style:{description:authored?`${job.creative_intent.style}; authored layered scene ${authored.title}`:job.creative_intent.style,palette:[...job.render_plan.palette]},
    ...(authored?{authored_motion_scene:authored}:{}),
    exclusions:{explicit:[...job.brief.exclusions],text_policy:job.creative_intent.text_policy,audio_policy:job.creative_intent.audio},
    proof:{technical_status:job.proof.technical_status,visual_review:"PENDING_VISUAL_REVIEW",human_acceptance:"PENDING_HUMAN_REVIEW",technical_obligations,visual_obligations}
  };
}
