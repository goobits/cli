//! Native std-only parser: first eager option wins, trailing JSON is not parsed.
use std::{
    env, fs, process,
    time::{SystemTime, UNIX_EPOCH},
};
fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    let eager = args.iter().position(|a| a == "--help" || a == "--version");
    let parsed = &args[..eager.unwrap_or(args.len())];
    let words: Vec<&str> = parsed
        .iter()
        .filter(|a| !a.starts_with("--"))
        .map(String::as_str)
        .collect();
    let command = if words.len() >= 2 {
        format!("pilot item {}", words[1])
    } else if words.first() == Some(&"item") {
        "pilot item".into()
    } else {
        "pilot".into()
    };
    let has = |flag: &str| args.iter().any(|a| a == flag);
    let machine = parsed.iter().any(|a| a == "--json");
    let usage = format!(
        "Usage: {}{} [OPTIONS]",
        command,
        if command.ends_with("require") {
            " INPUT"
        } else {
            ""
        }
    );
    let help = format!("{}\n{}", usage, include_str!("help.txt"));
    let mut code = 0;
    let data;
    if let Some(index) = eager {
        let version = args[index] == "--version";
        let text = if version { "2.0.0" } else { &help };
        if !machine {
            println!("{}", text);
            return;
        }
        data = format!(
            "{{\"{}\":{:?}}}",
            if version { "version" } else { "text" },
            text
        );
    } else {
        let allowed = [
            "--json",
            "--quiet",
            "--verbose",
            "--yes",
            "--no-input",
            "--canonical-exits",
        ];
        if args
            .iter()
            .any(|a| a.starts_with("--") && !allowed.contains(&a.as_str()))
            || (has("--quiet") && has("--verbose"))
            || (command.ends_with("require") && !has("INPUT"))
        {
            code = if has("--canonical-exits") { 2 } else { 22 };
        }
        if has("--verbose") {
            eprintln!("native diagnostic");
        }
        data = if code == 0 {
            "{\"schema\":\"pilot.payload/2\",\"value\":\"value\"}".into()
        } else {
            "null".into()
        };
    }
    let id = format!(
        "{}-{}",
        process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    );
    let errors = if code == 0 {
        "[]"
    } else {
        "[{\"code\":\"usage\",\"message\":\"bad input\",\"retryable\":false,\"next_action\":\"Read --help\",\"target\":null}]"
    };
    let result = format!("{{\"contract\":\"v2\",\"path\":{:?},\"success\":{},\"payload\":{},\"problems\":{},\"correlation\":{:?},\"state\":{:?}}}", command, code == 0, data, errors, id, if code == 0 { "done" } else { "failed" });
    if code == 0 && eager.is_none() {
        let marker = std::path::PathBuf::from(env::var("GOOBITS_CONFORMANCE_STATE").unwrap())
            .join("native-result.json");
        fs::write(marker, &result).unwrap();
    }
    println!("{}", result);
    process::exit(code);
}
