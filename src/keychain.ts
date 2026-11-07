import { spawnSync } from "node:child_process";

export interface SecretStore { get(): Promise<string|undefined>; set(value:string):Promise<void>; delete():Promise<void>; }

// The secret is passed over stdin to a tiny Swift Security.framework client;
// it never appears in argv, a file, shell history, or diagnostic output.
const helper = String.raw`
import Foundation
import Security
let input = FileHandle.standardInput.readDataToEndOfFile()
let request = try JSONSerialization.jsonObject(with: input) as! [String: Any]
let service = "com.dexvideocode.studio.oauth"
let account = "google-drive-refresh-v1"
let base: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account]
let action = request["action"] as! String
func emit(_ obj: [String: Any]) { let d = try! JSONSerialization.data(withJSONObject: obj); FileHandle.standardOutput.write(d) }
if action == "get" {
  var q = base; q[kSecReturnData as String] = true; q[kSecMatchLimit as String] = kSecMatchLimitOne
  var item: CFTypeRef?; let status = SecItemCopyMatching(q as CFDictionary, &item)
  if status == errSecItemNotFound { emit(["found": false]) }
  else if status == errSecSuccess, let d = item as? Data { emit(["found": true, "secret": d.base64EncodedString()]) }
  else { emit(["ok": false, "status": status]) }
} else if action == "set", let encoded = request["secret"] as? String, let data = Data(base64Encoded: encoded) {
  let update = [kSecValueData as String: data]
  let status = SecItemUpdate(base as CFDictionary, update as CFDictionary)
  if status == errSecItemNotFound {
    var add = base; add[kSecValueData as String] = data; add[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
    let added = SecItemAdd(add as CFDictionary, nil); emit(["ok": added == errSecSuccess, "status": added])
  } else { emit(["ok": status == errSecSuccess, "status": status]) }
} else if action == "delete" {
  let status = SecItemDelete(base as CFDictionary); emit(["ok": status == errSecSuccess || status == errSecItemNotFound, "status": status])
} else { emit(["ok": false, "status": -1]) }
`;

export class MacOSKeychainStore implements SecretStore {
  constructor(private readonly platform=process.platform) {}
  private call(action:"get"|"set"|"delete",secret?:string):Record<string,unknown>{
    if(this.platform!=="darwin")throw new Error("Secure Google credential storage requires macOS Keychain.");
    const input=JSON.stringify({action,...(secret!==undefined?{secret:Buffer.from(secret,"utf8").toString("base64")}:{})});
    const result=spawnSync("swift",["-e",helper],{input,encoding:"utf8",timeout:30000,maxBuffer:1024*1024});
    if(result.error||result.status!==0)throw new Error("macOS Keychain operation failed; credential contents were withheld.");
    try{return JSON.parse(result.stdout) as Record<string,unknown>;}catch{throw new Error("macOS Keychain returned an invalid response; credential contents were withheld.");}
  }
  async get():Promise<string|undefined>{const r=this.call("get");if(r.found!==true)return undefined;if(typeof r.secret!=="string")throw new Error("macOS Keychain credential could not be read.");return Buffer.from(r.secret,"base64").toString("utf8");}
  async set(value:string):Promise<void>{const r=this.call("set",value);if(r.ok!==true)throw new Error("macOS Keychain refused to store the Google refresh credential.");}
  async delete():Promise<void>{const r=this.call("delete");if(r.ok!==true)throw new Error("macOS Keychain refused to remove the Google refresh credential.");}
}
