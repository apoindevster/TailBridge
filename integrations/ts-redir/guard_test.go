package web

import (
	"crypto/sha256"
	"encoding/base64"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestCSPMatchesRenderedScript(t *testing.T) {
	server, err := NewServer(nil, "tailscale0", 8800)
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest("GET", "http://100.100.20.40:8800/", nil)
	recorder := httptest.NewRecorder()
	guard(http.HandlerFunc(server.handleIndex), request.Host, nil).ServeHTTP(recorder, request)
	body := recorder.Body.String()
	script := strings.SplitN(strings.SplitN(body, "<script>", 2)[1], "</script>", 2)[0]
	hash := sha256.Sum256([]byte(script))
	if !strings.Contains(recorder.Header().Get("Content-Security-Policy"), "sha256-"+base64.StdEncoding.EncodeToString(hash[:])) {
		t.Fatal("CSP would block rendered UI JavaScript")
	}
}

func TestBrowserBoundary(t *testing.T) {
	authority := "100.100.20.40:8800"
	dns := "ts-redir.example-tailnet.ts.net:8800"
	called := false
	handler := guard(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		if _, err := io.ReadAll(r.Body); err != nil {
			http.Error(w, "large body", 413)
			return
		}
		w.WriteHeader(204)
	}), authority, func() string { return "ts-redir.example-tailnet.ts.net" })
	cases := []struct {
		method, host, origin, content, body string
		want                                int
	}{
		{"GET", authority, "", "", "", 204},
		{"GET", dns, "", "", "", 204},
		{"GET", strings.ToUpper(dns), "", "", "", 204},
		{"GET", "ts-redir.example-tailnet.ts.net.:8800", "", "", "", 403},
		{"GET", "ts-redir.example-tailnet.ts.net", "", "", "", 403},
		{"GET", "ts-redir.example-tailnet.ts.net:80", "", "", "", 403},
		{"GET", "other.example-tailnet.ts.net:8800", "", "", "", 403},
		{"GET", "ts-redir.example-tailnet.ts.net.evil.test:8800", "", "", "", 403},
		{"GET", "attacker.example:8800", "", "", "", 403},
		{"POST", dns, "http://" + dns, "application/json", "{}", 204},
		{"DELETE", dns, "http://" + dns, "", "", 204},
		{"POST", dns, "http://" + authority, "application/json", "{}", 403},
		{"POST", authority, "http://" + dns, "application/json", "{}", 403},
		{"POST", dns, "https://" + dns, "application/json", "{}", 403},
		{"POST", dns, "http://" + dns + "/", "application/json", "{}", 403},
		{"POST", dns, "null", "application/json", "{}", 403},
		{"POST", authority, "http://evil.example", "application/json", "{}", 403},
		{"DELETE", authority, "", "", "", 403},
		{"POST", authority, "http://" + authority, "text/plain", "{}", 415},
		{"POST", authority, "http://" + authority, "application/json", "{}", 204},
		{"DELETE", authority, "http://" + authority, "", "", 204},
		{"POST", authority, "http://" + authority, "application/json", strings.Repeat("x", 32769), 413},
	}
	for _, test := range cases {
		called = false
		request := httptest.NewRequest(test.method, "http://"+test.host+"/api/rules", strings.NewReader(test.body))
		request.Header.Set("Origin", test.origin)
		request.Header.Set("Content-Type", test.content)
		request.Header.Set("X-Forwarded-Host", dns)
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, request)
		if recorder.Code != test.want {
			t.Errorf("%s %s: got %d want %d", test.method, test.origin, recorder.Code, test.want)
		}
		if (test.want == 403 || test.want == 415) && called {
			t.Error("rejected request reached firewall handler")
		}
		if !strings.Contains(recorder.Header().Get("Content-Security-Policy"), "sha256-") {
			t.Error("missing script CSP")
		}
	}
}

func TestDNSUnavailableAndFetchMetadata(t *testing.T) {
	authority := "100.100.20.40:8800"
	handler := guard(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(204) }), authority, func() string { return "" })
	for _, host := range []string{authority, "ts-redir.example-tailnet.ts.net:8800"} {
		request := httptest.NewRequest("GET", "http://"+host, nil)
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, request)
		want := 403
		if host == authority {
			want = 204
		}
		if recorder.Code != want {
			t.Fatalf("no DNS: got %d want %d", recorder.Code, want)
		}
	}
	request := httptest.NewRequest("DELETE", "http://"+authority, nil)
	request.Header.Set("Origin", "http://"+authority)
	request.Header.Set("Sec-Fetch-Site", "cross-site")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != 403 {
		t.Fatal("cross-site metadata must be rejected")
	}
}

func TestUIUsesTextNodes(t *testing.T) {
	if strings.Contains(indexHTML, "tr.innerHTML") {
		t.Fatal("untrusted rule fields must use textContent")
	}
	if strings.Contains(indexHTML, "https://cdn") {
		t.Fatal("management UI must work without remote CSS")
	}
}
