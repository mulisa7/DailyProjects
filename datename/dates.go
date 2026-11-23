package main

import (
	"encoding/binary"
	"errors"
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// validDate reports whether the components form a real calendar date.
func validDate(y, mo, d int) bool {
	t := time.Date(y, time.Month(mo), d, 0, 0, 0, 0, time.UTC)
	return t.Year() == y && int(t.Month()) == mo && t.Day() == d
}

var nameRe = regexp.MustCompile(`(?:^|\D)((?:19|20)\d\d)[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])(?:[-_. T]?([01]\d|2[0-3])[-_.:]?([0-5]\d)[-_.:]?([0-5]\d)\d{0,3})?(?:\D|$)`)

// dateFromName finds a date (and optional time) embedded in a file name,
// such as IMG_20240315_142210.jpg or Screenshot 2024-03-15 at 14.22.10.png.
func dateFromName(name string) (time.Time, bool) {
	for _, s := range []string{strings.ReplaceAll(name, " at ", " "), name} {
		m := nameRe.FindStringSubmatch(s)
		if m == nil {
			continue
		}
		y, _ := strconv.Atoi(m[1])
		mo, _ := strconv.Atoi(m[2])
		d, _ := strconv.Atoi(m[3])
		if !validDate(y, mo, d) {
			continue
		}
		h, mi, se := 0, 0, 0
		if m[4] != "" {
			h, _ = strconv.Atoi(m[4])
			mi, _ = strconv.Atoi(m[5])
			se, _ = strconv.Atoi(m[6])
		}
		return time.Date(y, time.Month(mo), d, h, mi, se, 0, time.UTC), true
	}
	return time.Time{}, false
}

var errNoExif = errors.New("no EXIF date")

// parseExifDate parses "YYYY:MM:DD HH:MM:SS".
func parseExifDate(b []byte) (time.Time, error) {
	s := strings.TrimRight(string(b), "\x00 ")
	t, err := time.Parse("2006:01:02 15:04:05", s)
	if err != nil {
		return time.Time{}, fmt.Errorf("bad EXIF date %q", s)
	}
	return t, nil
}

// exifDate reads DateTimeOriginal (falling back to DateTime) from JPEG data.
func exifDate(data []byte) (time.Time, error) {
	if len(data) < 4 || data[0] != 0xFF || data[1] != 0xD8 {
		return time.Time{}, errNoExif
	}
	i := 2
	for i+4 <= len(data) {
		if data[i] != 0xFF {
			return time.Time{}, errNoExif
		}
		marker := data[i+1]
		if marker == 0xFF { // padding
			i++
			continue
		}
		if marker == 0xDA || marker == 0xD9 { // start of scan / end
			return time.Time{}, errNoExif
		}
		size := int(binary.BigEndian.Uint16(data[i+2 : i+4]))
		if size < 2 || i+2+size > len(data) {
			return time.Time{}, errNoExif
		}
		if marker == 0xE1 {
			seg := data[i+4 : i+2+size]
			if len(seg) > 6 && string(seg[:6]) == "Exif\x00\x00" {
				return tiffDate(seg[6:])
			}
		}
		i += 2 + size
	}
	return time.Time{}, errNoExif
}

type tiff struct {
	b  []byte
	bo binary.ByteOrder
}

func (t tiff) u16(off int) (int, bool) {
	if off < 0 || off+2 > len(t.b) {
		return 0, false
	}
	return int(t.bo.Uint16(t.b[off:])), true
}

func (t tiff) u32(off int) (int, bool) {
	if off < 0 || off+4 > len(t.b) {
		return 0, false
	}
	return int(t.bo.Uint32(t.b[off:])), true
}

// find returns the raw value bytes of an ASCII tag, or the long value of a pointer tag.
func (t tiff) entries(ifd int) map[int][2]int {
	out := map[int][2]int{} // tag -> {count, valueOrOffsetField position}
	n, ok := t.u16(ifd)
	if !ok {
		return out
	}
	for k := 0; k < n && k < 512; k++ {
		e := ifd + 2 + k*12
		tag, ok1 := t.u16(e)
		cnt, ok2 := t.u32(e + 4)
		if !ok1 || !ok2 || e+12 > len(t.b) {
			break
		}
		out[tag] = [2]int{cnt, e + 8}
	}
	return out
}

func (t tiff) ascii(ent [2]int) ([]byte, bool) {
	cnt, pos := ent[0], ent[1]
	if cnt < 1 || cnt > 64 {
		return nil, false
	}
	if cnt <= 4 {
		return t.b[pos : pos+cnt], true
	}
	off, ok := t.u32(pos)
	if !ok || off < 0 || off+cnt > len(t.b) {
		return nil, false
	}
	return t.b[off : off+cnt], true
}

func tiffDate(b []byte) (time.Time, error) {
	if len(b) < 8 {
		return time.Time{}, errNoExif
	}
	t := tiff{b: b}
	switch string(b[:2]) {
	case "II":
		t.bo = binary.LittleEndian
	case "MM":
		t.bo = binary.BigEndian
	default:
		return time.Time{}, errNoExif
	}
	ifd0, ok := t.u32(4)
	if !ok {
		return time.Time{}, errNoExif
	}
	e0 := t.entries(ifd0)
	if p, ok := e0[0x8769]; ok {
		if off, ok := t.u32(p[1]); ok {
			if ent, ok := t.entries(off)[0x9003]; ok {
				if raw, ok := t.ascii(ent); ok {
					if tm, err := parseExifDate(raw); err == nil {
						return tm, nil
					}
				}
			}
		}
	}
	if ent, ok := e0[0x0132]; ok {
		if raw, ok := t.ascii(ent); ok {
			if tm, err := parseExifDate(raw); err == nil {
				return tm, nil
			}
		}
	}
	return time.Time{}, errNoExif
}

// dateFromExifFile reads a file and extracts its EXIF date. Only the first
// 256 KiB are read since EXIF lives at the start of a JPEG.
func dateFromExifFile(path string) (time.Time, error) {
	f, err := os.Open(path)
	if err != nil {
		return time.Time{}, err
	}
	defer f.Close()
	buf := make([]byte, 256*1024)
	n, _ := f.Read(buf)
	return exifDate(buf[:n])
}
