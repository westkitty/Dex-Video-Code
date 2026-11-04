import { lstat, mkdir, realpath } from "node:fs/promises";
import path from "node:path";
import { safeRelative } from "./job.js";

export async function assertNoSymlinks(root:string,relative:string):Promise<void>{
  safeRelative(relative);const boundary=await realpath(root);let current=boundary;
  for(const part of relative.split("/")){current=path.join(current,part);try{const st=await lstat(current);if(st.isSymbolicLink())throw new Error(`Refusing symlink in path: ${part}`);if(!current.startsWith(boundary+path.sep))throw new Error("Path escapes project root.");}catch(e){if((e as NodeJS.ErrnoException).code==="ENOENT")continue;throw e;}}
}
export async function ensureDirectoriesNoSymlink(root:string,relativeDirectory:string):Promise<void>{
  const boundary=await realpath(root);const rootInfo=await lstat(boundary);if(rootInfo.isSymbolicLink()||!rootInfo.isDirectory())throw new Error("Workspace root must be a real directory.");
  if(!relativeDirectory)return;safeRelative(relativeDirectory);let current=boundary;
  for(const part of relativeDirectory.split("/")){
    current=path.join(current,part);if(!current.startsWith(boundary+path.sep))throw new Error("Directory path escapes workspace.");
    try{const st=await lstat(current);if(st.isSymbolicLink())throw new Error(`Refusing symlink in directory path: ${part}`);if(!st.isDirectory())throw new Error(`Path component is not a directory: ${part}`);}
    catch(e){if((e as NodeJS.ErrnoException).code!=="ENOENT")throw e;try{await mkdir(current);}catch(createError){if((createError as NodeJS.ErrnoException).code!=="EEXIST")throw createError;}const st=await lstat(current);if(st.isSymbolicLink()||!st.isDirectory())throw new Error(`Unsafe directory component appeared during creation: ${part}`);}
  }
}
