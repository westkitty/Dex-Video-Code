import { strict as assert } from "node:assert";
import { test } from "node:test";
import { resolveTemporalPrecision, type TemporalPrecisionContract } from "../src/temporal-precision.js";
const base=():TemporalPrecisionContract=>({
  schema_version:"temporal-precision.v1",
  source:{path:"source.mp4",sha256:"a".repeat(64),rights:"authorized"},
  alignment:{source_sha256:"a".repeat(64),method:"forced_alignment",engine:"fixture-aligner",evidence:"fixture/word-times.json",words:[{text:"FLASH",start_seconds:2.2,end_seconds:2.51}]},
  timing:{fps_numerator:24,fps_denominator:1,duration_frames:120},
  edit:{trigger:{kind:"spoken_word_end",literal:"FLASH",occurrence:1},operation:"high_contrast_lighting",allowed:["luminance","contrast"],protected:["audio","geometry","identity","camera","framing","timing"],transition_frames:0},
  output_path:"edited.mp4",captions:"off"
});
test("observed word completion at 2.51s becomes frame 61",()=>{const r=resolveTemporalPrecision(base());assert.equal(r.state,"READY");if(r.state==="READY")assert.equal(r.first_edited_frame,61)});
test("exact boundary 2.5 seconds becomes frame 60",()=>{const c=base();c.alignment.words[0]!.end_seconds=2.5;const r=resolveTemporalPrecision(c);assert.equal(r.state,"READY");if(r.state==="READY")assert.equal(r.first_edited_frame,60)});
test("no guessed timestamps: missing alignment holds",()=>{const c=base();c.alignment.words=[];assert.equal(resolveTemporalPrecision(c).state,"HOLD")});
test("unbound or manually assigned alignments hold",()=>{const c=base();c.alignment.source_sha256="b".repeat(64);assert.equal(resolveTemporalPrecision(c).state,"HOLD");c.alignment.source_sha256=c.source.sha256;(c.alignment as any).method="manual";assert.equal(resolveTemporalPrecision(c).state,"HOLD")});
test("missing protection lock holds",()=>{const c=base();c.edit.protected=[];assert.equal(resolveTemporalPrecision(c).state,"HOLD")});
test("out of clip holds",()=>{const c=base();c.alignment.words[0]!.end_seconds=5;assert.equal(resolveTemporalPrecision(c).state,"HOLD")});
test("captions and unsupported property hold",()=>{const c=base();(c as any).captions="on";assert.equal(resolveTemporalPrecision(c).state,"HOLD");c.captions="off";(c.edit.allowed as string[]).push("camera");assert.equal(resolveTemporalPrecision(c).state,"HOLD")});
test("extra manifest fields and unsafe path hold",()=>{const c=base();(c as any).authorization="granted";assert.equal(resolveTemporalPrecision(c).state,"HOLD");delete (c as any).authorization;c.source.path="../private.mp4";assert.equal(resolveTemporalPrecision(c).state,"HOLD")});
test("select explicit occurrence of repeated trigger",()=>{const c=base();c.alignment.words=[{text:"flash",start_seconds:0.2,end_seconds:0.5},{text:"FLASH!",start_seconds:2.2,end_seconds:2.51}];c.edit.trigger.occurrence=2;const r=resolveTemporalPrecision(c);assert.equal(r.state,"READY");if(r.state==="READY")assert.equal(r.first_edited_frame,61)});
