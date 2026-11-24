use std::io::Write;
use std::process::{Command, Stdio};

fn run(args: &[&str], stdin: Option<&str>) -> (i32, String, String) {
    let mut c = Command::new(env!("CARGO_BIN_EXE_robotscheck"));
    c.args(args).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());
    let mut child = c.spawn().unwrap();
    if let Some(s) = stdin {
        child.stdin.take().unwrap().write_all(s.as_bytes()).unwrap();
    } else {
        drop(child.stdin.take());
    }
    let o = child.wait_with_output().unwrap();
    (o.status.code().unwrap(), String::from_utf8_lossy(&o.stdout).into(), String::from_utf8_lossy(&o.stderr).into())
}

const R: &str = "User-agent: *\nDisallow: /private/\nAllow: /private/ok\n";

#[test]
fn allowed_exit_zero() {
    let (c, o, _) = run(&["-f", "-", "https://x.com/public"], Some(R));
    assert_eq!(c, 0);
    assert!(o.starts_with("ALLOWED"));
}

#[test]
fn blocked_exit_one_with_explain() {
    let (c, o, _) = run(&["-f", "-", "-e", "/private/a", "/private/ok/b"], Some(R));
    assert_eq!(c, 1);
    assert!(o.contains("BLOCKED  /private/a  <- Disallow /private/ (line 2"));
    assert!(o.contains("ALLOWED  /private/ok/b  <- Allow /private/ok"));
}

#[test]
fn quiet_prints_nothing() {
    let (c, o, _) = run(&["-f", "-", "-q", "/private/a"], Some(R));
    assert_eq!((c, o.as_str()), (1, ""));
}

#[test]
fn empty_robots_allows_everything() {
    let (c, o, _) = run(&["-f", "-", "-e", "/a"], Some(""));
    assert_eq!(c, 0);
    assert!(o.contains("no group applies"));
}

#[test]
fn missing_file_is_error() {
    let (c, _, e) = run(&["-f", "/nonexistent/robots.txt", "/a"], None);
    assert_eq!(c, 2);
    assert!(e.contains("cannot read"));
}

#[test]
fn bad_target_is_error() {
    let (c, _, e) = run(&["-f", "-", "nopath"], Some(R));
    assert_eq!(c, 2);
    assert!(e.contains("expected a full URL"));
}

#[test]
fn usage_errors() {
    assert_eq!(run(&["/a"], None).0, 2);
    assert_eq!(run(&["-f", "-"], Some(R)).0, 2);
    assert_eq!(run(&["-f"], None).0, 2);
    assert_eq!(run(&["--bogus", "-f", "-", "/a"], Some(R)).0, 2);
    assert_eq!(run(&["-f", "-", "-a", " ", "/a"], Some(R)).0, 2);
}

#[test]
fn binary_garbage_input_does_not_crash() {
    let (c, _, _) = run(&["-f", "-", "/a"], Some("\u{0}\u{1}:::\n:\nUser-agent\n"));
    assert_eq!(c, 0);
}

#[test]
fn agent_option_selects_group() {
    let r = "User-agent: *\nDisallow: /\nUser-agent: goodbot\nDisallow:\n";
    assert_eq!(run(&["-f", "-", "-a", "GoodBot/1.0", "/a"], Some(r)).0, 0);
    assert_eq!(run(&["-f", "-", "/a"], Some(r)).0, 1);
}
