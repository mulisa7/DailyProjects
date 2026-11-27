// harscrub removes credentials from HAR files before they are shared.
package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"harscrub/scrub"
)

const usage = `harscrub - redact cookies, tokens and passwords from a HAR file

Usage:
  harscrub [options] input.har        write input.scrubbed.har
  harscrub -o out.har input.har       choose the output file ("-" for stdout)
  harscrub --check input.har          only report; exit 1 if anything sensitive is found

Options:
  -o FILE         output file (default: <input>.scrubbed.har; "-" is stdout)
  --check         do not write anything, just report
  --drop-bodies   delete response bodies entirely
  --header NAME   also redact this header (repeatable)
  --param NAME    also redact this query/form/JSON key (repeatable)
  -q              no report on stderr
  -h, --help      show this help

Input "-" reads standard input. Exit codes: 0 ok, 1 sensitive data found
(--check only), 2 bad usage or unreadable/invalid input.
`

type config struct {
	input, output string
	check, quiet  bool
	opts          scrub.Options
}

func parseArgs(args []string) (*config, error) {
	c := &config{}
	need := func(i *int, name string) (string, error) {
		if *i+1 >= len(args) {
			return "", fmt.Errorf("%s needs a value", name)
		}
		*i++
		return args[*i], nil
	}
	for i := 0; i < len(args); i++ {
		a := args[i]
		var err error
		var v string
		switch {
		case a == "-h" || a == "--help":
			return nil, errHelp
		case a == "--check":
			c.check = true
		case a == "-q":
			c.quiet = true
		case a == "--drop-bodies":
			c.opts.DropBodies = true
		case a == "-o":
			c.output, err = need(&i, "-o")
		case a == "--header":
			if v, err = need(&i, "--header"); err == nil {
				c.opts.ExtraHeaders = append(c.opts.ExtraHeaders, v)
			}
		case a == "--param":
			if v, err = need(&i, "--param"); err == nil {
				c.opts.ExtraParams = append(c.opts.ExtraParams, v)
			}
		case a != "-" && strings.HasPrefix(a, "-"):
			err = fmt.Errorf("unknown option %q", a)
		default:
			if c.input != "" {
				err = fmt.Errorf("only one input file is allowed (got %q and %q)", c.input, a)
			}
			c.input = a
		}
		if err != nil {
			return nil, err
		}
	}
	if c.input == "" {
		return nil, errors.New("no input file given")
	}
	if c.check && c.output != "" {
		return nil, errors.New("--check cannot be combined with -o")
	}
	return c, nil
}

var errHelp = errors.New("help")

func defaultOutput(in string) string {
	if in == "-" {
		return "-"
	}
	ext := filepath.Ext(in)
	return strings.TrimSuffix(in, ext) + ".scrubbed.har"
}

func run(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	c, err := parseArgs(args)
	if err != nil {
		if err == errHelp {
			fmt.Fprint(stdout, usage)
			return 0
		}
		fmt.Fprintf(stderr, "harscrub: %v\n\n%s", err, usage)
		return 2
	}
	var data []byte
	if c.input == "-" {
		data, err = io.ReadAll(stdin)
	} else {
		data, err = os.ReadFile(c.input)
	}
	if err != nil {
		fmt.Fprintf(stderr, "harscrub: cannot read input: %v\n", err)
		return 2
	}
	if len(bytes.TrimSpace(data)) == 0 {
		fmt.Fprintln(stderr, "harscrub: input is empty")
		return 2
	}
	data = bytes.TrimPrefix(data, []byte("\xef\xbb\xbf"))
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.UseNumber()
	var doc any
	if err := dec.Decode(&doc); err != nil {
		fmt.Fprintf(stderr, "harscrub: input is not valid JSON: %v\n", err)
		return 2
	}
	report, err := scrub.Scrub(doc, c.opts)
	if err != nil {
		fmt.Fprintf(stderr, "harscrub: %v\n", err)
		return 2
	}
	if !c.quiet {
		if report.Total() == 0 {
			fmt.Fprintln(stderr, "nothing sensitive found")
		} else {
			fmt.Fprintf(stderr, "%d value(s) redacted:\n", report.Total())
			for _, l := range report.Lines() {
				fmt.Fprintf(stderr, "  %s\n", l)
			}
		}
	}
	if c.check {
		if report.Total() > 0 {
			return 1
		}
		return 0
	}
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(doc); err != nil {
		fmt.Fprintf(stderr, "harscrub: cannot encode output: %v\n", err)
		return 2
	}
	out := buf.Bytes()
	dest := c.output
	if dest == "" {
		dest = defaultOutput(c.input)
	}
	if dest == "-" {
		stdout.Write(out)
		return 0
	}
	if err := os.WriteFile(dest, out, 0o600); err != nil {
		fmt.Fprintf(stderr, "harscrub: cannot write output: %v\n", err)
		return 2
	}
	if !c.quiet {
		fmt.Fprintf(stderr, "wrote %s\n", dest)
	}
	return 0
}

func main() {
	os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr))
}
