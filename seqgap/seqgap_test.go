package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func analyze(t *testing.T, in string, o Options, order bool) []Series {
	t.Helper()
	e, _, err := Read(strings.NewReader(in), o)
	if err != nil {
		t.Fatal(err)
	}
	return Analyze(e, order)
}

func TestParseID(t *testing.T) {
	e, err := ParseID("INV-2024-0012", false)
	if err != nil || e.Num != 12 || e.Width != 4 || e.Key != "INV-2024-\x00" {
		t.Fatalf("%+v %v", e, err)
	}
	e, _ = ParseID("  7 ", false)
	if e.Num != 7 || e.Key != "\x00" {
		t.Fatalf("%+v", e)
	}
	e, _ = ParseID("A12-B", false)
	if e.Num != 12 || e.Key != "A\x00-B" {
		t.Fatalf("suffix: %+v", e)
	}
}

func TestParseIDErrors(t *testing.T) {
	for _, in := range []string{"", "   ", "INVOICE", "99999999999999999999999"} {
		if _, err := ParseID(in, false); err == nil {
			t.Errorf("expected error for %q", in)
		}
	}
}

func TestGapsAndRanges(t *testing.T) {
	s := analyze(t, "INV-1\nINV-2\nINV-5\nINV-6\nINV-10\n", Options{}, true)
	want := []Range{{3, 4}, {7, 9}}
	if len(s) != 1 || !reflect.DeepEqual(s[0].Missing, want) {
		t.Fatalf("%+v", s)
	}
	if s[0].Min != 1 || s[0].Max != 10 || s[0].Count != 5 {
		t.Fatalf("%+v", s[0])
	}
}

func TestCleanSeries(t *testing.T) {
	s := analyze(t, "100\n101\n102\n", Options{}, true)
	if s[0].Problems() {
		t.Fatalf("%+v", s[0])
	}
}

func TestDuplicates(t *testing.T) {
	s := analyze(t, "A-1\nA-2\nA-2\nA-3\nA-2\n", Options{}, true)
	d := s[0].Duplicates
	if len(d) != 1 || d[0].Number != 2 || !reflect.DeepEqual(d[0].Lines, []int{2, 3, 5}) {
		t.Fatalf("%+v", d)
	}
}

func TestOutOfOrder(t *testing.T) {
	in := "A-1\nA-3\nA-2\nA-4\n"
	s := analyze(t, in, Options{}, true)
	if len(s[0].OutOfOrder) != 1 || s[0].OutOfOrder[0].Line != 3 || s[0].OutOfOrder[0].Previous != 3 {
		t.Fatalf("%+v", s[0].OutOfOrder)
	}
	s = analyze(t, in, Options{}, false)
	if len(s[0].OutOfOrder) != 0 {
		t.Fatal("order check should be off")
	}
}

func TestSeparateSeries(t *testing.T) {
	s := analyze(t, "INV-2023-1\nINV-2024-1\nINV-2024-2\nCN-1\nCN-3\n", Options{}, true)
	if len(s) != 3 {
		t.Fatalf("%d series", len(s))
	}
	for _, x := range s {
		if x.Prefix == "CN-" && len(x.Missing) != 1 {
			t.Fatalf("%+v", x)
		}
	}
}

func TestIgnoreCase(t *testing.T) {
	if n := len(analyze(t, "inv-1\nINV-2\n", Options{IgnoreCase: true}, true)); n != 1 {
		t.Fatalf("got %d series", n)
	}
	if n := len(analyze(t, "inv-1\nINV-2\n", Options{}, true)); n != 2 {
		t.Fatalf("got %d series", n)
	}
}

func TestPaddingInconsistent(t *testing.T) {
	s := analyze(t, "A-001\nA-002\nA-03\n", Options{}, true)
	if len(s[0].Widths) != 2 {
		t.Fatalf("%+v", s[0].Widths)
	}
	// 9 -> 10 growth is not a padding problem
	s = analyze(t, "A-8\nA-9\nA-10\nA-11\n", Options{}, true)
	if len(s[0].Widths) != 0 {
		t.Fatalf("%+v", s[0].Widths)
	}
}

func TestLeadingZerosEqualNumbers(t *testing.T) {
	s := analyze(t, "A-007\nA-7\n", Options{}, true)
	if len(s[0].Duplicates) != 1 {
		t.Fatalf("007 and 7 are the same number: %+v", s[0])
	}
}

func TestSkipsBlankAndComments(t *testing.T) {
	e, w, _ := Read(strings.NewReader("\ufeffA-1\r\n\r\n# note\nA-2\nnonumber\n"), Options{})
	if len(e) != 2 || len(w) != 1 || e[0].Raw != "A-1" || e[1].Line != 4 {
		t.Fatalf("%+v %v", e, w)
	}
}

func TestCSVColumnByNumberAndName(t *testing.T) {
	csv := "date,number,amount\n2024-01-01,INV-1,10\n2024-01-02,INV-3,20\n"
	s := analyze(t, csv, Options{Column: "2", Header: true, Delimiter: ','}, true)
	if len(s[0].Missing) != 1 || s[0].Missing[0].From != 2 {
		t.Fatalf("%+v", s[0])
	}
	s = analyze(t, csv, Options{Column: "NUMBER", Header: true, Delimiter: ','}, true)
	if s[0].Count != 2 {
		t.Fatalf("%+v", s[0])
	}
	// without header, date row would be parsed too
	e, _, _ := Read(strings.NewReader("INV-1,x\nINV-2,y\n"), Options{Column: "1", Delimiter: ','})
	if len(e) != 2 {
		t.Fatal(len(e))
	}
}

func TestCSVErrors(t *testing.T) {
	cases := []struct {
		in string
		o  Options
	}{
		{"a,b\n1,2\n", Options{Column: "nope", Header: true, Delimiter: ','}},
		{"a,b\n1,2\n", Options{Column: "id", Delimiter: ','}},
		{"a,b\n1,2\n", Options{Column: "0", Delimiter: ','}},
	}
	for _, c := range cases {
		if _, _, err := Read(strings.NewReader(c.in), c.o); err == nil {
			t.Errorf("expected error for %+v", c.o)
		}
	}
}

func TestCSVShortAndEmptyRows(t *testing.T) {
	in := "id,n\nA-1,x\nA-2\n,\nA-3,z\n"
	e, w, err := Read(strings.NewReader(in), Options{Column: "2", Header: true, Delimiter: ','})
	_ = e
	if err != nil {
		t.Fatal(err)
	}
	if len(w) < 2 {
		t.Fatalf("warnings %v", w)
	}
	e, w, _ = Read(strings.NewReader(in), Options{Column: "id", Header: true, Delimiter: ','})
	if len(e) != 3 || len(w) != 1 {
		t.Fatalf("%d entries, warnings %v", len(e), w)
	}
}

func TestSemicolonAndQuoted(t *testing.T) {
	in := "\"INV-1\";a\n\"INV-2\";b\n"
	e, _, err := Read(strings.NewReader(in), Options{Column: "1", Delimiter: ';'})
	if err != nil || len(e) != 2 {
		t.Fatalf("%v %v", e, err)
	}
}

func runCLI(args []string, stdin string) (int, string, string) {
	var o, e bytes.Buffer
	c := run(args, strings.NewReader(stdin), &o, &e)
	return c, o.String(), e.String()
}

func TestCLIExitCodes(t *testing.T) {
	if c, out, _ := runCLI(nil, "A-1\nA-2\n"); c != 0 || !strings.Contains(out, "ok:") {
		t.Fatalf("clean: %d %s", c, out)
	}
	c, out, _ := runCLI(nil, "A-1\nA-4\n")
	if c != 1 || !strings.Contains(out, "missing 2-3 (2 numbers)") {
		t.Fatalf("gap: %d %s", c, out)
	}
	if c, _, e := runCLI(nil, ""); c != 2 || !strings.Contains(e, "no identifiers") {
		t.Fatalf("empty: %d %s", c, e)
	}
	if c, _, _ := runCLI([]string{"--bogus"}, ""); c != 2 {
		t.Fatalf("bad flag %d", c)
	}
	if c, _, e := runCLI([]string{"/no/such/file"}, ""); c != 2 || e == "" {
		t.Fatalf("missing file %d", c)
	}
	if c, _, _ := runCLI([]string{"a", "b"}, ""); c != 2 {
		t.Fatal("two files")
	}
	if c, _, _ := runCLI([]string{"-delimiter", "ab", "-column", "1"}, "x"); c != 2 {
		t.Fatal("delimiter")
	}
}

func TestCLIAllLinesInvalid(t *testing.T) {
	c, _, e := runCLI(nil, "foo\nbar\n")
	if c != 2 || !strings.Contains(e, "warning") || !strings.Contains(e, "no identifiers") {
		t.Fatalf("%d %s", c, e)
	}
}

func TestCLIFileAndTab(t *testing.T) {
	p := filepath.Join(t.TempDir(), "x.tsv")
	os.WriteFile(p, []byte("id\tamt\nA-1\t5\nA-2\t6\nA-2\t7\n"), 0o644)
	c, out, _ := runCLI([]string{"-column", "id", "-header", "-delimiter", `\t`, p}, "")
	if c != 1 || !strings.Contains(out, "duplicate 2 on lines 3, 4") {
		t.Fatalf("%d %s", c, out)
	}
}

func TestCLIJSON(t *testing.T) {
	c, out, _ := runCLI([]string{"-json"}, "A-1\nA-3\n")
	var v struct {
		OK     bool     `json:"ok"`
		Series []Series `json:"series"`
	}
	if err := json.Unmarshal([]byte(out), &v); err != nil {
		t.Fatal(err, out)
	}
	if c != 1 || v.OK || len(v.Series) != 1 || len(v.Series[0].Missing) != 1 {
		t.Fatalf("%d %+v", c, v)
	}
	if !strings.Contains(out, `"missing": [`) {
		t.Fatal("missing should always be an array")
	}
}

func TestLargeGapDoesNotExpand(t *testing.T) {
	s := analyze(t, "A-1\nA-4000000000\n", Options{}, true)
	if len(s[0].Missing) != 1 || s[0].Missing[0].To != 3999999999 {
		t.Fatalf("%+v", s[0].Missing)
	}
}
