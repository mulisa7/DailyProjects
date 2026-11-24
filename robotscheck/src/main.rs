use robotscheck::{check, parse, target_path};
use std::io::Read;
use std::process::exit;

const USAGE: &str = "usage: robotscheck --file ROBOTS.TXT|- [--agent NAME] [--explain] [--quiet] URL_OR_PATH...\n\
\n\
Checks each URL or path against a robots.txt file (RFC 9309 rules).\n\
Exit codes: 0 all allowed, 1 at least one blocked, 2 usage or input error.\n\
Use '-' as the file to read robots.txt from stdin. Default agent: *";

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut file: Option<String> = None;
    let mut agent = "*".to_string();
    let (mut explain, mut quiet) = (false, false);
    let mut targets: Vec<String> = Vec::new();
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "-h" | "--help" => {
                println!("{USAGE}");
                return;
            }
            "--file" | "-f" | "--agent" | "-a" => {
                let Some(val) = args.get(i + 1) else {
                    eprintln!("error: {} needs a value\n{USAGE}", args[i]);
                    exit(2);
                };
                if args[i] == "--file" || args[i] == "-f" { file = Some(val.clone()) } else { agent = val.clone() }
                i += 1;
            }
            "--explain" | "-e" => explain = true,
            "--quiet" | "-q" => quiet = true,
            s if s.starts_with('-') && s != "-" => {
                eprintln!("error: unknown option {s}\n{USAGE}");
                exit(2);
            }
            s => targets.push(s.to_string()),
        }
        i += 1;
    }
    let Some(file) = file else {
        eprintln!("error: --file is required\n{USAGE}");
        exit(2);
    };
    if targets.is_empty() {
        eprintln!("error: give at least one URL or path\n{USAGE}");
        exit(2);
    }
    if agent.trim().is_empty() {
        eprintln!("error: --agent must not be empty");
        exit(2);
    }
    let bytes = if file == "-" {
        let mut b = Vec::new();
        std::io::stdin().read_to_end(&mut b).map(|_| b)
    } else {
        std::fs::read(&file)
    };
    let bytes = match bytes {
        Ok(b) => b,
        Err(e) => {
            eprintln!("error: cannot read {file}: {e}");
            exit(2);
        }
    };
    let text = String::from_utf8_lossy(&bytes);
    let groups = parse(&text);
    let mut blocked = false;
    let mut bad = false;
    for t in &targets {
        match target_path(t) {
            Err(e) => {
                eprintln!("error: {e}");
                bad = true;
            }
            Ok(path) => {
                let v = check(&groups, &agent, &path);
                blocked |= !v.allowed;
                if !quiet {
                    let word = if v.allowed { "ALLOWED" } else { "BLOCKED" };
                    if explain {
                        match &v.rule {
                            Some(r) => println!(
                                "{word}  {t}  <- {} {} (line {}, {})",
                                if r.allow { "Allow" } else { "Disallow" },
                                r.pattern, r.line, v.note
                            ),
                            None => println!("{word}  {t}  ({})", v.note),
                        }
                    } else {
                        println!("{word}  {t}");
                    }
                }
            }
        }
    }
    exit(if bad { 2 } else if blocked { 1 } else { 0 });
}
