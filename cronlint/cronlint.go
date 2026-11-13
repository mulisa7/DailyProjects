package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
)

// Severity of a finding.
type Severity int

const (
	Warning Severity = iota
	Error
)

func (s Severity) String() string {
	if s == Error {
		return "error"
	}
	return "warning"
}

// Finding is one problem reported for a line.
type Finding struct {
	Line int
	Sev  Severity
	Code string
	Msg  string
}

// Options controls how a crontab is checked.
type Options struct {
	System      bool   // lines carry a user column (/etc/crontab, /etc/cron.d)
	CheckExists bool   // look up commands on the local disk
	DefaultPath string // cron's PATH when the file does not set one
}

// DefaultCronPath is what Vixie-style cron uses when PATH is not set.
const DefaultCronPath = "/usr/bin:/bin"

var macros = map[string]bool{
	"@reboot": true, "@yearly": true, "@annually": true, "@monthly": true,
	"@weekly": true, "@daily": true, "@midnight": true, "@hourly": true,
}

var monthNames = map[string]int{"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
	"jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
var dayNames = map[string]int{"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}

var envLine = regexp.MustCompile(`^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$`)

type fieldSpec struct {
	name     string
	min, max int
	names    map[string]int
}

var fields = []fieldSpec{
	{"minute", 0, 59, nil},
	{"hour", 0, 23, nil},
	{"day-of-month", 1, 31, nil},
	{"month", 1, 12, monthNames},
	{"day-of-week", 0, 7, dayNames},
}

// parseValue turns a number or a month/day name into an int.
func parseValue(s string, f fieldSpec) (int, error) {
	if n, ok := f.names[strings.ToLower(s)]; ok {
		return n, nil
	}
	if s == "" {
		return 0, fmt.Errorf("empty value")
	}
	n, err := strconv.Atoi(s)
	if err != nil || strings.HasPrefix(s, "+") || strings.HasPrefix(s, "-") {
		return 0, fmt.Errorf("%q is not a number", s)
	}
	if n < f.min || n > f.max {
		return 0, fmt.Errorf("%d is outside %d-%d", n, f.min, f.max)
	}
	return n, nil
}

// checkField validates one schedule field and returns the set of values it
// selects (nil when it is a bare wildcard) or an error description.
func checkField(text string, f fieldSpec) (map[int]bool, bool, error) {
	if text == "" {
		return nil, false, fmt.Errorf("empty %s field", f.name)
	}
	set := map[int]bool{}
	restricted := false
	for _, part := range strings.Split(text, ",") {
		if part == "" {
			return nil, false, fmt.Errorf("%s field has an empty list item", f.name)
		}
		rng, step := part, ""
		hasStep := false
		if i := strings.Index(part, "/"); i >= 0 {
			rng, step, hasStep = part[:i], part[i+1:], true
		}
		stepN := 1
		if hasStep {
			n, err := strconv.Atoi(step)
			if err != nil || n < 1 {
				return nil, false, fmt.Errorf("%s field has invalid step %q", f.name, step)
			}
			stepN = n
		}
		lo, hi := f.min, f.max
		if f.name == "day-of-week" {
			hi = 6
		}
		switch {
		case rng == "*":
			if !hasStep {
				// bare star adds everything
			} else {
				restricted = restricted || stepN > 1
			}
		case strings.Contains(rng, "-"):
			restricted = true
			ab := strings.SplitN(rng, "-", 2)
			a, err := parseValue(ab[0], f)
			if err != nil {
				return nil, false, fmt.Errorf("%s field: %v", f.name, err)
			}
			b, err := parseValue(ab[1], f)
			if err != nil {
				return nil, false, fmt.Errorf("%s field: %v", f.name, err)
			}
			if a > b {
				return nil, false, fmt.Errorf("%s field: range %s is backwards", f.name, rng)
			}
			lo, hi = a, b
		default:
			restricted = true
			a, err := parseValue(rng, f)
			if err != nil {
				return nil, false, fmt.Errorf("%s field: %v", f.name, err)
			}
			if hasStep {
				lo, hi = a, f.max
			} else {
				lo, hi = a, a
			}
		}
		for v := lo; v <= hi; v += stepN {
			if f.name == "day-of-week" && v == 7 {
				v = 0
				set[0] = true
				break
			}
			set[v] = true
		}
	}
	if !restricted {
		return nil, false, nil
	}
	return set, true, nil
}

var daysInMonth = map[int]int{1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}

// Check lints crontab text and returns findings sorted by line.
func Check(content string, opt Options) []Finding {
	var out []Finding
	add := func(line int, sev Severity, code, format string, a ...interface{}) {
		out = append(out, Finding{line, sev, code, fmt.Sprintf(format, a...)})
	}
	if opt.DefaultPath == "" {
		opt.DefaultPath = DefaultCronPath
	}
	if content == "" {
		return out
	}
	if !strings.HasSuffix(content, "\n") {
		n := strings.Count(content, "\n") + 1
		if strings.TrimSpace(content[strings.LastIndex(content, "\n")+1:]) != "" {
			add(n, Error, "no-newline", "last line has no trailing newline; cron silently ignores it")
		}
	}
	content = strings.ReplaceAll(content, "\r\n", "\n")
	lines := strings.Split(content, "\n")
	env := map[string]string{}
	seen := map[string]int{}
	jobs := 0
	for i, raw := range lines {
		no := i + 1
		if strings.Contains(raw, "\r") {
			add(no, Error, "carriage-return", "line contains a carriage return (file saved with Windows line endings?)")
		}
		line := strings.TrimSpace(raw)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if m := envLine.FindStringSubmatch(line); m != nil && !startsWithSchedule(line) {
			val := strings.TrimSpace(m[2])
			if len(val) >= 2 && (val[0] == '"' || val[0] == '\'') && val[len(val)-1] == val[0] {
				val = val[1 : len(val)-1]
			}
			env[m[1]] = val
			if strings.Contains(val, "$") {
				add(no, Warning, "env-expansion", "cron does not expand variables in %s=...; $ is kept literally", m[1])
			}
			continue
		}
		jobs++
		fs := strings.Fields(line)
		var sched []string
		rest := []string{}
		if strings.HasPrefix(fs[0], "@") {
			if !macros[strings.ToLower(fs[0])] {
				add(no, Error, "bad-macro", "unknown schedule shortcut %s", fs[0])
				continue
			}
			sched, rest = fs[:1], fs[1:]
		} else {
			if len(fs) < 5 {
				add(no, Error, "few-fields", "expected 5 schedule fields and a command, found %d words", len(fs))
				continue
			}
			sched, rest = fs[:5], fs[5:]
		}
		if !opt.System {
			// nothing to do
		} else if len(rest) > 0 {
			rest = rest[1:]
		}
		if len(rest) == 0 {
			add(no, Error, "no-command", "schedule has no command")
			continue
		}
		cmdStart := commandOffset(line, len(sched), opt.System)
		cmd := strings.TrimSpace(line[cmdStart:])

		ok := true
		sets := make([]map[int]bool, 5)
		restr := make([]bool, 5)
		if len(sched) == 5 {
			for k, f := range fields {
				s, r, err := checkField(sched[k], f)
				if err != nil {
					add(no, Error, "bad-field", "%v", err)
					ok = false
					continue
				}
				sets[k], restr[k] = s, r
			}
		}
		if ok && len(sched) == 5 {
			if restr[2] && restr[4] {
				add(no, Warning, "dom-dow-or", "both day-of-month and day-of-week are restricted; cron runs on days matching either, not both")
			}
			if restr[2] && restr[3] && !restr[4] {
				possible := false
				for m := range sets[3] {
					for d := range sets[2] {
						if d <= daysInMonth[m] {
							possible = true
						}
					}
				}
				if sets[3] != nil && sets[2] != nil && !possible {
					add(no, Warning, "never-runs", "no selected day exists in the selected months; this job never runs")
				}
			}
		}
		checkCommand(no, cmd, env, opt, add)

		key := strings.Join(sched, " ") + "\x00" + cmd
		if prev, dup := seen[key]; dup {
			add(no, Warning, "duplicate", "same schedule and command as line %d", prev)
		} else {
			seen[key] = no
		}
	}
	if jobs == 0 && len(out) == 0 {
		// not an error: empty crontab is valid
	}
	sortFindings(out)
	return out
}

func startsWithSchedule(line string) bool {
	return strings.HasPrefix(line, "@") || (len(line) > 0 && (line[0] == '*' || (line[0] >= '0' && line[0] <= '9')))
}

// commandOffset returns the byte offset in line where the command starts.
func commandOffset(line string, schedWords int, system bool) int {
	words := schedWords
	if system {
		words++
	}
	pos := 0
	for w := 0; w < words; w++ {
		for pos < len(line) && (line[pos] == ' ' || line[pos] == '\t') {
			pos++
		}
		for pos < len(line) && line[pos] != ' ' && line[pos] != '\t' {
			pos++
		}
	}
	for pos < len(line) && (line[pos] == ' ' || line[pos] == '\t') {
		pos++
	}
	return pos
}

var redirect = regexp.MustCompile(`(^|[^<])>|\|\s*(logger|mail|mailx|tee|sendmail)\b|2>&1`)

func checkCommand(no int, cmd string, env map[string]string, opt Options, add func(int, Severity, string, string, ...interface{})) {
	// unescaped %
	for i := 0; i < len(cmd); i++ {
		if cmd[i] == '\\' {
			i++
			continue
		}
		if cmd[i] == '%' {
			add(no, Error, "unescaped-percent", "unescaped %% in command: cron turns it into a newline and feeds the rest to stdin; write \\%%")
			break
		}
	}
	shell := env["SHELL"]
	if shell == "" || strings.HasSuffix(shell, "/sh") {
		for _, b := range []string{"[[", "source ", "<(", "&>", "function "} {
			if strings.Contains(cmd, b) {
				add(no, Warning, "bashism", "%q is a bash feature but cron uses /bin/sh unless SHELL is set", strings.TrimSpace(b))
				break
			}
		}
	}
	if !redirect.MatchString(cmd) {
		if _, has := env["MAILTO"]; !has {
			add(no, Warning, "silent-output", "no output redirection and no MAILTO; output goes to local mail (usually never read) or is dropped")
		} else if env["MAILTO"] == "" {
			add(no, Warning, "silent-output", "MAILTO is empty and the command does not redirect output; failures leave no trace")
		}
	}
	first := firstWord(cmd)
	if first == "" || strings.ContainsAny(first, "$`(") {
		return
	}
	if strings.HasPrefix(first, "./") || strings.HasPrefix(first, "../") {
		add(no, Error, "relative-path", "%q is relative; cron runs jobs from the user's home directory, not the directory you tested in", first)
		return
	}
	if strings.HasPrefix(first, "/") {
		if opt.CheckExists {
			fi, err := os.Stat(first)
			if err != nil {
				add(no, Warning, "missing-file", "%s does not exist on this machine", first)
			} else if fi.Mode()&0111 == 0 && !fi.IsDir() {
				add(no, Warning, "not-executable", "%s is not executable", first)
			}
		}
		return
	}
	if strings.Contains(first, "/") {
		return
	}
	if shellBuiltin[first] {
		return
	}
	path := opt.DefaultPath
	if p, ok := env["PATH"]; ok {
		path = p
	}
	if opt.CheckExists {
		if lookPath(first, path) == "" {
			if elsewhere := lookPath(first, os.Getenv("PATH")); elsewhere != "" {
				add(no, Error, "not-in-cron-path", "%q is at %s, which is not in cron's PATH (%s); use the full path or set PATH in the crontab", first, elsewhere, path)
			} else {
				add(no, Warning, "unknown-command", "%q was not found on this machine's PATH or cron's PATH", first)
			}
		}
	}
}

var shellBuiltin = map[string]bool{"cd": true, "echo": true, "exec": true, "export": true, "test": true, "true": true, "false": true, ".": true, "set": true, "exit": true, "umask": true, "if": true, "for": true, "while": true, "[": true}

func firstWord(cmd string) string {
	words := strings.Fields(cmd)
	for _, w := range words {
		if envLine.MatchString(w) {
			continue // VAR=value prefix
		}
		return w
	}
	return ""
}

func lookPath(name, path string) string {
	for _, d := range strings.Split(path, ":") {
		if d == "" {
			continue
		}
		p := filepath.Join(d, name)
		if fi, err := os.Stat(p); err == nil && !fi.IsDir() && fi.Mode()&0111 != 0 {
			return p
		}
	}
	return ""
}

func sortFindings(f []Finding) {
	for i := 1; i < len(f); i++ {
		for j := i; j > 0 && f[j].Line < f[j-1].Line; j-- {
			f[j], f[j-1] = f[j-1], f[j]
		}
	}
}
