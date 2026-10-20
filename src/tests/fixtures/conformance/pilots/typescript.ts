// Native argument parser: first eager flag wins; JSON is recognized globally.
declare const require: any;
declare const process: any;
const fs = require("fs");
const args: string[] = process.argv.slice(2);
const eager = args.findIndex(a => a === "--help" || a === "--version");
const prefix = eager < 0 ? args : args.slice(0, eager);
const words = prefix.filter(a => !a.startsWith("--"));
const command = words.length >= 2 ? `pilot item ${words[1]}` : words[0] === "item" ? "pilot item" : "pilot";
const has = (flag: string) => args.includes(flag);
const machine = has("--json");
const usage = `Usage: ${command}${command.endsWith("require") ? " INPUT" : ""} [OPTIONS]`;
const help = usage + "\n" + fs.readFileSync(process.env.PILOT_HELP, "utf8");
let code = 0;
let data: any;
if (eager >= 0) {
    const version = args[eager] === "--version";
    if (!machine) { console.log(version ? "2.0.0" : help); process.exit(0); }
    data = version ? {version: "2.0.0"} : {text: help};
} else {
    const allowed = ["--json", "--quiet", "--verbose", "--yes", "--no-input", "--canonical-exits"];
    if (args.some(a => a.startsWith("--") && !allowed.includes(a)) || (has("--quiet") && has("--verbose")) || (command.endsWith("require") && !has("INPUT"))) {
        code = has("--canonical-exits") ? 2 : 22;
    }
    if (has("--verbose")) console.error("native diagnostic");
    data = code ? null : {schema: "pilot.payload/2", value: "value"};
}
const result = {contract: "v2", path: command, success: code === 0, payload: data,
    problems: code ? [{code: "usage", message: "bad input", retryable: false, next_action: "Read --help", target: null}] : [],
    correlation: `${process.pid}-${Date.now()}-${Math.random()}`, state: code ? "failed" : "done"};
if (!code && eager < 0) fs.writeFileSync(process.env.GOOBITS_CONFORMANCE_STATE + "/native-result.json", JSON.stringify(result));
console.log(JSON.stringify(result));
process.exit(code);
