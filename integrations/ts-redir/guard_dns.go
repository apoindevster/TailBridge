package web

import (
	"context"
	"encoding/json"
	"net"
	"os/exec"
	"strings"
	"sync"
	"time"
)

func normalizeMagicDNS(name string) string {
	name = strings.ToLower(strings.TrimSuffix(name, "."))
	if len(name) > 253 || !strings.HasSuffix(name, ".ts.net") || strings.Count(name, ".") < 3 {
		return ""
	}
	for _, label := range strings.Split(name, ".") {
		if len(label) == 0 || len(label) > 63 || label[0] == '-' || label[len(label)-1] == '-' {
			return ""
		}
		for _, char := range label {
			if !(char >= 'a' && char <= 'z' || char >= '0' && char <= '9' || char == '-') {
				return ""
			}
		}
	}
	return name
}

func dnsNameFromStatus(data []byte, boundIP string) string {
	var status struct {
		BackendState string
		Self         *struct {
			DNSName      string
			TailscaleIPs []string
		}
	}
	if json.Unmarshal(data, &status) != nil || status.BackendState != "Running" || status.Self == nil {
		return ""
	}
	for _, ip := range status.Self.TailscaleIPs {
		if ip == boundIP {
			return normalizeMagicDNS(status.Self.DNSName)
		}
	}
	return ""
}

type localDNSCache struct {
	mu      sync.Mutex
	name    string
	expires time.Time
	lookup  func() string
	now     func() time.Time
}

func (cache *localDNSCache) get() string {
	cache.mu.Lock()
	defer cache.mu.Unlock()
	if !cache.now().Before(cache.expires) {
		// Cache failures too, replacing stale names and bounding subprocess load.
		cache.name = cache.lookup()
		cache.expires = cache.now().Add(30 * time.Second)
	}
	return cache.name
}

func cachedLocalDNSName(authority string) func() string {
	boundIP, _, _ := net.SplitHostPort(authority)
	cache := &localDNSCache{now: time.Now, lookup: func() string {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		output, err := exec.CommandContext(ctx, "/usr/bin/tailscale", "status", "--json").Output()
		if err != nil {
			return ""
		}
		return dnsNameFromStatus(output, boundIP)
	}}
	return cache.get
}
