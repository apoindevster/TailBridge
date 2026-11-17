"""NetworkManager adapter. Imported only by the local privileged broker."""
import ipaddress
import json
import subprocess
import time
import uuid

from .common import UserError, display_ssid, normalize_tailnet_name, ssid_bytes, validate_wifi

NM = "org.freedesktop.NetworkManager"
ROOT = "/org/freedesktop/NetworkManager"
PROPS = "org.freedesktop.DBus.Properties"


def security_type(flags, wpa, rsn):
    combined = wpa | rsn
    if rsn & 0x100:  # WPA2 PSK, including WPA2/WPA3 transition mode
        return "wpa-psk"
    if rsn & 0x400:  # SAE
        return "sae"
    if combined or flags & 1:
        return "unsupported"
    return "open"


class NetworkManager:
    def __init__(self, interface="wlan0", bus=None):
        import dbus
        self.dbus = dbus
        self.bus = bus or dbus.SystemBus()
        self.interface = interface
        self.login_process = None

    def obj(self, path):
        return self.bus.get_object(NM, path)

    def api(self, path, interface):
        return self.dbus.Interface(self.obj(path), interface)

    def props(self, path, interface):
        return dict(self.api(path, PROPS).GetAll(interface, timeout=8))

    def device(self):
        path = self.api(ROOT, NM).GetDeviceByIpIface(self.interface, timeout=8)
        if int(self.props(path, NM + ".Device")["DeviceType"]) != 2:
            raise UserError("The configured interface is not a Wi-Fi adapter.")
        return path

    def status(self):
        root = self.props(ROOT, NM)
        result = {"interface": self.interface, "enabled": bool(root["WirelessEnabled"]),
                  "hardware_enabled": bool(root["WirelessHardwareEnabled"]),
                  "connected": False, "ssid": "", "ipv4": [], "state": 0,
                  "tailnet": self.tailnet_status()}
        try:
            path = self.device()
        except self.dbus.DBusException:
            result["missing_adapter"] = True
            return result
        props = self.props(path, NM + ".Device")
        result["state"] = int(props["State"])
        result["connected"] = result["state"] == 100
        wireless = self.props(path, NM + ".Device.Wireless")
        ap = str(wireless["ActiveAccessPoint"])
        if ap != "/":
            result["ssid"] = display_ssid(bytes(self.props(ap, NM + ".AccessPoint")["Ssid"]))
        config = str(props["Ip4Config"])
        if config != "/":
            for address in self.props(config, NM + ".IP4Config").get("AddressData", []):
                result["ipv4"].append(str(address["address"]))
        return result

    def scan(self):
        path = self.device()
        root = self.props(ROOT, NM)
        if not root["WirelessHardwareEnabled"]:
            raise UserError("Wi-Fi is blocked. Check the radio and country setting through SSH.")
        if not root["WirelessEnabled"]:
            self.api(ROOT, PROPS).Set(NM, "WirelessEnabled", self.dbus.Boolean(True), timeout=8)
        wireless = self.api(path, NM + ".Device.Wireless")
        previous = self.props(path, NM + ".Device.Wireless")["LastScan"]
        try:
            wireless.RequestScan(self.dbus.Dictionary({}, signature="sv"), timeout=8)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if self.props(path, NM + ".Device.Wireless")["LastScan"] != previous:
                    break
                time.sleep(0.3)
        except self.dbus.DBusException as error:
            # NM rate limits rescans; its existing result remains usable.
            if not error.get_dbus_name().endswith("NotAllowed"):
                raise
        found = {}
        for ap in wireless.GetAllAccessPoints(timeout=8):
            info = self.props(ap, NM + ".AccessPoint")
            raw = bytes(info["Ssid"])
            if not raw or len(raw) > 32:
                continue
            security = security_type(int(info["Flags"]), int(info["WpaFlags"]), int(info["RsnFlags"]))
            key = (raw.hex(), security)
            item = {"ssid": display_ssid(raw), "ssid_hex": raw.hex(), "security": security,
                    "strength": int(info["Strength"])}
            if key not in found or found[key]["strength"] < item["strength"]:
                found[key] = item
        return sorted(found.values(), key=lambda row: -row["strength"])[:40]

    def connect(self, ssid_hex, security, password, hidden=False):
        validate_wifi(ssid_hex, security, password)
        dbus = self.dbus
        path = self.device()
        manager = self.api(ROOT, NM)
        # Only this Wi-Fi device is checkpointed; Ethernet/SSH remains untouched.
        checkpoint = manager.CheckpointCreate([path], dbus.UInt32(90), dbus.UInt32(0), timeout=8)
        profile = None
        committed = False
        try:
            self.api(ROOT, PROPS).Set(NM, "WirelessEnabled", dbus.Boolean(True), timeout=8)
            settings = {
                "connection": {"id": "tailbridge:" + ssid_hex, "uuid": str(uuid.uuid4()),
                               "type": "802-11-wireless", "interface-name": self.interface,
                               "autoconnect": dbus.Boolean(True)},
                "802-11-wireless": {"ssid": dbus.ByteArray(ssid_bytes(ssid_hex)),
                                    "mode": "infrastructure", "hidden": dbus.Boolean(hidden)},
                "ipv4": {"method": "auto"}, "ipv6": {"method": "auto"},
            }
            if security != "open":
                settings["802-11-wireless-security"] = {
                    "key-mgmt": security, "psk": password,
                    "psk-flags": dbus.UInt32(0), "proto": dbus.Array(["rsn"], signature="s")}
            profile, active, _ = manager.AddAndActivateConnection2(
                dbus.Dictionary({k: dbus.Dictionary(v, signature="sv") for k, v in settings.items()}, signature="sa{sv}"),
                path, dbus.ObjectPath("/"), dbus.Dictionary({"persist": "memory"}, signature="sv"), timeout=15)
            deadline = time.monotonic() + 55
            while time.monotonic() < deadline:
                props = self.props(path, NM + ".Device")
                # Check the requested active connection, not a reactivated old network.
                requested = str(props["ActiveConnection"]) == str(active)
                if requested and int(props["State"]) == 100 and str(props["Ip4Config"]) != "/":
                    addresses = self.props(props["Ip4Config"], NM + ".IP4Config").get("AddressData", [])
                    if addresses:
                        self.api(profile, NM + ".Settings.Connection").Save(timeout=8)
                        manager.CheckpointDestroy(checkpoint, timeout=8)
                        committed = True
                        self._remove_previous_owned_profiles(profile, ssid_hex)
                        return {"connected": True}
                if int(self.props(active, NM + ".Connection.Active")["State"]) == 4:
                    break
                time.sleep(0.5)
            raise UserError("Could not join. Check signal and retry." if security == "open" else
                            "Could not join. Check password and signal.")
        finally:
            password = ""  # Python cannot promise cryptographic erasure of immutable strings.
            if not committed:
                rolled_back = False
                try:
                    restored = manager.CheckpointRollback(checkpoint, timeout=8)
                    rolled_back = all(int(result) == 0 for result in restored.values())
                except dbus.DBusException:
                    pass  # NM's 90-second automatic rollback is still armed.
                if profile:
                    try:
                        self.api(profile, NM + ".Settings.Connection").Delete(timeout=8)
                    except dbus.DBusException:
                        pass
                if rolled_back:
                    try:
                        manager.CheckpointDestroy(checkpoint, timeout=8)
                    except dbus.DBusException:
                        pass

    def _remove_previous_owned_profiles(self, current, ssid_hex):
        try:
            for path in self.api(ROOT + "/Settings", NM + ".Settings").ListConnections(timeout=8):
                if path == current:
                    continue
                conn = self.api(path, NM + ".Settings.Connection")
                settings = conn.GetSettings(timeout=8)
                if settings.get("connection", {}).get("id") == "tailbridge:" + ssid_hex:
                    conn.Delete(timeout=8)
        except self.dbus.DBusException:
            pass  # Optional duplicate cleanup must not invalidate an established connection.

    def tailnet_status(self):
        try:
            result = subprocess.run(["/usr/bin/tailscale", "status", "--json"],
                                    capture_output=True, timeout=4, check=False)
            if result.returncode:
                raise ValueError("Tailscale status unavailable")
            data = json.loads(result.stdout)
            if not isinstance(data, dict):
                raise ValueError("Invalid Tailscale status")
            ipv4 = [v for v in (data.get("TailscaleIPs") or []) if ipaddress.ip_address(v).version == 4]
            own = data.get("Self") or {}
            dns_name = ""
            if (isinstance(own, dict) and data.get("BackendState") == "Running" and
                    ipv4 and ipv4[0] in (own.get("TailscaleIPs") or [])):
                dns_name = normalize_tailnet_name(own.get("DNSName"))
            auth_url = data.get("AuthURL") or ""
            # Only official HTTPS login links are shown; never echo raw CLI output.
            from urllib.parse import urlsplit
            parsed = urlsplit(auth_url)
            if parsed.scheme != "https" or parsed.hostname not in ("login.tailscale.com", "controlplane.tailscale.com"):
                auth_url = ""
            return {"state": data.get("BackendState", "Unknown"), "ipv4": ipv4,
                    "dns_name": dns_name,
                    "auth_url": auth_url, "login_running": self.login_process is not None and self.login_process.poll() is None}
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return {"state": "Unavailable", "ipv4": [], "dns_name": "", "auth_url": "", "login_running": False}

    def login(self):
        state = self.tailnet_status()
        if state["state"] == "Running":
            return {"started": False}
        if self.login_process is None or self.login_process.poll() is not None:
            self.login_process = subprocess.Popen(
                ["/usr/bin/tailscale", "up", "--timeout=120s"], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"started": True}
