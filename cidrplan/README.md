# cidrplan

## Problem

When you carve up a private network (VPC subnets, VPN ranges, office VLANs) the allocations usually live in a wiki page or a spreadsheet. Nothing stops you from handing out a /24 that is already inside somebody else's /16, and finding what is still free means doing binary arithmetic by hand. Calculators like `ipcalc` work on one network at a time and do not know about the other ones you already gave out.

## Solution

A small Go command-line tool that reads a plain text list of your allocations and answers three questions:

- `check`: do any blocks overlap or appear twice?
- `free`: what is left unallocated inside a parent range, as the smallest set of CIDR blocks?
- `next`: where is the first properly aligned /N block that fits?

## Features

- Input is one block per line: `10.0.1.0/24 prod-web`. Labels, blank lines and `#` comments are optional.
- Strict parsing: `10.0.0.1/24` is rejected with a "did you mean 10.0.0.0/24" hint instead of being silently rounded.
- All bad lines are reported in one go, with line numbers.
- Reads from a file or from stdin (`-`).
- Exit codes usable in CI: 0 fine, 1 findings (overlap, or no space), 2 bad input or usage.
- Standard library only.

## Install

Needs Go 1.21 or newer.

    cd cidrplan
    go build -o cidrplan .

## Usage

Example `networks.txt`:

    10.0.0.0/24   prod
    10.0.1.0/25   staging
    10.0.0.128/25 oops

    $ cidrplan check networks.txt
    line 1 10.0.0.0/24 (prod) overlaps line 3 10.0.0.128/25 (oops)
    1 conflict(s) among 3 blocks.

    $ cidrplan free -parent 10.0.0.0/22 networks.txt
    10.0.1.128/25
    10.0.2.0/23
    640 free addresses in 10.0.0.0/22.

    $ cidrplan next -parent 10.0.0.0/22 -size 24 networks.txt
    10.0.2.0/24

Blocks outside the parent are ignored by `free` and `next`. Blocks that overlap each other are handled (the union is treated as used), so you can run `free` on a messy file; use `check` to find the mess.

## Configuration

None. No environment variables, no config file.

## Project structure

    cidr.go       parsing, overlap detection, free-space calculation
    main.go       argument handling and output
    cidr_test.go  unit tests and CLI tests
    go.mod

## Tests

    cd cidrplan
    go test ./...

Covered: valid and invalid CIDRs (host bits, bad prefix, IPv6, garbage), comments and CRLF input, empty input, nested/duplicate/adjacent blocks, free space with overlapping used blocks, a block covering the whole parent, unaligned range splitting, the top of the address space (255.255.255.0/24), alignment in `next`, and every CLI error path with its exit code.

## Limitations

- IPv4 only. IPv6 input is rejected with a clear message.
- `check` compares every pair, so it is O(n^2). Fine for hundreds of blocks, not for hundreds of thousands.
- It does not know about reserved addresses (for example the 5 addresses AWS reserves per subnet) or cloud-specific minimum subnet sizes.
- It reads a text file only; it does not query any cloud provider or write anything back.
- Tested on Linux with Go 1.24 only.

## Future improvements

- IPv6 support.
- Import from `terraform show -json` or a CSV with a CIDR column.
- Option to reserve headroom (for example "leave 25% free").
