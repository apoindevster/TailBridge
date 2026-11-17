package web

import (
	"encoding/json"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestDNSNameFromLocalIdentity(t *testing.T) {
	for _, test := range []struct{ state, name, ip, want string }{
		{"Running", "TS-REDIR.example-tailnet.ts.net.", "100.100.20.40", "ts-redir.example-tailnet.ts.net"},
		{"Stopped", "ts-redir.example-tailnet.ts.net.", "100.100.20.40", ""},
		{"Running", "ts-redir.example-tailnet.ts.net.", "100.100.20.41", ""},
		{"Running", "http://ts-redir.example-tailnet.ts.net", "100.100.20.40", ""},
		{"Running", "ts-redir.example-tailnet.ts.net:8800", "100.100.20.40", ""},
		{"Running", "ts-redir.example-tailnet.ts.net..", "100.100.20.40", ""},
		{"Running", "ts-redir.example-tailnet.ts.net.evil.test", "100.100.20.40", ""},
		{"Running", "-bad.example-tailnet.ts.net", "100.100.20.40", ""},
		{"Running", strings.Repeat("a", 64) + ".example-tailnet.ts.net", "100.100.20.40", ""},
	} {
		data, _ := json.Marshal(map[string]any{"BackendState": test.state, "Self": map[string]any{"DNSName": test.name, "TailscaleIPs": []string{test.ip}}})
		if got := dnsNameFromStatus(data, "100.100.20.40"); got != test.want {
			t.Errorf("%q: got %q want %q", test.name, got, test.want)
		}
	}
	for _, data := range []string{`{`, `null`, `{"BackendState":"Running","Self":null}`, `{"BackendState":"Running","Peer":{"other":{"DNSName":"other.example.ts.net"}}}`} {
		if dnsNameFromStatus([]byte(data), "100.100.20.40") != "" {
			t.Fatal("missing local identity accepted")
		}
	}
}

func TestDNSCacheRefreshFailureAndConcurrency(t *testing.T) {
	now := time.Unix(100, 0)
	calls, name := 0, "old.example-tailnet.ts.net"
	cache := localDNSCache{now: func() time.Time { return now }, lookup: func() string { calls++; return name }}
	var workers sync.WaitGroup
	for i := 0; i < 20; i++ {
		workers.Add(1)
		go func() {
			defer workers.Done()
			if cache.get() != "old.example-tailnet.ts.net" {
				t.Error("missing cached name")
			}
		}()
	}
	workers.Wait()
	if calls != 1 {
		t.Fatalf("concurrent requests caused %d lookups", calls)
	}
	now = now.Add(30 * time.Second)
	name = "new.example-tailnet.ts.net"
	if cache.get() != name || calls != 2 {
		t.Fatal("renamed device not refreshed")
	}
	now = now.Add(30 * time.Second)
	name = ""
	if cache.get() != "" || calls != 3 {
		t.Fatal("failure retained stale name")
	}
	cache.get()
	if calls != 3 {
		t.Fatal("failures must also be cached")
	}
}
