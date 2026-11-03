use std::fs::{self, File};
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;

fn tmp(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("permcheck-{}-{}", name, std::process::id()));
    let _ = fs::remove_dir_all(&d);
    fs::create_dir_all(&d).unwrap();
    d
}
fn mk(p: &Path, mode: u32) {
    fs::create_dir_all(p.parent().unwrap()).unwrap();
    File::create(p).unwrap();
    fs::set_permissions(p, fs::Permissions::from_mode(mode)).unwrap();
}
fn mode(p: &Path) -> u32 {
    fs::metadata(p).unwrap().permissions().mode() & 0o777
}
fn run(args: &[&str]) -> (i32, String, String) {
    let o = Command::new(env!("CARGO_BIN_EXE_permcheck")).args(args).output().unwrap();
    (o.status.code().unwrap(), String::from_utf8_lossy(&o.stdout).into(), String::from_utf8_lossy(&o.stderr).into())
}

#[test]
fn clean_tree_exits_zero() {
    let d = tmp("clean");
    mk(&d.join(".env"), 0o600);
    mk(&d.join("a/.ssh/id_rsa"), 0o400);
    fs::set_permissions(d.join("a/.ssh"), fs::Permissions::from_mode(0o700)).unwrap();
    let (c, out, _) = run(&[d.to_str().unwrap()]);
    assert_eq!(c, 0, "{}", out);
    assert!(out.contains("ok: 3 files"));
}

#[test]
fn empty_dir_says_nothing_found() {
    let d = tmp("empty");
    let (c, out, _) = run(&[d.to_str().unwrap()]);
    assert_eq!(c, 0);
    assert!(out.contains("no secret-looking files"));
}

#[test]
fn reports_open_files_and_exits_one() {
    let d = tmp("open");
    mk(&d.join(".env"), 0o644);
    mk(&d.join("proj/.env.local"), 0o660);
    mk(&d.join(".env.example"), 0o644); // ignored
    let (c, out, _) = run(&[d.to_str().unwrap()]);
    assert_eq!(c, 1);
    assert!(out.contains("0644"));
    assert!(out.contains("world-accessible"));
    assert!(out.contains("group-accessible"));
    assert!(!out.contains(".env.example"));
    assert_eq!(mode(&d.join(".env")), 0o644, "must not change without --fix");
}

#[test]
fn fix_changes_modes_and_keeps_owner_bits() {
    let d = tmp("fix");
    mk(&d.join(".env"), 0o644);
    mk(&d.join("h/.aws/credentials"), 0o664);
    mk(&d.join("h/.ssh/id_ed25519"), 0o440);
    let (c, out, _) = run(&["--fix", d.to_str().unwrap()]);
    assert_eq!(c, 0, "{}", out);
    assert_eq!(mode(&d.join(".env")), 0o600 & 0o644);
    assert_eq!(mode(&d.join("h/.aws/credentials")), 0o600 & 0o664);
    assert_eq!(mode(&d.join("h/.ssh/id_ed25519")), 0o400, "only the group bit should be removed");
}

#[test]
fn ssh_dir_must_be_700() {
    let d = tmp("sshdir");
    mk(&d.join("h/.ssh/id_rsa"), 0o600);
    fs::set_permissions(d.join("h/.ssh"), fs::Permissions::from_mode(0o755)).unwrap();
    let (c, out, _) = run(&[d.to_str().unwrap()]);
    assert_eq!(c, 1);
    assert!(out.contains("ssh directory"));
    assert!(out.contains("0755"));
}

#[test]
fn json_output_is_well_formed() {
    let d = tmp("json");
    mk(&d.join(".env"), 0o666);
    let (c, out, _) = run(&["--json", d.to_str().unwrap()]);
    assert_eq!(c, 1);
    assert!(out.starts_with("{\"checked\":1,\"fixed\":0,\"findings\":[{\"path\":\""));
    assert!(out.contains("\"exposed_to\":\"world\""));
    assert!(out.trim_end().ends_with("}]}"));
}

#[test]
fn depth_limit_and_skipped_dirs() {
    let d = tmp("depth");
    mk(&d.join("a/b/c/.env"), 0o644);
    mk(&d.join("node_modules/x/.env"), 0o644);
    let (c, _, _) = run(&["--depth", "1", d.to_str().unwrap()]);
    assert_eq!(c, 0);
    let (c, out, _) = run(&["--depth", "5", d.to_str().unwrap()]);
    assert_eq!(c, 1);
    assert!(!out.contains("node_modules"));
}

#[test]
fn symlinks_are_not_followed() {
    let d = tmp("link");
    mk(&d.join("real/.env"), 0o600);
    std::os::unix::fs::symlink(d.join("real/.env"), d.join(".env")).unwrap();
    let (c, out, _) = run(&[d.to_str().unwrap()]);
    assert_eq!(c, 0);
    assert!(out.contains("ok: 1 files"));
}

#[test]
fn bad_arguments_exit_two() {
    assert_eq!(run(&["--bogus"]).0, 2);
    assert_eq!(run(&["--depth"]).0, 2);
    assert_eq!(run(&["--depth", "abc"]).0, 2);
    let (c, _, e) = run(&["/definitely/not/here"]);
    assert_eq!(c, 2);
    assert!(e.contains("not a directory"));
    let (c, out, _) = run(&["--help"]);
    assert_eq!(c, 0);
    assert!(out.contains("usage"));
}
