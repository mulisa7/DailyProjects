package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

// Plan is one intended rename.
type Plan struct {
	Old, New string
	Source   string // exif, name or mtime
}

var layoutTokens = strings.NewReplacer("YYYY", "2006", "MM", "01", "DD", "02", "hh", "15", "mm", "04", "ss", "05")

func formatStamp(t time.Time, layout string) string {
	return t.Format(layoutTokens.Replace(layout))
}

// resolveDate tries each source in order and returns the first date found.
func resolveDate(path string, sources []string) (time.Time, string, error) {
	base := filepath.Base(path)
	for _, s := range sources {
		switch s {
		case "exif":
			if t, err := dateFromExifFile(path); err == nil {
				return t, "exif", nil
			}
		case "name":
			if t, ok := dateFromName(base); ok {
				return t, "name", nil
			}
		case "mtime":
			if fi, err := os.Stat(path); err == nil {
				return fi.ModTime(), "mtime", nil
			}
		}
	}
	return time.Time{}, "", fmt.Errorf("no date found from sources %s", strings.Join(sources, ","))
}

func parseSources(s string) ([]string, error) {
	var out []string
	for _, p := range strings.Split(s, ",") {
		p = strings.TrimSpace(p)
		if p == "" {
			continue
		}
		if p != "exif" && p != "name" && p != "mtime" {
			return nil, fmt.Errorf("unknown source %q (use exif, name, mtime)", p)
		}
		out = append(out, p)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("no sources given")
	}
	return out, nil
}

// Options controls planning.
type Options struct {
	Layout   string
	Sources  []string
	KeepName bool
}

// buildPlans computes target names for the given files. taken tracks names
// that would exist after the renames so collisions get a numeric suffix.
func buildPlans(files []string, o Options) ([]Plan, []string) {
	sort.Strings(files)
	taken := map[string]bool{}
	for _, f := range files {
		taken[f] = true
	}
	var plans []Plan
	var problems []string
	for _, f := range files {
		t, src, err := resolveDate(f, o.Sources)
		if err != nil {
			problems = append(problems, fmt.Sprintf("%s: %v", f, err))
			continue
		}
		dir, base := filepath.Split(f)
		ext := filepath.Ext(base)
		stem := strings.TrimSuffix(base, ext)
		stamp := formatStamp(t, o.Layout)
		if o.KeepName && strings.HasPrefix(stem, stamp) {
			continue // already stamped
		}
		newStem := stamp
		if o.KeepName {
			newStem = stamp + "_" + stem
		}
		cand := dir + newStem + ext
		if cand == f {
			continue
		}
		delete(taken, f)
		for n := 2; taken[cand]; n++ {
			cand = fmt.Sprintf("%s%s_%d%s", dir, newStem, n, ext)
		}
		taken[cand] = true
		plans = append(plans, Plan{Old: f, New: cand, Source: src})
	}
	return plans, problems
}

// apply performs renames, refusing to overwrite anything. Renames whose
// target is another file's current name are done in two steps via a temp name.
func apply(plans []Plan) []error {
	var errs []error
	current := map[string]bool{}
	for _, p := range plans {
		current[p.Old] = true
	}
	var pending []Plan
	for _, p := range plans {
		if current[p.New] {
			tmp := p.Old + ".datename-tmp"
			if err := os.Rename(p.Old, tmp); err != nil {
				errs = append(errs, err)
				continue
			}
			pending = append(pending, Plan{Old: tmp, New: p.New})
			continue
		}
		if err := safeRename(p.Old, p.New); err != nil {
			errs = append(errs, err)
		}
	}
	for _, p := range pending {
		if err := safeRename(p.Old, p.New); err != nil {
			errs = append(errs, err)
		}
	}
	return errs
}

func safeRename(old, new string) error {
	if _, err := os.Lstat(new); err == nil {
		return fmt.Errorf("%s: target %s already exists, skipped", old, new)
	}
	return os.Rename(old, new)
}
