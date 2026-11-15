use contrastfix::*;
use std::io::{self, Read};
use std::process::exit;

const USAGE: &str = "usage: contrastfix [--aaa] [--large] [--fix] (FILE | - | --pair FG BG)

  FILE       text file with one 'FOREGROUND BACKGROUND [label]' per line
  -          read the same format from standard input
  --pair     check a single pair given on the command line
  --aaa      require WCAG AAA (default is AA)
  --large    use the large-text thresholds
  --fix      suggest a foreground colour that passes for failing pairs

exit codes: 0 all pass, 1 at least one pair fails, 2 bad input or usage";

fn die(msg: &str) -> ! {
    eprintln!("contrastfix: {}", msg);
    exit(2);
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let (mut level, mut large, mut fix) = (Level::Aa, false, false);
    let mut pair: Option<(String, String)> = None;
    let mut input: Option<String> = None;
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "-h" | "--help" => {
                println!("{}", USAGE);
                return;
            }
            "--aaa" => level = Level::Aaa,
            "--large" => large = true,
            "--fix" => fix = true,
            "--pair" => {
                if i + 2 >= args.len() {
                    die("--pair needs two colours");
                }
                pair = Some((args[i + 1].clone(), args[i + 2].clone()));
                i += 2;
            }
            "-" => input = Some("-".into()),
            a if a.starts_with("--") => die(&format!("unknown option '{}'\n{}", a, USAGE)),
            a => {
                if input.is_some() {
                    die("only one input file is accepted");
                }
                input = Some(a.to_string());
            }
        }
        i += 1;
    }

    let pairs = if let Some((f, b)) = pair {
        if input.is_some() {
            die("use either --pair or a file, not both");
        }
        let fg = parse_color(&f).unwrap_or_else(|e| die(&e.to_string()));
        let bg = parse_color(&b).unwrap_or_else(|e| die(&e.to_string()));
        vec![Pair { fg, bg, label: String::new() }]
    } else {
        let text = match input.as_deref() {
            None => die(&format!("no input given\n{}", USAGE)),
            Some("-") => {
                let mut s = String::new();
                io::stdin().read_to_string(&mut s).unwrap_or_else(|e| die(&format!("cannot read stdin: {}", e)));
                s
            }
            Some(path) => std::fs::read_to_string(path).unwrap_or_else(|e| die(&format!("cannot read {}: {}", path, e))),
        };
        parse_pairs(&text).unwrap_or_else(|e| die(&e))
    };

    if pairs.is_empty() {
        die("no colour pairs found in input");
    }

    let rows = evaluate(&pairs, level, large, fix);
    let mut failed = 0;
    for r in &rows {
        let status = if r.pass { "PASS" } else { "FAIL" };
        let mut line = format!(
            "{}  {} on {}  {:.2}:1 (need {:.1})",
            status, to_hex(r.fg), to_hex(r.bg), r.ratio, r.required
        );
        if !r.label.is_empty() {
            line.push_str(&format!("  {}", r.label));
        }
        println!("{}", line);
        if !r.pass {
            failed += 1;
            if fix {
                match r.suggestion {
                    Some(c) => println!(
                        "      try foreground {} ({:.2}:1)",
                        to_hex(c),
                        contrast_ratio(c, r.bg)
                    ),
                    None => println!("      no foreground with this hue reaches {:.1}:1 on this background; change the background", r.required),
                }
            }
        }
    }
    println!("{} of {} pairs pass", rows.len() - failed, rows.len());
    if failed > 0 {
        exit(1);
    }
}
