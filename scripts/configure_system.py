#!/usr/bin/env python3
"""File-only, reversible system setup. Tests use a temporary root directory."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

BEGIN, END = "# BEGIN TAILBRIDGE", "# END TAILBRIDGE"
PAYLOAD_DIRECTORIES = ('tailbridge', 'scripts', 'packaging', 'bin', 'vendor')
RETIRED_SCRIPTS = ('apply-boot-fix.sh', 'update_kiosk.py')


def boot_config(text):
    text = re.sub(r"\n?# BEGIN TAILBRIDGE\n.*?# END TAILBRIDGE\n?", "\n", text, flags=re.S)
    # Match the reviewed vendor Pi 4 framebuffer setup, without replacing config.txt.
    text = re.sub(r"^(\s*dtoverlay=vc4-(?:f?kms)-v3d[^\n]*)$", r"# TailBridge disabled: \1", text, flags=re.M)
    if re.search(r"^\s*dtoverlay=(?:mhs35ips|waveshare35|piscreen)", text, re.M):
        raise ValueError("Existing SPI LCD overlay found. Restore the pre-driver config before installing TailBridge.")
    return text.rstrip() + "\n\n" + BEGIN + "\n" + "\n".join([
        "[all]", "dtparam=spi=on", "dtoverlay=mhs35ips:rotate=90", "hdmi_force_hotplug=1",
        "hdmi_group=2", "hdmi_mode=87", "hdmi_cvt=480 320 60 6 0 0 0", "hdmi_drive=2",
        "max_framebuffers=2", END, ""])


class Installer:
    def __init__(self, root, backup):
        self.root, self.backup = Path(root), Path(backup)
        self.backup.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.manifest_path = self.backup / "files.json"
        self.manifest = json.loads(self.manifest_path.read_text()) if self.manifest_path.exists() else {}

    def preserve(self, relative):
        if relative in self.manifest:
            return
        path = self.root / relative
        if path.is_symlink():
            record = {"type": "symlink", "target": os.readlink(path)}
        elif path.exists():
            if not path.is_file():
                raise ValueError("Refusing to replace a non-file: " + relative)
            info = path.stat()
            record = {"type": "file", "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid}
            target = self.backup / "original" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        else:
            record = {"type": "absent"}
        self.manifest[relative] = record
        self.manifest_path.write_text(json.dumps(self.manifest, indent=2) + "\n")
        self.manifest_path.chmod(0o600)

    def write(self, relative, content, mode=0o644):
        self.preserve(relative)
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            path.unlink()
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
        path.chmod(mode)

    def restore(self):
        for relative, record in self.manifest.items():
            path = self.root / relative
            if path.is_symlink() or path.is_file():
                path.unlink()
            if record["type"] == "symlink":
                path.symlink_to(record["target"])
            elif record["type"] == "file":
                shutil.copy2(self.backup / "original" / relative, path)
                path.chmod(record["mode"])
                if os.geteuid() == 0:
                    os.chown(path, record["uid"], record["gid"])

    def mask(self, relative):
        self.preserve(relative)
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or path.is_file():
            path.unlink()
        path.symlink_to('/dev/null')


def configure_kiosk(installer, source):
    installer.write('etc/sysctl.d/99-tailbridge-kiosk.conf', (source / 'packaging/kiosk-sysctl.conf').read_bytes())
    installer.write('etc/systemd/system.conf.d/99-tailbridge-kiosk.conf', (source / 'packaging/kiosk-manager.conf').read_bytes())
    installer.mask('etc/systemd/system/ctrl-alt-del.target')
    installer.mask('etc/systemd/system/getty@tty1.service')
    # Retain the original live value once, including when upgrading an existing
    # installation whose services.json predates the kiosk policy.
    saved = installer.backup / 'kiosk.json'
    sysrq = installer.root / 'proc/sys/kernel/sysrq'
    if not saved.exists() and sysrq.exists():
        value = int(sysrq.read_text().strip())
        saved.write_text(json.dumps({'sysrq': value}) + '\n')
        saved.chmod(0o600)


def install_payload(source, root):
    destination = root / 'opt/tailbridge'
    for name in PAYLOAD_DIRECTORIES:
        if not (source / name).is_dir():
            raise ValueError('Incomplete installation bundle: ' + name)
    if not (source / 'bin/ts-redir').is_file() or not (source / 'vendor/mhs35ips.dtbo').is_file():
        raise ValueError('Use the complete built arm64 bundle.')
    for tree in (*(source / name for name in PAYLOAD_DIRECTORIES), destination):
        for path in (tree, *tree.rglob('*')):
            if path.is_symlink():
                raise ValueError('Unexpected symlink in the application payload: ' + str(path))
    destination.mkdir(parents=True, exist_ok=True)
    def copy_payload_file(src, dst):
        # Replace the inode instead of truncating a live executable (ETXTBSY).
        # Running processes keep their old image until the planned reboot.
        target = Path(dst)
        fd, temporary = tempfile.mkstemp(prefix='.install-', dir=target.parent)
        os.close(fd)
        try:
            shutil.copyfile(src, temporary)
            os.chmod(temporary, 0o755 if target.suffix == '.sh' or target.parent == destination / 'bin' else 0o644)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return str(target)
    for name in PAYLOAD_DIRECTORIES:
        if (source / name).resolve() != (destination / name).resolve():
            shutil.copytree(source / name, destination / name, dirs_exist_ok=True,
                            copy_function=copy_payload_file,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    # Remove only our retired patch entry points on reinstallation. User data,
    # saved profiles, identity and redirect rules live outside this code tree.
    for name in RETIRED_SCRIPTS:
        (destination / 'scripts' / name).unlink(missing_ok=True)
    for path in (destination, *destination.rglob('*')):
        mode = 0o755 if path.is_dir() or path.suffix == '.sh' or path.parent == destination / 'bin' else 0o644
        path.chmod(mode)
        if os.geteuid() == 0:
            os.chown(path, 0, 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/"))
    parser.add_argument("--backup", type=Path, default=Path("/var/lib/tailbridge/install-backup"))
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    installer = Installer(args.root, args.backup)
    if args.restore:
        installer.restore()
        return
    source = Path(__file__).resolve().parents[1]
    boot = "boot/firmware/config.txt"
    updated_boot = boot_config((args.root / boot).read_text())
    install_payload(source, args.root)
    installer.write(boot, updated_boot)
    installer.write("boot/firmware/overlays/mhs35ips.dtbo", (source / "vendor/mhs35ips.dtbo").read_bytes())
    for unit in (source / "packaging").glob("*.service"):
        installer.write("etc/systemd/system/" + unit.name, unit.read_bytes())
    if not (args.root / "etc/tailbridge/environment").exists():
        installer.write("etc/tailbridge/environment", (source / "packaging/environment").read_bytes())
    configure_kiosk(installer, source)
    # systemctl modifies these; preserve exact aliases/masks for recovery.
    for relative in ("etc/systemd/system/default.target", "etc/systemd/system/getty@tty1.service"):
        installer.preserve(relative)


if __name__ == "__main__":
    main()
