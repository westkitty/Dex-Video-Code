import {mkdir,readFile,writeFile,chmod} from "node:fs/promises";
import {readFileSync} from "node:fs";
import os from "node:os";
import path from "node:path";

export interface StudioLocalConfig {schema_version:1;driveFolderId?:string;googleOAuthClientId?:string;googlePickerApiKey?:string;googleCloudProjectNumber?:string;}
export const studioConfigPath=()=>path.join(os.homedir(),".config","dex-video-code","config.json");
export function readStudioConfig():StudioLocalConfig {try{const value=JSON.parse(readFileSync(studioConfigPath(),"utf8")) as StudioLocalConfig;return value?.schema_version===1?value:{schema_version:1};}catch{return {schema_version:1};}}
export async function updateStudioConfig(patch:Partial<Omit<StudioLocalConfig,"schema_version">>):Promise<void>{const file=studioConfigPath(),dir=path.dirname(file);await mkdir(dir,{recursive:true,mode:0o700});let current:StudioLocalConfig={schema_version:1};try{const parsed=JSON.parse(await readFile(file,"utf8")) as StudioLocalConfig;if(parsed?.schema_version===1)current=parsed;}catch{/* New local config. */}const next={...current,...patch,schema_version:1};await writeFile(file,JSON.stringify(next,null,2)+"\n",{mode:0o600});await chmod(file,0o600);}
