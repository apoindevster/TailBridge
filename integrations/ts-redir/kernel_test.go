package firewall

import (
    "os"
    "strings"
    "testing"
)

// Opt-in only, invoked in a fresh unshare --net namespace by kernel_smoke.sh.
func TestIsolatedKernelLifecycle(t *testing.T) {
    if os.Getenv("TAILBRIDGE_ISOLATED_KERNEL_TEST") != "1" { t.Skip("isolated kernel test not requested") }
    current, _ := os.Readlink("/proc/self/ns/net")
    if current == os.Getenv("TAILBRIDGE_HOST_NETNS") || os.Getenv("TAILBRIDGE_HOST_NETNS") == "" {
        t.Fatal("refusing kernel test in the host network namespace")
    }
    base, err := NewManager(); if err != nil { t.Fatal(err) }; defer base.Close()
    p, err := NewPersistentManager(base, t.TempDir() + "/rules.json"); if err != nil { t.Fatal(err) }
    rule := goodRule()
    rule.Description = "Test redirect"
    rule.TailscalePeer = "test-peer.tail-example.ts.net"
    if err := p.AddRedirectRule(rule); err != nil { t.Fatal(err) }
    rules, err := p.ListRedirectRules()
    if err != nil || len(rules) != 1 { t.Fatalf("list: %v %+v", err, rules) }
    if rules[0].TailscalePeer != rule.TailscalePeer { t.Fatal("lost peer metadata") }
    if err := p.DeleteRedirectRule(rules[0].Handle); err != nil { t.Fatal(err) }
    rules, err = p.ListRedirectRules()
    if err != nil || len(rules) != 0 { t.Fatalf("delete: %v %+v", err, rules) }
    // Oversized labels must fail at validation with an actionable error, not netlink.
    long := goodRule(); long.Description = strings.Repeat("description-", 40)
    if err := p.AddRedirectRule(long); err == nil { t.Fatal("unbounded label accepted") }
}
