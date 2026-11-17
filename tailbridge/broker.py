"""Root-owned Unix socket, restricted to the dedicated touchscreen account."""
import argparse
import grp
import json
import logging
import os
import pwd
import re
import socket
import struct

from .common import SOCKET, LockedError, UserError, read_message
from .lock import PinGate


def dispatch(backend, data, gate=None):
    command = data.get("command")
    fields = {"status": {"command", "session"}, "scan": {"command", "session"},
              "login": {"command", "session"}, "lock": {"command"},
              "lock_status": {"command"}, "unlock": {"command", "pin"},
              "connect": {"command", "session", "ssid_hex", "security", "password", "hidden"}}
    if not isinstance(command, str) or command not in fields or set(data) - fields[command]:
        raise UserError("Unsupported request.")
    if gate is None:
        raise LockedError('Screen locked. Enter your PIN.')
    if command == 'lock':
        return gate.lock()
    if command == 'lock_status':
        return gate.state()
    if command == 'unlock':
        return gate.unlock(data.get('pin'))
    gate.authorize(data.get('session'))
    if command == "connect":
        if not isinstance(data.get("hidden", False), bool):
            raise UserError("Invalid request.")
        return backend.connect(data.get("ssid_hex"), data.get("security"), data.get("password", ""), data.get("hidden", False))
    return getattr(backend, command)()


def allowed_peer(conn, uid):
    _, peer_uid, _ = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    return peer_uid in (0, uid)


def serve(backend, path, uid, gid, gate=None):
    gate = gate or PinGate()
    if os.path.lexists(path):
        os.unlink(path)  # Parent directory is root-owned and not writable by UI.
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(path)
        os.chown(path, 0, gid)
        os.chmod(path, 0o660)
        listener.listen(8)
        while True:
            conn, _ = listener.accept()
            with conn:
                conn.settimeout(5)
                if not allowed_peer(conn, uid):
                    continue
                try:
                    with conn.makefile("rwb") as stream:
                        try:
                            data = read_message(stream)
                            try:
                                result = dispatch(backend, data, gate)
                            finally:
                                data.clear()
                            answer = {"ok": True, "data": result}
                        except LockedError:
                            answer = {"ok": False, "code": "locked", "error": "Screen locked. Enter your PIN."}
                        except UserError as error:
                            answer = {"ok": False, "error": str(error)}
                        except Exception:
                            # D-Bus errors can include SSIDs/secrets: never log their text.
                            logging.warning("Network operation failed; details withheld")
                            answer = {"ok": False, "error": "Network unavailable. Retry or check SSH."}
                        stream.write(json.dumps(answer).encode() + b"\n")
                        stream.flush()
                except (OSError, TimeoutError):
                    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interface", default="wlan0")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,15}", args.interface):
        parser.error("invalid interface")
    from .network import NetworkManager
    serve(NetworkManager(args.interface), SOCKET, pwd.getpwnam("tailbridge").pw_uid, grp.getgrnam("tailbridge").gr_gid)


if __name__ == "__main__":
    main()
