package web

// TailBridge integration: preserve tailscale0 as the authentication boundary.
import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"mime"
	"net"
	"net/http"
	"strings"
	"syscall"

	"golang.org/x/sys/unix"
)

func listenOnInterface(addr, iface string) (net.Listener, error) {
	config := net.ListenConfig{Control: func(network, address string, raw syscall.RawConn) error {
		var socketErr error
		err := raw.Control(func(fd uintptr) {
			socketErr = unix.SetsockoptString(int(fd), unix.SOL_SOCKET, unix.SO_BINDTODEVICE, iface)
		})
		if err != nil {
			return err
		}
		return socketErr
	}}
	return config.Listen(context.Background(), "tcp4", addr)
}

func guard(next http.Handler, authority string, localDNSName func() string) http.Handler {
	_, port, _ := net.SplitHostPort(authority)
	script := strings.SplitN(strings.SplitN(indexHTML, "<script>", 2)[1], "</script>", 2)[0]
	hash := sha256.Sum256([]byte(script))
	csp := fmt.Sprintf("default-src 'none'; style-src 'self' 'unsafe-inline'; script-src 'sha256-%s'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'", base64.StdEncoding.EncodeToString(hash[:]))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("Content-Security-Policy", csp)
		// Only this device's numeric address or daemon-reported MagicDNS name.
		// Never trust forwarded headers, reverse DNS, or a wildcard ts.net suffix.
		allowed := r.Host == authority
		host, requestPort, err := net.SplitHostPort(r.Host)
		if !allowed && err == nil && requestPort == port && localDNSName != nil {
			candidate := strings.ToLower(host)
			if candidate != "" && normalizeMagicDNS(candidate) == candidate {
				name := localDNSName()
				allowed = name != "" && candidate == name
			}
		}
		if !allowed {
			http.Error(w, "Use the Tailscale IP or full name shown on the display, with port 8800.", 403)
			return
		}
		if r.Method != "GET" && r.Method != "HEAD" {
			// Each alias is a separate browser origin; accepting both Hosts must
			// not permit cross-origin mutations between the name and address.
			if r.Header.Get("Origin") != "http://"+r.Host {
				http.Error(w, "Same-origin request required.", 403)
				return
			}
			if site := r.Header.Get("Sec-Fetch-Site"); site != "" && site != "same-origin" {
				http.Error(w, "Same-origin request required.", 403)
				return
			}
		}
		if r.Method == "POST" {
			kind, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
			if err != nil || kind != "application/json" {
				http.Error(w, "JSON required.", 415)
				return
			}
		}
		r.Body = http.MaxBytesReader(w, r.Body, 32768)
		next.ServeHTTP(w, r)
	})
}
