package firewall

import (
    "encoding/json"
    "net"
    "os"
    "path/filepath"
    "testing"
)

type memoryManager struct { rules []RedirectRule; next uint64 }
func (m *memoryManager) ListRedirectRules() ([]RedirectRule, error) { return append([]RedirectRule{}, m.rules...), nil }
func (m *memoryManager) RuleExists(r RedirectRule) (bool, error) { for _, old := range m.rules { if ruleKey(old) == ruleKey(r) { return true, nil } }; return false, nil }
func (m *memoryManager) AddRedirectRule(r RedirectRule) error { m.next++; r.Handle = m.next; m.rules = append(m.rules, r); return nil }
func (m *memoryManager) DeleteRedirectRule(h uint64) error { for i, r := range m.rules { if r.Handle == h { m.rules = append(m.rules[:i], m.rules[i+1:]...); break } }; return nil }
func (m *memoryManager) Close() error { return nil }
func goodRule() RedirectRule { return RedirectRule{Protocol: ProtocolTCP, MatchInterface: "wlan0", MatchIP: net.ParseIP("192.0.2.40"), MatchPort: 8000, TargetIP: net.ParseIP("100.100.20.10"), TargetPort: 80} }

func TestDurableRuleLifecycle(t *testing.T) {
    path := filepath.Join(t.TempDir(), "rules.json")
    first := &memoryManager{}
    manager, err := NewPersistentManager(first, path); if err != nil { t.Fatal(err) }
    if err := manager.AddRedirectRule(goodRule()); err != nil { t.Fatal(err) }
    info, _ := os.Stat(path); if info.Mode().Perm() != 0600 { t.Fatal("rule file must be private") }
    second := &memoryManager{}
    restored, err := NewPersistentManager(second, path); if err != nil { t.Fatal(err) }
    if len(second.rules) != 1 { t.Fatal("reboot did not restore rule") }
    if _, err := NewPersistentManager(second, path); err != nil || len(second.rules) != 1 { t.Fatal("restart duplicated rule") }
    if err := restored.DeleteRedirectRule(second.rules[0].Handle); err != nil { t.Fatal(err) }
    third := &memoryManager{}
    if _, err := NewPersistentManager(third, path); err != nil || len(third.rules) != 0 { t.Fatal("deleted rule returned") }
}

func TestRestoreValidatesBeforeChangingFirewall(t *testing.T) {
    path := filepath.Join(t.TempDir(), "rules.json")
    invalid := goodRule(); invalid.TargetIP = net.ParseIP("8.8.8.8")
    data, _ := json.Marshal([]RedirectRule{goodRule(), invalid}); os.WriteFile(path, data, 0600)
    base := &memoryManager{}
    if _, err := NewPersistentManager(base, path); err == nil { t.Fatal("unsafe rule accepted") }
    if len(base.rules) != 0 { t.Fatal("partial restore before validation") }
}

func TestNarrowIngressAndTailnetDestination(t *testing.T) {
    for _, change := range []func(*RedirectRule){
        func(r *RedirectRule) { r.MatchPort = 22 },
        func(r *RedirectRule) { r.MatchPort = 8800 },
        func(r *RedirectRule) { r.MatchIP = nil },
        func(r *RedirectRule) { r.MatchIP = net.ParseIP("127.0.0.1") },
        func(r *RedirectRule) { r.MatchInterface = "tailscale0" },
        func(r *RedirectRule) { r.TargetIP = net.ParseIP("192.168.1.1") },
    } {
        r := goodRule(); change(&r)
        if validApplianceRule(r) == nil { t.Fatal("unsafe rule accepted") }
    }
}

func TestSavingFailureIsReported(t *testing.T) {
    p := &Persistent{Manager: &memoryManager{}, path: "/nonexistent/tailbridge/rules.json"}
    if p.AddRedirectRule(goodRule()) == nil { t.Fatal("false durable success") }
}
