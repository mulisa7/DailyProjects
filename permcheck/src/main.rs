use permcheck::{apply_fix, fmt_mode, scan};
use std::path::PathBuf;
use std::process::ExitCode;

const USAGE: &str = "usage: permcheck [--fix] [--depth N] [--json] [PATH ...]\n\
Scans PATH (default: current directory) for ssh keys, .env files, cloud and\n\
registry credentials that group or world can access.\n\
  --fix       chmod offending files to the strictest allowed mode\n\
  --depth N   how many folders deep to look (default 6)\n\
  --json      print findings as JSON\n\
exit codes: 0 clean, 1 problems found (and not fixed), 2 usage or I/O error";

fn esc(s: &str) -> String {
    let mut o = String::new();
    for c in s.chars() {
        match c {
            '"' => o.push_str("\\\""),
            '\\' => o.push_str("\\\\"),
            '\n' => o.push_str("\\n"),
            c if (c as u32) < 0x20 => o.push_str(&format!("\\u{:04x}", c as u32)),
            c => o.push(c),
        }
    }
    o
}

fn run(args: Vec<String>, out: &mut dyn std::io::Write, err: &mut dyn std::io::Write) -> u8 {
    let mut fix = false;
    let mut json = false;
    let mut depth = 6usize;
    let mut paths: Vec<PathBuf> = vec![];
    let mut it = args.into_iter();
    while let Some(a) = it.next() {
        match a.as_str() {
            "-h" | "--help" => {
                let _ = writeln!(out, "{}", USAGE);
                return 0;
            }
            "--fix" => fix = true,
            "--json" => json = true,
            "--depth" => match it.next().and_then(|v| v.parse::<usize>().ok()) {
                Some(n) => depth = n,
                None => {
                    let _ = writeln!(err, "permcheck: --depth needs a non-negative number\n{}", USAGE);
                    return 2;
                }
            },
            s if s.starts_with("--") => {
                let _ = writeln!(err, "permcheck: unknown option {}\n{}", s, USAGE);
                return 2;
            }
            s => paths.push(PathBuf::from(s)),
        }
    }
    if paths.is_empty() {
        paths.push(PathBuf::from("."));
    }
    let mut checked = 0;
    let mut findings = vec![];
    let mut errors = vec![];
    for p in &paths {
        if !p.is_dir() {
            let _ = writeln!(err, "permcheck: {} is not a directory", p.display());
            return 2;
        }
        let r = scan(p, depth);
        checked += r.checked;
        findings.extend(r.findings);
        errors.extend(r.errors);
    }
    let mut fix_failed = 0;
    let mut fixed = 0;
    if fix {
        for f in &findings {
            match apply_fix(f) {
                Ok(()) => fixed += 1,
                Err(e) => {
                    fix_failed += 1;
                    errors.push(e);
                }
            }
        }
    }
    if json {
        let items: Vec<String> = findings
            .iter()
            .map(|f| {
                format!(
                    "{{\"path\":\"{}\",\"kind\":\"{}\",\"mode\":\"{}\",\"fix_mode\":\"{}\",\"exposed_to\":\"{}\"}}",
                    esc(&f.path.display().to_string()), f.kind.label(), fmt_mode(f.mode), fmt_mode(f.fix_mode), f.audience
                )
            })
            .collect();
        let _ = writeln!(out, "{{\"checked\":{},\"fixed\":{},\"findings\":[{}]}}", checked, fixed, items.join(","));
    } else {
        for f in &findings {
            let _ = writeln!(out, "{} {} -> {}  {} ({}-accessible)", fmt_mode(f.mode), f.path.display(), fmt_mode(f.fix_mode), f.kind.label(), f.audience);
        }
        if checked == 0 {
            let _ = writeln!(out, "no secret-looking files found");
        } else if findings.is_empty() {
            let _ = writeln!(out, "ok: {} files checked, none too open", checked);
        } else if fix {
            let _ = writeln!(out, "{} of {} problem(s) fixed ({} files checked)", fixed, findings.len(), checked);
        } else {
            let _ = writeln!(out, "{} problem(s) in {} files checked; run with --fix to chmod", findings.len(), checked);
        }
    }
    for e in &errors {
        let _ = writeln!(err, "permcheck: warning: {}", e);
    }
    if fix_failed > 0 || (!fix && !findings.is_empty()) { 1 } else { 0 }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let code = run(args, &mut std::io::stdout(), &mut std::io::stderr());
    ExitCode::from(code)
}
