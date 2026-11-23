// datename renames photos and downloads to a date-based name, taking the date
// from EXIF, then the file name, then the modified time.
package main

import (
	"flag"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
)

const usage = `usage: datename [options] PATH...

Renames files to a date-based name. Dry run unless --apply is given.
PATH may be a file or a directory (use -r to descend into subfolders).

options:
`

func collect(paths []string, recursive bool) ([]string, error) {
	var files []string
	for _, p := range paths {
		fi, err := os.Stat(p)
		if err != nil {
			return nil, err
		}
		if !fi.IsDir() {
			files = append(files, p)
			continue
		}
		if !recursive {
			ents, err := os.ReadDir(p)
			if err != nil {
				return nil, err
			}
			for _, e := range ents {
				if e.Type().IsRegular() {
					files = append(files, filepath.Join(p, e.Name()))
				}
			}
			continue
		}
		err = filepath.WalkDir(p, func(path string, d fs.DirEntry, err error) error {
			if err != nil {
				return err
			}
			if d.Type().IsRegular() {
				files = append(files, path)
			}
			return nil
		})
		if err != nil {
			return nil, err
		}
	}
	return files, nil
}

func run(args []string, stdout, stderr io.Writer) int {
	fl := flag.NewFlagSet("datename", flag.ContinueOnError)
	fl.SetOutput(stderr)
	layout := fl.String("format", "YYYY-MM-DD_hhmmss", "name layout; tokens YYYY MM DD hh mm ss")
	sources := fl.String("sources", "exif,name,mtime", "comma list of date sources, tried in order")
	keep := fl.Bool("keep-name", false, "append the original name after the date")
	rec := fl.Bool("r", false, "descend into subdirectories")
	doApply := fl.Bool("apply", false, "actually rename (default is a dry run)")
	fl.Usage = func() {
		fmt.Fprint(stderr, usage)
		fl.PrintDefaults()
	}
	if err := fl.Parse(args); err != nil {
		if err == flag.ErrHelp {
			return 0
		}
		return 2
	}
	if fl.NArg() == 0 {
		fmt.Fprintln(stderr, "datename: no paths given")
		fl.Usage()
		return 2
	}
	srcs, err := parseSources(*sources)
	if err != nil {
		fmt.Fprintln(stderr, "datename:", err)
		return 2
	}
	files, err := collect(fl.Args(), *rec)
	if err != nil {
		fmt.Fprintln(stderr, "datename:", err)
		return 2
	}
	if len(files) == 0 {
		fmt.Fprintln(stdout, "no files found")
		return 0
	}
	plans, problems := buildPlans(files, Options{Layout: *layout, Sources: srcs, KeepName: *keep})
	for _, p := range plans {
		fmt.Fprintf(stdout, "%s -> %s  [%s]\n", p.Old, filepath.Base(p.New), p.Source)
	}
	for _, p := range problems {
		fmt.Fprintln(stderr, "skip:", p)
	}
	if len(plans) == 0 {
		fmt.Fprintln(stdout, "nothing to rename")
	} else if !*doApply {
		fmt.Fprintf(stdout, "%d file(s) would be renamed. Run again with --apply to do it.\n", len(plans))
	} else {
		errs := apply(plans)
		for _, e := range errs {
			fmt.Fprintln(stderr, "error:", e)
		}
		fmt.Fprintf(stdout, "renamed %d file(s)\n", len(plans)-len(errs))
		if len(errs) > 0 {
			return 1
		}
	}
	if len(problems) > 0 {
		return 1
	}
	return 0
}

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}
