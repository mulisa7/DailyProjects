package main

import (
	"flag"
	"fmt"
	"io"
	"os"
)

const usage = `usage: logfold [-top N] [-min N] [-examples] [FILE ...]

Groups log lines that differ only in timestamps, IDs, IPs and numbers, and
prints each pattern with a count. Reads standard input when no FILE is given.
`

func main() {
	os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr))
}

func run(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("logfold", flag.ContinueOnError)
	fs.SetOutput(stderr)
	fs.Usage = func() { fmt.Fprint(stderr, usage); fs.PrintDefaults() }
	top := fs.Int("top", 0, "show only the N most frequent patterns (0 = all)")
	min := fs.Int("min", 1, "hide patterns seen fewer than N times")
	examples := fs.Bool("examples", false, "also print the first raw line of each pattern")
	if err := fs.Parse(args); err != nil {
		if err == flag.ErrHelp {
			return 0
		}
		return 2
	}
	if *top < 0 || *min < 1 {
		fmt.Fprintln(stderr, "logfold: -top must be >= 0 and -min must be >= 1")
		return 2
	}

	var readers []io.Reader
	if fs.NArg() == 0 {
		readers = append(readers, stdin)
	}
	for _, p := range fs.Args() {
		f, err := os.Open(p)
		if err != nil {
			fmt.Fprintf(stderr, "logfold: %v\n", err)
			return 1
		}
		defer f.Close()
		readers = append(readers, f)
	}

	groups, total, err := Fold(io.MultiReader(readers...))
	if err != nil {
		fmt.Fprintf(stderr, "logfold: reading input: %v\n", err)
		return 1
	}
	if total == 0 {
		fmt.Fprintln(stderr, "logfold: no log lines in input")
		return 1
	}

	shown := 0
	for _, g := range groups {
		if g.Count < *min {
			continue
		}
		if *top > 0 && shown >= *top {
			break
		}
		shown++
		fmt.Fprintf(stdout, "%7d  %s\n", g.Count, g.Template)
		if *examples {
			fmt.Fprintf(stdout, "         e.g. (lines %d-%d) %s\n", g.FirstLine, g.LastLine, g.Example)
		}
	}
	fmt.Fprintf(stdout, "\n%d lines, %d patterns", total, len(groups))
	if shown < len(groups) {
		fmt.Fprintf(stdout, " (%d shown)", shown)
	}
	fmt.Fprintln(stdout)
	return 0
}
