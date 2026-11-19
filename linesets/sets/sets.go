package sets

import (
	"bufio"
	"fmt"
	"io"
	"sort"
	"strings"
)

// Options control how lines are normalised before comparison.
type Options struct {
	IgnoreCase bool // compare case-insensitively
	Trim       bool // trim ends and collapse inner whitespace runs
	KeepBlank  bool // keep empty lines (default: skip them)
}

// Entry is one distinct line (after normalisation) and the files it appears in.
type Entry struct {
	Text  string // first-seen original text (trimmed if Trim is set)
	Files []int  // sorted indexes of files containing it
}

// Key normalises a line according to opts.
func Key(line string, o Options) string {
	if o.Trim {
		line = strings.Join(strings.Fields(line), " ")
	}
	if o.IgnoreCase {
		line = strings.ToLower(line)
	}
	return line
}

// Read loads the distinct lines of one reader.
func Read(r io.Reader, o Options) ([]string, error) {
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 64*1024), 16*1024*1024)
	var out []string
	for sc.Scan() {
		l := strings.TrimSuffix(sc.Text(), "\r")
		l = strings.TrimPrefix(l, "\xef\xbb\xbf")
		if o.Trim {
			l = strings.Join(strings.Fields(l), " ")
		}
		if l == "" && !o.KeepBlank {
			continue
		}
		out = append(out, l)
	}
	return out, sc.Err()
}

// Build combines per-file line lists into entries in first-seen order.
func Build(files [][]string, o Options) []Entry {
	idx := map[string]int{}
	var entries []Entry
	for fi, lines := range files {
		for _, l := range lines {
			k := Key(l, o)
			i, ok := idx[k]
			if !ok {
				idx[k] = len(entries)
				entries = append(entries, Entry{Text: l, Files: []int{fi}})
				continue
			}
			e := &entries[i]
			if e.Files[len(e.Files)-1] != fi {
				e.Files = append(e.Files, fi)
			}
		}
	}
	return entries
}

// Ops supported by Select.
var Ops = []string{"union", "common", "only", "diff", "min"}

// Select filters entries. n is the number of files.
//
//	union:  in any file
//	common: in every file
//	only:   in exactly one file (when target >= 0, only that file)
//	diff:   in the first file and in no other file
//	min:    in at least k files
func Select(entries []Entry, op string, n, target, k int) ([]Entry, error) {
	valid := false
	for _, o := range Ops {
		valid = valid || o == op
	}
	if !valid {
		return nil, fmt.Errorf("unknown operation %q (want one of %s)", op, strings.Join(Ops, ", "))
	}
	var out []Entry
	for _, e := range entries {
		keep := false
		switch op {
		case "union":
			keep = true
		case "common":
			keep = len(e.Files) == n
		case "only":
			keep = len(e.Files) == 1 && (target < 0 || e.Files[0] == target)
		case "diff":
			keep = len(e.Files) == 1 && e.Files[0] == 0
		case "min":
			keep = len(e.Files) >= k
		}
		if keep {
			out = append(out, e)
		}
	}
	return out, nil
}

// SortEntries orders entries alphabetically by text.
func SortEntries(es []Entry) {
	sort.SliceStable(es, func(i, j int) bool { return es[i].Text < es[j].Text })
}
