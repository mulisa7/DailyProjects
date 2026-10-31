use std::fs;
use std::path::PathBuf;
use std::process::Command;

fn tmp(name: &str) -> PathBuf {
    let p = std::env::temp_dir().join(format!("dirdiff-cli-{}-{}", std::process::id(), name));
    let _ = fs::remove_dir_all(&p);
    fs::create_dir_all(&p).unwrap();
    p
}

fn bin(args: &[&str]) -> (i32, String, String) {
    let o = Command::new(env!("CARGO_BIN_EXE_dirdiff")).args(args).output().unwrap();
    (
        o.status.code().unwrap(),
        String::from_utf8_lossy(&o.stdout).into_owned(),
        String::from_utf8_lossy(&o.stderr).into_owned(),
    )
}

#[test]
fn matching_folders_exit_zero() {
    let (a, b) = (tmp("a1"), tmp("b1"));
    fs::write(a.join("f"), "x").unwrap();
    fs::write(b.join("f"), "x").unwrap();
    let (code, out, _) = bin(&[a.to_str().unwrap(), b.to_str().unwrap()]);
    assert_eq!(code, 0);
    assert!(out.contains("The folders match."));
}

#[test]
fn differences_exit_one_and_list_them() {
    let (a, b) = (tmp("a2"), tmp("b2"));
    fs::write(a.join("keep"), "1").unwrap();
    fs::write(b.join("keep"), "2").unwrap();
    fs::write(a.join("gone"), "zzz").unwrap();
    fs::write(b.join("extra"), "qqqq").unwrap();
    let (code, out, _) = bin(&[a.to_str().unwrap(), b.to_str().unwrap()]);
    assert_eq!(code, 1);
    assert!(out.contains("Changed") && out.contains("keep"));
    assert!(out.contains("Only in A") && out.contains("gone"));
    assert!(out.contains("Only in B") && out.contains("extra"));
}

#[test]
fn json_flag() {
    let (a, b) = (tmp("a3"), tmp("b3"));
    fs::write(a.join("old"), "same").unwrap();
    fs::write(b.join("new"), "same").unwrap();
    let (code, out, _) = bin(&["--json", a.to_str().unwrap(), b.to_str().unwrap()]);
    assert_eq!(code, 1);
    assert!(out.contains("\"moved\":[{\"from\":\"old\",\"to\":\"new\"}]"));
}

#[test]
fn ignore_flag() {
    let (a, b) = (tmp("a4"), tmp("b4"));
    fs::write(a.join("junk.tmp"), "1").unwrap();
    let (code, _, _) = bin(&["--ignore", "junk.tmp", a.to_str().unwrap(), b.to_str().unwrap()]);
    assert_eq!(code, 0);
}

#[test]
fn bad_usage_exits_two() {
    assert_eq!(bin(&[]).0, 2);
    assert_eq!(bin(&["only-one"]).0, 2);
    let (code, _, err) = bin(&["--bogus", "a", "b"]);
    assert_eq!(code, 2);
    assert!(err.contains("unknown option"));
    assert_eq!(bin(&["--ignore"]).0, 2);
}

#[test]
fn missing_folder_exits_two() {
    let a = tmp("a5");
    let (code, _, err) = bin(&[a.to_str().unwrap(), "/no/such/dir"]);
    assert_eq!(code, 2);
    assert!(err.contains("not a folder"));
}

#[test]
fn file_instead_of_folder() {
    let a = tmp("a6");
    fs::write(a.join("f"), "x").unwrap();
    let f = a.join("f");
    let (code, _, _) = bin(&[a.to_str().unwrap(), f.to_str().unwrap()]);
    assert_eq!(code, 2);
}

#[test]
fn help_exits_zero() {
    let (code, out, _) = bin(&["--help"]);
    assert_eq!(code, 0);
    assert!(out.contains("usage"));
}
