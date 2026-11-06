# branchsweep

## Problem
Local git branches pile up. `git branch --merged` finds branches merged with a merge commit, but misses the ones merged through a squash or rebase on a hosting site, which is how most teams merge now. Those branches look unmerged forever, so people either keep them or paste a long shell one-liner from Stack Overflow and hope it does not delete something useful.

## Solution
A small Python script that classifies every local branch and, only when asked, deletes the safe ones. Squash and rebase merges are detected with `git cherry`, which compares patch contents instead of commit ids.

## Features
- Statuses: `merged`, `squash-merged`, `upstream-gone` (remote branch deleted), `stale` (unmerged and older than N days), `active`, `protected`.
- Base branch is detected from `origin/HEAD`, then `main`, `master`, `trunk`, `develop`. Override with `--base`.
- The base branch, the checked-out branch, and `main/master/develop/dev/trunk` are never listed for deletion; add more with `--keep`.
- Read-only by default. `--delete` removes only `merged` branches (`git branch -d`). Squash-merged, gone and stale branches also need `--force` (`-D`).
- `--json` output, `--only` filter, exit code 2 for usage or git errors, 1 if some deletions were skipped.
- Standard library only.

## Install and usage
Needs Python 3.8+ and git on PATH.

```
python3 branchsweep.py                      # report for the repo in the current directory
python3 branchsweep.py ~/code/app --stale-days 30
python3 branchsweep.py --only squash-merged
python3 branchsweep.py --json
python3 branchsweep.py --delete             # delete merged branches only
python3 branchsweep.py --delete --force     # also squash-merged, gone and stale
```

Run the report first and read it before using `--force`.

## Configuration
No environment variables or config files. Options: `--base`, `--stale-days` (default 90, 0 disables), `--keep`, `--only`, `--json`, `--delete`, `--force`.

## Structure
```
branchsweep.py        the tool
test_branchsweep.py   unit tests (build throwaway repos in temp dirs)
```

## Tests
```
python3 -m unittest -v
```
Tests create real repositories with git and cover merge commits, squash merges, stale dates, protected and current branches, deletion with and without `--force`, JSON output, empty repos, non-repositories, bad base names and bad flags.

## Limitations
- Local branches only; remote branches are not touched and no `git fetch` is run, so `upstream-gone` is only as fresh as your last fetch/prune.
- `git cherry` fails to match a squash merge if the squashed result was edited (conflict fixes, amended message does not matter, changed content does), so such branches show as `active`.
- A branch checked out in another worktree cannot be deleted; git's error is reported as skipped.
- Tested on Linux with git 2.43 only. Not tested on Windows or with very large repositories.
- Deleted branches can be recovered with `git reflog`, but the tool prints no undo hints.

## Future improvements
- Option to also delete the remote branch.
- Print the commit id of each deleted branch for easy recovery.
- Optional `git fetch --prune` before reporting.
