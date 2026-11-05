package main

import (
	"encoding/csv"
	"errors"
	"fmt"
	"io"
	"sort"
	"strconv"
	"strings"
)

// Entry is one identifier read from the input.
type Entry struct {
	Line  int    // 1-based input line (record number for CSV)
	Raw   string // identifier as written
	Key   string // series key: text around the number
	Num   uint64
	Width int // digits as written, used to spot padding changes
}

// Range is an inclusive run of missing numbers.
type Range struct {
	From uint64 `json:"from"`
	To   uint64 `json:"to"`
}

// Dup lists the lines on which one number appears more than once.
type Dup struct {
	Number uint64 `json:"number"`
	Lines  []int  `json:"lines"`
}

// OutOfOrder is a number that is lower than the one before it in the input.
type OutOfOrder struct {
	Line     int    `json:"line"`
	Raw      string `json:"raw"`
	Previous uint64 `json:"previous"`
}

// Series is the analysis of all identifiers sharing a prefix and suffix.
type Series struct {
	Prefix     string       `json:"prefix"`
	Suffix     string       `json:"suffix"`
	Count      int          `json:"count"`
	Min        uint64       `json:"min"`
	Max        uint64       `json:"max"`
	Missing    []Range      `json:"missing"`
	Duplicates []Dup        `json:"duplicates"`
	OutOfOrder []OutOfOrder `json:"out_of_order"`
	Widths     []int        `json:"widths,omitempty"` // set only if padding varies
}

// Problems reports whether the series has anything worth flagging.
func (s Series) Problems() bool {
	return len(s.Missing) > 0 || len(s.Duplicates) > 0 || len(s.OutOfOrder) > 0 || len(s.Widths) > 0
}

// ParseID splits an identifier around its last run of digits.
// "INV-2024-0012" gives prefix "INV-2024-", number 12, width 4.
func ParseID(raw string, ignoreCase bool) (Entry, error) {
	s := strings.TrimSpace(raw)
	if s == "" {
		return Entry{}, errors.New("empty value")
	}
	end := -1
	for i := len(s) - 1; i >= 0; i-- {
		if s[i] >= '0' && s[i] <= '9' {
			end = i + 1
			break
		}
	}
	if end < 0 {
		return Entry{}, fmt.Errorf("no number in %q", s)
	}
	start := end
	for start > 0 && s[start-1] >= '0' && s[start-1] <= '9' {
		start--
	}
	n, err := strconv.ParseUint(s[start:end], 10, 64)
	if err != nil {
		return Entry{}, fmt.Errorf("number too large in %q", s)
	}
	key := s[:start] + "\x00" + s[end:]
	if ignoreCase {
		key = strings.ToLower(key)
	}
	return Entry{Raw: s, Key: key, Num: n, Width: end - start}, nil
}

// Options controls reading.
type Options struct {
	Column     string // "" means whole line; otherwise 1-based index or header name
	Header     bool
	Delimiter  rune
	IgnoreCase bool
}

// Read parses entries from r. Lines that cannot be parsed are returned as
// warnings so one bad row does not hide the rest.
func Read(r io.Reader, o Options) ([]Entry, []string, error) {
	var entries []Entry
	var warns []string
	if o.Column == "" {
		data, err := io.ReadAll(r)
		if err != nil {
			return nil, nil, err
		}
		text := strings.TrimPrefix(string(data), "\ufeff")
		for i, line := range strings.Split(text, "\n") {
			line = strings.TrimRight(line, "\r")
			if strings.TrimSpace(line) == "" || strings.HasPrefix(strings.TrimSpace(line), "#") {
				continue
			}
			e, err := ParseID(line, o.IgnoreCase)
			if err != nil {
				warns = append(warns, fmt.Sprintf("line %d: %v", i+1, err))
				continue
			}
			e.Line = i + 1
			entries = append(entries, e)
		}
		return entries, warns, nil
	}

	cr := csv.NewReader(r)
	cr.Comma = o.Delimiter
	cr.FieldsPerRecord = -1
	cr.LazyQuotes = true
	idx := -1
	if n, err := strconv.Atoi(o.Column); err == nil {
		if n < 1 {
			return nil, nil, errors.New("column numbers start at 1")
		}
		idx = n - 1
	} else if !o.Header {
		return nil, nil, fmt.Errorf("column %q is a name, which needs --header", o.Column)
	}
	rec := 0
	first := true
	for {
		row, err := cr.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, nil, fmt.Errorf("reading CSV: %v", err)
		}
		rec++
		if first {
			first = false
			if len(row) > 0 {
				row[0] = strings.TrimPrefix(row[0], "\ufeff")
			}
			if o.Header {
				if idx < 0 {
					for i, h := range row {
						if strings.EqualFold(strings.TrimSpace(h), o.Column) {
							idx = i
							break
						}
					}
					if idx < 0 {
						return nil, nil, fmt.Errorf("no column named %q in header", o.Column)
					}
				}
				continue
			}
		}
		if len(row) == 1 && strings.TrimSpace(row[0]) == "" {
			continue
		}
		if idx >= len(row) {
			warns = append(warns, fmt.Sprintf("row %d: has %d columns, wanted column %d", rec, len(row), idx+1))
			continue
		}
		if strings.TrimSpace(row[idx]) == "" {
			warns = append(warns, fmt.Sprintf("row %d: empty value", rec))
			continue
		}
		e, err := ParseID(row[idx], o.IgnoreCase)
		if err != nil {
			warns = append(warns, fmt.Sprintf("row %d: %v", rec, err))
			continue
		}
		e.Line = rec
		entries = append(entries, e)
	}
	return entries, warns, nil
}

// Analyze groups entries into series and finds gaps, duplicates and ordering problems.
func Analyze(entries []Entry, checkOrder bool) []Series {
	groups := map[string][]Entry{}
	var keys []string
	for _, e := range entries {
		if _, ok := groups[e.Key]; !ok {
			keys = append(keys, e.Key)
		}
		groups[e.Key] = append(groups[e.Key], e)
	}
	sort.Strings(keys)
	var out []Series
	for _, k := range keys {
		g := groups[k]
		parts := strings.SplitN(k, "\x00", 2)
		s := Series{Prefix: parts[0], Suffix: parts[1], Count: len(g), Min: g[0].Num, Max: g[0].Num,
			Missing: []Range{}, Duplicates: []Dup{}, OutOfOrder: []OutOfOrder{}}
		seen := map[uint64][]int{}
		widths := map[int]bool{}
		for i, e := range g {
			if e.Num < s.Min {
				s.Min = e.Num
			}
			if e.Num > s.Max {
				s.Max = e.Num
			}
			seen[e.Num] = append(seen[e.Num], e.Line)
			widths[e.Width] = true
			if checkOrder && i > 0 && e.Num < g[i-1].Num {
				s.OutOfOrder = append(s.OutOfOrder, OutOfOrder{Line: e.Line, Raw: e.Raw, Previous: g[i-1].Num})
			}
		}
		nums := make([]uint64, 0, len(seen))
		for n := range seen {
			nums = append(nums, n)
		}
		sort.Slice(nums, func(a, b int) bool { return nums[a] < nums[b] })
		for i, n := range nums {
			if len(seen[n]) > 1 {
				s.Duplicates = append(s.Duplicates, Dup{Number: n, Lines: seen[n]})
			}
			if i > 0 && n > nums[i-1]+1 {
				s.Missing = append(s.Missing, Range{From: nums[i-1] + 1, To: n - 1})
			}
		}
		// Padding only matters when numbers are not simply longer because they grew
		// (9 -> 10 is fine); flag widths that differ for the same-length numbers.
		bad := false
		byLen := map[int]map[int]bool{}
		for _, e := range g {
			l := len(strconv.FormatUint(e.Num, 10))
			if byLen[l] == nil {
				byLen[l] = map[int]bool{}
			}
			byLen[l][e.Width] = true
		}
		for _, w := range byLen {
			if len(w) > 1 {
				bad = true
			}
		}
		if bad {
			for w := range widths {
				s.Widths = append(s.Widths, w)
			}
			sort.Ints(s.Widths)
		}
		out = append(out, s)
	}
	return out
}
