// Package scrub removes credentials and session data from HAR files.
package scrub

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"regexp"
	"sort"
	"strings"
)

// Redacted replaces any value that was removed.
const Redacted = "[REDACTED]"

// Options controls what is removed beyond the built-in rules.
type Options struct {
	ExtraHeaders []string // header names to redact, case-insensitive
	ExtraParams  []string // query/form/JSON key names to redact, case-insensitive
	DropBodies   bool     // delete response bodies entirely
}

// Report counts findings by category, e.g. "header:authorization".
type Report struct {
	Counts map[string]int
}

// Total is the number of redactions made (or that would be made).
func (r *Report) Total() int {
	n := 0
	for _, c := range r.Counts {
		n += c
	}
	return n
}

// Lines returns "category: count" lines in a stable order.
func (r *Report) Lines() []string {
	keys := make([]string, 0, len(r.Counts))
	for k := range r.Counts {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	out := make([]string, 0, len(keys))
	for _, k := range keys {
		out = append(out, fmt.Sprintf("%s: %d", k, r.Counts[k]))
	}
	return out
}

var sensitiveHeaders = map[string]bool{
	"authorization": true, "proxy-authorization": true, "cookie": true,
	"set-cookie": true, "x-api-key": true, "x-auth-token": true,
	"x-csrf-token": true, "x-xsrf-token": true, "x-amz-security-token": true,
	"x-access-token": true, "x-goog-api-key": true, "x-session-id": true,
}

var sensitiveSubstrings = []string{
	"token", "secret", "passw", "apikey", "accesskey", "privatekey",
	"session", "signature", "credential", "bearer", "otp", "authorization",
}

var sensitiveExact = map[string]bool{
	"key": true, "code": true, "sig": true, "auth": true, "sid": true,
	"pin": true, "jwt": true, "pwd": true,
}

var (
	jwtRe    = regexp.MustCompile(`eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*`)
	bearerRe = regexp.MustCompile(`(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}`)
)

type scrubber struct {
	opts    Options
	headers map[string]bool
	params  map[string]bool
	counts  map[string]int
}

func normalizeKey(k string) string {
	k = strings.ToLower(k)
	k = strings.ReplaceAll(k, "-", "")
	k = strings.ReplaceAll(k, "_", "")
	return k
}

func (s *scrubber) sensitiveParam(name string) bool {
	n := normalizeKey(name)
	if n == "" {
		return false
	}
	if s.params[n] || sensitiveExact[n] {
		return true
	}
	for _, sub := range sensitiveSubstrings {
		if strings.Contains(n, sub) {
			return true
		}
	}
	return false
}

func (s *scrubber) sensitiveHeader(name string) bool {
	n := strings.ToLower(strings.TrimSpace(name))
	return sensitiveHeaders[n] || s.headers[n]
}

func (s *scrubber) count(cat string) { s.counts[cat]++ }

// text removes JWTs and Bearer/Basic credentials found anywhere in a string.
func (s *scrubber) text(in, cat string) string {
	out := jwtRe.ReplaceAllStringFunc(in, func(string) string {
		s.count("pattern:jwt")
		return "[REDACTED-JWT]"
	})
	out = bearerRe.ReplaceAllStringFunc(out, func(m string) string {
		s.count("pattern:bearer-or-basic")
		return strings.Fields(m)[0] + " " + Redacted
	})
	return out
}

// Scrub redacts the decoded HAR document in place and reports what it found.
// root must come from json.Unmarshal into an any (ideally with UseNumber).
func Scrub(root any, opts Options) (*Report, error) {
	s := &scrubber{opts: opts, headers: map[string]bool{}, params: map[string]bool{}, counts: map[string]int{}}
	for _, h := range opts.ExtraHeaders {
		s.headers[strings.ToLower(strings.TrimSpace(h))] = true
	}
	for _, p := range opts.ExtraParams {
		s.params[normalizeKey(strings.TrimSpace(p))] = true
	}
	top, ok := root.(map[string]any)
	if !ok {
		return nil, errors.New("not a HAR file: top level is not a JSON object")
	}
	log, ok := top["log"].(map[string]any)
	if !ok {
		return nil, errors.New("not a HAR file: missing \"log\" object")
	}
	entries, ok := log["entries"].([]any)
	if !ok {
		return nil, errors.New("not a HAR file: missing \"log.entries\" array")
	}
	for _, e := range entries {
		entry, ok := e.(map[string]any)
		if !ok {
			continue
		}
		if req, ok := entry["request"].(map[string]any); ok {
			s.message(req, true)
		}
		if resp, ok := entry["response"].(map[string]any); ok {
			s.message(resp, false)
		}
	}
	return &Report{Counts: s.counts}, nil
}

func (s *scrubber) message(m map[string]any, isReq bool) {
	side := "response"
	if isReq {
		side = "request"
	}
	s.nameValueList(m["headers"], true, side+"-header")
	s.cookies(m["cookies"], side)
	if u, ok := m["url"].(string); ok {
		m["url"] = s.url(u)
	}
	if u, ok := m["redirectURL"].(string); ok && u != "" {
		m["redirectURL"] = s.url(u)
	}
	s.nameValueList(m["queryString"], false, "query")
	if pd, ok := m["postData"].(map[string]any); ok {
		s.nameValueList(pd["params"], false, "form")
		s.body(pd, "text", pd["mimeType"], "request-body")
	}
	if c, ok := m["content"].(map[string]any); ok {
		if s.opts.DropBodies {
			if t, has := c["text"]; has && t != "" {
				delete(c, "text")
				s.count("response-body:dropped")
			}
		} else {
			s.body(c, "text", c["mimeType"], "response-body")
		}
	}
}

func (s *scrubber) nameValueList(v any, isHeader bool, cat string) {
	list, ok := v.([]any)
	if !ok {
		return
	}
	for _, it := range list {
		nv, ok := it.(map[string]any)
		if !ok {
			continue
		}
		name, _ := nv["name"].(string)
		val, isStr := nv["value"].(string)
		if !isStr {
			continue
		}
		sens := s.sensitiveParam(name)
		if isHeader {
			sens = s.sensitiveHeader(name)
		}
		if sens && val != "" {
			nv["value"] = Redacted
			s.count(cat + ":" + strings.ToLower(name))
			continue
		}
		if nv2 := s.text(val, cat); nv2 != val {
			nv["value"] = nv2
		}
	}
}

func (s *scrubber) cookies(v any, side string) {
	list, ok := v.([]any)
	if !ok {
		return
	}
	for _, it := range list {
		c, ok := it.(map[string]any)
		if !ok {
			continue
		}
		if val, ok := c["value"].(string); ok && val != "" {
			c["value"] = Redacted
			s.count(side + "-cookie")
		}
	}
}

// url redacts userinfo, sensitive query values and fragment values.
func (s *scrubber) url(raw string) string {
	frag := ""
	if i := strings.Index(raw, "#"); i >= 0 {
		frag = raw[i+1:]
		raw = raw[:i]
	}
	query := ""
	if i := strings.Index(raw, "?"); i >= 0 {
		query = raw[i+1:]
		raw = raw[:i]
	}
	if i := strings.Index(raw, "://"); i >= 0 {
		rest := raw[i+3:]
		end := strings.IndexAny(rest, "/")
		host := rest
		if end >= 0 {
			host = rest[:end]
		}
		if at := strings.LastIndex(host, "@"); at >= 0 {
			s.count("url:userinfo")
			raw = raw[:i+3] + Redacted + "@" + rest[at+1:]
		}
	}
	out := raw
	if query != "" {
		out += "?" + s.encoded(query, "url-query")
	}
	if frag != "" {
		if strings.Contains(frag, "=") {
			out += "#" + s.encoded(frag, "url-fragment")
		} else {
			out += "#" + s.text(frag, "url-fragment")
		}
	}
	return out
}

// encoded handles a key=value&key=value string, keeping its original shape.
func (s *scrubber) encoded(q, cat string) string {
	parts := strings.Split(q, "&")
	for i, p := range parts {
		k, v, hasEq := strings.Cut(p, "=")
		if !hasEq {
			continue
		}
		key, err := url.QueryUnescape(k)
		if err != nil {
			key = k
		}
		if s.sensitiveParam(key) && v != "" {
			parts[i] = k + "=" + Redacted
			s.count(cat + ":" + strings.ToLower(key))
			continue
		}
		parts[i] = k + "=" + s.text(v, cat)
	}
	return strings.Join(parts, "&")
}

func (s *scrubber) body(m map[string]any, field string, mime any, cat string) {
	t, ok := m[field].(string)
	if !ok || t == "" {
		return
	}
	if enc, _ := m["encoding"].(string); enc == "base64" {
		return
	}
	mt, _ := mime.(string)
	mt = strings.ToLower(mt)
	switch {
	case strings.Contains(mt, "json") || looksJSON(t):
		var doc any
		dec := json.NewDecoder(strings.NewReader(t))
		dec.UseNumber()
		if err := dec.Decode(&doc); err == nil && !dec.More() {
			s.json(doc, cat)
			var buf bytes.Buffer
			enc := json.NewEncoder(&buf)
			enc.SetEscapeHTML(false)
			if err := enc.Encode(doc); err == nil {
				m[field] = strings.TrimRight(buf.String(), "\n")
				return
			}
		}
		m[field] = s.text(t, cat)
	case strings.Contains(mt, "x-www-form-urlencoded"):
		m[field] = s.encoded(t, cat)
	default:
		m[field] = s.text(t, cat)
	}
}

func looksJSON(t string) bool {
	t = strings.TrimSpace(t)
	return len(t) > 1 && (t[0] == '{' || t[0] == '[')
}

func (s *scrubber) json(v any, cat string) any {
	switch x := v.(type) {
	case map[string]any:
		for k, val := range x {
			switch val.(type) {
			case map[string]any, []any:
				if s.sensitiveParam(k) {
					x[k] = Redacted
					s.count(cat + ":" + strings.ToLower(k))
				} else {
					s.json(val, cat)
				}
			case string:
				str := val.(string)
				if s.sensitiveParam(k) && str != "" {
					x[k] = Redacted
					s.count(cat + ":" + strings.ToLower(k))
				} else {
					x[k] = s.text(str, cat)
				}
			case json.Number:
				if s.sensitiveParam(k) {
					x[k] = Redacted
					s.count(cat + ":" + strings.ToLower(k))
				}
			}
		}
	case []any:
		for i, val := range x {
			switch e := val.(type) {
			case string:
				x[i] = s.text(e, cat)
			default:
				s.json(val, cat)
			}
		}
	}
	return v
}
