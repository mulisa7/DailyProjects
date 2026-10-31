//! Folder comparison by content.

pub mod sha256;

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io;
use std::path::Path;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Entry {
    pub size: u64,
}

#[derive(Debug, Default)]
pub struct Scan {
    /// relative path (always '/' separated) -> entry
    pub files: BTreeMap<String, Entry>,
    pub skipped_links: usize,
    pub errors: Vec<String>,
}

#[derive(Debug, Default, PartialEq, Eq)]
pub struct Report {
    pub identical: usize,
    pub changed: Vec<String>,
    pub moved: Vec<(String, String)>,
    pub only_a: Vec<String>,
    pub only_b: Vec<String>,
    pub errors: Vec<String>,
    pub skipped_links: usize,
}

impl Report {
    pub fn has_differences(&self) -> bool {
        !(self.changed.is_empty() && self.moved.is_empty() && self.only_a.is_empty() && self.only_b.is_empty())
    }
}

/// Walk `root`, collecting regular files. Names in `ignore` are skipped at any depth.
pub fn scan(root: &Path, ignore: &[String]) -> Scan {
    let mut out = Scan::default();
    walk(root, "", ignore, &mut out);
    out
}

fn walk(dir: &Path, prefix: &str, ignore: &[String], out: &mut Scan) {
    let rd = match fs::read_dir(dir) {
        Ok(r) => r,
        Err(e) => {
            out.errors.push(format!("{}: {}", dir.display(), e));
            return;
        }
    };
    for item in rd {
        let item = match item {
            Ok(i) => i,
            Err(e) => {
                out.errors.push(format!("{}: {}", dir.display(), e));
                continue;
            }
        };
        let name = item.file_name().to_string_lossy().into_owned();
        if ignore.iter().any(|i| i == &name) {
            continue;
        }
        let rel = if prefix.is_empty() { name.clone() } else { format!("{}/{}", prefix, name) };
        let ft = match item.file_type() {
            Ok(t) => t,
            Err(e) => {
                out.errors.push(format!("{}: {}", item.path().display(), e));
                continue;
            }
        };
        if ft.is_symlink() {
            out.skipped_links += 1;
        } else if ft.is_dir() {
            walk(&item.path(), &rel, ignore, out);
        } else if ft.is_file() {
            match item.metadata() {
                Ok(m) => {
                    out.files.insert(rel, Entry { size: m.len() });
                }
                Err(e) => out.errors.push(format!("{}: {}", item.path().display(), e)),
            }
        }
        // sockets, fifos and devices are ignored
    }
}

fn hash_file(root: &Path, rel: &str) -> io::Result<String> {
    let f = fs::File::open(root.join(rel))?;
    sha256::hash_reader(io::BufReader::new(f))
}

/// Compare two scanned trees by content. Same-path files are hashed only when sizes match.
pub fn compare(root_a: &Path, a: &Scan, root_b: &Path, b: &Scan) -> Report {
    let mut r = Report { skipped_links: a.skipped_links + b.skipped_links, ..Default::default() };
    r.errors.extend(a.errors.iter().cloned());
    r.errors.extend(b.errors.iter().cloned());

    let mut only_a: BTreeSet<String> = BTreeSet::new();
    for (path, ea) in &a.files {
        match b.files.get(path) {
            None => {
                only_a.insert(path.clone());
            }
            Some(eb) => {
                if ea.size != eb.size {
                    r.changed.push(path.clone());
                    continue;
                }
                match (hash_file(root_a, path), hash_file(root_b, path)) {
                    (Ok(ha), Ok(hb)) => {
                        if ha == hb {
                            r.identical += 1;
                        } else {
                            r.changed.push(path.clone());
                        }
                    }
                    (ra, rb) => {
                        for (root, res) in [(root_a, ra), (root_b, rb)] {
                            if let Err(e) = res {
                                r.errors.push(format!("{}: {}", root.join(path).display(), e));
                            }
                        }
                    }
                }
            }
        }
    }
    let mut only_b: BTreeSet<String> =
        b.files.keys().filter(|p| !a.files.contains_key(*p)).cloned().collect();

    // Detect moves: an only-A file and an only-B file with identical content.
    // Only hash files whose size occurs on both sides.
    let mut by_hash_b: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut hashed_b: BTreeSet<u64> = BTreeSet::new();
    let sizes_a: BTreeSet<u64> = only_a.iter().map(|p| a.files[p].size).collect();
    for p in only_b.iter() {
        let sz = b.files[p].size;
        if sizes_a.contains(&sz) {
            hashed_b.insert(sz);
            match hash_file(root_b, p) {
                Ok(h) => by_hash_b.entry(h).or_default().push(p.clone()),
                Err(e) => r.errors.push(format!("{}: {}", root_b.join(p).display(), e)),
            }
        }
    }
    let mut moved = Vec::new();
    let mut remaining_a = Vec::new();
    for p in only_a.iter() {
        let sz = a.files[p].size;
        let mut matched = false;
        if hashed_b.contains(&sz) {
            match hash_file(root_a, p) {
                Ok(h) => {
                    if let Some(list) = by_hash_b.get_mut(&h) {
                        if !list.is_empty() {
                            let q = list.remove(0);
                            only_b.remove(&q);
                            moved.push((p.clone(), q));
                            matched = true;
                        }
                    }
                }
                Err(e) => r.errors.push(format!("{}: {}", root_a.join(p).display(), e)),
            }
        }
        if !matched {
            remaining_a.push(p.clone());
        }
    }
    r.moved = moved;
    r.only_a = remaining_a;
    r.only_b = only_b.into_iter().collect();
    r
}

pub fn json_escape(s: &str) -> String {
    let mut o = String::with_capacity(s.len() + 2);
    o.push('"');
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
    o.push('"');
    o
}

pub fn render_text(r: &Report) -> String {
    let mut s = String::new();
    let section = |s: &mut String, title: &str, items: Vec<String>| {
        if !items.is_empty() {
            s.push_str(&format!("{} ({}):\n", title, items.len()));
            for i in items {
                s.push_str(&format!("  {}\n", i));
            }
        }
    };
    section(&mut s, "Changed (same path, different content)", r.changed.clone());
    section(&mut s, "Moved or renamed (A -> B)", r.moved.iter().map(|(a, b)| format!("{} -> {}", a, b)).collect());
    section(&mut s, "Only in A", r.only_a.clone());
    section(&mut s, "Only in B", r.only_b.clone());
    section(&mut s, "Errors", r.errors.clone());
    s.push_str(&format!(
        "Summary: {} identical, {} changed, {} moved, {} only in A, {} only in B",
        r.identical,
        r.changed.len(),
        r.moved.len(),
        r.only_a.len(),
        r.only_b.len()
    ));
    if r.skipped_links > 0 {
        s.push_str(&format!(", {} symlinks skipped", r.skipped_links));
    }
    s.push('\n');
    if !r.has_differences() && r.errors.is_empty() {
        s.push_str("The folders match.\n");
    }
    s
}

pub fn render_json(r: &Report) -> String {
    let arr = |v: &[String]| format!("[{}]", v.iter().map(|x| json_escape(x)).collect::<Vec<_>>().join(","));
    let moved = format!(
        "[{}]",
        r.moved
            .iter()
            .map(|(a, b)| format!("{{\"from\":{},\"to\":{}}}", json_escape(a), json_escape(b)))
            .collect::<Vec<_>>()
            .join(",")
    );
    format!(
        "{{\"identical\":{},\"changed\":{},\"moved\":{},\"only_a\":{},\"only_b\":{},\"errors\":{},\"symlinks_skipped\":{}}}\n",
        r.identical,
        arr(&r.changed),
        moved,
        arr(&r.only_a),
        arr(&r.only_b),
        arr(&r.errors),
        r.skipped_links
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn tmp(name: &str) -> PathBuf {
        let p = std::env::temp_dir().join(format!("dirdiff-test-{}-{}", std::process::id(), name));
        let _ = fs::remove_dir_all(&p);
        fs::create_dir_all(&p).unwrap();
        p
    }

    fn put(root: &Path, rel: &str, data: &str) {
        let p = root.join(rel);
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(p, data).unwrap();
    }

    fn run(a: &Path, b: &Path) -> Report {
        let sa = scan(a, &[]);
        let sb = scan(b, &[]);
        compare(a, &sa, b, &sb)
    }

    #[test]
    fn identical_trees() {
        let (a, b) = (tmp("i-a"), tmp("i-b"));
        for r in [&a, &b] {
            put(r, "x.txt", "hello");
            put(r, "d/y.txt", "world");
        }
        let rep = run(&a, &b);
        assert_eq!(rep.identical, 2);
        assert!(!rep.has_differences());
    }

    #[test]
    fn empty_folders_match() {
        let (a, b) = (tmp("e-a"), tmp("e-b"));
        let rep = run(&a, &b);
        assert!(!rep.has_differences());
        assert_eq!(rep.identical, 0);
        assert!(render_text(&rep).contains("The folders match."));
    }

    #[test]
    fn changed_content_same_size() {
        let (a, b) = (tmp("c-a"), tmp("c-b"));
        put(&a, "f", "aaaa");
        put(&b, "f", "aaab");
        assert_eq!(run(&a, &b).changed, vec!["f"]);
    }

    #[test]
    fn changed_content_different_size() {
        let (a, b) = (tmp("cs-a"), tmp("cs-b"));
        put(&a, "f", "aa");
        put(&b, "f", "aaaa");
        assert_eq!(run(&a, &b).changed, vec!["f"]);
    }

    #[test]
    fn detects_move_and_rename() {
        let (a, b) = (tmp("m-a"), tmp("m-b"));
        put(&a, "old/name.txt", "same content");
        put(&b, "new/other.txt", "same content");
        let rep = run(&a, &b);
        assert_eq!(rep.moved, vec![("old/name.txt".to_string(), "new/other.txt".to_string())]);
        assert!(rep.only_a.is_empty() && rep.only_b.is_empty());
    }

    #[test]
    fn same_size_different_content_is_not_a_move() {
        let (a, b) = (tmp("n-a"), tmp("n-b"));
        put(&a, "one", "abcd");
        put(&b, "two", "abce");
        let rep = run(&a, &b);
        assert!(rep.moved.is_empty());
        assert_eq!(rep.only_a, vec!["one"]);
        assert_eq!(rep.only_b, vec!["two"]);
    }

    #[test]
    fn duplicates_pair_one_to_one() {
        let (a, b) = (tmp("d-a"), tmp("d-b"));
        put(&a, "a1", "dup");
        put(&b, "b1", "dup");
        put(&b, "b2", "dup");
        let rep = run(&a, &b);
        assert_eq!(rep.moved.len(), 1);
        assert_eq!(rep.only_b.len(), 1);
    }

    #[test]
    fn empty_files_are_handled() {
        let (a, b) = (tmp("z-a"), tmp("z-b"));
        put(&a, "empty1", "");
        put(&b, "empty2", "");
        assert_eq!(run(&a, &b).moved.len(), 1);
    }

    #[test]
    fn ignore_names_at_any_depth() {
        let (a, b) = (tmp("g-a"), tmp("g-b"));
        put(&a, ".git/HEAD", "x");
        put(&a, "sub/.git/HEAD", "x");
        put(&a, "k", "1");
        put(&b, "k", "1");
        let ign = vec![".git".to_string()];
        let rep = compare(&a, &scan(&a, &ign), &b, &scan(&b, &ign));
        assert!(!rep.has_differences());
    }

    #[test]
    fn missing_root_reports_error() {
        let s = scan(Path::new("/definitely/not/here"), &[]);
        assert_eq!(s.errors.len(), 1);
    }

    #[cfg(unix)]
    #[test]
    fn symlinks_are_skipped_not_followed() {
        let (a, b) = (tmp("l-a"), tmp("l-b"));
        put(&a, "real", "x");
        put(&b, "real", "x");
        std::os::unix::fs::symlink(&a, a.join("loop")).unwrap();
        let rep = run(&a, &b);
        assert_eq!(rep.skipped_links, 1);
        assert!(!rep.has_differences());
    }

    #[test]
    fn json_output_escapes() {
        let mut r = Report::default();
        r.only_a.push("we\"ird\\name\n".to_string());
        let j = render_json(&r);
        assert!(j.contains("we\\\"ird\\\\name\\n"));
    }

    #[test]
    fn unicode_names() {
        let (a, b) = (tmp("u-a"), tmp("u-b"));
        put(&a, "café/naïve.txt", "x");
        put(&b, "café/naïve.txt", "x");
        assert_eq!(run(&a, &b).identical, 1);
    }
}
