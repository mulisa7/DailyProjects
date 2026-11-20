use std::process::{Command, ExitCode};
use std::time::{SystemTime, UNIX_EPOCH};
use todoage::*;

const USAGE: &str = "usage: todoage [PATH] [options]
  --older-than AGE   only show items at least AGE old (e.g. 90d, 12w, 6m, 2y)
  --tags A,B,C       tags to look for (default TODO,FIXME,HACK,XXX)
  --sort age|file    oldest first (default) or by file and line
  --json             machine-readable output
  --fail             exit 1 if any item is shown (for CI)
  --now UNIXTIME     override the current time (for testing)
  -h, --help         show this help
exit codes: 0 ok, 1 items found with --fail, 2 usage or git error";

struct Opts {
    path: String,
    older: u64,
    tags: Vec<String>,
    by_file: bool,
    json: bool,
    fail: bool,
    now: Option<i64>,
}

fn parse_args(args: &[String]) -> Result<Option<Opts>, String> {
    let mut o = Opts { path: ".".into(), older: 0, tags: DEFAULT_TAGS.iter().map(|s| s.to_string()).collect(),
        by_file: false, json: false, fail: false, now: None };
    let mut path_set = false;
    let mut i = 0;
    let need = |i: usize, name: &str| args.get(i + 1).cloned().ok_or(format!("{name} needs a value"));
    while i < args.len() {
        match args[i].as_str() {
            "-h" | "--help" => return Ok(None),
            "--older-than" => { o.older = parse_age(&need(i, "--older-than")?)?; i += 1; }
            "--tags" => {
                let v = need(i, "--tags")?;
                o.tags = v.split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect();
                if o.tags.is_empty() { return Err("--tags needs at least one tag".into()); }
                i += 1;
            }
            "--sort" => match need(i, "--sort")?.as_str() {
                "age" => { o.by_file = false; i += 1; }
                "file" => { o.by_file = true; i += 1; }
                other => return Err(format!("--sort must be age or file, got '{other}'")),
            },
            "--now" => {
                o.now = Some(need(i, "--now")?.parse().map_err(|_| "--now needs a unix timestamp".to_string())?);
                i += 1;
            }
            "--json" => o.json = true,
            "--fail" => o.fail = true,
            a if a.starts_with('-') => return Err(format!("unknown option '{a}'")),
            a => {
                if path_set { return Err("only one PATH is allowed".into()); }
                o.path = a.to_string();
                path_set = true;
            }
        }
        i += 1;
    }
    Ok(Some(o))
}

fn git(dir: &str, args: &[&str]) -> Result<Vec<u8>, String> {
    let out = Command::new("git").arg("-C").arg(dir).args(args).output()
        .map_err(|e| format!("could not run git: {e}"))?;
    if !out.status.success() {
        return Err(format!("git {} failed: {}", args.join(" "), String::from_utf8_lossy(&out.stderr).trim()));
    }
    Ok(out.stdout)
}

fn run(o: &Opts) -> Result<Vec<Item>, String> {
    let now = o.now.unwrap_or_else(|| {
        SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs() as i64).unwrap_or(0)
    });
    let files = git(&o.path, &["ls-files", "-z", "--cached", "--others", "--exclude-standard", "."])
        .map_err(|e| format!("{e} (is '{}' inside a git repository?)", o.path))?;
    let mut items = Vec::new();
    for name in files.split(|b| *b == 0).filter(|s| !s.is_empty()) {
        let name = String::from_utf8_lossy(name).to_string();
        let full = std::path::Path::new(&o.path).join(&name);
        let Ok(bytes) = std::fs::read(&full) else { continue };
        let Ok(content) = String::from_utf8(bytes) else { continue }; // binary or non-UTF-8: skip
        let hits = scan_text(&content, &o.tags);
        if hits.is_empty() { continue; }
        let blame = match git(&o.path, &["blame", "--porcelain", "--", &name]) {
            Ok(b) => parse_blame(&String::from_utf8_lossy(&b)),
            Err(_) => Default::default(), // untracked file: no history
        };
        for h in hits {
            let (author, time, unc) = match blame.get(&h.line) {
                Some(b) => (b.author.clone(), b.time, b.time.is_none()),
                None => ("(uncommitted)".to_string(), None, true),
            };
            let days = age_days(now, time);
            if days >= o.older {
                items.push(Item { file: name.clone(), line: h.line, tag: h.tag, text: h.text,
                    author, days, uncommitted: unc });
            }
        }
    }
    if o.by_file {
        items.sort_by(|a, b| (&a.file, a.line).cmp(&(&b.file, b.line)));
    } else {
        items.sort_by(|a, b| b.days.cmp(&a.days).then((&a.file, a.line).cmp(&(&b.file, b.line))));
    }
    Ok(items)
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let opts = match parse_args(&args) {
        Ok(Some(o)) => o,
        Ok(None) => { println!("{USAGE}"); return ExitCode::SUCCESS; }
        Err(e) => { eprintln!("todoage: {e}\n{USAGE}"); return ExitCode::from(2); }
    };
    match run(&opts) {
        Ok(items) => {
            if opts.json { println!("{}", to_json(&items)); }
            else if items.is_empty() { println!("No matching items found."); }
            else { print!("{}", to_table(&items)); println!("{} item(s)", items.len()); }
            if opts.fail && !items.is_empty() { ExitCode::from(1) } else { ExitCode::SUCCESS }
        }
        Err(e) => { eprintln!("todoage: {e}"); ExitCode::from(2) }
    }
}
