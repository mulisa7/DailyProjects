package scrub

import (
	"encoding/json"
	"strings"
	"testing"
)

func parse(t *testing.T, s string) any {
	t.Helper()
	dec := json.NewDecoder(strings.NewReader(s))
	dec.UseNumber()
	var v any
	if err := dec.Decode(&v); err != nil {
		t.Fatal(err)
	}
	return v
}

func dump(t *testing.T, v any) string {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func har(entry string) string {
	return `{"log":{"version":"1.2","entries":[` + entry + `]}}`
}

const jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijk"

func TestHeadersAndCookies(t *testing.T) {
	doc := parse(t, har(`{"request":{"method":"GET","url":"https://a.test/x",
	"headers":[{"name":"Authorization","value":"Bearer abcdefgh12345"},{"name":"Accept","value":"text/html"},{"name":"Cookie","value":"sid=1"}],
	"cookies":[{"name":"sid","value":"1"}]},
	"response":{"headers":[{"name":"Set-Cookie","value":"a=b; Path=/"}],"cookies":[{"name":"a","value":"b"}],"content":{}}}`))
	r, err := Scrub(doc, Options{})
	if err != nil {
		t.Fatal(err)
	}
	out := dump(t, doc)
	for _, bad := range []string{"abcdefgh12345", `"sid=1"`, "a=b; Path", `"value":"1"`, `"value":"b"`} {
		if strings.Contains(out, bad) {
			t.Errorf("still contains %s: %s", bad, out)
		}
	}
	if !strings.Contains(out, "text/html") {
		t.Error("harmless header was removed")
	}
	if r.Counts["request-header:authorization"] != 1 || r.Counts["request-cookie"] != 1 || r.Counts["response-cookie"] != 1 {
		t.Errorf("counts: %v", r.Counts)
	}
}

func TestURLQueryUserinfoFragment(t *testing.T) {
	doc := parse(t, har(`{"request":{"method":"GET","url":"https://bob:pw@a.test/p?page=2&access_token=zzz&api-key=k1&q=hello%20x#access_token=frag&state=ok","headers":[],"queryString":[{"name":"page","value":"2"},{"name":"access_token","value":"zzz"}]},
	"response":{"redirectURL":"https://a.test/cb?code=abc&x=1","headers":[],"content":{}}}`))
	r, _ := Scrub(doc, Options{})
	out := dump(t, doc)
	for _, bad := range []string{"bob:pw", "zzz", "k1", "frag", "code=abc"} {
		if strings.Contains(out, bad) {
			t.Errorf("leaked %q in %s", bad, out)
		}
	}
	for _, keep := range []string{"page=2", "q=hello%20x", "state=ok", "x=1"} {
		if !strings.Contains(out, keep) {
			t.Errorf("lost %q in %s", keep, out)
		}
	}
	if r.Counts["url:userinfo"] != 1 {
		t.Errorf("counts: %v", r.Counts)
	}
}

func TestJSONBodies(t *testing.T) {
	body := `{"user":"bob","password":"hunter2","profile":{"refresh_token":"rt","age":5,"postcode":"AB1"},"list":[{"clientSecret":"s3"}],"n":12345678901234567890}`
	b, _ := json.Marshal(body)
	doc := parse(t, har(`{"request":{"url":"https://a.test/","headers":[],"postData":{"mimeType":"application/json","text":`+string(b)+`}},"response":{"headers":[],"content":{"mimeType":"application/json","text":`+string(b)+`}}}`))
	r, _ := Scrub(doc, Options{})
	out := dump(t, doc)
	for _, bad := range []string{"hunter2", `rt\"`, "s3"} {
		if strings.Contains(out, bad) {
			t.Errorf("leaked %q in %s", bad, out)
		}
	}
	for _, keep := range []string{"bob", "AB1", "12345678901234567890"} {
		if !strings.Contains(out, keep) {
			t.Errorf("lost %q in %s", keep, out)
		}
	}
	if r.Total() < 6 {
		t.Errorf("counts: %v", r.Counts)
	}
}

func TestFormBodyAndParams(t *testing.T) {
	doc := parse(t, har(`{"request":{"url":"https://a.test/","headers":[],"postData":{"mimeType":"application/x-www-form-urlencoded","text":"user=bob&password=p%40ss&remember=1","params":[{"name":"user","value":"bob"},{"name":"password","value":"p@ss"}]}},"response":{"headers":[],"content":{}}}`))
	Scrub(doc, Options{})
	out := dump(t, doc)
	if strings.Contains(out, "p%40ss") || strings.Contains(out, "p@ss") {
		t.Errorf("password leaked: %s", out)
	}
	if !strings.Contains(out, "user=bob") || !strings.Contains(out, "remember=1") {
		t.Errorf("harmless fields lost: %s", out)
	}
}

func TestPatternsInPlainText(t *testing.T) {
	doc := parse(t, har(`{"request":{"url":"https://a.test/","headers":[{"name":"X-Debug","value":"jwt `+jwt+`"}]},"response":{"headers":[],"content":{"mimeType":"text/html","text":"<script>var t='`+jwt+`'; auth: Basic dXNlcjpwYXNzd29yZA==</script>"}}}`))
	r, _ := Scrub(doc, Options{})
	out := dump(t, doc)
	if strings.Contains(out, "eyJhbGci") || strings.Contains(out, "dXNlcjpw") {
		t.Errorf("leaked: %s", out)
	}
	if r.Counts["pattern:jwt"] != 2 || r.Counts["pattern:bearer-or-basic"] != 1 {
		t.Errorf("counts: %v", r.Counts)
	}
}

func TestExtraNamesAndDropBodies(t *testing.T) {
	doc := parse(t, har(`{"request":{"url":"https://a.test/?tenant=acme","headers":[{"name":"X-Tenant","value":"acme"}],"queryString":[{"name":"tenant","value":"acme"}]},"response":{"headers":[],"content":{"mimeType":"text/plain","text":"hello"}}}`))
	r, _ := Scrub(doc, Options{ExtraHeaders: []string{"x-tenant"}, ExtraParams: []string{"Tenant"}, DropBodies: true})
	out := dump(t, doc)
	if strings.Contains(out, "acme") || strings.Contains(out, "hello") {
		t.Errorf("not removed: %s", out)
	}
	if r.Counts["response-body:dropped"] != 1 {
		t.Errorf("counts: %v", r.Counts)
	}
}

func TestBase64AndBinaryBodiesUntouched(t *testing.T) {
	doc := parse(t, har(`{"request":{"url":"https://a.test/","headers":[]},"response":{"headers":[],"content":{"mimeType":"image/png","encoding":"base64","text":"iVBORw0KGgo="}}}`))
	r, _ := Scrub(doc, Options{})
	if r.Total() != 0 || !strings.Contains(dump(t, doc), "iVBORw0KGgo=") {
		t.Errorf("modified base64 body: %v", r.Counts)
	}
}

func TestCleanFileAndEmptyEntries(t *testing.T) {
	for _, in := range []string{har(``), har(`{"request":{"url":"https://a.test/a?b=1","headers":[{"name":"Accept","value":"*/*"}]},"response":{"headers":[],"content":{}}}`)} {
		r, err := Scrub(parse(t, in), Options{})
		if err != nil || r.Total() != 0 {
			t.Errorf("err=%v counts=%v", err, r.Counts)
		}
	}
}

func TestMalformedEntriesDoNotPanic(t *testing.T) {
	in := har(`null, 5, {"request":"x","response":[]}, {"request":{"url":7,"headers":"no","cookies":[1],"postData":{"text":5}},"response":{"content":{"text":null}}}, {"request":{"headers":[{"name":"Cookie"},{"value":"v"}]}}`)
	if _, err := Scrub(parse(t, in), Options{}); err != nil {
		t.Fatal(err)
	}
}

func TestInvalidShapes(t *testing.T) {
	for _, in := range []string{`[]`, `{}`, `{"log":5}`, `{"log":{}}`, `{"log":{"entries":{}}}`, `"x"`, `null`} {
		if _, err := Scrub(parse(t, in), Options{}); err == nil {
			t.Errorf("expected error for %s", in)
		}
	}
}

func TestBrokenJSONBodyFallsBackToPatterns(t *testing.T) {
	doc := parse(t, har(`{"request":{"url":"https://a.test/","headers":[]},"response":{"headers":[],"content":{"mimeType":"application/json","text":"{\"a\": Bearer abcdefgh1234 oops"}}}`))
	Scrub(doc, Options{})
	if strings.Contains(dump(t, doc), "abcdefgh1234") {
		t.Error("leaked in malformed JSON body")
	}
}

func TestNoHTMLEscapingInBodies(t *testing.T) {
	doc := parse(t, har(`{"request":{"url":"https://a.test/","headers":[]},"response":{"headers":[],"content":{"mimeType":"application/json","text":"{\"html\":\"<b>&</b>\"}"}}}`))
	Scrub(doc, Options{})
	// the body string itself must keep the literal characters
	e := doc.(map[string]any)["log"].(map[string]any)["entries"].([]any)[0].(map[string]any)
	txt := e["response"].(map[string]any)["content"].(map[string]any)["text"].(string)
	if txt != `{"html":"<b>&</b>"}` {
		t.Errorf("got %s", txt)
	}
}
