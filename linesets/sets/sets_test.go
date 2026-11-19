package sets

import (
	"reflect"
	"strings"
	"testing"
)

func load(t *testing.T, o Options, texts ...string) []Entry {
	t.Helper()
	var fs [][]string
	for _, s := range texts {
		l, err := Read(strings.NewReader(s), o)
		if err != nil {
			t.Fatal(err)
		}
		fs = append(fs, l)
	}
	return Build(fs, o)
}

func texts(es []Entry) []string {
	out := []string{}
	for _, e := range es {
		out = append(out, e.Text)
	}
	return out
}

func sel(t *testing.T, es []Entry, op string, n, target, k int) []string {
	t.Helper()
	r, err := Select(es, op, n, target, k)
	if err != nil {
		t.Fatal(err)
	}
	return texts(r)
}

func TestCommonAndUnion(t *testing.T) {
	es := load(t, Options{}, "a\nb\nc\n", "b\nc\nd\n", "c\ne\n")
	if got := sel(t, es, "common", 3, -1, 0); !reflect.DeepEqual(got, []string{"c"}) {
		t.Errorf("common = %v", got)
	}
	if got := sel(t, es, "union", 3, -1, 0); !reflect.DeepEqual(got, []string{"a", "b", "c", "d", "e"}) {
		t.Errorf("union = %v", got)
	}
}

func TestOnlyDiffMin(t *testing.T) {
	es := load(t, Options{}, "a\nb\nc\n", "b\nc\nd\n", "c\ne\n")
	if got := sel(t, es, "only", 3, -1, 0); !reflect.DeepEqual(got, []string{"a", "d", "e"}) {
		t.Errorf("only = %v", got)
	}
	if got := sel(t, es, "only", 3, 1, 0); !reflect.DeepEqual(got, []string{"d"}) {
		t.Errorf("only file2 = %v", got)
	}
	if got := sel(t, es, "diff", 3, -1, 0); !reflect.DeepEqual(got, []string{"a"}) {
		t.Errorf("diff = %v", got)
	}
	if got := sel(t, es, "min", 3, -1, 2); !reflect.DeepEqual(got, []string{"b", "c"}) {
		t.Errorf("min2 = %v", got)
	}
}

func TestUnsortedInputAndDuplicatesWithinFile(t *testing.T) {
	es := load(t, Options{}, "z\na\nz\nz\n", "a\n")
	if es[0].Text != "z" || len(es[0].Files) != 1 {
		t.Errorf("duplicate within file must count once: %+v", es[0])
	}
	if got := sel(t, es, "common", 2, -1, 0); !reflect.DeepEqual(got, []string{"a"}) {
		t.Errorf("common = %v", got)
	}
}

func TestIgnoreCaseKeepsFirstSpelling(t *testing.T) {
	es := load(t, Options{IgnoreCase: true}, "Alice\nBob\n", "ALICE\ncarol\n")
	got := sel(t, es, "common", 2, -1, 0)
	if !reflect.DeepEqual(got, []string{"Alice"}) {
		t.Errorf("got %v", got)
	}
	es = load(t, Options{}, "Alice\n", "ALICE\n")
	if len(sel(t, es, "common", 2, -1, 0)) != 0 {
		t.Error("case-sensitive should not match")
	}
}

func TestTrimCollapsesWhitespace(t *testing.T) {
	es := load(t, Options{Trim: true}, "  John   Smith \n", "John Smith\n")
	if got := sel(t, es, "common", 2, -1, 0); !reflect.DeepEqual(got, []string{"John Smith"}) {
		t.Errorf("got %v", got)
	}
}

func TestBlankLinesAndCRLFAndBOM(t *testing.T) {
	es := load(t, Options{}, "\xef\xbb\xbfa\r\n\r\nb\r\n", "a\nb\n")
	if got := sel(t, es, "common", 2, -1, 0); !reflect.DeepEqual(got, []string{"a", "b"}) {
		t.Errorf("got %v", got)
	}
	es = load(t, Options{KeepBlank: true}, "a\n\n", "\n")
	if got := sel(t, es, "common", 2, -1, 0); !reflect.DeepEqual(got, []string{""}) {
		t.Errorf("blank kept: %q", got)
	}
}

func TestEmptyFiles(t *testing.T) {
	es := load(t, Options{}, "", "a\n")
	if len(sel(t, es, "common", 2, -1, 0)) != 0 {
		t.Error("common with empty file must be empty")
	}
	if got := sel(t, es, "union", 2, -1, 0); !reflect.DeepEqual(got, []string{"a"}) {
		t.Errorf("got %v", got)
	}
	if len(load(t, Options{}, "", "")) != 0 {
		t.Error("expected no entries")
	}
}

func TestLastLineWithoutNewlineAndLongLine(t *testing.T) {
	es := load(t, Options{}, "a\nb", "b\n"+strings.Repeat("x", 200000)+"\n")
	if got := sel(t, es, "common", 2, -1, 0); !reflect.DeepEqual(got, []string{"b"}) {
		t.Errorf("got %v", got)
	}
}

func TestUnknownOp(t *testing.T) {
	if _, err := Select(nil, "nope", 2, -1, 0); err == nil {
		t.Error("expected error")
	}
}

func TestSortAndFiles(t *testing.T) {
	es := load(t, Options{}, "b\na\n", "a\n")
	r, _ := Select(es, "union", 2, -1, 0)
	SortEntries(r)
	if r[0].Text != "a" || !reflect.DeepEqual(r[0].Files, []int{0, 1}) {
		t.Errorf("%+v", r)
	}
}
