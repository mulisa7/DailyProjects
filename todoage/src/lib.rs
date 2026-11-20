//! todoage: find TODO-style tags in files and attach the age of each line from `git blame`.

use std::collections::HashMap;

pub const DEFAULT_TAGS: &[&str] = &["TODO", "FIXME", "HACK", "XXX"];

#[derive(Debug, Clone, PartialEq)]
pub struct Hit {
    pub line: usize,
    pub tag: String,
    pub text: String,
}

/// Parse a duration such as "90d", "12w", "6m", "2y" or a bare number of days.
/// Months are 30 days and years are 365 days.
pub fn parse_age(s: &str) -> Result<u64, String> {
    let s = s.trim();
    if s.is_empty() {
        return Err("empty duration".into());
    }
    let (num, mult) = match s.chars().last().unwrap() {
        'd' => (&s[..s.len() - 1], 1),
        'w' => (&s[..s.len() - 1], 7),
        'm' => (&s[..s.len() - 1], 30),
        'y' => (&s[..s.len() - 1], 365),
        c if c.is_ascii_digit() => (s, 1),
        _ => return Err(format!("bad duration '{s}': use a number with d, w, m or y")),
    };
    let n: u64 = num
        .parse()
        .map_err(|_| format!("bad duration '{s}': '{num}' is not a whole number"))?;
    n.checked_mul(mult).ok_or_else(|| format!("duration '{s}' is too large"))
}

fn is_word_char(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
}

/// Find tags in one line. A tag counts only as a whole upper-case word, so
/// "TODOS" and "mastodon" do not match, and it must appear after a comment
/// marker (`//`, `/*`, `<!--`, `#`, `--`, `;`, `%`, `*`) so that code
/// identifiers are not reported. Markers inside string literals are not
/// detected, so a string like "# TODO" will still match.
pub fn find_tag(line: &str, tags: &[String]) -> Option<(String, String)> {
    let markers = ["//", "/*", "<!--", "#", "--", ";", "%", "*"];
    let comment_start = markers.iter().filter_map(|m| line.find(m)).min()?;
    let rest = &line[comment_start..];
    for (idx, _) in rest.char_indices() {
        for tag in tags {
            if rest[idx..].starts_with(tag.as_str()) {
                let before_ok = rest[..idx].chars().next_back().map_or(true, |c| !is_word_char(c));
                let after_ok = rest[idx + tag.len()..].chars().next().map_or(true, |c| !is_word_char(c));
                if before_ok && after_ok {
                    let text = rest[idx + tag.len()..]
                        .trim_start_matches(|c: char| c == ':' || c == '-' || c.is_whitespace())
                        .trim_end_matches(|c: char| c == '*' || c == '/' || c == '>' || c == '-' || c.is_whitespace())
                        .to_string();
                    return Some((tag.clone(), text));
                }
            }
        }
    }
    None
}

pub fn scan_text(content: &str, tags: &[String]) -> Vec<Hit> {
    content
        .lines()
        .enumerate()
        .filter_map(|(i, l)| {
            find_tag(l, tags).map(|(tag, text)| Hit { line: i + 1, tag, text })
        })
        .collect()
}

#[derive(Debug, Clone, PartialEq)]
pub struct BlameInfo {
    pub author: String,
    /// Unix time of the commit, or None for uncommitted lines.
    pub time: Option<i64>,
}

/// Parse `git blame --porcelain` output into a map from final line number to info.
pub fn parse_blame(out: &str) -> HashMap<usize, BlameInfo> {
    let mut commits: HashMap<String, BlameInfo> = HashMap::new();
    let mut lines = HashMap::new();
    let mut cur: Option<(String, usize)> = None;
    for l in out.lines() {
        if l.starts_with('\t') {
            if let Some((sha, n)) = cur.take() {
                if let Some(info) = commits.get(&sha) {
                    lines.insert(n, info.clone());
                }
            }
            continue;
        }
        let mut parts = l.split(' ');
        let first = parts.next().unwrap_or("");
        if first.len() == 40 && first.chars().all(|c| c.is_ascii_hexdigit()) {
            let _orig = parts.next();
            if let Some(Ok(n)) = parts.next().map(|x| x.parse::<usize>()) {
                cur = Some((first.to_string(), n));
                let uncommitted = first.chars().all(|c| c == '0');
                commits.entry(first.to_string()).or_insert(BlameInfo {
                    author: String::new(),
                    time: if uncommitted { None } else { Some(0) },
                });
            }
            continue;
        }
        if let Some((sha, _)) = &cur {
            if let Some(a) = l.strip_prefix("author ") {
                if let Some(c) = commits.get_mut(sha) {
                    c.author = a.to_string();
                }
            } else if let Some(t) = l.strip_prefix("author-time ") {
                if let (Some(c), Ok(t)) = (commits.get_mut(sha), t.trim().parse::<i64>()) {
                    if c.time.is_some() {
                        c.time = Some(t);
                    }
                }
            }
        }
    }
    lines
}

/// Whole days between a commit time and now; never negative.
pub fn age_days(now: i64, then: Option<i64>) -> u64 {
    match then {
        None => 0,
        Some(t) => ((now - t).max(0) / 86_400) as u64,
    }
}

pub fn human_age(days: u64) -> String {
    if days < 60 {
        format!("{days}d")
    } else if days < 730 {
        format!("{}m", days / 30)
    } else {
        format!("{:.1}y", days as f64 / 365.0)
    }
}

pub fn json_escape(s: &str) -> String {
    let mut o = String::with_capacity(s.len() + 2);
    for c in s.chars() {
        match c {
            '"' => o.push_str("\\\""),
            '\\' => o.push_str("\\\\"),
            '\n' => o.push_str("\\n"),
            '\r' => o.push_str("\\r"),
            '\t' => o.push_str("\\t"),
            c if (c as u32) < 0x20 => o.push_str(&format!("\\u{:04x}", c as u32)),
            c => o.push(c),
        }
    }
    o
}

#[derive(Debug, Clone)]
pub struct Item {
    pub file: String,
    pub line: usize,
    pub tag: String,
    pub text: String,
    pub author: String,
    pub days: u64,
    pub uncommitted: bool,
}

pub fn to_json(items: &[Item]) -> String {
    let rows: Vec<String> = items
        .iter()
        .map(|i| {
            format!(
                "  {{\"file\":\"{}\",\"line\":{},\"tag\":\"{}\",\"text\":\"{}\",\"author\":\"{}\",\"age_days\":{},\"uncommitted\":{}}}",
                json_escape(&i.file), i.line, json_escape(&i.tag), json_escape(&i.text),
                json_escape(&i.author), i.days, i.uncommitted
            )
        })
        .collect();
    if rows.is_empty() { "[]".into() } else { format!("[\n{}\n]", rows.join(",\n")) }
}

pub fn to_table(items: &[Item]) -> String {
    let mut out = String::new();
    for i in items {
        let age = if i.uncommitted { "new".to_string() } else { human_age(i.days) };
        out.push_str(&format!(
            "{:>6}  {:<6} {}:{}  {}  [{}]\n",
            age, i.tag, i.file, i.line, i.text, i.author
        ));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    fn tags() -> Vec<String> { DEFAULT_TAGS.iter().map(|s| s.to_string()).collect() }

    #[test] fn age_units() {
        assert_eq!(parse_age("90d"), Ok(90));
        assert_eq!(parse_age("2w"), Ok(14));
        assert_eq!(parse_age("6m"), Ok(180));
        assert_eq!(parse_age("1y"), Ok(365));
        assert_eq!(parse_age("45"), Ok(45));
    }
    #[test] fn age_invalid() {
        assert!(parse_age("").is_err());
        assert!(parse_age("abc").is_err());
        assert!(parse_age("d").is_err());
        assert!(parse_age("-3d").is_err());
        assert!(parse_age("1.5y").is_err());
        assert!(parse_age("99999999999999999999d").is_err());
        assert!(parse_age("18446744073709551615y").is_err());
    }
    #[test] fn tag_in_comment() {
        let r = find_tag("let x = 1; // TODO: fix this later", &tags()).unwrap();
        assert_eq!(r, ("TODO".into(), "fix this later".into()));
        assert_eq!(find_tag("# FIXME handle empty", &tags()).unwrap().1, "handle empty");
        assert_eq!(find_tag("/* HACK - ugly */", &tags()).unwrap().1, "ugly");
    }
    #[test] fn tag_not_in_code_or_substring() {
        assert!(find_tag("let TODO = 3;", &tags()).is_none());
        assert!(find_tag("// TODOS are listed elsewhere", &tags()).is_none());
        assert!(find_tag("// the mastodon app", &tags()).is_none());
        assert!(find_tag("// todo lowercase ignored", &tags()).is_none());
        assert!(find_tag("", &tags()).is_none());
    }
    #[test] fn tag_empty_text() {
        assert_eq!(find_tag("// TODO", &tags()).unwrap().1, "");
    }
    #[test] fn custom_tags() {
        let t = vec!["NOTE".to_string()];
        assert!(find_tag("// NOTE: x", &t).is_some());
        assert!(find_tag("// TODO: x", &t).is_none());
    }
    #[test] fn unicode_line_does_not_panic() {
        assert!(find_tag("// é TODO: café ☕", &tags()).is_some());
        assert!(find_tag("日本語 # 漢字", &tags()).is_none());
    }
    #[test] fn scan_numbers_lines() {
        let h = scan_text("a\n// TODO one\nb\n# FIXME two\n", &tags());
        assert_eq!(h.len(), 2);
        assert_eq!((h[0].line, h[1].line), (2, 4));
        assert!(scan_text("", &tags()).is_empty());
    }
    #[test] fn blame_parse() {
        let sha1 = "a".repeat(40);
        let sha0 = "0".repeat(40);
        let out = format!("{sha1} 1 1 2\nauthor Ann Lee\nauthor-time 1000000\nsummary x\nfilename f\n\tline one\n{sha1} 2 2\n\tline two\n{sha0} 3 3 1\nauthor Not Committed Yet\nauthor-time 5\nfilename f\n\tnew\n");
        let m = parse_blame(&out);
        assert_eq!(m[&1].author, "Ann Lee");
        assert_eq!(m[&2].time, Some(1_000_000));
        assert_eq!(m[&3].time, None);
        assert!(parse_blame("").is_empty());
        assert!(parse_blame("garbage\nmore garbage").is_empty());
    }
    #[test] fn ages() {
        assert_eq!(age_days(86_400 * 10, Some(0)), 10);
        assert_eq!(age_days(0, Some(100)), 0);
        assert_eq!(age_days(100, None), 0);
        assert_eq!(human_age(5), "5d");
        assert_eq!(human_age(90), "3m");
        assert_eq!(human_age(800), "2.2y");
    }
    #[test] fn json_output() {
        assert_eq!(to_json(&[]), "[]");
        let i = Item { file: "a\"b".into(), line: 3, tag: "TODO".into(), text: "x\ty\\".into(),
            author: "Z".into(), days: 4, uncommitted: false };
        let j = to_json(&[i]);
        assert!(j.contains("a\\\"b") && j.contains("x\\ty\\\\") && j.contains("\"age_days\":4"));
    }
}
