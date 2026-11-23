package main

import (
	"bytes"
	"encoding/binary"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestDateFromName(t *testing.T) {
	cases := []struct {
		in   string
		want string
		ok   bool
	}{
		{"IMG_20240315_142210.jpg", "2024-03-15 14:22:10", true},
		{"Screenshot 2024-03-15 at 14.22.10.png", "2024-03-15 14:22:10", true},
		{"PXL_20231201_090000123.jpg", "2023-12-01 09:00:00", true},
		{"scan-2022-07-04.pdf", "2022-07-04 00:00:00", true},
		{"2021.02.28 notes.txt", "2021-02-28 00:00:00", true},
		{"report_20240230.pdf", "", false},     // Feb 30
		{"invoice 12345678901.pdf", "", false}, // digits, not a date
		{"photo.jpg", "", false},
		{"", "", false},
		{"id_1234520240315999.bin", "", false},
	}
	for _, c := range cases {
		got, ok := dateFromName(c.in)
		if ok != c.ok {
			t.Errorf("%q: ok=%v want %v (%v)", c.in, ok, c.ok, got)
			continue
		}
		if ok && got.Format("2006-01-02 15:04:05") != c.want {
			t.Errorf("%q: got %s want %s", c.in, got.Format("2006-01-02 15:04:05"), c.want)
		}
	}
}

// makeJPEG builds a minimal JPEG with an EXIF segment.
func makeJPEG(bo binary.ByteOrder, order string, original, plain string) []byte {
	ascii := func(s string) []byte { return append([]byte(s), 0) }
	var tf bytes.Buffer
	tf.WriteString(order)
	put16 := func(v uint16) { b := make([]byte, 2); bo.PutUint16(b, v); tf.Write(b) }
	put32 := func(v uint32) { b := make([]byte, 4); bo.PutUint32(b, v); tf.Write(b) }
	put16(42)
	put32(8)
	// IFD0 at 8: entries DateTime(0x132) and ExifIFD pointer(0x8769)
	n := 0
	if plain != "" {
		n++
	}
	if original != "" {
		n++
	}
	put16(uint16(n))
	base := 8 + 2 + n*12 + 4
	dtOff := base
	exifOff := dtOff
	if plain != "" {
		exifOff += 20
	}
	if plain != "" {
		put16(0x0132)
		put16(2)
		put32(20)
		put32(uint32(dtOff))
	}
	if original != "" {
		put16(0x8769)
		put16(4)
		put32(1)
		put32(uint32(exifOff))
	}
	put32(0)
	if plain != "" {
		tf.Write(ascii(plain))
	}
	if original != "" {
		put16(1)
		put16(0x9003)
		put16(2)
		put32(20)
		put32(uint32(exifOff + 2 + 12 + 4))
		put32(0)
		tf.Write(ascii(original))
	}
	seg := append([]byte("Exif\x00\x00"), tf.Bytes()...)
	out := []byte{0xFF, 0xD8, 0xFF, 0xE1}
	l := make([]byte, 2)
	binary.BigEndian.PutUint16(l, uint16(len(seg)+2))
	out = append(out, l...)
	out = append(out, seg...)
	return append(out, 0xFF, 0xD9)
}

func TestExifDate(t *testing.T) {
	for _, tc := range []struct {
		name  string
		bo    binary.ByteOrder
		order string
	}{{"little", binary.LittleEndian, "II"}, {"big", binary.BigEndian, "MM"}} {
		t.Run(tc.name, func(t *testing.T) {
			d, err := exifDate(makeJPEG(tc.bo, tc.order, "2019:08:09 10:11:12", "2020:01:01 00:00:00"))
			if err != nil || d.Format("2006-01-02 15:04:05") != "2019-08-09 10:11:12" {
				t.Fatalf("got %v %v", d, err)
			}
			d, err = exifDate(makeJPEG(tc.bo, tc.order, "", "2020:01:02 03:04:05"))
			if err != nil || d.Format("2006-01-02") != "2020-01-02" {
				t.Fatalf("fallback got %v %v", d, err)
			}
		})
	}
}

func TestExifBadInput(t *testing.T) {
	good := makeJPEG(binary.LittleEndian, "II", "2019:08:09 10:11:12", "")
	bad := [][]byte{
		nil, {}, {0xFF}, []byte("not a jpeg at all"),
		{0xFF, 0xD8}, {0xFF, 0xD8, 0xFF, 0xD9},
		good[:20], good[:len(good)/2],
		makeJPEG(binary.LittleEndian, "II", "0000:00:00 00:00:00", ""),
		makeJPEG(binary.LittleEndian, "II", "garbage garbage garb", ""),
	}
	for i, b := range bad {
		if _, err := exifDate(b); err == nil {
			t.Errorf("case %d: expected error", i)
		}
	}
	// corrupt every byte position: must never panic
	for i := range good {
		c := append([]byte(nil), good...)
		c[i] ^= 0xFF
		exifDate(c)
	}
}

func TestFormatStamp(t *testing.T) {
	tm := time.Date(2024, 3, 5, 7, 8, 9, 0, time.UTC)
	if got := formatStamp(tm, "YYYY-MM-DD_hhmmss"); got != "2024-03-05_070809" {
		t.Fatal(got)
	}
	if got := formatStamp(tm, "YYYYMMDD"); got != "20240305" {
		t.Fatal(got)
	}
}

func TestParseSources(t *testing.T) {
	if _, err := parseSources("exif,bogus"); err == nil {
		t.Error("expected error")
	}
	if _, err := parseSources(" , "); err == nil {
		t.Error("expected error for empty")
	}
	s, err := parseSources("name, mtime")
	if err != nil || len(s) != 2 || s[0] != "name" {
		t.Error(s, err)
	}
}

func write(t *testing.T, dir, name string, data []byte) string {
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, data, 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestEndToEnd(t *testing.T) {
	dir := t.TempDir()
	write(t, dir, "a.jpg", makeJPEG(binary.LittleEndian, "II", "2019:08:09 10:11:12", ""))
	write(t, dir, "IMG_20240315_142210.png", []byte("x"))
	mt := write(t, dir, "plain.txt", []byte("x"))
	when := time.Date(2018, 5, 6, 7, 8, 9, 0, time.Local)
	os.Chtimes(mt, when, when)

	var out, errb bytes.Buffer
	if code := run([]string{dir}, &out, &errb); code != 0 {
		t.Fatalf("dry run code %d: %s", code, errb.String())
	}
	if !strings.Contains(out.String(), "would be renamed") {
		t.Fatal(out.String())
	}
	if _, err := os.Stat(filepath.Join(dir, "a.jpg")); err != nil {
		t.Fatal("dry run must not rename")
	}
	out.Reset()
	if code := run([]string{"--apply", dir}, &out, &errb); code != 0 {
		t.Fatalf("code %d: %s", code, errb.String())
	}
	for _, n := range []string{"2019-08-09_101112.jpg", "2024-03-15_142210.png", "2018-05-06_070809.txt"} {
		if _, err := os.Stat(filepath.Join(dir, n)); err != nil {
			t.Errorf("missing %s: %v", n, err)
		}
	}
	// second run is a no-op
	out.Reset()
	run([]string{"--apply", dir}, &out, &errb)
	if !strings.Contains(out.String(), "nothing to rename") {
		t.Errorf("not idempotent: %s", out.String())
	}
}

func TestCollisionsGetSuffix(t *testing.T) {
	dir := t.TempDir()
	write(t, dir, "IMG_20240315_142210.jpg", []byte("1"))
	write(t, dir, "VID_20240315_142210.jpg", []byte("2"))
	var out, errb bytes.Buffer
	if code := run([]string{"--apply", dir}, &out, &errb); code != 0 {
		t.Fatal(errb.String())
	}
	for _, n := range []string{"2024-03-15_142210.jpg", "2024-03-15_142210_2.jpg"} {
		if _, err := os.Stat(filepath.Join(dir, n)); err != nil {
			t.Errorf("missing %s", n)
		}
	}
}

func TestExistingTargetNotOverwritten(t *testing.T) {
	dir := t.TempDir()
	keep := write(t, dir, "2024-03-15_142210.jpg", []byte("original"))
	write(t, dir, "IMG_20240315_142210.jpg", []byte("new"))
	var out, errb bytes.Buffer
	run([]string{"--apply", dir}, &out, &errb)
	b, _ := os.ReadFile(keep)
	if string(b) != "original" {
		t.Fatal("existing file overwritten")
	}
}

func TestSwapStyleChain(t *testing.T) {
	// a file whose target is another file's current name
	dir := t.TempDir()
	a := write(t, dir, "2024-03-15_142210.jpg", []byte("A")) // name date 2024-03-15 14:22:10 -> same, skipped
	_ = a
	plans, _ := buildPlans([]string{filepath.Join(dir, "2024-03-15_142210.jpg")}, Options{Layout: "YYYY-MM-DD_hhmmss", Sources: []string{"name"}})
	if len(plans) != 0 {
		t.Fatalf("expected no plan, got %v", plans)
	}
}

func TestKeepName(t *testing.T) {
	dir := t.TempDir()
	write(t, dir, "trip_20240315.jpg", []byte("x"))
	var out, errb bytes.Buffer
	run([]string{"--apply", "--keep-name", "--format", "YYYYMMDD", dir}, &out, &errb)
	if _, err := os.Stat(filepath.Join(dir, "20240315_trip_20240315.jpg")); err != nil {
		t.Fatal(out.String(), errb.String())
	}
	out.Reset()
	run([]string{"--apply", "--keep-name", "--format", "YYYYMMDD", dir}, &out, &errb)
	if !strings.Contains(out.String(), "nothing to rename") {
		t.Fatal("keep-name not idempotent: " + out.String())
	}
}

func TestSourcesOrderAndNoDate(t *testing.T) {
	dir := t.TempDir()
	write(t, dir, "scan_20200101.txt", []byte("x"))
	var out, errb bytes.Buffer
	code := run([]string{"--sources", "exif,name", dir}, &out, &errb)
	if code != 0 || !strings.Contains(out.String(), "[name]") {
		t.Fatal(code, out.String())
	}
	dir2 := t.TempDir()
	write(t, dir2, "nodate.txt", []byte("x"))
	out.Reset()
	errb.Reset()
	code = run([]string{"--sources", "exif,name", dir2}, &out, &errb)
	if code != 1 || !strings.Contains(errb.String(), "no date found") {
		t.Fatal(code, errb.String())
	}
}

func TestCLIErrors(t *testing.T) {
	var out, errb bytes.Buffer
	if run(nil, &out, &errb) != 2 {
		t.Error("no args should be 2")
	}
	if run([]string{"/definitely/not/here"}, &out, &errb) != 2 {
		t.Error("missing path should be 2")
	}
	if run([]string{"--sources", "zzz", "."}, &out, &errb) != 2 {
		t.Error("bad source should be 2")
	}
	if run([]string{"--nope"}, &out, &errb) != 2 {
		t.Error("bad flag should be 2")
	}
	empty := t.TempDir()
	out.Reset()
	if run([]string{empty}, &out, &errb) != 0 || !strings.Contains(out.String(), "no files found") {
		t.Error("empty dir: " + out.String())
	}
}

func TestRecursive(t *testing.T) {
	dir := t.TempDir()
	os.Mkdir(filepath.Join(dir, "sub"), 0o755)
	write(t, filepath.Join(dir, "sub"), "x_20240101.txt", []byte("x"))
	var out, errb bytes.Buffer
	run([]string{"--apply", dir}, &out, &errb)
	if _, err := os.Stat(filepath.Join(dir, "sub", "x_20240101.txt")); err != nil {
		t.Fatal("non-recursive touched subfolder")
	}
	run([]string{"--apply", "-r", dir}, &out, &errb)
	if _, err := os.Stat(filepath.Join(dir, "sub", "2024-01-01_000000.txt")); err != nil {
		t.Fatal(out.String(), errb.String())
	}
}
