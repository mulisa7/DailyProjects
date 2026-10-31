use dirdiff::{compare, render_json, render_text, scan};
use std::io::Write;
use std::path::Path;
use std::process::ExitCode;

const USAGE: &str = "usage: dirdiff [--json] [--ignore NAME]... <folder-a> <folder-b>

Compares two folders by file content. Reports files that changed, were
moved or renamed, or exist on only one side.

options:
  --json         print machine-readable JSON
  --ignore NAME  skip files or folders with this name at any depth (repeatable)
  -h, --help     show this help

exit codes: 0 folders match, 1 differences found, 2 error or bad usage";

pub fn run(args: &[String], out: &mut dyn Write, err: &mut dyn Write) -> u8 {
    let mut json = false;
    let mut ignore: Vec<String> = Vec::new();
    let mut paths: Vec<&str> = Vec::new();
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "-h" | "--help" => {
                let _ = writeln!(out, "{}", USAGE);
                return 0;
            }
            "--json" => json = true,
            "--ignore" => {
                i += 1;
                match args.get(i) {
                    Some(v) if !v.is_empty() => ignore.push(v.clone()),
                    _ => {
                        let _ = writeln!(err, "dirdiff: --ignore needs a name");
                        return 2;
                    }
                }
            }
            a if a.starts_with("--") => {
                let _ = writeln!(err, "dirdiff: unknown option {}\n{}", a, USAGE);
                return 2;
            }
            a => paths.push(a),
        }
        i += 1;
    }
    if paths.len() != 2 {
        let _ = writeln!(err, "dirdiff: expected two folders, got {}\n{}", paths.len(), USAGE);
        return 2;
    }
    for p in &paths {
        if !Path::new(p).is_dir() {
            let _ = writeln!(err, "dirdiff: {} is not a folder", p);
            return 2;
        }
    }
    let (a, b) = (Path::new(paths[0]), Path::new(paths[1]));
    let report = compare(a, &scan(a, &ignore), b, &scan(b, &ignore));
    let text = if json { render_json(&report) } else { render_text(&report) };
    let _ = write!(out, "{}", text);
    if !report.errors.is_empty() {
        2
    } else if report.has_differences() {
        1
    } else {
        0
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let stdout = std::io::stdout();
    let stderr = std::io::stderr();
    ExitCode::from(run(&args, &mut stdout.lock(), &mut stderr.lock()))
}
