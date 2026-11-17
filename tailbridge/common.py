"""Bounded local protocol and shared validation (no shell expansion)."""
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import tempfile

MAX_MESSAGE = 16384
SOCKET = "/run/tailbridge/network.sock"


class UserError(Exception):
    """A deliberately safe message suitable for display without raw diagnostics."""


def read_message(stream):
    data = stream.readline(MAX_MESSAGE + 1)
    if len(data) > MAX_MESSAGE or not data.endswith(b"\n"):
        raise UserError("Request is too large or incomplete.")
    try:
        value = json.loads(data)
    except (ValueError, UnicodeError):
        raise UserError("Invalid request.") from None
    if not isinstance(value, dict):
        raise UserError("Invalid request.")
    return value


def request(command, path=SOCKET, **kwargs):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(95)
        sock.connect(path)
        with sock.makefile("rwb") as stream:
            stream.write(json.dumps({"command": command, **kwargs}).encode() + b"\n")
            stream.flush()
            answer = read_message(stream)
    if not answer.get("ok"):
        raise UserError(answer.get("error", "Service unavailable."))
    return answer["data"]


def atomic_json(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".new-")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(value, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ssid_bytes(value):
    try:
        raw = bytes.fromhex(value)
    except (ValueError, TypeError):
        raise UserError("Invalid network name.") from None
    if not 1 <= len(raw) <= 32:
        raise UserError("A network name must be 1–32 bytes.")
    return raw


def display_ssid(raw):
    # SSIDs are hostile radio data. Never display controls or terminal escapes.
    return "".join(c if c.isprintable() else "�" for c in raw.decode("utf-8", "replace"))


def validate_wifi(ssid, security, password):
    ssid_bytes(ssid)
    if security not in ("open", "wpa-psk", "sae"):
        raise UserError("This network needs enterprise or legacy setup through SSH.")
    if not isinstance(password, str) or "\x00" in password:
        raise UserError("Invalid Wi-Fi password.")
    if security == "open":
        if password:
            raise UserError("Open networks do not use a password.")
    elif security == "sae":
        if not 1 <= len(password.encode()) <= 63:
            raise UserError("Use a WPA3 password of 1–63 bytes.")
    elif not (8 <= len(password) <= 63 and password.isascii()) and not (
        len(password) == 64 and all(c in "0123456789abcdefABCDEF" for c in password)
    ):
        raise UserError("Use 8–63 ASCII characters or a 64-digit hex key.")


def is_tailnet_ipv4(value):
    try:
        return ipaddress.ip_address(value) in ipaddress.ip_network("100.64.0.0/10")
    except ValueError:
        return False


def normalize_tailnet_name(value):
    """Only display an ordinary MagicDNS FQDN; strip the daemon's root dot."""
    if not isinstance(value, str):
        return ""
    name = value.removesuffix(".").lower()
    if len(name) > 253 or not name.endswith(".ts.net") or name.count(".") < 3:
        return ""
    if not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
               for label in name.split(".")):
        return ""
    return name


def management_urls(tailnet):
    """Construct ordinary web URLs only; never reuse an enrollment URL/token."""
    if tailnet.get("state") != "Running":
        return "", ""
    ipv4 = next((value for value in (tailnet.get("ipv4") or [])
                 if isinstance(value, str) and is_tailnet_ipv4(value)), "")
    if not ipv4:
        return "", ""
    name = normalize_tailnet_name(tailnet.get("dns_name"))
    return "http://" + ipv4 + ":8800", "http://" + name + ":8800" if name else ""
