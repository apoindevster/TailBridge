#!/usr/bin/env python3
"""Apply a small integration to an exact upstream checkout, failing on drift."""
import argparse
from pathlib import Path
import shutil
import subprocess

REVISION = "935fda9def785f49dc1e5435388c6c344b8e68a1"


def replace(path, before, after):
    text = path.read_text()
    if text.count(before) != 1:
        raise SystemExit(f"Upstream shape changed: {path.name}")
    path.write_text(text.replace(before, after))


def prepare(source, project):
    actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if actual != REVISION:
        raise SystemExit("Unexpected ts-redir revision")
    server = source / "internal/web/server.go"
    replace(server, 'var indexHTML string', 'var indexHTML string\n\n//go:embed templates/pico.min.css\nvar picoCSS string')
    replace(server, 'mux := http.NewServeMux()', '''mux := http.NewServeMux()
    mux.HandleFunc("/pico.min.css", func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "text/css; charset=utf-8")
        _, _ = w.Write([]byte(picoCSS))
    })''')
    replace(server, 'Handler: withLogging(mux),', '''Handler: guard(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            s.mu.Lock(); defer s.mu.Unlock()
            mux.ServeHTTP(w, r)
        }), addr, cachedLocalDNSName(addr)),
        ReadHeaderTimeout: 5 * time.Second,
        ReadTimeout: 10 * time.Second,
        WriteTimeout: 15 * time.Second,
        IdleTimeout: 30 * time.Second,
        MaxHeaderBytes: 8192,''')
    replace(server, 'if err := s.server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {', '''listener, err := listenOnInterface(addr, s.ifaceName)
    if err != nil { return err }
    if err := s.server.Serve(listener); err != nil && !errors.Is(err, http.ErrServerClosed) {''')
    main = source / "cmd/ts-redir/main.go"
    replace(main, 'defer mgr.Close()\n\n\tserver, err :=', '''defer mgr.Close()
    if state := os.Getenv("TAILBRIDGE_RULES_FILE"); state != "" {
        mgr, err = firewall.NewPersistentManager(mgr, state)
        if err != nil { log.Fatal("ts-redir: cannot restore saved rules: ", err) }
    }

    server, err :=''')
    html = source / "internal/web/templates/index.html"
    replace(html, 'https://cdn.jsdelivr.net/npm/@picocss/pico@2.0.0-alpha1/css/pico.min.css', '/pico.min.css')
    replace(html, '''          tr.innerHTML = `
            <td>${sourceLabel(rule)}</td>
            <td>${rule.target_ip}:${rule.target_port}</td>
            <td>${protocolLabel}</td>
            <td>${rule.tailscale_peer || ""}</td>
            <td><button data-handle="${rule.handle}" class="secondary outline">Delete</button></td>
          `;''', '''          for (const value of [sourceLabel(rule), `${rule.target_ip}:${rule.target_port}`, protocolLabel, rule.tailscale_peer || ""]) {
            const cell = document.createElement("td"); cell.textContent = value; tr.appendChild(cell);
          }
          const cell = document.createElement("td");
          const button = document.createElement("button");
          button.textContent = "Delete"; button.dataset.handle = String(rule.handle);
          button.className = "secondary outline"; cell.appendChild(button); tr.appendChild(cell);''')
    # Explicit interface and Pi LAN address preserve the narrow entry-point scope.
    replace(html, '<input type="text" name="match_ip" placeholder="192.168.1.10" />', '<input type="text" name="match_ip" placeholder="Pi LAN IP, e.g. 192.168.1.10" required />')
    for path in (project / "integrations/ts-redir").glob("guard*.go"):
        shutil.copyfile(path, source / "internal/web" / path.name)
    for name in ("persistent.go", "persistent_test.go", "kernel_test.go"):
        shutil.copyfile(project / "integrations/ts-redir" / name, source / "internal/firewall" / name)
    shutil.copyfile(project / ".cache/pico.min.css", source / "internal/web/templates/pico.min.css")
    subprocess.run(["gofmt", "-w", "cmd", "internal"], cwd=source, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    prepare(args.source.resolve(), Path(__file__).resolve().parents[1])
