package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"
)

const usage = `seqgap - find missing, duplicate and out-of-order numbers in invoice or cheque series

Usage:
  seqgap [flags] [file]      (reads standard input if file is omitted or "-")

Flags:
`

func main() {
	os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr))
}

func run(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("seqgap", flag.ContinueOnError)
	fs.SetOutput(stderr)
	fs.Usage = func() { fmt.Fprint(stderr, usage); fs.PrintDefaults() }
	column := fs.String("column", "", "read a CSV column: 1-based number, or a name (needs -header)")
	header := fs.Bool("header", false, "first CSV row is a header")
	delim := fs.String("delimiter", ",", "CSV delimiter (use \\t for tab)")
	ic := fs.Bool("ignore-case", false, "treat INV-1 and inv-1 as the same series")
	noOrder := fs.Bool("no-order", false, "do not report numbers that are lower than the one before")
	asJSON := fs.Bool("json", false, "print JSON")
	if err := fs.Parse(args); err != nil {
		if err == flag.ErrHelp {
			return 0
		}
		return 2
	}
	if fs.NArg() > 1 {
		fmt.Fprintln(stderr, "seqgap: give at most one file")
		return 2
	}
	d := *delim
	if d == `\t` {
		d = "\t"
	}
	if len([]rune(d)) != 1 {
		fmt.Fprintln(stderr, "seqgap: delimiter must be a single character")
		return 2
	}
	var in io.Reader = stdin
	if fs.NArg() == 1 && fs.Arg(0) != "-" {
		f, err := os.Open(fs.Arg(0))
		if err != nil {
			fmt.Fprintf(stderr, "seqgap: %v\n", err)
			return 2
		}
		defer f.Close()
		in = f
	}
	entries, warns, err := Read(in, Options{Column: *column, Header: *header, Delimiter: []rune(d)[0], IgnoreCase: *ic})
	if err != nil {
		fmt.Fprintf(stderr, "seqgap: %v\n", err)
		return 2
	}
	for _, w := range warns {
		fmt.Fprintf(stderr, "warning: skipped %s\n", w)
	}
	if len(entries) == 0 {
		fmt.Fprintln(stderr, "seqgap: no identifiers found in the input")
		return 2
	}
	series := Analyze(entries, !*noOrder)
	problems := false
	for _, s := range series {
		if s.Problems() {
			problems = true
		}
	}
	if *asJSON {
		enc := json.NewEncoder(stdout)
		enc.SetIndent("", "  ")
		enc.Encode(map[string]any{"series": series, "skipped": len(warns), "ok": !problems})
	} else {
		writeText(stdout, series)
	}
	if problems {
		return 1
	}
	return 0
}

func label(s Series) string {
	if s.Prefix == "" && s.Suffix == "" {
		return "(plain numbers)"
	}
	return s.Prefix + "#" + s.Suffix
}

func writeText(w io.Writer, series []Series) {
	for _, s := range series {
		fmt.Fprintf(w, "%s  %d entries, %d to %d\n", label(s), s.Count, s.Min, s.Max)
		if !s.Problems() {
			fmt.Fprintln(w, "  ok: no gaps, duplicates or ordering problems")
			continue
		}
		for _, r := range s.Missing {
			if r.From == r.To {
				fmt.Fprintf(w, "  missing %d\n", r.From)
			} else {
				fmt.Fprintf(w, "  missing %d-%d (%d numbers)\n", r.From, r.To, r.To-r.From+1)
			}
		}
		for _, d := range s.Duplicates {
			fmt.Fprintf(w, "  duplicate %d on lines %s\n", d.Number, joinInts(d.Lines))
		}
		for _, o := range s.OutOfOrder {
			fmt.Fprintf(w, "  out of order: line %d (%s) comes after %d\n", o.Line, o.Raw, o.Previous)
		}
		if len(s.Widths) > 0 {
			fmt.Fprintf(w, "  inconsistent zero padding, widths seen: %s\n", joinInts(s.Widths))
		}
	}
}

func joinInts(v []int) string {
	p := make([]string, len(v))
	for i, n := range v {
		p[i] = strconv.Itoa(n)
	}
	return strings.Join(p, ", ")
}
