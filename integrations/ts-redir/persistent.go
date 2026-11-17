package firewall

import (
    "encoding/json"
    "errors"
    "fmt"
    "io"
    "net"
    "os"
    "path/filepath"
)

// Persistent wraps the upstream manager; it does not flush unrelated nftables.
type Persistent struct { Manager; path string }

func validApplianceRule(r RedirectRule) error {
    if err := validateRule(r); err != nil { return err }
    if r.MatchPort == 22 || r.MatchPort == 8800 { return errors.New("ports 22 and 8800 are reserved for recovery and management") }
    _, tailnet, _ := net.ParseCIDR("100.64.0.0/10")
    if !tailnet.Contains(r.TargetIP) { return errors.New("target must be a Tailscale IPv4 address") }
    if r.MatchInterface != "wlan0" && r.MatchInterface != "eth0" {
        return errors.New("select wlan0 or eth0 as the ingress interface")
    }
    if r.MatchIP == nil || !r.MatchIP.IsGlobalUnicast() || r.MatchIP.IsLoopback() || tailnet.Contains(r.MatchIP) {
        return errors.New("set match IP to the Pi's LAN IPv4 address")
    }
    if len(r.Description) > 80 || len(r.TailscalePeer) > 160 { return errors.New("description or peer name too long") }
    // Linux limits nft rule userdata to 256 bytes, including JSON escapes/keys.
    metadata, err := marshalMetadata(buildMetadata(r, stagePostrouting))
    if err != nil { return err }
    if len(metadata) > 256 { return errors.New("description and peer label exceed nftables storage; shorten the description or use a shorter peer label") }
    return nil
}

func NewPersistentManager(base Manager, path string) (Manager, error) {
    p := &Persistent{Manager: base, path: path}
    file, err := os.Open(path)
    if errors.Is(err, os.ErrNotExist) { return p, nil }
    if err != nil { return nil, err }
    defer file.Close()
    decoder := json.NewDecoder(io.LimitReader(file, 131073))
    decoder.DisallowUnknownFields()
    var saved []RedirectRule
    if err := decoder.Decode(&saved); err != nil { return nil, fmt.Errorf("read saved rules: %w", err) }
    if len(saved) > 64 { return nil, errors.New("too many saved rules") }
    if err := decoder.Decode(new(any)); err != io.EOF { return nil, errors.New("trailing saved data") }
    for _, rule := range saved { if err := validApplianceRule(rule); err != nil { return nil, err } }
    for _, rule := range saved {
        exists, err := base.RuleExists(rule)
        if err != nil { return nil, err }
        if !exists { if err := base.AddRedirectRule(rule); err != nil { return nil, err } }
    }
    return p, nil
}

func (p *Persistent) save() error {
    rules, err := p.Manager.ListRedirectRules()
    if err != nil { return err }
    for i := range rules { rules[i].Handle = 0 }
    file, err := os.CreateTemp(filepath.Dir(p.path), ".rules-")
    if err != nil { return err }
    name := file.Name()
    defer os.Remove(name)
    defer file.Close()
    if err = file.Chmod(0600); err != nil { return err }
    if err = json.NewEncoder(file).Encode(rules); err != nil { return err }
    if err = file.Sync(); err != nil { return err }
    if err = file.Close(); err != nil { return err }
    if err = os.Rename(name, p.path); err != nil { return err }
    dir, err := os.Open(filepath.Dir(p.path)); if err != nil { return err }; defer dir.Close()
    return dir.Sync()
}

func (p *Persistent) AddRedirectRule(rule RedirectRule) error {
    if err := validApplianceRule(rule); err != nil { return err }
    before, err := p.Manager.ListRedirectRules(); if err != nil { return err }
    if len(before) >= 64 { return errors.New("64-rule limit reached") }
    if err := p.Manager.AddRedirectRule(rule); err != nil { return err }
    if err := p.save(); err != nil {
        // The rule may be active: never report a successful durable change.
        return fmt.Errorf("rule applied but saving failed; check storage before reboot: %w", err)
    }
    return nil
}

func (p *Persistent) DeleteRedirectRule(handle uint64) error {
    if err := p.Manager.DeleteRedirectRule(handle); err != nil { return err }
    if err := p.save(); err != nil { return fmt.Errorf("rule removed but saving failed; it may return after reboot: %w", err) }
    return nil
}
