import test from "node:test";
import assert from "node:assert/strict";
import {circleSquareContour} from "../src/morph.js";
import {makeJob,validateJob} from "../src/job.js";
import {frameSvg} from "../src/render.js";

const radial=(p:{x:number;y:number},c:{x:number;y:number})=>Math.hypot(p.x-c.x,p.y-c.y);
const film=()=>makeJob("Create a 12-second motion graphic where one luminous circle smoothly morphs into one square, centered and stationary, with no text or subtitles.");

test("new explicit circle-square morph briefs select the versioned continuous-geometry mode",()=>{
  const job=film();validateJob(job);assert.equal(job.route_decision.status,"READY");assert.equal(job.render_plan.shape_transform_mode,"continuous_circle_square_v1");assert.equal(job.render_plan.source_shape,"circle");assert.equal(job.render_plan.shape,"square");assert.equal(job.creative_intent.actions.includes("morphs"),true);assert.equal(job.brief.duration_seconds,12);assert.deepEqual(job.shots_or_beats.map(b=>[b.start,b.end]),[[0,3],[3,8],[8,12]]);
});
test("circle formation, intermediate contour and terminal square preserve one fixed centroid",()=>{
  const formed=circleSquareContour(3),mid=circleSquareContour(5.5),square=circleSquareContour(8),hold=circleSquareContour(11.5);
  const radii=formed.points.map(p=>radial(p,formed.center));assert.ok(Math.max(...radii)-Math.min(...radii)<1e-8);
  assert.equal(mid.progress,.5);assert.ok(mid.points.some((p,i)=>Math.hypot(p.x-formed.points[i]!.x,p.y-formed.points[i]!.y)>1));
  const half=Math.min(1280,720)*.22;for(const p of square.points)assert.ok(Math.abs(Math.abs(p.x-square.center.x)-half)<1e-8||Math.abs(Math.abs(p.y-square.center.y)-half)<1e-8);
  assert.deepEqual(hold.points,square.points);for(const sample of [formed,mid,square,hold])assert.deepEqual(sample.center,{x:640,y:360});
});
test("encoded-frame SVG source has one continuous path and no shape crossfade",()=>{
  const job=film();for(const frame of [12,72,132,156,192,276]){const svg=frameSvg(job,frame);assert.equal((svg.match(/<path\b/g)??[]).length,1);assert.equal((svg.match(/<rect\b/g)??[]).length,1);assert.doesNotMatch(svg,/<circle\b|<polygon\b|opacity=/);}
  assert.equal(frameSvg(job,192),frameSvg(job,276));
});
test("older unversioned circle-to-square jobs keep their original renderer behavior",()=>{
  const old=makeJob("Create a 12-second motion graphic showing a circle transforming into a square without text");assert.equal(old.render_plan.shape_transform_mode,undefined);const svg=frameSvg(old,144);assert.match(svg,/<circle\b/);assert.match(svg,/<rect x=/);assert.match(svg,/opacity=/);
});
test("previous v1.1 morph plans without the new variant remain valid and unchanged",()=>{const old=film();delete old.render_plan.shape_transform_mode;assert.doesNotThrow(()=>validateJob(old));const svg=frameSvg(old,144);assert.match(svg,/<circle\b/);assert.match(svg,/<rect x=/);});
