package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"strconv"
)

const usage = `cidrplan - check and plan IPv4 CIDR allocations from a text file

Usage:
  cidrplan check <file>                          report overlapping or duplicate blocks
  cidrplan free  -parent <cidr> <file>           list unallocated space inside a parent range
  cidrplan next  -parent <cidr> -size <n> <file> first free /n block inside the parent

Use "-" as the file to read standard input.
Input lines look like:  10.0.1.0/24 prod-web   (labels and # comments are optional)

Exit codes: 0 ok, 1 findings (overlaps, no space), 2 bad input or usage.
`

func main() { os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr)) }

func load(path string, stdin io.Reader) ([]Block, error) {
	var r io.Reader = stdin
	if path != "-" {
		f, err := os.Open(path)
		if err != nil {
			return nil, err
		}
		defer f.Close()
		r = f
	}
	return ParseBlocks(r)
}

func run(args []string, stdin io.Reader, out, errw io.Writer) int {
	if len(args) == 0 || args[0] == "-h" || args[0] == "--help" {
		fmt.Fprint(errw, usage)
		if len(args) == 0 {
			return 2
		}
		return 0
	}
	cmd := args[0]
	fs := flag.NewFlagSet(cmd, flag.ContinueOnError)
	fs.SetOutput(errw)
	parent := fs.String("parent", "", "parent CIDR")
	size := fs.String("size", "", "prefix length wanted")
	switch cmd {
	case "check", "free", "next":
	default:
		fmt.Fprintf(errw, "cidrplan: unknown command %q\n\n%s", cmd, usage)
		return 2
	}
	if err := fs.Parse(args[1:]); err != nil {
		return 2
	}
	if fs.NArg() != 1 {
		fmt.Fprintf(errw, "cidrplan %s: expected exactly one input file\n", cmd)
		return 2
	}
	blocks, err := load(fs.Arg(0), stdin)
	if err != nil {
		fmt.Fprintf(errw, "cidrplan: %v\n", err)
		return 2
	}

	if cmd == "check" {
		if len(blocks) == 0 {
			fmt.Fprintln(out, "No blocks found in input.")
			return 0
		}
		cs := FindConflicts(blocks)
		if len(cs) == 0 {
			fmt.Fprintf(out, "OK: %d blocks, no overlaps.\n", len(blocks))
			return 0
		}
		for _, c := range cs {
			kind := "overlaps"
			if c.Duplicate {
				kind = "duplicates"
			}
			fmt.Fprintf(out, "line %d %s %s line %d %s\n", c.A.Line, describe(c.A), kind, c.B.Line, describe(c.B))
		}
		fmt.Fprintf(out, "%d conflict(s) among %d blocks.\n", len(cs), len(blocks))
		return 1
	}

	if *parent == "" {
		fmt.Fprintf(errw, "cidrplan %s: -parent is required\n", cmd)
		return 2
	}
	ps, pe, err := ParseCIDR(*parent)
	if err != nil {
		fmt.Fprintf(errw, "cidrplan: parent: %v\n", err)
		return 2
	}
	free := FreeRanges(Range{ps, pe}, blocks)

	if cmd == "free" {
		if len(free) == 0 {
			fmt.Fprintf(out, "No free space left in %s.\n", *parent)
			return 1
		}
		var total uint64
		for _, r := range free {
			total += uint64(r.End) - uint64(r.Start) + 1
			for _, c := range RangeToCIDRs(r) {
				fmt.Fprintln(out, c)
			}
		}
		fmt.Fprintf(out, "%d free addresses in %s.\n", total, *parent)
		return 0
	}

	if *size == "" {
		fmt.Fprintln(errw, "cidrplan next: -size is required")
		return 2
	}
	n, err := strconv.Atoi(*size)
	if err != nil || n < 0 || n > 32 {
		fmt.Fprintf(errw, "cidrplan next: -size must be a number from 0 to 32, got %q\n", *size)
		return 2
	}
	if c, ok := NextFree(free, n); ok {
		fmt.Fprintln(out, c)
		return 0
	}
	fmt.Fprintf(out, "No free /%d block in %s.\n", n, *parent)
	return 1
}

func describe(b Block) string {
	if b.Label == "" {
		return b.CIDR
	}
	return fmt.Sprintf("%s (%s)", b.CIDR, b.Label)
}
