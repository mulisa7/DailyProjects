package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func exec(t *testing.T, stdin string, args ...string) (int, string, string) {
	t.Helper()
	var o, e bytes.Buffer
	c := run(args, strings.NewReader(stdin), &o, &e)
	return c, o.String(), e.String()
}

func write(t *testing.T, dir, name, s string) string {
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, []byte(s), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestCLICommon(t *testing.T) {
	d := t.TempDir()
	a, b := write(t, d, "a", "x\ny\nz\n"), write(t, d, "b", "z\nx\n")
	c, out, _ := exec(t, "", "common", a, b)
	if c != 0 || out != "x\nz\n" {
		t.Errorf("%d %q", c, out)
	}
}

func TestCLICountAndWhich(t *testing.T) {
	d := t.TempDir()
	a, b := write(t, d, "a", "x\ny\n"), write(t, d, "b", "x\n")
	_, out, _ := exec(t, "", "-c", "-w", "union", a, b)
	if out != "2\tx\t[1,2]\n1\ty\t[1]\n" {
		t.Errorf("%q", out)
	}
}

func TestCLIStdinAndNoResultExit1(t *testing.T) {
	d := t.TempDir()
	a := write(t, d, "a", "x\n")
	c, out, _ := exec(t, "q\n", "common", a, "-")
	if c != 1 || out != "" {
		t.Errorf("%d %q", c, out)
	}
	c, out, _ = exec(t, "x\n", "diff", "-", a)
	if c != 1 {
		t.Errorf("%d %q", c, out)
	}
}

func TestCLIErrors(t *testing.T) {
	d := t.TempDir()
	a := write(t, d, "a", "x\n")
	cases := [][]string{
		{},
		{"union"},
		{"bogus", a, a},
		{"common", a},
		{"common", a, filepath.Join(d, "missing")},
		{"only", "-f", "5", a, a},
		{"min", "-k", "9", a, a},
		{"common", "-", "-"},
		{"--nope", "union", a},
	}
	for _, args := range cases {
		c, _, e := exec(t, "", args...)
		if c != 2 || (e == "") {
			t.Errorf("%v: code %d stderr %q", args, c, e)
		}
	}
}

func TestCLIOnlyFileAndSort(t *testing.T) {
	d := t.TempDir()
	a, b := write(t, d, "a", "m\nb\n"), write(t, d, "b", "z\nc\nm\n")
	_, out, _ := exec(t, "", "-s", "only", "-f", "2", a, b)
	if out != "c\nz\n" {
		t.Errorf("%q", out)
	}
}

func TestCLIUnionSingleFile(t *testing.T) {
	d := t.TempDir()
	a := write(t, d, "a", "q\nq\nr\n")
	c, out, _ := exec(t, "", "union", a)
	_ = c
	if out != "q\nr\n" {
		t.Errorf("%q", out)
	}
}
