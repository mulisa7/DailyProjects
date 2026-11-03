//! Classification and permission rules. No filesystem access except in `scan`.
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    SshPrivateKey,
    EnvFile,
    CloudCredentials,
    PackageToken,
    SshDir,
}

impl Kind {
    pub fn label(self) -> &'static str {
        match self {
            Kind::SshPrivateKey => "ssh private key",
            Kind::EnvFile => "env file",
            Kind::CloudCredentials => "cloud credentials",
            Kind::PackageToken => "package registry token",
            Kind::SshDir => "ssh directory",
        }
    }
    /// Highest mode we accept for this kind.
    pub fn max_mode(self) -> u32 {
        match self {
            Kind::SshDir => 0o700,
            _ => 0o600,
        }
    }
}

/// Decide what kind of secret file a path is, from its name and parent folder only.
pub fn classify(path: &Path, is_dir: bool) -> Option<Kind> {
    let name = path.file_name()?.to_str()?;
    let parent = path.parent().and_then(|p| p.file_name()).and_then(|n| n.to_str()).unwrap_or("");
    if is_dir {
        return if name == ".ssh" { Some(Kind::SshDir) } else { None };
    }
    if name == ".env" || name.starts_with(".env.") || name.ends_with(".env") {
        let lower = name.to_lowercase();
        if lower.ends_with(".example") || lower.ends_with(".sample") || lower.ends_with(".template") {
            return None;
        }
        return Some(Kind::EnvFile);
    }
    if parent == ".ssh" {
        if name.ends_with(".pub") || matches!(name, "known_hosts" | "known_hosts.old" | "config" | "authorized_keys") {
            return None;
        }
        if name.starts_with("id_") || name.ends_with(".pem") || name.ends_with(".key") {
            return Some(Kind::SshPrivateKey);
        }
        return None;
    }
    if name.ends_with(".pem") || name.ends_with(".key") {
        return Some(Kind::SshPrivateKey);
    }
    match (parent, name) {
        (".aws", "credentials") => Some(Kind::CloudCredentials),
        (".docker", "config.json") => Some(Kind::CloudCredentials),
        (".kube", "config") => Some(Kind::CloudCredentials),
        (".azure", "accessTokens.json") => Some(Kind::CloudCredentials),
        (_, ".npmrc") | (_, ".pypirc") | (_, ".netrc") | (_, ".git-credentials") => Some(Kind::PackageToken),
        _ => None,
    }
}

/// Bits set in `mode` that are not allowed by `max`.
pub fn excess_bits(mode: u32, max: u32) -> u32 {
    (mode & 0o777) & !max
}

/// Which audience can reach the file with this mode.
pub fn exposure(mode: u32) -> &'static str {
    let m = mode & 0o777;
    if m & 0o007 != 0 {
        "world"
    } else if m & 0o070 != 0 {
        "group"
    } else {
        "owner"
    }
}

pub fn fmt_mode(mode: u32) -> String {
    format!("{:04o}", mode & 0o7777)
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Finding {
    pub path: PathBuf,
    pub kind: Kind,
    pub mode: u32,
    pub fix_mode: u32,
    pub audience: &'static str,
}

#[derive(Debug, Default)]
pub struct Report {
    pub checked: usize,
    pub findings: Vec<Finding>,
    pub errors: Vec<String>,
}

const SKIP_DIRS: &[&str] = &[".git", "node_modules", "target", ".venv", "venv", "__pycache__"];

pub fn scan(root: &Path, max_depth: usize) -> Report {
    let mut r = Report::default();
    walk(root, 0, max_depth, &mut r);
    r.findings.sort_by(|a, b| a.path.cmp(&b.path));
    r
}

fn walk(dir: &Path, depth: usize, max_depth: usize, r: &mut Report) {
    if depth == 0 {
        check(dir, true, r);
    }
    let rd = match fs::read_dir(dir) {
        Ok(rd) => rd,
        Err(e) => {
            r.errors.push(format!("{}: {}", dir.display(), e));
            return;
        }
    };
    for entry in rd {
        let entry = match entry {
            Ok(e) => e,
            Err(e) => {
                r.errors.push(format!("{}: {}", dir.display(), e));
                continue;
            }
        };
        let path = entry.path();
        let ft = match entry.file_type() {
            Ok(t) => t,
            Err(e) => {
                r.errors.push(format!("{}: {}", path.display(), e));
                continue;
            }
        };
        if ft.is_symlink() {
            continue; // never follow links; their own mode is meaningless
        }
        if ft.is_dir() {
            check(&path, true, r);
            let name = entry.file_name();
            if depth < max_depth && !SKIP_DIRS.iter().any(|s| name.to_str() == Some(*s)) {
                walk(&path, depth + 1, max_depth, r);
            }
        } else if ft.is_file() {
            check(&path, false, r);
        }
    }
}

fn check(path: &Path, is_dir: bool, r: &mut Report) {
    let Some(kind) = classify(path, is_dir) else { return };
    let meta = match fs::metadata(path) {
        Ok(m) => m,
        Err(e) => {
            r.errors.push(format!("{}: {}", path.display(), e));
            return;
        }
    };
    r.checked += 1;
    let mode = meta.permissions().mode() & 0o777;
    let bad = excess_bits(mode, kind.max_mode());
    if bad != 0 {
        r.findings.push(Finding { path: path.to_path_buf(), kind, mode, fix_mode: mode & !bad, audience: exposure(mode) });
    }
}

/// Apply the fix (chmod to the stripped mode). Returns an error string on failure.
pub fn apply_fix(f: &Finding) -> Result<(), String> {
    fs::set_permissions(&f.path, fs::Permissions::from_mode(f.fix_mode)).map_err(|e| format!("{}: {}", f.path.display(), e))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classifies_names() {
        let c = |p: &str, d| classify(Path::new(p), d);
        assert_eq!(c("/h/.ssh/id_ed25519", false), Some(Kind::SshPrivateKey));
        assert_eq!(c("/h/.ssh/id_ed25519.pub", false), None);
        assert_eq!(c("/h/.ssh/known_hosts", false), None);
        assert_eq!(c("/h/.ssh", true), Some(Kind::SshDir));
        assert_eq!(c("/app/.env", false), Some(Kind::EnvFile));
        assert_eq!(c("/app/.env.production", false), Some(Kind::EnvFile));
        assert_eq!(c("/app/.env.example", false), None);
        assert_eq!(c("/app/prod.env", false), Some(Kind::EnvFile));
        assert_eq!(c("/h/.aws/credentials", false), Some(Kind::CloudCredentials));
        assert_eq!(c("/h/other/credentials", false), None);
        assert_eq!(c("/h/.npmrc", false), Some(Kind::PackageToken));
        assert_eq!(c("/x/server.pem", false), Some(Kind::SshPrivateKey));
        assert_eq!(c("/x/readme.md", false), None);
        assert_eq!(c("/x/.envrc", false), None);
        assert_eq!(c("/x/data", true), None);
    }

    #[test]
    fn mode_math() {
        assert_eq!(excess_bits(0o644, 0o600), 0o044);
        assert_eq!(excess_bits(0o600, 0o600), 0);
        assert_eq!(excess_bits(0o400, 0o600), 0);
        assert_eq!(excess_bits(0o755, 0o700), 0o055);
        assert_eq!(exposure(0o640), "group");
        assert_eq!(exposure(0o604), "world");
        assert_eq!(exposure(0o600), "owner");
        assert_eq!(fmt_mode(0o600), "0600");
    }
}
