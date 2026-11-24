//! robots.txt parsing and matching following RFC 9309 (longest match wins,
//! Allow wins ties, `*` and `$` wildcards in paths).

#[derive(Debug, Clone, PartialEq)]
pub struct Rule {
    pub allow: bool,
    pub pattern: String,
    pub line: usize,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Group {
    /// Lowercased user-agent tokens.
    pub agents: Vec<String>,
    pub rules: Vec<Rule>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Verdict {
    pub allowed: bool,
    /// The rule that decided the outcome, if any.
    pub rule: Option<Rule>,
    /// Why there is no rule (or a note about the decision).
    pub note: String,
}

/// Parse robots.txt text into groups. Unknown directives are ignored.
pub fn parse(text: &str) -> Vec<Group> {
    let text = text.strip_prefix('\u{feff}').unwrap_or(text);
    let mut groups: Vec<Group> = Vec::new();
    let mut last_was_agent = false;
    for (i, raw) in text.lines().enumerate() {
        let line = raw.split('#').next().unwrap_or("").trim();
        if line.is_empty() {
            continue;
        }
        let Some((key, value)) = line.split_once(':') else { continue };
        let key = key.trim().to_ascii_lowercase();
        let value = value.trim();
        match key.as_str() {
            "user-agent" => {
                if value.is_empty() {
                    continue;
                }
                if !last_was_agent || groups.is_empty() {
                    groups.push(Group { agents: Vec::new(), rules: Vec::new() });
                }
                groups.last_mut().unwrap().agents.push(value.to_ascii_lowercase());
                last_was_agent = true;
            }
            "allow" | "disallow" => {
                last_was_agent = false;
                if let Some(g) = groups.last_mut() {
                    // An empty Disallow means "nothing is disallowed"; an empty
                    // Allow is equally a no-op. Neither creates a rule.
                    if !value.is_empty() {
                        g.rules.push(Rule {
                            allow: key == "allow",
                            pattern: normalize(value),
                            line: i + 1,
                        });
                    }
                }
            }
            _ => {
                // sitemap, crawl-delay, host...: do not break a group
            }
        }
    }
    groups
}

/// Uppercase the hex digits of percent escapes so %2f and %2F compare equal.
fn normalize(s: &str) -> String {
    let b: Vec<char> = s.chars().collect();
    let mut out = String::new();
    let mut i = 0;
    while i < b.len() {
        if b[i] == '%' && i + 2 < b.len() && b[i + 1].is_ascii_hexdigit() && b[i + 2].is_ascii_hexdigit() {
            out.push('%');
            out.push(b[i + 1].to_ascii_uppercase());
            out.push(b[i + 2].to_ascii_uppercase());
            i += 3;
        } else {
            out.push(b[i]);
            i += 1;
        }
    }
    out
}

/// Does `pattern` (with `*` and a trailing `$`) match the start of `path`?
pub fn pattern_matches(pattern: &str, path: &str) -> bool {
    let (pat, anchored) = match pattern.strip_suffix('$') {
        Some(p) => (p, true),
        None => (pattern, false),
    };
    let p: Vec<char> = pat.chars().collect();
    let t: Vec<char> = path.chars().collect();
    let (mut pi, mut ti) = (0usize, 0usize);
    let mut star: Option<(usize, usize)> = None;
    loop {
        if pi == p.len() {
            if !anchored || ti == t.len() {
                return true;
            }
        } else if p[pi] == '*' {
            star = Some((pi, ti));
            pi += 1;
            continue;
        } else if ti < t.len() && p[pi] == t[ti] {
            pi += 1;
            ti += 1;
            continue;
        }
        // mismatch: backtrack to the last star, consuming one more char
        match star {
            Some((sp, st)) if st < t.len() => {
                star = Some((sp, st + 1));
                pi = sp + 1;
                ti = st + 1;
            }
            _ => return false,
        }
    }
}

/// Pick the group for a user agent: the longest group token that is a
/// case-insensitive prefix of the agent; otherwise `*`. Groups naming the
/// same token are merged.
pub fn rules_for<'a>(groups: &'a [Group], agent: &str) -> (Vec<&'a Rule>, Option<String>) {
    let agent = agent.to_ascii_lowercase();
    let mut best: Option<&str> = None;
    for g in groups {
        for a in &g.agents {
            if a != "*" && agent.starts_with(a.as_str()) && best.map_or(true, |b| a.len() > b.len()) {
                best = Some(a);
            }
        }
    }
    let token = best.unwrap_or("*");
    let mut rules = Vec::new();
    let mut found = false;
    for g in groups {
        if g.agents.iter().any(|a| a == token) {
            found = true;
            rules.extend(g.rules.iter());
        }
    }
    (rules, if found { Some(token.to_string()) } else { None })
}

/// Reduce a URL or path to the path-plus-query that robots rules apply to.
pub fn target_path(input: &str) -> Result<String, String> {
    let s = input.trim();
    if s.is_empty() {
        return Err("empty URL or path".into());
    }
    let rest = if let Some(idx) = s.find("://") {
        let scheme = &s[..idx];
        if scheme.is_empty() || !scheme.chars().all(|c| c.is_ascii_alphanumeric() || "+-.".contains(c)) {
            return Err(format!("not a valid URL: {s}"));
        }
        let after = &s[idx + 3..];
        match after.find(|c| c == '/' || c == '?') {
            Some(p) if after.as_bytes()[p] == b'/' => after[p..].to_string(),
            Some(p) => format!("/{}", &after[p..]),
            None => {
                if after.is_empty() {
                    return Err(format!("URL has no host: {s}"));
                }
                "/".to_string()
            }
        }
    } else if s.starts_with('/') {
        s.to_string()
    } else {
        return Err(format!("expected a full URL or a path starting with '/': {s}"));
    };
    let rest = rest.split('#').next().unwrap_or("").to_string();
    Ok(normalize(&rest))
}

/// Decide whether `agent` may fetch `path` (already reduced by `target_path`).
pub fn check(groups: &[Group], agent: &str, path: &str) -> Verdict {
    if path == "/robots.txt" {
        return Verdict { allowed: true, rule: None, note: "robots.txt itself is always fetchable".into() };
    }
    let (rules, token) = rules_for(groups, agent);
    let mut best: Option<&Rule> = None;
    for r in rules {
        if pattern_matches(&r.pattern, path) {
            best = match best {
                None => Some(r),
                Some(b) => {
                    let (rl, bl) = (r.pattern.chars().count(), b.pattern.chars().count());
                    if rl > bl || (rl == bl && r.allow && !b.allow) { Some(r) } else { Some(b) }
                }
            };
        }
    }
    match best {
        Some(r) => Verdict {
            allowed: r.allow,
            rule: Some(r.clone()),
            note: format!("group '{}'", token.unwrap_or_default()),
        },
        None => Verdict {
            allowed: true,
            rule: None,
            note: match token {
                Some(t) => format!("no rule in group '{t}' matches"),
                None => "no group applies to this agent".into(),
            },
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(txt: &str, ua: &str, p: &str) -> bool {
        check(&parse(txt), ua, p).allowed
    }

    #[test]
    fn basic_disallow() {
        let t = "User-agent: *\nDisallow: /private/\n";
        assert!(!v(t, "bot", "/private/a"));
        assert!(v(t, "bot", "/public"));
        assert!(v(t, "bot", "/private")); // no trailing slash: not matched
    }

    #[test]
    fn empty_disallow_allows_all() {
        assert!(v("User-agent: *\nDisallow:\n", "bot", "/x"));
    }

    #[test]
    fn longest_match_beats_order() {
        let t = "User-agent: *\nDisallow: /a/\nAllow: /a/b/\n";
        assert!(v(t, "bot", "/a/b/c"));
        let t2 = "User-agent: *\nAllow: /a/b/\nDisallow: /a/\n";
        assert!(v(t2, "bot", "/a/b/c"));
        assert!(!v(t2, "bot", "/a/z"));
    }

    #[test]
    fn tie_goes_to_allow() {
        let t = "User-agent: *\nDisallow: /p\nAllow: /p\n";
        assert!(v(t, "bot", "/p"));
    }

    #[test]
    fn wildcards_and_anchor() {
        let t = "User-agent: *\nDisallow: /*.pdf$\nDisallow: /tmp*/cache\n";
        assert!(!v(t, "bot", "/docs/a.pdf"));
        assert!(v(t, "bot", "/docs/a.pdf?x=1"));
        assert!(v(t, "bot", "/docs/a.pdfx"));
        assert!(!v(t, "bot", "/tmp123/cache/x"));
    }

    #[test]
    fn star_backtracking() {
        assert!(pattern_matches("/a*b*c", "/aXbYbZc"));
        assert!(!pattern_matches("/a*b*c", "/aXbYbZ"));
        assert!(pattern_matches("/*", "/anything"));
        assert!(pattern_matches("/a$", "/a"));
        assert!(!pattern_matches("/a$", "/ab"));
    }

    #[test]
    fn specific_agent_wins_over_star() {
        let t = "User-agent: *\nDisallow: /\n\nUser-agent: googlebot\nDisallow: /nogoogle/\n";
        assert!(v(t, "Googlebot/2.1", "/open"));
        assert!(!v(t, "Googlebot", "/nogoogle/x"));
        assert!(!v(t, "otherbot", "/open"));
    }

    #[test]
    fn longest_agent_token_chosen() {
        let t = "User-agent: googlebot\nDisallow: /a\n\nUser-agent: googlebot-image\nDisallow: /b\n";
        assert!(v(t, "Googlebot-Image", "/a"));
        assert!(!v(t, "Googlebot-Image", "/b"));
    }

    #[test]
    fn stacked_agents_share_rules() {
        let t = "User-agent: a\nUser-agent: b\nDisallow: /x\n";
        assert!(!v(t, "a", "/x"));
        assert!(!v(t, "b", "/x"));
        assert!(v(t, "c", "/x"));
    }

    #[test]
    fn same_agent_groups_merge() {
        let t = "User-agent: a\nDisallow: /x\n\nUser-agent: a\nDisallow: /y\n";
        assert!(!v(t, "a", "/x"));
        assert!(!v(t, "a", "/y"));
    }

    #[test]
    fn comments_bom_crlf_case() {
        let t = "\u{feff}USER-AGENT: * # all\r\nDISALLOW: /x # no\r\nSitemap: http://e/s.xml\r\n";
        assert!(!v(t, "bot", "/x"));
    }

    #[test]
    fn sitemap_does_not_end_group() {
        let t = "User-agent: *\nSitemap: http://e/s.xml\nDisallow: /x\n";
        assert!(!v(t, "bot", "/x"));
    }

    #[test]
    fn empty_file_allows() {
        let r = check(&parse(""), "bot", "/x");
        assert!(r.allowed && r.rule.is_none());
    }

    #[test]
    fn rules_before_any_agent_ignored() {
        assert!(v("Disallow: /x\n", "bot", "/x"));
    }

    #[test]
    fn robots_txt_always_allowed() {
        assert!(v("User-agent: *\nDisallow: /\n", "bot", "/robots.txt"));
    }

    #[test]
    fn percent_case_insensitive() {
        let t = "User-agent: *\nDisallow: /a%2fb\n";
        let p = target_path("http://h/a%2Fb").unwrap();
        assert!(!v(t, "bot", &p));
    }

    #[test]
    fn target_path_forms() {
        assert_eq!(target_path("https://ex.com").unwrap(), "/");
        assert_eq!(target_path("https://ex.com?q=1").unwrap(), "/?q=1");
        assert_eq!(target_path("https://ex.com/a/b?q=1#frag").unwrap(), "/a/b?q=1");
        assert_eq!(target_path("/x").unwrap(), "/x");
        assert!(target_path("x/y").is_err());
        assert!(target_path("").is_err());
        assert!(target_path("https://").is_err());
        assert!(target_path("://host/x").is_err());
    }
}
