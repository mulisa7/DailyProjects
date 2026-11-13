package main

import (
	"flag"
	"fmt"
	"io"
	"os"
)

func main() { os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr)) }

func run(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("cronlint", flag.ContinueOnError)
	fs.SetOutput(stderr)
	system := fs.Bool("system", false, "lines have a user column (/etc/crontab, /etc/cron.d files)")
	exists := fs.Bool("check-exists", false, "look commands up on this machine")
	strict := fs.Bool("strict", false, "exit 1 on warnings too")
	path := fs.String("cron-path", DefaultCronPath, "PATH cron uses when the file sets none")
	fs.Usage = func() {
		fmt.Fprintln(stderr, "usage: cronlint [flags] [file ...]   (no file or '-' reads stdin; try: crontab -l | cronlint)")
		fs.PrintDefaults()
	}
	if err := fs.Parse(args); err != nil {
		if err == flag.ErrHelp {
			return 0
		}
		return 2
	}
	files := fs.Args()
	if len(files) == 0 {
		files = []string{"-"}
	}
	opt := Options{System: *system, CheckExists: *exists, DefaultPath: *path}
	errs, warns := 0, 0
	for _, name := range files {
		var data []byte
		var err error
		label := name
		if name == "-" {
			label = "<stdin>"
			data, err = io.ReadAll(stdin)
		} else {
			data, err = os.ReadFile(name)
		}
		if err != nil {
			fmt.Fprintf(stderr, "cronlint: %v\n", err)
			return 2
		}
		if len(data) == 0 {
			fmt.Fprintf(stderr, "cronlint: %s: empty crontab, nothing to check\n", label)
			continue
		}
		for _, f := range Check(string(data), opt) {
			fmt.Fprintf(stdout, "%s:%d: %s: [%s] %s\n", label, f.Line, f.Sev, f.Code, f.Msg)
			if f.Sev == Error {
				errs++
			} else {
				warns++
			}
		}
	}
	fmt.Fprintf(stdout, "%d error(s), %d warning(s)\n", errs, warns)
	if errs > 0 || (*strict && warns > 0) {
		return 1
	}
	return 0
}
