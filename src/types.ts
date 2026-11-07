export type CapabilityState = "VERIFIED" | "AVAILABLE_UNPROVEN" | "DORMANT" | "BROKEN" | "UNAVAILABLE" | "EXCLUDED";
export interface Capability { id: string; state: CapabilityState; host: string; command?: string; version?: string; reason: string; cost: "none" | "unknown"; privacy: "local" | "manual"; }
export interface CreativeJob {
  schema_version: "1.1"; job_id: string; source_prompt: string;
  brief: { deliverable_type: "video"|"image"|"audio"|"scene"|"document"|"unknown"; format: string; aspect_ratio: string; duration_seconds: number; tone: string; exclusions: string[]; captions: "off"|"on"|"unspecified" };
  creative_intent: { subject: string; setting: string; actions: string[]; purpose: string; style: string; audio: string; technique: string; proof_requirements: string[]; text_policy: "no_text"|"text_allowed"|"unspecified"; requested_constraints: string[]; uncertainties: string[] };
  route_decision: { selected: string; status: "READY"|"BLOCKED"|"NEEDS_CLARIFICATION"; alternatives: string[]; reason: string; evidence: string[] };
  render_plan: { kind: "signal_path"|"shape_transformation"|"shape_rotation"|"none"; shape: "circle"|"square"|"triangle"|"signal"; source_shape?: "circle"|"square"|"triangle"; shape_transform_mode?: "continuous_circle_square_v1"; title_text?: string; palette: string[]; fps: number; width: number; height: number };
  shots_or_beats: Array<{start:number;end:number;purpose:string;visual_state:string;continuity?:string;sound?:string}>;
  assets: Array<{asset_id:string;sha256:string|null;rights:string;source:string;derived_from?:string[]}>;
  execution_plan: Array<{operation:string;adapter:string;approval:"not_required"|"required";timeout_seconds:number}>;
  artifacts: Array<{role:string;format:string;path:string;sha256?:string}>;
  proof: {technical_status:string;artistic_status:string;evidence:string[]};
}
export interface Route { id:string; score:number; selected:boolean; requires3dRig:boolean; available:boolean; rationale:string; }
