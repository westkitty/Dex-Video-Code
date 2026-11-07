import test from "node:test";
import assert from "node:assert/strict";
import {mkdtemp,readFile,readdir,rm} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {spawnSync} from "node:child_process";
import {fileURLToPath} from "node:url";

const cli=fileURLToPath(new URL("../src/cli.js",import.meta.url));
const run=(cwd:string,args:string[])=>spawnSync(process.execPath,[cli,...args],{cwd,encoding:"utf8",timeout:30000});

test("studio make creates an honest blocked session for a route that cannot execute",async()=>{
  const root=await mkdtemp(path.join(os.tmpdir(),"dvc-studio-blocked-"));
  try{
    const result=run(root,["studio","make","--no-open","--input","Create a 5-second articulated 3D robot performance with no text"]);
    assert.equal(result.status,0,result.stderr);const output=JSON.parse(result.stdout);
    assert.equal(output.state,"BLOCKED");assert.match(output.reason,/3D character performance requires a verified native rig/i);
    const history=run(root,["studio","history"]);assert.equal(history.status,0,history.stderr);
    const rows=JSON.parse(history.stdout);assert.equal(rows.length,1);assert.equal(rows[0].state,"BLOCKED");assert.equal(rows[0].delivery,"NOT_REQUESTED");
    const dirs=await readdir(path.join(root,"runs","studio"));const session=JSON.parse(await readFile(path.join(root,"runs","studio",dirs[0]!,"studio-session.json"),"utf8"));
    assert.equal(session.artistic_review,"PENDING_HUMAN_REVIEW");assert.equal(session.state,"BLOCKED");
  }finally{await rm(root,{recursive:true,force:true});}
});

test("interactive approval refuses non-TTY callers and records no artistic approval",async()=>{
  const root=await mkdtemp(path.join(os.tmpdir(),"dvc-studio-review-"));
  try{
    const result=run(root,["studio","review","--job","missing.json","--decision","approve"]);
    assert.notEqual(result.status,0);assert.match(result.stderr,/requires an interactive terminal/);
    assert.equal((await readdir(root)).length,0);
  }finally{await rm(root,{recursive:true,force:true});}
});
