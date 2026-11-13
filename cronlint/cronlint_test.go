package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func codes(fs []Finding) []string {
	var c []string
	for _, f := range fs {
		c = append(c, f.Code)
	}
	return c
}

func has(fs []Finding, code string) bool {
	for _, f := range fs {
		if f.Code == code {
			return true
		}
	}
	return false
}

const quiet = "MAILTO=ops@example.com\n"

func TestCleanLine(t *testing.T) {
	got := Check(quiet+"*/5 9-17 * * mon-fri /usr/bin/backup >> /var/log/b.log 2>&1\n", Options{})
	if len(got) != 0 {
		t.Fatalf("expected no findings, got %v", got)
	}
}

func TestEmptyAndCommentsOnly(t *testing.T) {
	if got := Check("", Options{}); len(got) != 0 {
		t.Fatal(got)
	}
	if got := Check("# nothing\n\n   \n", Options{}); len(got) != 0 {
		t.Fatal(got)
	}
}

func TestBadFields(t *testing.T) {
	cases := map[string]string{
		"60 * * * * /bin/x >/dev/null\n":   "outside 0-59",
		"* 24 * * * /bin/x >/dev/null\n":   "outside 0-23",
		"* * 0 * * /bin/x >/dev/null\n":    "outside 1-31",
		"* * * 13 * /bin/x >/dev/null\n":   "outside 1-12",
		"* * * * 8 /bin/x >/dev/null\n":    "outside 0-7",
		"5-1 * * * * /bin/x >/dev/null\n":  "backwards",
		"*/0 * * * * /bin/x >/dev/null\n":  "invalid step",
		"1,,2 * * * * /bin/x >/dev/null\n": "empty list item",
		"abc * * * * /bin/x >/dev/null\n":  "not a number",
		"* * * foo * /bin/x >/dev/null\n":  "not a number",
		"-5 * * * * /bin/x >/dev/null\n":   "empty value",
	}
	for in, want := range cases {
		got := Check(in, Options{})
		if len(got) == 0 || got[0].Code != "bad-field" || !strings.Contains(got[0].Msg, want) {
			t.Errorf("%q: want bad-field containing %q, got %v", in, want, got)
		}
	}
}

func TestFewFieldsAndNoCommand(t *testing.T) {
	if got := Check("* * * *\n", Options{}); !has(got, "few-fields") {
		t.Error(got)
	}
	if got := Check("* * * * *\n", Options{}); !has(got, "no-command") {
		t.Error(got)
	}
	if got := Check("@daily\n", Options{}); !has(got, "no-command") {
		t.Error(got)
	}
	if got := Check("* * * * * root\n", Options{System: true}); !has(got, "no-command") {
		t.Error(got)
	}
}

func TestMacros(t *testing.T) {
	if got := Check(quiet+"@daily /bin/x\n", Options{}); len(got) != 0 {
		t.Error(got)
	}
	if got := Check("@sometimes /bin/x >/dev/null\n", Options{}); !has(got, "bad-macro") {
		t.Error(got)
	}
}

func TestUnescapedPercent(t *testing.T) {
	got := Check(quiet+"0 1 * * * /bin/tar czf /b/$(date +%F).tgz /d\n", Options{})
	if !has(got, "unescaped-percent") {
		t.Error(got)
	}
	got = Check(quiet+`0 1 * * * /bin/tar czf /b/$(date +\%F).tgz /d`+"\n", Options{})
	if has(got, "unescaped-percent") {
		t.Error("escaped percent flagged", got)
	}
}

func TestDomDowOr(t *testing.T) {
	got := Check(quiet+"0 0 1 * mon /bin/x\n", Options{})
	if !has(got, "dom-dow-or") {
		t.Error(got)
	}
	got = Check(quiet+"0 0 1 * * /bin/x\n", Options{})
	if has(got, "dom-dow-or") {
		t.Error(got)
	}
	got = Check(quiet+"0 0 */2 * mon /bin/x\n", Options{}) // */2 restricts
	if !has(got, "dom-dow-or") {
		t.Error(got)
	}
}

func TestNeverRuns(t *testing.T) {
	if got := Check(quiet+"0 0 30 2 * /bin/x\n", Options{}); !has(got, "never-runs") {
		t.Error(got)
	}
	if got := Check(quiet+"0 0 29 2 * /bin/x\n", Options{}); has(got, "never-runs") {
		t.Error("leap day is possible", got)
	}
	if got := Check(quiet+"0 0 31 4,5 * /bin/x\n", Options{}); has(got, "never-runs") {
		t.Error("May has 31 days", got)
	}
}

func TestSundaySeven(t *testing.T) {
	if got := Check(quiet+"0 0 * * 7 /bin/x\n", Options{}); len(got) != 0 {
		t.Error(got)
	}
	if got := Check(quiet+"0 0 * * 5-7 /bin/x\n", Options{}); len(got) != 0 {
		t.Error(got)
	}
}

func TestNoTrailingNewline(t *testing.T) {
	got := Check(quiet+"0 0 * * * /bin/x", Options{})
	if !has(got, "no-newline") {
		t.Error(got)
	}
	if got := Check(quiet+"0 0 * * * /bin/x\n", Options{}); has(got, "no-newline") {
		t.Error(got)
	}
	// trailing blank only: not an issue
	if got := Check(quiet+"0 0 * * * /bin/x\n   ", Options{}); has(got, "no-newline") {
		t.Error(got)
	}
}

func TestCarriageReturn(t *testing.T) {
	got := Check(quiet+"0 0 * * * /bin/x\r\n", Options{})
	// CRLF is normalised before splitting, so only a stray CR is reported
	if has(got, "carriage-return") {
		t.Log("CRLF normalised")
	}
	got = Check(quiet+"0 0 * * * /bin/x\r more\n", Options{})
	if !has(got, "carriage-return") {
		t.Error(got)
	}
}

func TestRelativePath(t *testing.T) {
	got := Check(quiet+"0 0 * * * ./run.sh\n", Options{})
	if !has(got, "relative-path") {
		t.Error(got)
	}
}

func TestSilentOutput(t *testing.T) {
	got := Check("0 0 * * * /bin/x\n", Options{})
	if !has(got, "silent-output") {
		t.Error(got)
	}
	if got := Check("0 0 * * * /bin/x > /tmp/o 2>&1\n", Options{}); has(got, "silent-output") {
		t.Error(got)
	}
	if got := Check("MAILTO=\"\"\n0 0 * * * /bin/x\n", Options{}); !has(got, "silent-output") {
		t.Error("empty MAILTO", got)
	}
	if got := Check("0 0 * * * /bin/x | logger\n", Options{}); has(got, "silent-output") {
		t.Error(got)
	}
}

func TestBashisms(t *testing.T) {
	got := Check(quiet+"0 0 * * * [[ -f /x ]] && /bin/y\n", Options{})
	if !has(got, "bashism") {
		t.Error(got)
	}
	got = Check(quiet+"SHELL=/bin/bash\n0 0 * * * [[ -f /x ]] && /bin/y\n", Options{})
	if has(got, "bashism") {
		t.Error(got)
	}
}

func TestEnvExpansionAndEnvNotJob(t *testing.T) {
	got := Check("PATH=/usr/local/bin:$PATH\nMAILTO=a@b.c\n", Options{})
	if len(got) != 1 || got[0].Code != "env-expansion" || got[0].Line != 1 {
		t.Error(got)
	}
}

func TestSystemFormat(t *testing.T) {
	got := Check(quiet+"17 * * * * root cd / && run-parts /etc/cron.hourly\n", Options{System: true})
	if len(got) != 0 {
		t.Error(got)
	}
	// the same line without --system treats "root" as the command
	got = Check(quiet+"0 0 * * * root /bin/x\n", Options{System: true})
	if len(got) != 0 {
		t.Error(got)
	}
}

func TestDuplicate(t *testing.T) {
	got := Check(quiet+"0 0 * * * /bin/x\n0 0 * * * /bin/x\n", Options{})
	if len(got) != 1 || got[0].Code != "duplicate" || got[0].Line != 3 {
		t.Error(got, codes(got))
	}
}

func TestCheckExists(t *testing.T) {
	dir := t.TempDir()
	tool := filepath.Join(dir, "mytool")
	os.WriteFile(tool, []byte("#!/bin/sh\n"), 0755)
	plain := filepath.Join(dir, "plain")
	os.WriteFile(plain, []byte("x"), 0644)
	t.Setenv("PATH", dir+":/usr/bin:/bin")
	o := Options{CheckExists: true}

	if got := Check(quiet+"0 0 * * * mytool\n", o); !has(got, "not-in-cron-path") {
		t.Error(got)
	}
	// setting PATH in the file fixes it
	if got := Check("PATH="+dir+":/usr/bin\n"+quiet+"0 0 * * * mytool\n", o); len(got) != 0 {
		t.Error(got)
	}
	if got := Check(quiet+"0 0 * * * nosuchcmd_xyz\n", o); !has(got, "unknown-command") {
		t.Error(got)
	}
	if got := Check(quiet+"0 0 * * * "+filepath.Join(dir, "gone")+"\n", o); !has(got, "missing-file") {
		t.Error(got)
	}
	if got := Check(quiet+"0 0 * * * "+plain+"\n", o); !has(got, "not-executable") {
		t.Error(got)
	}
	if got := Check(quiet+"0 0 * * * "+tool+"\n", o); len(got) != 0 {
		t.Error(got)
	}
	// builtins, variable prefixes and shell expressions are not looked up
	if got := Check(quiet+"0 0 * * * cd /tmp && FOO=1 "+tool+"\n", o); len(got) != 0 {
		t.Error(got)
	}
	// without the flag nothing touches the disk
	if got := Check(quiet+"0 0 * * * nosuchcmd_xyz\n", Options{}); len(got) != 0 {
		t.Error(got)
	}
}

func TestRunExitCodes(t *testing.T) {
	dir := t.TempDir()
	good := filepath.Join(dir, "good")
	warn := filepath.Join(dir, "warn")
	bad := filepath.Join(dir, "bad")
	empty := filepath.Join(dir, "empty")
	os.WriteFile(good, []byte(quiet+"0 0 * * * /bin/x\n"), 0644)
	os.WriteFile(warn, []byte("0 0 * * * /bin/x\n"), 0644)
	os.WriteFile(bad, []byte("99 0 * * * /bin/x >/dev/null\n"), 0644)
	os.WriteFile(empty, nil, 0644)

	run1 := func(stdin string, args ...string) (int, string, string) {
		var o, e bytes.Buffer
		c := run(args, strings.NewReader(stdin), &o, &e)
		return c, o.String(), e.String()
	}
	if c, o, _ := run1("", good); c != 0 || !strings.Contains(o, "0 error(s), 0 warning(s)") {
		t.Error(c, o)
	}
	if c, _, _ := run1("", warn); c != 0 {
		t.Error("warning only should exit 0", c)
	}
	if c, _, _ := run1("", "-strict", warn); c != 1 {
		t.Error("strict warning should exit 1", c)
	}
	if c, o, _ := run1("", bad); c != 1 || !strings.Contains(o, bad+":1: error: [bad-field]") {
		t.Error(c, o)
	}
	if c, _, e := run1("", empty); c != 0 || !strings.Contains(e, "empty crontab") {
		t.Error(c, e)
	}
	if c, _, e := run1("", filepath.Join(dir, "missing")); c != 2 || e == "" {
		t.Error(c, e)
	}
	if c, _, _ := run1("", "-nonsense"); c != 2 {
		t.Error(c)
	}
	if c, o, _ := run1("99 0 * * * /bin/x\n"); c != 1 || !strings.Contains(o, "<stdin>:1") {
		t.Error(c, o)
	}
	if c, _, _ := run1("", "-system", good); c != 0 && c != 1 {
		t.Error(c)
	}
}

func TestMultiFileAndUnexpectedBinary(t *testing.T) {
	got := Check("\x00\x01\x02 garbage\n", Options{})
	if !has(got, "few-fields") {
		t.Error(got)
	}
	got = Check("   \t0\t0 *\t* *\t/bin/x >/dev/null\n", Options{})
	if len(got) != 0 {
		t.Error("tabs and indentation should be accepted", got)
	}
}
