package main

import (
	"bufio"
	"fmt"
	"io"
	"net/netip"
	"sort"
	"strings"
)

// Block is one IPv4 CIDR from the input file.
type Block struct {
	CIDR  string
	Label string
	Line  int
	Start uint32
	End   uint32 // inclusive
}

func (b Block) size() uint64 { return uint64(b.End) - uint64(b.Start) + 1 }

func ipToUint(a netip.Addr) uint32 {
	v := a.As4()
	return uint32(v[0])<<24 | uint32(v[1])<<16 | uint32(v[2])<<8 | uint32(v[3])
}

func uintToIP(u uint32) string {
	return fmt.Sprintf("%d.%d.%d.%d", u>>24, (u>>16)&255, (u>>8)&255, u&255)
}

// ParseCIDR parses a strict IPv4 CIDR. Host bits must be zero.
func ParseCIDR(s string) (start, end uint32, err error) {
	p, err := netip.ParsePrefix(s)
	if err != nil {
		return 0, 0, fmt.Errorf("%q is not a valid CIDR", s)
	}
	if !p.Addr().Is4() {
		return 0, 0, fmt.Errorf("%q: only IPv4 is supported", s)
	}
	if p.Masked() != p {
		return 0, 0, fmt.Errorf("%q has host bits set (did you mean %s?)", s, p.Masked())
	}
	bits := p.Bits()
	start = ipToUint(p.Addr())
	end = start | (uint32(0xFFFFFFFF) >> uint(bits))
	if bits == 0 {
		end = 0xFFFFFFFF
	}
	return start, end, nil
}

// ParseBlocks reads "CIDR [label...]" lines. Blank lines and # comments are skipped.
// All bad lines are reported together.
func ParseBlocks(r io.Reader) ([]Block, error) {
	var blocks []Block
	var errs []string
	sc := bufio.NewScanner(r)
	n := 0
	for sc.Scan() {
		n++
		line := sc.Text()
		if i := strings.Index(line, "#"); i >= 0 {
			line = line[:i]
		}
		f := strings.Fields(line)
		if len(f) == 0 {
			continue
		}
		s, e, err := ParseCIDR(f[0])
		if err != nil {
			errs = append(errs, fmt.Sprintf("line %d: %v", n, err))
			continue
		}
		blocks = append(blocks, Block{CIDR: f[0], Label: strings.Join(f[1:], " "), Line: n, Start: s, End: e})
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	if len(errs) > 0 {
		return nil, fmt.Errorf("%s", strings.Join(errs, "\n"))
	}
	return blocks, nil
}

// Conflict is a pair of blocks that share addresses.
type Conflict struct {
	A, B      Block
	Duplicate bool
}

// FindConflicts returns every overlapping pair, in input order.
func FindConflicts(blocks []Block) []Conflict {
	var out []Conflict
	for i := 0; i < len(blocks); i++ {
		for j := i + 1; j < len(blocks); j++ {
			a, b := blocks[i], blocks[j]
			if a.Start <= b.End && b.Start <= a.End {
				out = append(out, Conflict{A: a, B: b, Duplicate: a.Start == b.Start && a.End == b.End})
			}
		}
	}
	return out
}

// Range is an inclusive address range.
type Range struct{ Start, End uint32 }

// FreeRanges returns the gaps inside parent not covered by any block.
func FreeRanges(parent Range, blocks []Block) []Range {
	var used []Range
	for _, b := range blocks {
		if b.Start <= parent.End && parent.Start <= b.End {
			s, e := b.Start, b.End
			if s < parent.Start {
				s = parent.Start
			}
			if e > parent.End {
				e = parent.End
			}
			used = append(used, Range{s, e})
		}
	}
	sort.Slice(used, func(i, j int) bool { return used[i].Start < used[j].Start })
	var free []Range
	cur := uint64(parent.Start)
	for _, u := range used {
		if uint64(u.Start) > cur {
			free = append(free, Range{uint32(cur), u.Start - 1})
		}
		if uint64(u.End)+1 > cur {
			cur = uint64(u.End) + 1
		}
	}
	if cur <= uint64(parent.End) {
		free = append(free, Range{uint32(cur), parent.End})
	}
	return free
}

// RangeToCIDRs splits a range into the fewest aligned CIDR blocks.
func RangeToCIDRs(r Range) []string {
	var out []string
	cur := uint64(r.Start)
	end := uint64(r.End)
	for cur <= end {
		bits := 32
		for bits > 0 {
			size := uint64(1) << uint(32-(bits-1))
			if cur%size != 0 || cur+size-1 > end {
				break
			}
			bits--
		}
		out = append(out, fmt.Sprintf("%s/%d", uintToIP(uint32(cur)), bits))
		cur += uint64(1) << uint(32-bits)
	}
	return out
}

// NextFree finds the first aligned block of the given prefix length in free space.
func NextFree(free []Range, prefix int) (string, bool) {
	size := uint64(1) << uint(32-prefix)
	for _, r := range free {
		start := (uint64(r.Start) + size - 1) / size * size
		if start+size-1 <= uint64(r.End) {
			return fmt.Sprintf("%s/%d", uintToIP(uint32(start)), prefix), true
		}
	}
	return "", false
}
