package main

import (
	"bufio"
	"io"
	"regexp"
	"sort"
	"strings"
)

// Replacement rules, applied in order. Earlier rules must run first so that,
// for example, an IP address is not chopped up into four <NUM> tokens.
var rules = []struct {
	re  *regexp.Regexp
	rep string
}{
	{regexp.MustCompile(`\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?`), "<TS>"},
	{regexp.MustCompile(`\d{1,2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2}(?: [+-]\d{4})?`), "<TS>"},
	{regexp.MustCompile(`\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) +\d{1,2} \d{2}:\d{2}:\d{2}\b`), "<TS>"},
	{regexp.MustCompile(`\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b`), "<UUID>"},
	{regexp.MustCompile(`\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b`), "<IP>"},
	{regexp.MustCompile(`\b0x[0-9a-fA-F]+\b`), "<HEX>"},
	// Long hex strings (hashes, request ids). Twelve characters keeps ordinary
	// words out in practice; Go's regexp has no lookahead to require a digit.
	{regexp.MustCompile(`\b[0-9a-f]{12,}\b`), "<HEX>"},
	{regexp.MustCompile(`\b\d+(?:\.\d+)?`), "<NUM>"},
}

// Normalize replaces the variable parts of a log line with placeholders.
func Normalize(line string) string {
	line = strings.TrimSpace(line)
	for _, r := range rules {
		line = r.re.ReplaceAllString(line, r.rep)
	}
	return line
}

// Group is one distinct template with how often it occurred.
type Group struct {
	Template  string
	Count     int
	Example   string // first raw line that matched
	FirstLine int    // 1-based line numbers within the combined input
	LastLine  int
}

// Fold reads lines from r and groups them by normalised template.
// Blank lines are skipped. Groups are returned most frequent first; ties keep
// first-seen order. The second return value is the number of lines counted.
func Fold(r io.Reader) ([]*Group, int, error) {
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 64*1024), 16*1024*1024)
	index := map[string]*Group{}
	var order []*Group
	n, total := 0, 0
	for sc.Scan() {
		n++
		raw := strings.TrimRight(sc.Text(), "\r")
		if strings.TrimSpace(raw) == "" {
			continue
		}
		total++
		t := Normalize(raw)
		g, ok := index[t]
		if !ok {
			g = &Group{Template: t, Example: raw, FirstLine: n}
			index[t] = g
			order = append(order, g)
		}
		g.Count++
		g.LastLine = n
	}
	if err := sc.Err(); err != nil {
		return nil, 0, err
	}
	sort.SliceStable(order, func(i, j int) bool { return order[i].Count > order[j].Count })
	return order, total, nil
}
