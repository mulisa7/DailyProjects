# permcheck

## Problem

Files that hold secrets often end up readable by every user on the machine: a `.env` created with the default umask, an AWS credentials file copied from another host, a `.npmrc` with a registry token. OpenSSH refuses a private key that is too open, but nothing warns about the others. Existing tools cover pieces (ssh key checks, secret scanners that read file contents), but I did not find a simple one that audits modes across all of these at once.

## Solution

`permcheck` walks one or more folders, picks out files that look like secrets by name and location, and reports any whose mode gives access to group or others. With `--fix` it removes the offending bits. It only looks at metadata and never reads file contents.

## Features

- Recognises ssh private keys (`id_*`, `*.pem`, `*.key`), `.env` and `.env.*` files, `~/.aws/credentials`, `~/.docker/config.json`, `~/.kube/config`, `~/.azure/accessTokens.json`, `.npmrc`, `.pypirc`, `.netrc`, `.git-credentials`, and `.ssh` directories
- Ignores `.env.example`, `.env.sample`, `.env.template`, public keys, `known_hosts` and ssh `config`
- Files must be 0600 or stricter; `.ssh` directories 0700 or stricter
- `--fix` only removes bits (0644 becomes 0600, 0440 becomes 0400); it never adds permissions
- `--json` output for scripts
- Skips `.git`, `node_modules`, `target`, `.venv`, `venv`, `__pycache__`; does not follow symlinks
- No dependencies

## Install

Needs a Rust toolchain.

```
cd permcheck
cargo build --release
# binary: target/release/permcheck
```

## Usage

```
permcheck [--fix] [--depth N] [--json] [PATH ...]
```

```
$ permcheck ~
0644 /home/me/projects/app/.env -> 0600  env file (world-accessible)
0664 /home/me/.aws/credentials -> 0664  cloud credentials (group-accessible)
2 problem(s) in 9 files checked; run with --fix to chmod
```

(The example is illustrative output; the arrow shows the mode `--fix` would set.)

Exit codes: 0 nothing wrong, 1 problems found and not fixed (or a fix failed), 2 bad arguments or unreadable path. Unreadable subfolders produce a warning on stderr and the scan continues. Default depth is 6 folders.

## Configuration

None. There are no environment variables or config files.

## Project structure

```
permcheck/
  Cargo.toml
  src/lib.rs     name classification, mode rules, scanning, fixing
  src/main.rs    argument parsing and output
  tests/cli.rs   end-to-end tests against temporary folders
```

## Tests

```
cd permcheck
cargo test
```

Covers name classification, mode arithmetic, clean and empty trees, group/world detection, `--fix` results, `.ssh` directory mode, JSON output, the depth limit, skipped folders, symlinks and bad arguments.

## Limitations

- Unix only (uses mode bits). Windows ACLs are not examined.
- Detection is by file name and folder, so a secret stored under another name is missed, and a file named like a key but holding something else is flagged.
- Only classic mode bits are checked. ACLs, ownership (a file owned by another user) and parent directory permissions are not.
- `--fix` does not change ownership, and was only tested on files owned by the test user.
- Not tested on macOS or on network filesystems that report synthetic modes.
- Running as root against other users' home folders was not tested.

## Future improvements

- Check file ownership and parent folder modes
- A user-supplied list of extra file name patterns
- Optionally follow symlinks to their target
