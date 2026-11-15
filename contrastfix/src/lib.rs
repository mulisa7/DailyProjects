//! WCAG 2.x contrast checking plus a "nearest passing colour" search.

use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Rgb {
    pub r: u8,
    pub g: u8,
    pub b: u8,
}

#[derive(Debug, PartialEq, Eq)]
pub enum ParseError {
    Empty,
    BadHex(String),
    BadRgb(String),
    UnknownName(String),
    WrongFieldCount { line: usize, found: usize },
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ParseError::Empty => write!(f, "empty colour value"),
            ParseError::BadHex(s) => write!(f, "invalid hex colour '{}' (use #rgb or #rrggbb)", s),
            ParseError::BadRgb(s) => write!(f, "invalid rgb() value '{}' (use rgb(0-255, 0-255, 0-255))", s),
            ParseError::UnknownName(s) => write!(f, "unknown colour '{}'", s),
            ParseError::WrongFieldCount { line, found } => write!(
                f,
                "line {}: expected 'FOREGROUND BACKGROUND [label]' but found {} field(s)",
                line, found
            ),
        }
    }
}

impl std::error::Error for ParseError {}

const NAMES: &[(&str, (u8, u8, u8))] = &[
    ("black", (0, 0, 0)),
    ("white", (255, 255, 255)),
    ("red", (255, 0, 0)),
    ("green", (0, 128, 0)),
    ("blue", (0, 0, 255)),
    ("yellow", (255, 255, 0)),
    ("gray", (128, 128, 128)),
    ("grey", (128, 128, 128)),
    ("orange", (255, 165, 0)),
    ("purple", (128, 0, 128)),
    ("navy", (0, 0, 128)),
    ("silver", (192, 192, 192)),
];

pub fn parse_color(input: &str) -> Result<Rgb, ParseError> {
    let s = input.trim();
    if s.is_empty() {
        return Err(ParseError::Empty);
    }
    if let Some(hex) = s.strip_prefix('#') {
        if !hex.chars().all(|c| c.is_ascii_hexdigit()) {
            return Err(ParseError::BadHex(s.to_string()));
        }
        let h = |i: usize, n: usize| u8::from_str_radix(&hex[i..i + n], 16).unwrap();
        return match hex.len() {
            3 => Ok(Rgb { r: h(0, 1) * 17, g: h(1, 1) * 17, b: h(2, 1) * 17 }),
            6 => Ok(Rgb { r: h(0, 2), g: h(2, 2), b: h(4, 2) }),
            _ => Err(ParseError::BadHex(s.to_string())),
        };
    }
    let lower = s.to_ascii_lowercase();
    if let Some(rest) = lower.strip_prefix("rgb(") {
        let inner = rest.strip_suffix(')').ok_or_else(|| ParseError::BadRgb(s.to_string()))?;
        let parts: Vec<&str> = inner.split(',').collect();
        if parts.len() != 3 {
            return Err(ParseError::BadRgb(s.to_string()));
        }
        let mut v = [0u8; 3];
        for (i, p) in parts.iter().enumerate() {
            v[i] = p.trim().parse::<u8>().map_err(|_| ParseError::BadRgb(s.to_string()))?;
        }
        return Ok(Rgb { r: v[0], g: v[1], b: v[2] });
    }
    NAMES
        .iter()
        .find(|(n, _)| *n == lower)
        .map(|(_, (r, g, b))| Rgb { r: *r, g: *g, b: *b })
        .ok_or_else(|| ParseError::UnknownName(s.to_string()))
}

pub fn to_hex(c: Rgb) -> String {
    format!("#{:02x}{:02x}{:02x}", c.r, c.g, c.b)
}

fn channel(v: u8) -> f64 {
    let s = v as f64 / 255.0;
    if s <= 0.03928 {
        s / 12.92
    } else {
        ((s + 0.055) / 1.055).powf(2.4)
    }
}

pub fn luminance(c: Rgb) -> f64 {
    0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b)
}

pub fn contrast_ratio(a: Rgb, b: Rgb) -> f64 {
    let (la, lb) = (luminance(a), luminance(b));
    let (hi, lo) = if la >= lb { (la, lb) } else { (lb, la) };
    (hi + 0.05) / (lo + 0.05)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Level {
    Aa,
    Aaa,
}

/// Minimum ratio required. Large text is 18pt, or 14pt bold, and up.
pub fn required_ratio(level: Level, large: bool) -> f64 {
    match (level, large) {
        (Level::Aa, false) => 4.5,
        (Level::Aa, true) => 3.0,
        (Level::Aaa, false) => 7.0,
        (Level::Aaa, true) => 4.5,
    }
}

fn rgb_to_hsl(c: Rgb) -> (f64, f64, f64) {
    let (r, g, b) = (c.r as f64 / 255.0, c.g as f64 / 255.0, c.b as f64 / 255.0);
    let max = r.max(g).max(b);
    let min = r.min(g).min(b);
    let l = (max + min) / 2.0;
    let d = max - min;
    if d == 0.0 {
        return (0.0, 0.0, l);
    }
    let s = d / (1.0 - (2.0 * l - 1.0).abs());
    let h = if max == r {
        ((g - b) / d).rem_euclid(6.0)
    } else if max == g {
        (b - r) / d + 2.0
    } else {
        (r - g) / d + 4.0
    };
    (h * 60.0, s, l)
}

fn hsl_to_rgb(h: f64, s: f64, l: f64) -> Rgb {
    let c = (1.0 - (2.0 * l - 1.0).abs()) * s;
    let x = c * (1.0 - ((h / 60.0) % 2.0 - 1.0).abs());
    let m = l - c / 2.0;
    let (r, g, b) = match (h / 60.0) as u32 {
        0 => (c, x, 0.0),
        1 => (x, c, 0.0),
        2 => (0.0, c, x),
        3 => (0.0, x, c),
        4 => (x, 0.0, c),
        _ => (c, 0.0, x),
    };
    let q = |v: f64| ((v + m) * 255.0).round().clamp(0.0, 255.0) as u8;
    Rgb { r: q(r), g: q(g), b: q(b) }
}

/// Finds the colour closest in HSL lightness to `fg` (same hue and saturation)
/// that reaches `target` contrast on `bg`. Returns None when no lightness works.
pub fn suggest_foreground(fg: Rgb, bg: Rgb, target: f64) -> Option<Rgb> {
    if contrast_ratio(fg, bg) >= target {
        return Some(fg);
    }
    let (h, s, l) = rgb_to_hsl(fg);
    let steps = 1000;
    for i in 1..=steps {
        let delta = i as f64 / steps as f64;
        let mut candidates = Vec::new();
        for nl in [l - delta, l + delta] {
            if (0.0..=1.0).contains(&nl) {
                let c = hsl_to_rgb(h, s, nl);
                if contrast_ratio(c, bg) >= target {
                    candidates.push((contrast_ratio(c, bg), c));
                }
            }
        }
        // Prefer the candidate with the lower ratio: the smaller visual change.
        candidates.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap());
        if let Some((_, c)) = candidates.first() {
            return Some(*c);
        }
    }
    None
}

#[derive(Debug, PartialEq)]
pub struct Pair {
    pub fg: Rgb,
    pub bg: Rgb,
    pub label: String,
}

/// Parses lines of `FOREGROUND BACKGROUND [label...]`. Blank lines and lines
/// starting with `//` are skipped. `rgb(...)` values may not contain spaces here
/// unless written without them, e.g. rgb(10,20,30).
pub fn parse_pairs(text: &str) -> Result<Vec<Pair>, String> {
    let mut out = Vec::new();
    for (i, raw) in text.lines().enumerate() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with("//") {
            continue;
        }
        let fields: Vec<&str> = line.split_whitespace().collect();
        if fields.len() < 2 {
            return Err(ParseError::WrongFieldCount { line: i + 1, found: fields.len() }.to_string());
        }
        let fg = parse_color(fields[0]).map_err(|e| format!("line {}: {}", i + 1, e))?;
        let bg = parse_color(fields[1]).map_err(|e| format!("line {}: {}", i + 1, e))?;
        out.push(Pair { fg, bg, label: fields[2..].join(" ") });
    }
    Ok(out)
}

#[derive(Debug)]
pub struct Row {
    pub label: String,
    pub fg: Rgb,
    pub bg: Rgb,
    pub ratio: f64,
    pub required: f64,
    pub pass: bool,
    pub suggestion: Option<Rgb>,
}

pub fn evaluate(pairs: &[Pair], level: Level, large: bool, fix: bool) -> Vec<Row> {
    let required = required_ratio(level, large);
    pairs
        .iter()
        .map(|p| {
            let ratio = contrast_ratio(p.fg, p.bg);
            let pass = ratio >= required;
            let suggestion = if !pass && fix { suggest_foreground(p.fg, p.bg, required) } else { None };
            Row { label: p.label.clone(), fg: p.fg, bg: p.bg, ratio, required, pass, suggestion }
        })
        .collect()
}
