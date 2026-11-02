package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func blocks(t *testing.T, in string) []Block {
	t.Helper()
	b, err := ParseBlocks(strings.NewReader(in))
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func TestParseCIDR(t *testing.T) {
	s, e, err := ParseCIDR("10.0.1.0/24")
	if err != nil || uintToIP(s) != "10.0.1.0" || uintToIP(e) != "10.0.1.255" {
		t.Fatalf("got %v %v %v", s, e, err)
	}
	s, e, _ = ParseCIDR("0.0.0.0/0")
	if s != 0 || e != 0xFFFFFFFF {
		t.Fatal("/0 wrong")
	}
	s, e, _ = ParseCIDR("1.2.3.4/32")
	if s != e {
		t.Fatal("/32 wrong")
	}
}

func TestParseCIDRErrors(t *testing.T) {
	for _, in := range []string{"", "banana", "10.0.0.0", "10.0.0.0/33", "10.0.0.1/24", "::1/128", "300.1.1.1/8", "10.0.0.0/-1"} {
		if _, _, err := ParseCIDR(in); err == nil {
			t.Errorf("expected error for %q", in)
		}
	}
	_, _, err := ParseCIDR("10.0.0.1/24")
	if !strings.Contains(err.Error(), "10.0.0.0/24") {
		t.Errorf("no suggestion: %v", err)
	}
}

func TestParseBlocks(t *testing.T) {
	b := blocks(t, "# comment\n\n10.0.0.0/24 prod web  # trailing\n  10.0.1.0/24\r\n")
	if len(b) != 2 || b[0].Label != "prod web" || b[1].Line != 4 {
		t.Fatalf("%+v", b)
	}
	if len(blocks(t, "")) != 0 || len(blocks(t, "# only\n")) != 0 {
		t.Fatal("empty input should give no blocks")
	}
}

func TestParseBlocksReportsAllBadLines(t *testing.T) {
	_, err := ParseBlocks(strings.NewReader("10.0.0.0/24\nfoo\n10.0.0.5/24\n"))
	if err == nil || !strings.Contains(err.Error(), "line 2") || !strings.Contains(err.Error(), "line 3") {
		t.Fatalf("%v", err)
	}
}

func TestConflicts(t *testing.T) {
	b := blocks(t, "10.0.0.0/16 a\n10.0.1.0/24 b\n10.1.0.0/24 c\n10.1.0.0/24 d\n")
	cs := FindConflicts(b)
	if len(cs) != 2 {
		t.Fatalf("%d conflicts", len(cs))
	}
	if cs[0].Duplicate || !cs[1].Duplicate {
		t.Fatal("duplicate flag wrong")
	}
	if len(FindConflicts(blocks(t, "10.0.0.0/24\n10.0.1.0/24\n"))) != 0 {
		t.Fatal("adjacent blocks must not conflict")
	}
	if len(FindConflicts(nil)) != 0 {
		t.Fatal("nil")
	}
}

func TestFreeAndCIDRs(t *testing.T) {
	ps, pe, _ := ParseCIDR("10.0.0.0/24")
	free := FreeRanges(Range{ps, pe}, blocks(t, "10.0.0.0/26\n10.0.0.128/26\n"))
	var got []string
	for _, r := range free {
		got = append(got, RangeToCIDRs(r)...)
	}
	want := "10.0.0.64/26,10.0.0.192/26"
	if strings.Join(got, ",") != want {
		t.Fatalf("got %v", got)
	}
}

func TestFreeEdgeCases(t *testing.T) {
	ps, pe, _ := ParseCIDR("10.0.0.0/24")
	p := Range{ps, pe}
	if f := FreeRanges(p, nil); len(f) != 1 || len(RangeToCIDRs(f[0])) != 1 {
		t.Fatalf("empty: %v", f)
	}
	if f := FreeRanges(p, blocks(t, "10.0.0.0/16\n")); len(f) != 0 {
		t.Fatalf("covering block: %v", f)
	}
	if f := FreeRanges(p, blocks(t, "192.168.0.0/24\n")); len(f) != 1 {
		t.Fatal("unrelated block should be ignored")
	}
	// overlapping used blocks must not produce bogus gaps
	if f := FreeRanges(p, blocks(t, "10.0.0.0/25\n10.0.0.0/26\n10.0.0.128/25\n")); len(f) != 0 {
		t.Fatalf("overlap: %v", f)
	}
	// top of address space
	s, e, _ := ParseCIDR("255.255.255.0/24")
	if f := FreeRanges(Range{s, e}, nil); len(f) != 1 || f[0].End != 0xFFFFFFFF {
		t.Fatal("top of space")
	}
}

func TestRangeToCIDRsUnaligned(t *testing.T) {
	got := strings.Join(RangeToCIDRs(Range{1, 6}), ",")
	if got != "0.0.0.1/32,0.0.0.2/31,0.0.0.4/31,0.0.0.6/32" {
		t.Fatal(got)
	}
	if got := RangeToCIDRs(Range{0, 0xFFFFFFFF}); len(got) != 1 || got[0] != "0.0.0.0/0" {
		t.Fatal(got)
	}
}

func TestNextFree(t *testing.T) {
	ps, pe, _ := ParseCIDR("10.0.0.0/16")
	free := FreeRanges(Range{ps, pe}, blocks(t, "10.0.0.0/24\n10.0.1.0/25\n"))
	if c, ok := NextFree(free, 24); !ok || c != "10.0.2.0/24" {
		t.Fatalf("%v %v", c, ok)
	}
	if c, ok := NextFree(free, 25); !ok || c != "10.0.1.128/25" {
		t.Fatalf("%v %v", c, ok)
	}
	if _, ok := NextFree(free, 15); ok {
		t.Fatal("block bigger than parent should not fit")
	}
	if _, ok := NextFree(nil, 24); ok {
		t.Fatal("no free space")
	}
}

func runCLI(args []string, stdin string) (int, string, string) {
	var o, e bytes.Buffer
	c := run(args, strings.NewReader(stdin), &o, &e)
	return c, o.String(), e.String()
}

func TestCLI(t *testing.T) {
	dir := t.TempDir()
	f := filepath.Join(dir, "n.txt")
	os.WriteFile(f, []byte("10.0.0.0/24 a\n10.0.0.128/25 b\n"), 0o600)

	c, out, _ := runCLI([]string{"check", f}, "")
	if c != 1 || !strings.Contains(out, "overlaps") {
		t.Fatal(c, out)
	}
	c, out, _ = runCLI([]string{"check", "-"}, "10.0.0.0/24\n10.0.1.0/24\n")
	if c != 0 || !strings.Contains(out, "OK") {
		t.Fatal(c, out)
	}
	c, out, _ = runCLI([]string{"check", "-"}, "")
	if c != 0 || !strings.Contains(out, "No blocks") {
		t.Fatal(c, out)
	}
	c, out, _ = runCLI([]string{"free", "-parent", "10.0.0.0/23", "-"}, "10.0.0.0/24\n")
	if c != 0 || !strings.HasPrefix(out, "10.0.1.0/24") {
		t.Fatal(c, out)
	}
	c, out, _ = runCLI([]string{"free", "-parent", "10.0.0.0/24", "-"}, "10.0.0.0/24\n")
	if c != 1 || !strings.Contains(out, "No free space") {
		t.Fatal(c, out)
	}
	c, out, _ = runCLI([]string{"next", "-parent", "10.0.0.0/23", "-size", "25", "-"}, "10.0.0.0/24\n")
	if c != 0 || strings.TrimSpace(out) != "10.0.1.0/25" {
		t.Fatal(c, out)
	}
	c, out, _ = runCLI([]string{"next", "-parent", "10.0.0.0/24", "-size", "24", "-"}, "10.0.0.0/25\n")
	if c != 1 || !strings.Contains(out, "No free /24") {
		t.Fatal(c, out)
	}
}

func TestCLIErrors(t *testing.T) {
	cases := [][]string{
		{},
		{"bogus"},
		{"check"},
		{"check", "/no/such/file"},
		{"free", "-"},
		{"free", "-parent", "nope", "-"},
		{"free", "-parent", "10.0.0.1/24", "-"},
		{"next", "-parent", "10.0.0.0/24", "-"},
		{"next", "-parent", "10.0.0.0/24", "-size", "abc", "-"},
		{"next", "-parent", "10.0.0.0/24", "-size", "33", "-"},
		{"check", "--nonsense", "-"},
	}
	for _, a := range cases {
		if c, _, e := runCLI(a, "10.0.0.0/24\n"); c != 2 || e == "" {
			t.Errorf("%v: code %d stderr %q", a, c, e)
		}
	}
	if c, _, e := runCLI([]string{"check", "-"}, "garbage\n"); c != 2 || !strings.Contains(e, "line 1") {
		t.Errorf("bad input: %d %q", c, e)
	}
	if c, _, _ := runCLI([]string{"--help"}, ""); c != 0 {
		t.Error("help should exit 0")
	}
}
