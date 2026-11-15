use contrastfix::*;
use std::process::Command;

fn c(s: &str) -> Rgb {
    parse_color(s).unwrap()
}

#[test]
fn black_on_white_is_21() {
    assert!((contrast_ratio(c("#000"), c("#fff")) - 21.0).abs() < 1e-9);
}

#[test]
fn same_colour_is_1() {
    assert!((contrast_ratio(c("#777"), c("#777")) - 1.0).abs() < 1e-9);
}

#[test]
fn ratio_is_symmetric() {
    let a = contrast_ratio(c("#336699"), c("#ffeecc"));
    let b = contrast_ratio(c("#ffeecc"), c("#336699"));
    assert!((a - b).abs() < 1e-12);
}

#[test]
fn known_grey_value() {
    // #767676 on white is the classic 4.54:1 AA boundary.
    let r = contrast_ratio(c("#767676"), c("white"));
    assert!(r > 4.5 && r < 4.6, "{}", r);
    let r = contrast_ratio(c("#777777"), c("white"));
    assert!(r < 4.5, "{}", r);
}

#[test]
fn parses_formats() {
    assert_eq!(c("#abc"), Rgb { r: 0xaa, g: 0xbb, b: 0xcc });
    assert_eq!(c("#AABBCC"), Rgb { r: 0xaa, g: 0xbb, b: 0xcc });
    assert_eq!(c("rgb(1, 2,3)"), Rgb { r: 1, g: 2, b: 3 });
    assert_eq!(c("RGB(255,255,255)"), c("white"));
    assert_eq!(c("  Navy "), Rgb { r: 0, g: 0, b: 128 });
}

#[test]
fn rejects_bad_colours() {
    assert_eq!(parse_color(""), Err(ParseError::Empty));
    assert_eq!(parse_color("   "), Err(ParseError::Empty));
    assert!(matches!(parse_color("#12"), Err(ParseError::BadHex(_))));
    assert!(matches!(parse_color("#12345g"), Err(ParseError::BadHex(_))));
    assert!(matches!(parse_color("#"), Err(ParseError::BadHex(_))));
    assert!(matches!(parse_color("rgb(1,2)"), Err(ParseError::BadRgb(_))));
    assert!(matches!(parse_color("rgb(256,0,0)"), Err(ParseError::BadRgb(_))));
    assert!(matches!(parse_color("rgb(1,2,3"), Err(ParseError::BadRgb(_))));
    assert!(matches!(parse_color("rgb(-1,2,3)"), Err(ParseError::BadRgb(_))));
    assert!(matches!(parse_color("chartreuse"), Err(ParseError::UnknownName(_))));
}

#[test]
fn non_ascii_hex_does_not_panic() {
    assert!(parse_color("#éé").is_err());
}

#[test]
fn thresholds() {
    assert_eq!(required_ratio(Level::Aa, false), 4.5);
    assert_eq!(required_ratio(Level::Aa, true), 3.0);
    assert_eq!(required_ratio(Level::Aaa, false), 7.0);
    assert_eq!(required_ratio(Level::Aaa, true), 4.5);
}

#[test]
fn suggestion_passes_and_keeps_passing_input() {
    let bg = c("#ffffff");
    assert_eq!(suggest_foreground(c("#000"), bg, 4.5), Some(c("#000")));
    let fixed = suggest_foreground(c("#777777"), bg, 4.5).unwrap();
    assert!(contrast_ratio(fixed, bg) >= 4.5);
    // Should be a small nudge, not a jump to black.
    assert!(fixed.r > 0x50, "{:?}", fixed);
}

#[test]
fn suggestion_goes_lighter_on_dark_background() {
    let bg = c("#101010");
    let fixed = suggest_foreground(c("#444444"), bg, 4.5).unwrap();
    assert!(contrast_ratio(fixed, bg) >= 4.5);
    assert!(fixed.r > 0x44);
}

#[test]
fn suggestion_keeps_hue() {
    let fixed = suggest_foreground(c("#ff9999"), c("#ffffff"), 4.5).unwrap();
    assert!(fixed.r > fixed.g && fixed.r > fixed.b, "{:?}", fixed);
    assert!(contrast_ratio(fixed, c("#ffffff")) >= 4.5);
}

#[test]
fn impossible_suggestion_returns_none() {
    // Mid grey background cannot reach 7:1 with any grey foreground.
    assert_eq!(suggest_foreground(c("#808080"), c("#777777"), 7.0), None);
}

#[test]
fn parses_pair_file() {
    let t = "// header\n\n#000 #fff body text\n  red   white  \n";
    let p = parse_pairs(t).unwrap();
    assert_eq!(p.len(), 2);
    assert_eq!(p[0].label, "body text");
    assert_eq!(p[1].label, "");
}

#[test]
fn pair_file_errors_name_the_line() {
    let e = parse_pairs("#000 #fff\n#abc\n").unwrap_err();
    assert!(e.contains("line 2"), "{}", e);
    let e = parse_pairs("#000 nope\n").unwrap_err();
    assert!(e.contains("line 1") && e.contains("nope"), "{}", e);
}

#[test]
fn empty_pair_file_is_ok_here() {
    assert!(parse_pairs("").unwrap().is_empty());
    assert!(parse_pairs("// only comments\n").unwrap().is_empty());
}

#[test]
fn evaluate_marks_failures() {
    let pairs = parse_pairs("#000 #fff\n#aaa #fff\n").unwrap();
    let rows = evaluate(&pairs, Level::Aa, false, true);
    assert!(rows[0].pass && rows[0].suggestion.is_none());
    assert!(!rows[1].pass && rows[1].suggestion.is_some());
    let rows = evaluate(&pairs, Level::Aa, true, false);
    assert!(!rows[1].pass && rows[1].suggestion.is_none());
}

// CLI behaviour

fn run(args: &[&str]) -> (i32, String, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_contrastfix")).args(args).output().unwrap();
    (
        out.status.code().unwrap(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
    )
}

#[test]
fn cli_pass_exit_0() {
    let (code, out, _) = run(&["--pair", "#000", "#fff"]);
    assert_eq!(code, 0);
    assert!(out.contains("PASS") && out.contains("1 of 1"));
}

#[test]
fn cli_fail_exit_1_with_fix() {
    let (code, out, _) = run(&["--pair", "#999", "#fff", "--fix"]);
    assert_eq!(code, 1);
    assert!(out.contains("FAIL") && out.contains("try foreground"), "{}", out);
}

#[test]
fn cli_bad_colour_exit_2() {
    let (code, _, err) = run(&["--pair", "#zzz", "#fff"]);
    assert_eq!(code, 2);
    assert!(err.contains("invalid hex"));
}

#[test]
fn cli_no_args_and_missing_file() {
    assert_eq!(run(&[]).0, 2);
    let (code, _, err) = run(&["/nonexistent/pairs.txt"]);
    assert_eq!(code, 2);
    assert!(err.contains("cannot read"));
}

#[test]
fn cli_unknown_option_and_missing_pair_args() {
    assert_eq!(run(&["--bogus"]).0, 2);
    assert_eq!(run(&["--pair", "#000"]).0, 2);
}

#[test]
fn cli_empty_file_exit_2() {
    let dir = std::env::temp_dir().join("contrastfix_empty_test.txt");
    std::fs::write(&dir, "// nothing\n").unwrap();
    let (code, _, err) = run(&[dir.to_str().unwrap()]);
    std::fs::remove_file(&dir).ok();
    assert_eq!(code, 2);
    assert!(err.contains("no colour pairs"));
}

#[test]
fn cli_file_mixed_results() {
    let path = std::env::temp_dir().join("contrastfix_mixed_test.txt");
    std::fs::write(&path, "#000 #fff body\n#bbb #fff muted\n").unwrap();
    let (code, out, _) = run(&["--aaa", path.to_str().unwrap()]);
    std::fs::remove_file(&path).ok();
    assert_eq!(code, 1);
    assert!(out.contains("1 of 2 pairs pass") && out.contains("muted"), "{}", out);
}
