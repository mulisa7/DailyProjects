package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const sample = `{"log":{"version":"1.2","entries":[{"request":{"method":"GET","url":"https://a.test/?token=abc123","headers":[{"name":"Authorization","value":"Bearer abcdefgh12345"}]},"response":{"status":200,"headers":[],"content":{"mimeType":"text/plain","text":"ok"}}}]}}`

func do(t *testing.T, stdin string, args ...string) (int, string, string) {
	t.Helper()
	var out, errb bytes.Buffer
	code := run(args, strings.NewReader(stdin), &out, &errb)
	return code, out.String(), errb.String()
}

func write(t *testing.T, content string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "session.har")
	if err := os.WriteFile(p, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestWritesDefaultOutputFile(t *testing.T) {
	p := write(t, sample)
	code, _, errs := do(t, "", p)
	if code != 0 {
		t.Fatalf("code %d: %s", code, errs)
	}
	b, err := os.ReadFile(strings.TrimSuffix(p, ".har") + ".scrubbed.har")
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(b), "abc123") || strings.Contains(string(b), "abcdefgh12345") {
		t.Errorf("leak: %s", b)
	}
	if !strings.Contains(errs, "redacted") {
		t.Errorf("no report: %s", errs)
	}
	orig, _ := os.ReadFile(p)
	if string(orig) != sample {
		t.Error("input file was modified")
	}
}

func TestStdinToStdout(t *testing.T) {
	code, out, _ := do(t, sample, "-q", "-o", "-", "-")
	if code != 0 || strings.Contains(out, "abc123") || !strings.Contains(out, "[REDACTED]") {
		t.Errorf("code %d out %s", code, out)
	}
}

func TestCheckMode(t *testing.T) {
	p := write(t, sample)
	code, _, _ := do(t, "", "--check", p)
	if code != 1 {
		t.Errorf("want 1 got %d", code)
	}
	if _, err := os.Stat(strings.TrimSuffix(p, ".har") + ".scrubbed.har"); err == nil {
		t.Error("check wrote a file")
	}
	clean := `{"log":{"entries":[{"request":{"url":"https://a.test/","headers":[]},"response":{"headers":[],"content":{}}}]}}`
	code, _, errs := do(t, clean, "--check", "-")
	if code != 0 || !strings.Contains(errs, "nothing sensitive") {
		t.Errorf("code %d %s", code, errs)
	}
}

func TestExtraFlagsAfterInput(t *testing.T) {
	in := `{"log":{"entries":[{"request":{"url":"https://a.test/?org=zed","headers":[{"name":"X-Org","value":"zed"}]},"response":{"headers":[],"content":{}}}]}}`
	code, out, _ := do(t, in, "-", "-q", "--header", "x-org", "--param", "org", "-o", "-")
	if code != 0 || strings.Contains(out, "zed") {
		t.Errorf("code %d out %s", code, out)
	}
}

func TestErrors(t *testing.T) {
	cases := []struct {
		name  string
		stdin string
		args  []string
		want  string
	}{
		{"no args", "", nil, "no input"},
		{"unknown flag", "", []string{"--nope", "x"}, "unknown option"},
		{"two inputs", "", []string{"a", "b"}, "only one input"},
		{"missing value", "", []string{"x", "-o"}, "needs a value"},
		{"check with -o", "", []string{"--check", "-o", "y", "x"}, "cannot be combined"},
		{"missing file", "", []string{"/no/such/file.har"}, "cannot read"},
		{"empty", "  \n", []string{"-"}, "empty"},
		{"not json", "hello", []string{"-"}, "not valid JSON"},
		{"not har", `{"a":1}`, []string{"-"}, "not a HAR"},
		{"unwritable", sample, []string{"-o", "/no/such/dir/o.har", "-"}, "cannot write"},
	}
	for _, c := range cases {
		code, _, errs := do(t, c.stdin, c.args...)
		if code != 2 || !strings.Contains(errs, c.want) {
			t.Errorf("%s: code %d stderr %q", c.name, code, errs)
		}
	}
}

func TestHelpAndBOM(t *testing.T) {
	if code, out, _ := do(t, "", "--help"); code != 0 || !strings.Contains(out, "Usage") {
		t.Errorf("help: %d", code)
	}
	code, out, _ := do(t, "\xef\xbb\xbf"+sample, "-q", "-o", "-", "-")
	if code != 0 || strings.Contains(out, "abc123") {
		t.Errorf("BOM input: %d", code)
	}
}
