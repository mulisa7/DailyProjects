package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestNormalize(t *testing.T) {
	cases := []struct{ in, want string }{
		{"2026-10-30T07:10:04Z user 42 logged in", "<TS> user <NUM> logged in"},
		{"2026-10-30 07:10:04,123 WARN slow", "<TS> WARN slow"},
		{"2026-10-30T07:10:04.5+02:00 x", "<TS> x"},
		{"Oct  3 07:10:04 host sshd[311]: bad", "<TS> host sshd[<NUM>]: bad"},
		{`1.2.3.4 - [30/Oct/2026:07:10:04 +0000] "GET /a" 200`, `<IP> - [<TS>] "GET /a" <NUM>`},
		{"req 3f2504e0-4f89-41d3-9a0c-0305e82c3301 failed", "req <UUID> failed"},
		{"ptr 0xdeadBEEF freed", "ptr <HEX> freed"},
		{"sha 9f86d081884c7d659a2feaa0c55ad015 ok", "sha <HEX> ok"},
		{"took 12.5ms", "took <NUM>ms"},
		{"  padded line \t", "padded line"},
		{"no variable parts", "no variable parts"},
		{"deadbeefcafe is a word-ish", "<HEX> is a word-ish"},
		{"abc123 stays", "abc123 stays"},
	}
	for _, c := range cases {
		if got := Normalize(c.in); got != c.want {
			t.Errorf("Normalize(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestFoldGroupsAndOrder(t *testing.T) {
	in := "a 1\nb 2\na 3\n\n  \na 4\nb 5\nc\n"
	g, total, err := Fold(strings.NewReader(in))
	if err != nil {
		t.Fatal(err)
	}
	if total != 6 || len(g) != 3 {
		t.Fatalf("total=%d groups=%d", total, len(g))
	}
	if g[0].Template != "a <NUM>" || g[0].Count != 3 || g[0].Example != "a 1" || g[0].FirstLine != 1 || g[0].LastLine != 6 {
		t.Errorf("bad first group: %+v", g[0])
	}
	if g[1].Template != "b <NUM>" || g[2].Template != "c" {
		t.Errorf("order wrong: %v %v", g[1].Template, g[2].Template)
	}
}

func TestFoldEmptyAndBlank(t *testing.T) {
	for _, in := range []string{"", "\n\n  \n"} {
		g, total, err := Fold(strings.NewReader(in))
		if err != nil || total != 0 || len(g) != 0 {
			t.Errorf("input %q: %v %d %d", in, err, total, len(g))
		}
	}
}

func TestFoldCRLFAndNoTrailingNewline(t *testing.T) {
	g, total, _ := Fold(strings.NewReader("x 1\r\nx 2"))
	if total != 2 || len(g) != 1 || g[0].Count != 2 {
		t.Errorf("got %d lines, %d groups", total, len(g))
	}
}

func TestFoldVeryLongLine(t *testing.T) {
	long := strings.Repeat("a", 200000)
	g, total, err := Fold(strings.NewReader(long + "\n"))
	if err != nil || total != 1 || len(g) != 1 {
		t.Errorf("err=%v total=%d", err, total)
	}
}

func TestFoldBinaryishInput(t *testing.T) {
	_, _, err := Fold(strings.NewReader("\x00\xff\xfe 12\n"))
	if err != nil {
		t.Errorf("unexpected error: %v", err)
	}
}

func runCLI(stdin string, args ...string) (int, string, string) {
	var out, errb bytes.Buffer
	code := run(args, strings.NewReader(stdin), &out, &errb)
	return code, out.String(), errb.String()
}

func TestCLIStdin(t *testing.T) {
	code, out, _ := runCLI("e 1\ne 2\nf\n")
	if code != 0 || !strings.Contains(out, "      2  e <NUM>") || !strings.Contains(out, "3 lines, 2 patterns") {
		t.Errorf("code=%d out=%q", code, out)
	}
}

func TestCLIFlags(t *testing.T) {
	in := "a 1\na 2\nb 1\nc\n"
	_, out, _ := runCLI(in, "-top", "1")
	if strings.Contains(out, "b <NUM>") || !strings.Contains(out, "(1 shown)") {
		t.Errorf("-top failed: %q", out)
	}
	_, out, _ = runCLI(in, "-min", "2")
	if strings.Contains(out, "b <NUM>") || !strings.Contains(out, "a <NUM>") {
		t.Errorf("-min failed: %q", out)
	}
	_, out, _ = runCLI(in, "-examples")
	if !strings.Contains(out, "e.g. (lines 1-2) a 1") {
		t.Errorf("-examples failed: %q", out)
	}
}

func TestCLIErrors(t *testing.T) {
	if code, _, e := runCLI(""); code != 1 || !strings.Contains(e, "no log lines") {
		t.Errorf("empty: %d %q", code, e)
	}
	if code, _, e := runCLI("x", "-top", "-1"); code != 2 || e == "" {
		t.Errorf("negative top: %d %q", code, e)
	}
	if code, _, _ := runCLI("x", "-min", "0"); code != 2 {
		t.Errorf("min 0: %d", code)
	}
	if code, _, _ := runCLI("x", "-bogus"); code != 2 {
		t.Errorf("bad flag: %d", code)
	}
	if code, _, e := runCLI("", "/no/such/file.log"); code != 1 || !strings.Contains(e, "no such file") {
		t.Errorf("missing file: %d %q", code, e)
	}
}

func TestCLIFilesCombined(t *testing.T) {
	d := t.TempDir()
	a, b := filepath.Join(d, "a.log"), filepath.Join(d, "b.log")
	os.WriteFile(a, []byte("job 1 done\n"), 0o644)
	os.WriteFile(b, []byte("job 2 done\n"), 0o644)
	code, out, _ := runCLI("", a, b)
	if code != 0 || !strings.Contains(out, "      2  job <NUM> done") {
		t.Errorf("code=%d out=%q", code, out)
	}
}
