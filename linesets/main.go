package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"strings"

	"linesets/sets"
)

const usage = `usage: linesets [flags] <op> FILE [FILE...]

ops:
  union    lines found in any file
  common   lines found in every file
  only     lines found in exactly one file (-f N limits to file N, 1-based)
  diff     lines in the first file and in no other file
  min      lines found in at least -k files

flags:
`

func main() { os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr)) }

func run(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("linesets", flag.ContinueOnError)
	fs.SetOutput(stderr)
	fs.Usage = func() { fmt.Fprint(stderr, usage); fs.PrintDefaults() }
	ic := fs.Bool("i", false, "ignore case")
	trim := fs.Bool("t", false, "trim and collapse whitespace")
	blank := fs.Bool("b", false, "keep blank lines")
	sorted := fs.Bool("s", false, "sort output alphabetically (default: first-seen order)")
	count := fs.Bool("c", false, "prefix each line with how many files contain it")
	which := fs.Bool("w", false, "append the (1-based) files that contain each line")
	target := fs.Int("f", 0, "with 'only': restrict to this file number")
	k := fs.Int("k", 2, "with 'min': minimum number of files")
	// Parse flags anywhere on the line, not only before the operation.
	var rest []string
	for {
		if err := fs.Parse(args); err != nil {
			if err == flag.ErrHelp {
				return 0
			}
			return 2
		}
		args = fs.Args()
		if len(args) == 0 {
			break
		}
		rest = append(rest, args[0])
		args = args[1:]
	}
	if len(rest) < 2 {
		fmt.Fprintln(stderr, "linesets: need an operation and at least one file (use - for stdin)")
		fs.Usage()
		return 2
	}
	op, names := rest[0], rest[1:]
	valid := false
	for _, o := range sets.Ops {
		valid = valid || o == op
	}
	if !valid {
		fmt.Fprintf(stderr, "linesets: unknown operation %q (want one of %s)\n", op, strings.Join(sets.Ops, ", "))
		return 2
	}
	if op != "union" && op != "min" && len(names) < 2 {
		fmt.Fprintf(stderr, "linesets: %q needs at least two files\n", op)
		return 2
	}
	if *target < 0 || *target > len(names) {
		fmt.Fprintf(stderr, "linesets: -f %d is out of range (1-%d)\n", *target, len(names))
		return 2
	}
	if op == "min" && (*k < 1 || *k > len(names)) {
		fmt.Fprintf(stderr, "linesets: -k %d is out of range (1-%d)\n", *k, len(names))
		return 2
	}
	o := sets.Options{IgnoreCase: *ic, Trim: *trim, KeepBlank: *blank}
	var files [][]string
	stdinUsed := false
	for _, n := range names {
		var r io.Reader
		if n == "-" {
			if stdinUsed {
				fmt.Fprintln(stderr, "linesets: stdin (-) can only be used once")
				return 2
			}
			stdinUsed = true
			r = stdin
		} else {
			f, err := os.Open(n)
			if err != nil {
				fmt.Fprintf(stderr, "linesets: %v\n", err)
				return 2
			}
			defer f.Close()
			r = f
		}
		lines, err := sets.Read(r, o)
		if err != nil {
			fmt.Fprintf(stderr, "linesets: reading %s: %v\n", n, err)
			return 2
		}
		files = append(files, lines)
	}
	entries := sets.Build(files, o)
	res, err := sets.Select(entries, op, len(names), *target-1, *k)
	if err != nil {
		fmt.Fprintln(stderr, "linesets:", err)
		return 2
	}
	if *sorted {
		sets.SortEntries(res)
	}
	for _, e := range res {
		var b strings.Builder
		if *count {
			fmt.Fprintf(&b, "%d\t", len(e.Files))
		}
		b.WriteString(e.Text)
		if *which {
			b.WriteString("\t[")
			for i, f := range e.Files {
				if i > 0 {
					b.WriteString(",")
				}
				fmt.Fprint(&b, f+1)
			}
			b.WriteString("]")
		}
		fmt.Fprintln(stdout, b.String())
	}
	if len(res) == 0 {
		return 1
	}
	return 0
}
