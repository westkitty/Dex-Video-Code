import test from "node:test";
import assert from "node:assert/strict";
import {Ajv2020} from "ajv/dist/2020.js";
import {readFile} from "node:fs/promises";
import {BlockedWorkerTransport,DeterministicTestWorker,submitAndReconcile,validateWorkerRequest,validateWorkerResponse,type WorkerRequest,type WorkerReceipt} from "../src/worker-bridge.js";

const request:WorkerRequest={schema_version:"blender-worker-request.v1",request_id:"request-001",operation:"submit-approved-job",job_id:"job-001",approved_contract_id:"the_second_light_v1",contract_sha256:"a".repeat(64),render_quality:"interaction",frame_start:1,frame_end:48,director_commit:"b".repeat(40)};
const fixtureReceipt=(worker:DeterministicTestWorker):Omit<WorkerReceipt,"schema_version"|"job_id"|"request_id"|"worker"|"evidence_scope">=>({state:"SUCCEEDED",contract_id:"the_second_light_v1",contract_sha256:"a".repeat(64),output_relative_path:"jobs/job-001/preview.mp4",output_sha256:"c".repeat(64),output_bytes:42000,render_quality:"interaction",frame_start:1,frame_end:48,video:{codec:"h264",width:320,height:180,fps:24,frame_count:48,audio:false,subtitles:false}});

test("worker contract rejects arbitrary commands, paths, long frames and unbounded render quality",()=>{
  for(const bad of [{...request,command:"blender --python evil.py"},{...request,output_path:"../../master.mp4"},{...request,frame_end:49},{...request,render_quality:"master"},{...request,director_commit:"b".repeat(39)+"x"}])assert.throws(()=>validateWorkerRequest(bad));
});

test("deterministic fixture worker reconciles idempotent submit, status and a bound receipt without claiming production",async()=>{
  const worker=new DeterministicTestWorker();const transport={request:async(r:WorkerRequest)=>{if(r.operation==="status")worker.setFixtureReceipt(r.job_id!,request.request_id,fixtureReceipt(worker));return worker.request(r);}};
  const response=await submitAndReconcile(transport,request);validateWorkerResponse(response,{schema_version:"blender-worker-request.v1",request_id:request.request_id,operation:"read-receipt",job_id:request.job_id});
  assert.equal(response.operation,"read-receipt");if(response.operation!=="read-receipt")throw new Error("expected receipt");
  assert.equal(response.receipt.output_sha256,"c".repeat(64));assert.equal(response.receipt.evidence_scope,"WORKER_RECEIPT_REQUIRES_DIRECTOR_READBACK");
  const duplicate=await worker.request({...request,request_id:"request-duplicate"});assert.equal((duplicate as {state:string}).state,"SUCCEEDED");
  const health=await worker.request({schema_version:"blender-worker-request.v1",request_id:"health-001",operation:"health"});assert.equal((health as {state:string}).state,"BLOCKED");
});

test("receipt reconciliation rejects identity and path mismatches; live transport remains fail-closed",async()=>{
  const bad={request:async(r:WorkerRequest)=>({schema_version:"blender-worker-response.v1",request_id:r.request_id,operation:r.operation,job_id:r.job_id,state:"SUCCEEDED",worker:{worker_id:"w",hostname:"host",platform:"darwin",arch:"arm64",blender_version:"5.2",worker_script_sha256:"d".repeat(64),policy_version:"p1",observed_at:"2026-01-01T00:00:00.000Z"},receipt:{schema_version:"blender-worker-receipt.v1",job_id:r.job_id,request_id:r.request_id,state:"SUCCEEDED",worker:{},contract_id:"c",contract_sha256:"a".repeat(64),output_relative_path:"../../escape.mp4",output_sha256:"c".repeat(64),output_bytes:9,render_quality:"interaction",frame_start:1,frame_end:1,video:{codec:"h264",width:320,height:180,fps:24,frame_count:1,audio:false,subtitles:false},evidence_scope:"WORKER_RECEIPT_REQUIRES_DIRECTOR_READBACK"}})};
  const receiptRequest:WorkerRequest={schema_version:"blender-worker-request.v1",request_id:"request-001",operation:"read-receipt",job_id:"job-001"};await assert.rejects(async()=>{const value=await bad.request(receiptRequest);validateWorkerResponse(value,receiptRequest);},/unsafe|identity/i);
  await assert.rejects(()=>new BlockedWorkerTransport().request(request),/BLOCKED_WORKER_TRANSPORT/);
});

test("a worker receipt cannot substitute another approved contract or render interval",async()=>{
  const worker=new DeterministicTestWorker();
  const transport={request:async(r:WorkerRequest)=>{if(r.operation==="status")worker.setFixtureReceipt(r.job_id!,request.request_id,{...fixtureReceipt(worker),contract_sha256:"f".repeat(64)});return worker.request(r);}};
  await assert.rejects(()=>submitAndReconcile(transport,request),/does not reconcile to the approved submission/);
});

test("published JSON schema matches the bounded request and response envelope",async()=>{
  const schema=JSON.parse(await readFile(new URL("../schemas/blender-worker-bridge.v1.schema.json",import.meta.url),"utf8"));
  const ajv=new Ajv2020({strict:false});const validate=ajv.compile(schema);
  assert.equal(validate(request),true);
  const worker=new DeterministicTestWorker();const health=await worker.request({schema_version:"blender-worker-request.v1",request_id:"schema-health",operation:"health"});
  assert.equal(validate(health),true);
  assert.equal(validate({...health as Record<string,unknown>,command:"arbitrary shell"}),false);
});
