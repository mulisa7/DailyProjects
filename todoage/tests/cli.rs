use std::process::Command;
use std::path::PathBuf;

fn bin() -> &'static str { env!("CARGO_BIN_EXE_todoage") }

fn sh(dir: &PathBuf, date: &str, args: &[&str]) {
    let s = Command::new("git").current_dir(dir).args(args)
        .env("GIT_AUTHOR_DATE", date).env("GIT_COMMITTER_DATE", date)
        .env("GIT_AUTHOR_NAME", "Test Dev").env("GIT_AUTHOR_EMAIL", "t@example.com")
        .env("GIT_COMMITTER_NAME", "Test Dev").env("GIT_COMMITTER_EMAIL", "t@example.com")
        .status().unwrap();
    assert!(s.success(), "git {args:?}");
}

fn repo(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("todoage-test-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&d);
    std::fs::create_dir_all(&d).unwrap();
    sh(&d, "2020-01-01T00:00:00Z", &["init", "-q"]);
    d
}

fn run(d: &PathBuf, extra: &[&str]) -> (i32, String, String) {
    let o = Command::new(bin()).arg(d).args(extra).args(["--now", "1735689600"]).output().unwrap(); // 2025-01-01
    (o.status.code().unwrap(), String::from_utf8_lossy(&o.stdout).into(), String::from_utf8_lossy(&o.stderr).into())
}

#[test]
fn ages_come_from_blame() {
    let d = repo("blame");
    std::fs::write(d.join("a.rs"), "fn a() {}\n// TODO: old thing\n").unwrap();
    sh(&d, "2020-01-01T00:00:00Z", &["add", "."]);
    sh(&d, "2020-01-01T00:00:00Z", &["commit", "-qm", "one"]);
    std::fs::write(d.join("b.py"), "# FIXME recent\n").unwrap();
    sh(&d, "2024-12-22T00:00:00Z", &["add", "."]);
    sh(&d, "2024-12-22T00:00:00Z", &["commit", "-qm", "two"]);
    let (c, out, _) = run(&d, &[]);
    assert_eq!(c, 0);
    let lines: Vec<&str> = out.lines().collect();
    assert!(lines[0].contains("a.rs:2") && lines[0].contains("Test Dev"), "{out}");
    assert!(lines[1].contains("b.py:1") && lines[1].contains("10d"), "{out}");
    assert!(out.contains("2 item(s)"));
    let (_, out, _) = run(&d, &["--older-than", "1y"]);
    assert!(out.contains("a.rs") && !out.contains("b.py"), "{out}");
    let (c, _, _) = run(&d, &["--older-than", "1y", "--fail"]);
    assert_eq!(c, 1);
    let (c, out, _) = run(&d, &["--older-than", "50y", "--fail"]);
    assert_eq!(c, 0);
    assert!(out.contains("No matching"));
    let (_, out, _) = run(&d, &["--json", "--sort", "file"]);
    assert!(out.starts_with('[') && out.contains("\"file\":\"a.rs\""));
}

#[test]
fn uncommitted_and_untracked() {
    let d = repo("unc");
    std::fs::write(d.join("a.txt"), "# TODO x\n").unwrap();
    sh(&d, "2020-01-01T00:00:00Z", &["add", "."]);
    sh(&d, "2020-01-01T00:00:00Z", &["commit", "-qm", "one"]);
    std::fs::write(d.join("a.txt"), "# TODO x\n# TODO added now\n").unwrap();
    std::fs::write(d.join("new.txt"), "# HACK untracked\n").unwrap();
    let (_, out, _) = run(&d, &[]);
    assert!(out.contains("a.txt:2") && out.contains("new.txt:1") && out.contains("new"), "{out}");
    assert!(out.contains("3 item(s)"));
}

#[test]
fn empty_repo_and_binary_files() {
    let d = repo("empty");
    let (c, out, _) = run(&d, &[]);
    assert_eq!(c, 0);
    assert!(out.contains("No matching"));
    std::fs::write(d.join("bin.dat"), [0xff, 0xfe, 0x00, b'/', b'/', b'T', b'O', b'D', b'O']).unwrap();
    let (c, out, _) = run(&d, &[]);
    assert_eq!(c, 0);
    assert!(out.contains("No matching"), "{out}");
}

#[test]
fn errors() {
    let d = std::env::temp_dir().join(format!("todoage-notrepo-{}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    let (c, _, err) = run(&d, &[]);
    assert_eq!(c, 2);
    assert!(err.contains("todoage:"));
    let o = Command::new(bin()).arg("--bogus").output().unwrap();
    assert_eq!(o.status.code(), Some(2));
    let o = Command::new(bin()).args(["--older-than", "xyz"]).output().unwrap();
    assert_eq!(o.status.code(), Some(2));
    let o = Command::new(bin()).args(["--sort", "size"]).output().unwrap();
    assert_eq!(o.status.code(), Some(2));
    let o = Command::new(bin()).args(["--tags"]).output().unwrap();
    assert_eq!(o.status.code(), Some(2));
    let o = Command::new(bin()).arg("--help").output().unwrap();
    assert_eq!(o.status.code(), Some(0));
}
