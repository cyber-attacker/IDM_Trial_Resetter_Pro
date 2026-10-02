"""IDM Trial Resetter Pro — core engine (IDM 6.42 / 6.43+).

Live-calibrated against an EXPIRED IDM 6.43.10 (v6.43b10 Trial) install.

Trial-state storage found on disk:
  HKCU\\Software\\DownloadManager values:
      tvfrdt, radxcnt (day counter; 29 at expiry), scansk, CheckUpdtVM,
      LastCheckQU (unix ts), LstCheck, LastCheck, MData, ptrk_scdt,
      cDTvBFquXk0, bRmGUCfEx + vCOUFP (new 6.43.x obfuscated markers),
      FName/LName/Email/Serial (registration identity)
  HKCU\\Software\\DownloadManager\\ConfigTime      ((Default) = unix install clock)
  HKCU\\Software\\DownloadManager\\SpecialData     (lgfgf.1/.2, lgasa.1/.2 blobs)
  HKCU\\Software\\Classes\\[WOW6432Node\\]CLSID\\{07999AC3-058B-40BF-984F-69EB1E554CA7}
      Model / Therad / MData
  HKCU\\Software\\Classes\\WOW6432Node\\CLSID\\{5ED60779-4DE2-4E07-B862-974CA4FF2E9C}
      ACL-locked with a deny-Everyone ACE (freeze artifact / anti-tamper):
      invisible to plain KEY_READ existence checks and undeletable until the
      resetter enables SeTakeOwnershipPrivilege, takes ownership and
      REPLACES the whole DACL (dropping every deny ACE)
  HKEY_USERS\\*_Classes mirrors of the CLSID keys
  HKLM\\SOFTWARE\\WOW6432Node\\Internet Download Manager\\AdvIntDriverEnabled2
  %APPDATA%\\IDM\\idmupdt.exe  (downloaded self-updater payload)

Anti-reset defenses handled (verified live):
  * deny-Everyone ACLs on CLSID keys — see {5ED60779-…} above
  * a watchdog thread inside IDMShellExt64.dll/IDMNetMon64.dll (loaded in
    explorer.exe and other shell hosts) re-creates ConfigTime from a cached
    copy ~1s after deletion. Verified harmless (IDM overwrites ConfigTime at
    the next fresh start — a stale planted copy did NOT resurrect the old
    trial day counter), and the resetter re-anchors it to NOW.
  * the recurring "trial period is over" nag with otherwise-fresh state:
    the trial clock is re-derived from the CLSID tracking copies, so a
    freeze that leaves ANY tracking key writable fails (observed here:
    {07999AC3-…} stayed writable and IDM rebuilt the clock in it). Freeze
    now wipes the DownloadManager state, SEEDS both tracking keys when
    missing, and locks every one of them. Activate goes further: registers
    IDM with an IAS-format serial, locks the CLSID keys and sinkholes the
    update/activation domains so the serial is never server-validated.
"""
from __future__ import annotations

import os
import sys
import re
import json
import random
import shutil
import ctypes
import datetime
import subprocess
import traceback
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

if os.name != "nt":
    raise RuntimeError("Windows only")

import winreg

VERSION = "5.3.0"
APP_NAME = "IDM Trial Resetter Pro"
APP_ORG = "IDMTools"

DM_TRIAL_VALUES = [
    "FName", "LName", "Email", "Serial",
    "tvfrdt", "radxcnt", "scansk", "CheckUpdtVM",
    "LastCheck", "LastCheckQU", "LstCheck", "MData",
    "ptrk_scdt", "cDTvBFquXk0", "auto_reset_trial",
    # New obfuscated markers found live on IDM 6.43.10:
    "bRmGUCfEx", "vCOUFP",
]

# ConfigTime  = installation clock ((Default) = unix timestamp)
# SpecialData = obfuscated state blobs (lgfgf.1/.2, lgasa.1/.2) — 6.43.x
DM_TRIAL_SUBKEYS = ["ConfigTime", "SpecialData"]

IDM_CLSID_GUIDS = [
    "{07999AC3-058B-40BF-984F-69EB1E554CA7}",
    "{7B8E9164-324D-4A2E-A46D-0165FB2000EC}",
    "{6DDF00DB-1234-46EC-8356-27E7B2051192}",
    "{D5B91409-A8CA-4973-9A0B-59F713D25671}",
    "{5ED60779-4DE2-4E07-B862-974CA4FF2E9C}",
]

# The two GUIDs 6.42/6.43 actively writes trial state into (observed live:
# {07999AC3-…} recreated on every fresh start, {5ED60779-…} present in the
# expired state). The other three are legacy keys kept for older builds,
# and 6.43 additionally rotates fresh GUIDs — caught by the dynamic scan.
ACTIVE_TRACKER_GUIDS = (
    "{07999AC3-058B-40BF-984F-69EB1E554CA7}",
    "{5ED60779-4DE2-4E07-B862-974CA4FF2E9C}",
)

CLSID_MARKERS = ("MData", "Model", "scansk", "Therad", "tvfrdt", "cDTvBFquXk0")

CLSID_BASES = [
    (winreg.HKEY_CURRENT_USER, r"Software\Classes\CLSID"),
    (winreg.HKEY_CURRENT_USER, r"Software\Classes\WOW6432Node\CLSID"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Classes\CLSID"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Classes\WOW6432Node\CLSID"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Classes\CLSID"),
]

HKLM_IDM_PATHS = [
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Internet Download Manager"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Internet Download Manager"),
]

IDM_PROCESSES = [
    "IDMan.exe", "IDMIntegrator.exe", "IDMIntegrator64.exe",
    "IEMonitor.exe", "idmupdate.exe", "IDMHelp.exe",
    "IDMNotification.exe", "IDMGrHlp.exe", "IDMMsgHost.exe",
    "idmBroker.exe", "idmupdt.exe",
]

# Downloaded self-updater payload found in %APPDATA%\IDM on 6.43.10 —
# lets IDM silently update itself (changing the registry layout).
APPDATA_TRIAL_FILES = ("idmupdt.exe",)

# Subkeys identifying a real COM class — never treat those as IDM trackers.
COM_PROTECTED_SUBKEYS = ("LocalServer32", "InProcServer32", "InProcHandler32")

IDM_EXE_CANDIDATES = [
    r"C:\Program Files (x86)\Internet Download Manager\IDMan.exe",
    r"C:\Program Files\Internet Download Manager\IDMan.exe",
]

IDM_BLOCK_DOMAINS = [
    "tonec.com", "www.tonec.com", "star.tonec.com",
    "registeridm.com", "www.registeridm.com", "secure.registeridm.com",
    "internetdownloadmanager.com", "www.internetdownloadmanager.com",
    "secure.internetdownloadmanager.com",
    "mirror.internetdownloadmanager.com",
    "mirror2.internetdownloadmanager.com",
    "mirror3.internetdownloadmanager.com",
    "dl.internetdownloadmanager.com",
    "download.internetdownloadmanager.com",
    "update.internetdownloadmanager.com",
    "support.internetdownloadmanager.com",
]

HOSTS_PATH = Path(r"C:\Windows\System32\drivers\etc\hosts")
HOSTS_HEADER = "# --- IDM Block Start ---"
HOSTS_FOOTER = "# --- IDM Block End ---"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

# Enable SeTakeOwnership / SeBackup / SeRestore (9, 17, 18) in the current
# process token — required to open deny-ACL'd registry keys for WRITE_OWNER
# and to replace their DACL (proven approach from IDM-Activation-Script).
PS_PRIVILEGES = (
    "$ab=[AppDomain]::CurrentDomain.DefineDynamicAssembly(4,1);"
    "$mb=$ab.DefineDynamicModule(2,$false);"
    "$tb=$mb.DefineType(0);"
    "$tb.DefinePInvokeMethod('RtlAdjustPrivilege','ntdll.dll','Public, Static',"
    "1,[int],@([int],[bool],[bool],[bool].MakeByRefType()),1,3)|Out-Null;"
    "9,17,18|ForEach-Object{"
    "$tb.CreateType()::RtlAdjustPrivilege($_,$true,$false,[ref]$false)|Out-Null};"
)

# Registration serial generator (IAS-compatible format:
# XXXXX-XXXXX-XXXXX-XXXXX, 20 chars from A-Z0-9 — accepted by IDM 6.4x).
SERIAL_CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def generate_serial() -> str:
    rnd = random.SystemRandom()
    chars = [rnd.choice(SERIAL_CHARSET) for _ in range(20)]
    return "-".join("".join(chars[i:i + 5]) for i in range(0, 20, 5))


@dataclass
class ActionResult:
    action: str
    success: bool
    total: int = 0
    details: List[str] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: int = 0

    def summary(self) -> str:
        if self.error:
            return f"Failed: {self.error}"
        if self.details:
            return " · ".join(str(d) for d in self.details[:4])
        return f"{self.total} op(s)"


@dataclass
class IDMStatus:
    installed: bool = False
    version: str = "—"
    idmvers: str = "—"
    registered: bool = False
    registrant: str = ""
    trial_clean: bool = False
    frozen: bool = False
    updates_blocked: bool = False
    auto_reset: bool = False
    process_running: bool = False
    exe_path: str = ""
    days_left: Optional[int] = None
    expired: bool = False
    recommended: str = ""   # action key to run next ("" = nothing needed)
    rec_tone: str = ""      # 'good' | 'warn' | 'bad'
    rec_title: str = ""
    rec_detail: str = ""
    trial_markers: List[str] = field(default_factory=list)
    clsid_hits: List[str] = field(default_factory=list)
    details: List[str] = field(default_factory=list)

    def trial_label(self) -> str:
        if self.frozen:
            return "Frozen"
        if self.trial_clean:
            return "Clean trial"
        return "Tracking active"


def recommend(st: IDMStatus) -> None:
    """Attach a smart 'what should I run now?' advisory to the status.

    Decision table (latest IDM 6.4x):
      expired trial            -> Activate  (one click: reset+register+lock+block)
      fresh/counting trial     -> Freeze    (perpetual trial) or Activate
      registered + unlocked    -> Freeze    (IDM can rebuild the trial clock)
      registered + open net    -> Block Updates (serial revalidation nag)
      fully protected          -> nothing   (registered + locked + blocked)
    """
    if not st.installed:
        st.recommended, st.rec_tone = "", "bad"
        st.rec_title = "IDM not found"
        st.rec_detail = (
            "Internet Download Manager is not installed on this machine "
            "(no registry key, no binary)."
        )
        return
    if st.registered and st.frozen and st.updates_blocked:
        st.recommended, st.rec_tone = "", "good"
        st.rec_title = "Fully protected — nothing to do"
        st.rec_detail = (
            "IDM is registered, every tracker key is ACL-locked and "
            "update/activation servers are blocked. Just use IDM."
        )
        return
    if st.registered:
        if not st.frozen:
            st.recommended, st.rec_tone = "freeze", "warn"
            st.rec_title = "Registered — tracker keys still writable"
            st.rec_detail = (
                "CLSID tracker keys are unlocked, so IDM can rebuild its "
                "trial clock and bring the nag back. Run Freeze to lock them."
            )
        else:
            st.recommended, st.rec_tone = "block_updates", "warn"
            st.rec_title = "Registered — update servers reachable"
            st.rec_detail = (
                "IDM can phone home and revalidate the serial "
                "(fake-serial nag) or silently self-update. Run Block Updates."
            )
        return
    if st.expired:
        st.recommended, st.rec_tone = "activate", "bad"
        st.rec_title = "Trial period is over"
        st.rec_detail = (
            "Run Activate — one click resets, registers IDM with a serial, "
            "locks every tracker key and blocks phone-home servers. "
            "Prefer staying on trial? Run Freeze instead."
        )
        return
    if st.frozen:
        st.recommended, st.rec_tone = "", "good"
        st.rec_title = "Frozen trial — never expires"
        st.rec_detail = (
            "Tracker keys are ACL-locked, so the trial clock cannot advance. "
            "Nothing else needed."
        )
        return
    if st.trial_clean:
        st.recommended, st.rec_tone = "freeze", "warn"
        st.rec_title = "Fresh trial — lock it now"
        st.rec_detail = (
            "Trial state is clean. Run Freeze before IDM advances the "
            "counter (perpetual trial), or Activate to register instead."
        )
        return
    st.recommended, st.rec_tone = "freeze", "warn"
    left = st.days_left if st.days_left is not None else 30
    st.rec_title = f"Trial counting down — about {left} day(s) left"
    st.rec_detail = (
        "Run Freeze for a never-expiring trial, or Activate for a fully "
        "registered IDM with no nags."
    )


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate_and_exit() -> None:
    script = os.path.abspath(sys.argv[0])
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, " ".join(f'"{a}"' for a in sys.argv[1:])
    else:
        exe = sys.executable
        rest = " ".join(f'"{a}"' for a in sys.argv[1:])
        params = f'"{script}"' + (f" {rest}" if rest else "")
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    sys.exit(0)


def _run(cmd, timeout: int = 30, shell: bool = False) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=shell,
            creationflags=CREATE_NO_WINDOW,
        )
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -1, "", str(e)


def run_powershell(script: str, timeout: int = 60) -> Tuple[int, str, str]:
    return _run(
        ["powershell", "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-Command", script],
        timeout=timeout,
    )


def get_file_version(path: str) -> Optional[str]:
    if not os.path.isfile(path):
        return None
    path_esc = path.replace("'", "''")
    ps = (
        f"$v=(Get-Item -LiteralPath '{path_esc}').VersionInfo; "
        "if($v.FileVersion){$v.FileVersion}else{$v.ProductVersion}"
    )
    code, out, _ = run_powershell(ps, timeout=8)
    ver = (out or "").strip()
    if code != 0 or not ver:
        return None
    if "," in ver:
        parts = [p.strip() for p in ver.split(",") if p.strip()]
        if parts and all(p.isdigit() for p in parts):
            ver = ".".join(parts)
    return ver


def reg_exists(root: int, subkey: str) -> bool:
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ):
            return True
    except OSError:
        return False


def reg_state(root: int, subkey: str) -> str:
    """Tri-state probe: 'present' | 'locked' | 'absent'.

    'locked' (PermissionError, winerror 5) means the key EXISTS but denies
    access — typically a deny-Everyone ACL left by a previous freeze or by
    IDM's anti-tamper. Treating such keys as absent is the classic
    silent-failure bug that lets IDM restore the trial clock from a hidden
    CLSID copy, so locked keys must be collected as reset targets.
    """
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ):
            return "present"
    except FileNotFoundError:
        return "absent"
    except PermissionError:
        return "locked"
    except OSError:
        return "absent"


def probe_values(root: int, subkey: str) -> Tuple[List[str], bool]:
    """(value names, locked?) — locked=True when the key denies read access."""
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as k:
            out: List[str] = []
            i = 0
            while True:
                try:
                    name, _, _ = winreg.EnumValue(k, i)
                    out.append(name)
                    i += 1
                except OSError:
                    break
            return out, False
    except PermissionError:
        return [], True
    except OSError:
        return [], False


def current_user_classes() -> Optional[str]:
    """The `<SID>_Classes` subkey of HKEY_USERS that mirrors the CURRENT
    user's HKCU\\Software\\Classes (IAS 'HKCUsync' check). Scans must skip
    that mirror: it is the same physical key as the HKCU target, and
    operating on both doubles work and reports false failures."""
    marker = "_IDMTR_SID_PROBE"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{marker}"):
            pass
    except OSError:
        return None
    found: Optional[str] = None
    for sid in enum_keys(winreg.HKEY_USERS, ""):
        if not sid.endswith("_Classes"):
            continue
        if reg_exists(winreg.HKEY_USERS, rf"{sid}\{marker}"):
            found = sid
            break
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{marker}")
    except OSError:
        pass
    return found


def enum_keys(root: int, subkey: str) -> List[str]:
    out: List[str] = []
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as k:
            i = 0
            while True:
                try:
                    out.append(winreg.EnumKey(k, i))
                    i += 1
                except OSError:
                    break
    except OSError:
        pass
    return out


def enum_values(root: int, subkey: str) -> List[str]:
    out: List[str] = []
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as k:
            i = 0
            while True:
                try:
                    name, _, _ = winreg.EnumValue(k, i)
                    out.append(name)
                    i += 1
                except OSError:
                    break
    except OSError:
        pass
    return out


def get_value(root: int, subkey: str, name: str) -> Optional[Tuple[Any, int]]:
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as k:
            return winreg.QueryValueEx(k, name)
    except OSError:
        return None


def delete_value(root: int, subkey: str, name: str) -> Tuple[bool, str]:
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_ALL_ACCESS) as k:
            try:
                winreg.DeleteValue(k, name)
                return True, f"Deleted value '{name}'"
            except FileNotFoundError:
                return False, f"'{name}' not present"
    except FileNotFoundError:
        return False, "Key not found"
    except PermissionError:
        return False, "ACCESS DENIED"
    except OSError as e:
        return False, str(e)


def delete_key_tree(root: int, subkey: str) -> Tuple[bool, str]:
    try:
        try:
            with winreg.OpenKey(root, subkey, 0, winreg.KEY_ALL_ACCESS) as k:
                children = []
                i = 0
                while True:
                    try:
                        children.append(winreg.EnumKey(k, i))
                        i += 1
                    except OSError:
                        break
        except FileNotFoundError:
            return False, "Not found"
        for child in reversed(children):
            delete_key_tree(root, f"{subkey}\\{child}")
        winreg.DeleteKey(root, subkey)
        return True, "Deleted"
    except PermissionError:
        return False, "ACCESS DENIED"
    except OSError as e:
        return False, str(e)


def set_value(root: int, subkey: str, name: str, value: Any, vtype: int) -> Tuple[bool, str]:
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_ALL_ACCESS) as k:
            winreg.SetValueEx(k, name, 0, vtype, value)
            return True, f"Set '{name}'"
    except FileNotFoundError:
        try:
            with winreg.CreateKey(root, subkey) as k:
                winreg.SetValueEx(k, name, 0, vtype, value)
                return True, f"Created + set '{name}'"
        except OSError as e:
            return False, str(e)
    except PermissionError:
        return False, "ACCESS DENIED"
    except OSError as e:
        return False, str(e)


def hive_label(root: int) -> str:
    return {
        winreg.HKEY_CURRENT_USER: "HKCU",
        winreg.HKEY_LOCAL_MACHINE: "HKLM",
        winreg.HKEY_USERS: "HKU",
        winreg.HKEY_CLASSES_ROOT: "HKCR",
    }.get(root, str(root))


def reg_export(key_path: str, out_file: str, hklm: bool = False) -> Tuple[bool, str]:
    root = "HKLM" if hklm else "HKCU"
    code, _, err = _run(f'reg export "{root}\\{key_path}" "{out_file}" /y', shell=True, timeout=25)
    if code == 0 and os.path.exists(out_file):
        return True, out_file
    return False, (err or "export failed").strip()


def reg_import(path: str) -> Tuple[bool, str]:
    code, _, err = _run(f'reg import "{path}"', shell=True, timeout=25)
    if code == 0:
        return True, "ok"
    return False, (err or "import failed").strip()


def appdata_idm() -> Path:
    return Path(os.path.expandvars(r"%APPDATA%\IDM"))


def app_store_dir() -> Path:
    base = Path(os.path.expandvars(r"%APPDATA%\IDMTools\IDMTrialResetterPro"))
    base.mkdir(parents=True, exist_ok=True)
    return base


class IDMEngine:
    def __init__(
        self,
        log_cb: Optional[Callable[[str, str], None]] = None,
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
        status_cb: Optional[Callable[[str], None]] = None,
    ):
        self._log = log_cb or (lambda m, l="info": None)
        self._progress = progress_cb or (lambda c, t, s="": None)
        self._status = status_cb or (lambda m: None)

    def log(self, msg: str, level: str = "info") -> None:
        self._log(msg, level)

    def progress(self, cur: int, total: int, label: str = "") -> None:
        self._progress(cur, total, label)
        if label:
            self._status(label)

    def kill_idm(self) -> int:
        killed = 0
        for proc in IDM_PROCESSES:
            code, _, _ = _run(["taskkill", "/F", "/IM", proc], timeout=6)
            if code == 0:
                self.log(f"  ✓ Terminated {proc}", "success")
                killed += 1
        if not killed:
            self.log("  · No IDM processes running", "info")
        return killed

    def is_idm_running(self) -> bool:
        _, out, _ = _run(["tasklist", "/FO", "CSV", "/NH"], timeout=8)
        low = (out or "").lower()
        return any(p.lower() in low for p in IDM_PROCESSES)

    def collect_clsid_targets(self) -> List[Tuple[int, str, str]]:
        found: List[Tuple[int, str, str]] = []
        seen = set()

        def add(root: int, full: str, note: str = "") -> None:
            key = (root, full.lower())
            if key in seen:
                return
            state = reg_state(root, full)
            if state == "absent":
                return
            seen.add(key)
            label = f"{hive_label(root)}\\...\\{full.split(chr(92))[-1][:28]}"
            if state == "locked":
                label += " [ACL-LOCKED]"
            if note:
                label += f" ({note})"
            found.append((root, full, label))
            self.log(f"  · {label}")

        try:
            sids = enum_keys(winreg.HKEY_USERS, "")
        except OSError:
            sids = []
        # The current user's HKU\<SID>_Classes mirror is the same physical
        # key as HKCU\Software\Classes — skip it (IAS 'HKCUsync' behavior).
        own_classes = current_user_classes()
        hku_sids = [s for s in sids if s.endswith("_Classes") and s != own_classes]

        # 1. Known IDM GUIDs across every hive mirror (locked keys included).
        for guid in IDM_CLSID_GUIDS:
            for root, base in CLSID_BASES:
                add(root, f"{base}\\{guid}", "known")

        # 2. Per-user Classes mirrors of the known GUIDs (other users only).
        for sid in hku_sids:
            for sub in (rf"{sid}\CLSID", rf"{sid}\WOW6432Node\CLSID"):
                for guid in IDM_CLSID_GUIDS:
                    add(winreg.HKEY_USERS, f"{sub}\\{guid}", "HKU")

        # 3. Dynamic discovery. IDM rotates GUIDs between builds, so scan the
        #    user-writable CLSID hives for its signature content — marker
        #    values, numeric/encoded default values, empty seed keys — while
        #    skipping real COM classes. Unreadable (locked) keys are always
        #    targets. Heuristics mirror IDM-Activation-Script, calibrated on
        #    a live 6.43.10 install.
        dynamic_bases = [
            (winreg.HKEY_CURRENT_USER, r"Software\Classes\CLSID"),
            (winreg.HKEY_CURRENT_USER, r"Software\Classes\WOW6432Node\CLSID"),
        ]
        dynamic_bases += [
            (winreg.HKEY_USERS, rf"{sid}\CLSID") for sid in hku_sids
        ]
        dynamic_bases += [
            (winreg.HKEY_USERS, rf"{sid}\WOW6432Node\CLSID") for sid in hku_sids
        ]
        guid_re = re.compile(
            r"^\{[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}"
            r"-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\}$"
        )
        for root, base in dynamic_bases:
            for guid in enum_keys(root, base):
                if not guid_re.match(guid):
                    continue
                full = f"{base}\\{guid}"
                if (root, full.lower()) in seen:
                    continue
                vals, locked = probe_values(root, full)
                if locked:
                    add(root, full, "locked")
                    continue
                if any(m in vals for m in CLSID_MARKERS):
                    add(root, full, "dynamic")
                    continue
                children = enum_keys(root, full)
                if any(c in COM_PROTECTED_SUBKEYS for c in children):
                    continue
                dval = get_value(root, full, "")
                dstr = str(dval[0]) if dval and dval[0] != "" else ""
                if not vals and not children:
                    add(root, full, "seed")
                    continue
                if dstr.isdigit() and not children:
                    add(root, full, "numeric")
                    continue
                if ("+" in dstr or "=" in dstr) and not children:
                    add(root, full, "encoded")
                    continue
                if children == ["Version"]:
                    vdef = get_value(root, rf"{full}\Version", "")
                    if vdef and str(vdef[0]).isdigit():
                        add(root, full, "version")

        return found

    def _unlock_registry_key(self, root: int, full: str) -> bool:
        """Break a deny-ACL lock on a registry key.

        Enables ownership/backup/restore privileges in a PowerShell child,
        takes ownership as BUILTIN\\Administrators, then REPLACES the whole
        DACL with a single Everyone-FullControl rule (protected) — dropping
        every inherited and explicit deny ACE so the key can be deleted.
        """
        if root == winreg.HKEY_USERS:
            ps_root, path = "Users", full
        elif root == winreg.HKEY_CURRENT_USER:
            ps_root, path = "CurrentUser", full
        elif root == winreg.HKEY_LOCAL_MACHINE:
            ps_root, path = "LocalMachine", full
        else:
            return False
        path = path.replace("'", "''")
        ps = f"""
{PS_PRIVILEGES}
$rootKey = [Microsoft.Win32.Registry]::{ps_root}
$path = '{path}'
try {{
  $key = $rootKey.OpenSubKey($path, 'ReadWriteSubTree', 'TakeOwnership')
  if ($key) {{
    $acl = New-Object System.Security.AccessControl.RegistrySecurity
    $acl.SetOwner([System.Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
    $key.SetAccessControl($acl); $key.Close()
  }}
  $key = $rootKey.OpenSubKey($path, 'ReadWriteSubTree', 'ChangePermissions')
  if ($key) {{
    $acl = New-Object System.Security.AccessControl.RegistrySecurity
    $rule = New-Object System.Security.AccessControl.RegistryAccessRule(
      [System.Security.Principal.SecurityIdentifier]::new('S-1-1-0'),
      'FullControl','ContainerInherit,ObjectInherit','None','Allow')
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetAccessRule($rule)
    $key.SetAccessControl($acl); $key.Close()
    'UNLOCKED'
  }} else {{ 'FAILED: open ChangePermissions' }}
}} catch {{ 'FAILED: ' + $_.Exception.Message }}
"""
        code, out, _err = run_powershell(ps, timeout=30)
        ok = "UNLOCKED" in (out or "")
        self.log(
            f"  {'✓' if ok else '✗'} ACL unlock {'succeeded' if ok else 'failed'}: "
            f"{hive_label(root)}\\...\\{full.split(chr(92))[-1][:28]}",
            "success" if ok else "error",
        )
        return ok

    def reset_trial(self) -> ActionResult:
        t0 = datetime.datetime.now()
        details: List[str] = []
        self.log("═" * 54, "header")
        self.log("  RESET TRIAL  —  full 30-day restoration (IDM 6.43.x)", "header")
        self.log("═" * 54, "header")
        self.kill_idm()
        steps = 7
        dm = r"Software\DownloadManager"

        self.progress(1, steps, "Cleaning DownloadManager trial values")
        self.log("\n[1/7] HKCU\\Software\\DownloadManager trial values …")
        n = 0
        for val in DM_TRIAL_VALUES:
            ok, msg = delete_value(winreg.HKEY_CURRENT_USER, dm, val)
            if ok:
                n += 1
                self.log(f"  ✓ {msg}", "success")
        self.log(f"  → {n} value(s) removed")
        details.append(f"DM values: {n}")

        self.progress(2, steps, "Removing ConfigTime / SpecialData")
        self.log("\n[2/7] Installation-clock subkeys (ConfigTime, SpecialData) …")
        start_ts = int(t0.timestamp())
        for sub in DM_TRIAL_SUBKEYS:
            ok, msg = delete_key_tree(winreg.HKEY_CURRENT_USER, rf"{dm}\{sub}")
            if ok:
                self.log(f"  ✓ Deleted {sub}", "success")
                details.append(f"{sub} removed")
            else:
                self.log(f"  · {sub}: {msg}", "info")
        # IDM 6.43.x ships a watchdog inside IDMShellExt64/IDMNetMon (loaded
        # in explorer.exe and other shell hosts) that re-creates ConfigTime
        # from a cached copy ~1s after deletion. Verified harmless — IDM
        # itself overwrites ConfigTime at the next fresh start — but we
        # re-anchor it to NOW so the machine is left exactly as a fresh
        # IDM install would be.
        time.sleep(1.5)
        if reg_state(winreg.HKEY_CURRENT_USER, rf"{dm}\ConfigTime") != "absent":
            ok, msg = set_value(
                winreg.HKEY_CURRENT_USER, rf"{dm}\ConfigTime", "",
                int(time.time()), winreg.REG_DWORD,
            )
            if ok:
                self.log(
                    "  · ConfigTime re-created by shell watchdog "
                    "(IDMShellExt64) — re-anchored to now",
                    "warning",
                )
            details.append("ConfigTime re-anchored")

        self.progress(3, steps, "Removing CLSID tracking keys")
        self.log("\n[3/7] CLSID tracking keys (ACL-locked keys are unlocked first) …")
        targets = self.collect_clsid_targets()
        removed = unlocked = denied = 0
        for root, full, label in targets:
            ok, msg = delete_key_tree(root, full)
            if not ok and "DENIED" in msg.upper():
                unlocked += 1
                self._unlock_registry_key(root, full)
                ok, msg = delete_key_tree(root, full)
            if ok:
                removed += 1
                self.log(f"  ✓ Removed {label}", "success")
            elif "Not found" not in msg:
                denied += 1
                self.log(f"  ! {label}: {msg}", "warning")
        summary = f"  → {removed} key(s) removed"
        if unlocked:
            summary += f", {unlocked} ACL-unlocked"
        if denied:
            summary += f", {denied} denied"
        self.log(summary)
        details.append(f"CLSID removed: {removed}")

        self.progress(4, steps, "HKEY_USERS DownloadManager")
        self.log("\n[4/7] HKEY_USERS DownloadManager values …")
        hku_n = 0
        try:
            for sid in enum_keys(winreg.HKEY_USERS, ""):
                if sid.endswith("_Classes") or sid in ("S-1-5-18", "S-1-5-19", "S-1-5-20"):
                    continue
                user_dm = rf"{sid}\Software\DownloadManager"
                if reg_state(winreg.HKEY_USERS, user_dm) != "present":
                    continue
                for val in DM_TRIAL_VALUES:
                    ok, _ = delete_value(winreg.HKEY_USERS, user_dm, val)
                    if ok:
                        hku_n += 1
                for sub in DM_TRIAL_SUBKEYS:
                    delete_key_tree(winreg.HKEY_USERS, rf"{user_dm}\{sub}")
        except Exception as e:
            self.log(f"  ! HKU DM: {e}", "warning")
        self.log(f"  → {hku_n} user value(s) cleaned")
        details.append(f"HKU DM: {hku_n}")

        self.progress(5, steps, "HKLM cleanup")
        self.log("\n[5/7] HKLM machine keys …")
        hklm_n = 0
        for root, path in HKLM_IDM_PATHS:
            ok, _ = delete_key_tree(root, path)
            if ok:
                hklm_n += 1
                self.log(f"  ✓ Cleared {hive_label(root)}\\{path}", "success")
        try:
            with winreg.CreateKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"Software\WOW6432Node\Internet Download Manager",
            ) as k:
                winreg.SetValueEx(k, "AdvIntDriverEnabled2", 0, winreg.REG_DWORD, 1)
            self.log("  ✓ AdvIntDriverEnabled2 = 1 (key recreated clean)", "success")
        except PermissionError:
            self.log("  ! Could not set AdvIntDriverEnabled2 (need admin)", "warning")
        except OSError as e:
            self.log(f"  ! AdvIntDriverEnabled2: {e}", "warning")
        details.append(f"HKLM cleaned: {hklm_n}")

        self.progress(6, steps, "AppData cache (safe)")
        self.log("\n[6/7] AppData cache (preserving active downloads) …")
        ad = appdata_idm()
        if ad.exists():
            skip_dirs = {"DwnlData", "Scheduler", "Grabber"}
            for child in list(ad.iterdir()):
                if child.name in skip_dirs:
                    self.log(f"  · Preserved {child.name}/")
                    continue
                if child.name in APPDATA_TRIAL_FILES and child.is_file():
                    try:
                        child.unlink(missing_ok=True)
                        self.log(f"  ✓ Removed {child.name} (self-updater payload)", "success")
                        details.append("idmupdt removed")
                    except Exception as e:
                        self.log(f"  ! {child.name}: {e}", "warning")
                    continue
                try:
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                    elif child.suffix.lower() in {".log", ".tmp", ".bak"}:
                        child.unlink(missing_ok=True)
                except Exception as e:
                    self.log(f"  ! {child.name}: {e}", "warning")
            self.log("  ✓ Safe cache touch-up complete", "success")
        else:
            self.log("  · AppData\\IDM not present")
        details.append("AppData safe-clean")

        self.progress(7, steps, "Verifying")
        self.log("\n[7/7] Verification …")
        remaining = []
        for val in ("tvfrdt", "radxcnt", "LastCheckQU", "LstCheck",
                    "CheckUpdtVM", "bRmGUCfEx", "vCOUFP"):
            if get_value(winreg.HKEY_CURRENT_USER, dm, val) is not None:
                remaining.append(val)
        if reg_state(winreg.HKEY_CURRENT_USER, rf"{dm}\SpecialData") != "absent":
            remaining.append("SpecialData")
        # ConfigTime only counts as leftover when it holds a STALE timestamp
        # (older than this run). A fresh one — written by us or by IDM at the
        # next start — is exactly what a clean install looks like.
        ct = get_value(winreg.HKEY_CURRENT_USER, rf"{dm}\ConfigTime", "")
        if ct is not None:
            try:
                if int(ct[0]) < start_ts:
                    remaining.append("ConfigTime(stale)")
            except (TypeError, ValueError):
                remaining.append("ConfigTime")
        clsid_left = [
            label for root, full, label in targets
            if reg_state(root, full) != "absent"
        ]
        remaining.extend(clsid_left)

        ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
        if remaining:
            self.log(f"  ! Still present: {', '.join(remaining)}", "error")
            details.append(f"leftover: {','.join(remaining)}")
            self.log("\n" + "═" * 54, "header")
            self.log("  ✗ RESET INCOMPLETE — restart IDM is NOT safe yet", "error")
            self.log("═" * 54, "header")
            return ActionResult(
                "reset", False, total=removed + n,
                details=details,
                error=f"Leftover trial state: {', '.join(remaining[:6])}",
                duration_ms=ms,
            )
        self.log("  ✓ Core trial markers cleared", "success")
        self.log("  ✓ All CLSID tracking keys removed", "success")
        details.append("markers clean")
        self.log("\n" + "═" * 54, "header")
        self.log("  ✓ TRIAL RESET COMPLETE — restart IDM for a fresh 30 days", "success")
        self.log("═" * 54, "header")
        return ActionResult("reset", True, total=removed + n, details=details, duration_ms=ms)

    def _soft_reset(self) -> None:
        """Quiet trial-state wipe used by Freeze / Activate: clears the
        DownloadManager trial values + clock subkeys and recreates the HKLM
        key clean (parity with the IAS delete_queue + add_key flow)."""
        dm = r"Software\DownloadManager"
        for val in DM_TRIAL_VALUES:
            delete_value(winreg.HKEY_CURRENT_USER, dm, val)
        for sub in DM_TRIAL_SUBKEYS:
            delete_key_tree(winreg.HKEY_CURRENT_USER, rf"{dm}\{sub}")
        for root, path in HKLM_IDM_PATHS:
            delete_key_tree(root, path)
        try:
            with winreg.CreateKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"Software\WOW6432Node\Internet Download Manager",
            ) as k:
                winreg.SetValueEx(k, "AdvIntDriverEnabled2", 0, winreg.REG_DWORD, 1)
        except OSError:
            pass

    def _ensure_clsid_keys(self) -> int:
        """Create the active IDM CLSID GUID keys (empty) when absent.

        Freezing only works while EVERY tracking copy is locked. If a key is
        missing, IDM simply re-creates it writable and resumes counting —
        the exact failure mode observed on this machine, where a previous
        freeze left {07999AC3-…} absent and IDM rebuilt the trial clock in it.
        """
        created = 0
        for guid in ACTIVE_TRACKER_GUIDS:
            for root, base in CLSID_BASES[:2]:  # HKCU Classes\CLSID + WOW6432Node
                full = f"{base}\\{guid}"
                if reg_state(root, full) == "absent":
                    try:
                        winreg.CreateKey(root, full)
                        created += 1
                        self.log(
                            f"  · Created {hive_label(root)}\\…\\{guid[:20]}… "
                            "(seed so the lock covers it)",
                            "info",
                        )
                    except OSError as e:
                        self.log(f"  ! create {guid[:20]}…: {e}", "warning")
        return created

    def _lock_clsid_targets(self, keys: List[Tuple[int, str, str]]) -> Tuple[int, int]:
        """Apply deny-Everyone ACL locks to the given CLSID targets.
        Returns (frozen, failed)."""
        blocks = []
        for root, full, label in keys:
            safe = label.replace("'", "")
            if root == winreg.HKEY_CURRENT_USER:
                root_expr = "[Microsoft.Win32.Registry]::CurrentUser"
            elif root == winreg.HKEY_LOCAL_MACHINE:
                root_expr = "[Microsoft.Win32.Registry]::LocalMachine"
            elif root == winreg.HKEY_USERS:
                root_expr = "[Microsoft.Win32.Registry]::Users"
            else:
                continue
            path_esc = full.replace("'", "''")
            blocks.append(f"""
$rootKey = {root_expr}
$path = '{path_esc}'
try {{
  $key = $rootKey.OpenSubKey($path, 'ReadWriteSubTree', 'TakeOwnership')
  if ($null -eq $key) {{ Write-Output 'FAILED: {safe} open'; continue }}
  $acl = New-Object System.Security.AccessControl.RegistrySecurity
  $acl.SetOwner([System.Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
  $key.SetAccessControl($acl); $key.Close()

  $key = $rootKey.OpenSubKey($path, 'ReadWriteSubTree', 'ChangePermissions')
  if ($null -eq $key) {{ Write-Output 'FAILED: {safe} perms'; continue }}
  $acl = $key.GetAccessControl()
  $rule = New-Object System.Security.AccessControl.RegistryAccessRule(
    [System.Security.Principal.SecurityIdentifier]::new('S-1-1-0'),
    'FullControl','ContainerInherit,ObjectInherit','None','Deny')
  $acl.ResetAccessRule($rule)
  $key.SetAccessControl($acl); $key.Close()

  $key = $rootKey.OpenSubKey($path, 'ReadWriteSubTree', 'TakeOwnership')
  if ($key) {{
    $acl = New-Object System.Security.AccessControl.RegistrySecurity
    $acl.SetOwner([System.Security.Principal.SecurityIdentifier]::new('S-1-0-0'))
    $key.SetAccessControl($acl); $key.Close()
  }}
  Write-Output 'FROZEN: {safe}'
}} catch {{ Write-Output ("FAILED: {safe} - " + $_.Exception.Message) }}
""")
        if not blocks:
            return 0, 0
        _, stdout, _stderr = run_powershell(
            PS_PRIVILEGES + "\n" + "\n".join(blocks), timeout=120,
        )
        frozen = failed = 0
        for line in (stdout or "").splitlines():
            line = line.strip()
            if line.startswith("FROZEN:"):
                frozen += 1
                self.log(f"  ✓ Locked {line[7:].strip()}", "success")
            elif line.startswith("FAILED:"):
                failed += 1
                self.log(f"  ✗ {line}", "error")
        return frozen, failed

    def freeze_trial(self) -> ActionResult:
        t0 = datetime.datetime.now()
        self.log("═" * 54, "header")
        self.log("  FREEZE TRIAL  —  wipe state, then ACL-lock ALL CLSID keys", "header")
        self.log("═" * 54, "header")
        self.kill_idm()

        self.progress(1, 3, "Wiping trial state")
        self.log("\n[1/3] Wiping current trial state (lock must freeze a FRESH trial) …")
        self._soft_reset()
        self.log("  ✓ Trial values and clocks cleared", "success")

        self.progress(2, 3, "Locating / seeding CLSID keys")
        self.log("\n[2/3] Locating CLSID tracking keys (missing ones are seeded) …")
        self._ensure_clsid_keys()
        keys = self.collect_clsid_targets()
        if not keys:
            self.log("  ! No CLSID keys found to freeze.", "warning")
            return ActionResult("freeze", False, error="No CLSID keys found")

        self.log(f"\n[3/3] Locking {len(keys)} key(s) …")
        self.progress(3, 3, "Applying ACL locks")
        frozen, failed = self._lock_clsid_targets(keys)

        ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
        if frozen > 0:
            self.log(f"\n  ✓ Frozen {frozen} key(s) — trial starts fresh and cannot advance", "success")
            return ActionResult(
                "freeze", True, total=frozen,
                details=[f"Frozen: {frozen}", f"Failed: {failed}"], duration_ms=ms,
            )
        return ActionResult(
            "freeze", False, details=[f"Failed: {failed}"],
            error="No keys frozen — run as Administrator",
            duration_ms=ms,
        )

    def unfreeze_trial(self) -> ActionResult:
        t0 = datetime.datetime.now()
        self.log("═" * 54, "header")
        self.log("  UNFREEZE TRIAL  —  restore ACL write access", "header")
        self.log("═" * 54, "header")

        self.progress(1, 2, "Locating keys")
        keys = self.collect_clsid_targets()
        for guid in IDM_CLSID_GUIDS:
            for root, base in CLSID_BASES:
                full = f"{base}\\{guid}"
                if not any(f == full for _, f, _ in keys):
                    keys.append((root, full, f"{hive_label(root)}\\…\\{guid[:12]}… (force)"))

        uniq = []
        seen = set()
        for r, f, l in keys:
            k = (r, f.lower())
            if k in seen:
                continue
            seen.add(k)
            uniq.append((r, f, l))
        keys = uniq
        self.log(f"  → {len(keys)} candidate(s)")
        self.progress(2, 2, "Restoring permissions")

        blocks = []
        for root, full, label in keys:
            safe = label.replace("'", "")
            if root == winreg.HKEY_CURRENT_USER:
                ps_root = "CurrentUser"
            elif root == winreg.HKEY_LOCAL_MACHINE:
                ps_root = "LocalMachine"
            elif root == winreg.HKEY_USERS:
                ps_root = "Users"
            else:
                continue
            path = full.replace("'", "''")
            blocks.append(f"""
$root = [Microsoft.Win32.Registry]::{ps_root}
$path = '{path}'
try {{
  $key = $root.OpenSubKey($path, 'ReadWriteSubTree', 'TakeOwnership')
  if ($key) {{
    $acl = New-Object System.Security.AccessControl.RegistrySecurity
    $acl.SetOwner([System.Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
    $key.SetAccessControl($acl); $key.Close()
  }}
  $key = $root.OpenSubKey($path, 'ReadWriteSubTree', 'ChangePermissions')
  if ($key) {{
    $acl = $key.GetAccessControl()
    $acl.SetAccessRuleProtection($false, $true)
    foreach ($ace in @($acl.GetAccessRules($true,$true,[System.Security.Principal.NTAccount]))) {{
      if ($ace.AccessControlType -eq 'Deny') {{ $acl.RemoveAccessRule($ace) | Out-Null }}
    }}
    $rule = New-Object System.Security.AccessControl.RegistryAccessRule(
      [System.Security.Principal.SecurityIdentifier]::new('S-1-1-0'),
      'FullControl','ContainerInherit,ObjectInherit','None','Allow')
    $acl.SetAccessRule($rule)
    $key.SetAccessControl($acl); $key.Close()
    Write-Output 'UNFROZEN'
  }} else {{ Write-Output 'SKIP' }}
}} catch {{ Write-Output ("FAILED: {safe} - " + $_.Exception.Message) }}
""")
        _, stdout, _ = run_powershell(
            PS_PRIVILEGES + "\n" + ("\n".join(blocks) if blocks else "''"),
            timeout=120,
        )
        unfrozen = sum(1 for l in (stdout or "").splitlines() if "UNFROZEN" in l)
        ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
        self.log(f"  ✓ Unfrozen {unfrozen} key(s)", "success" if unfrozen else "info")
        return ActionResult(
            "unfreeze", True, total=unfrozen,
            details=[f"Unfrozen: {unfrozen}"], duration_ms=ms,
        )

    def activate(
        self,
        fname: str = "",
        lname: str = "",
        email: str = "",
        serial: str = "",
        block_updates: bool = True,
    ) -> ActionResult:
        """IAS-parity activation pipeline for latest IDM (6.4x).

        Order matters and mirrors the proven IDM-Activation-Script flow:
        reset -> seed CLSID keys -> LOCK them -> write registration
        (random IAS-format serial) -> block update/activation servers ->
        brief IDM start so it picks up the registration -> re-lock anything
        IDM re-created. Registered mode never shows the trial-expired nag,
        and the hosts block prevents the server-side serial revalidation
        that triggers the fake-serial nag.
        """
        t0 = datetime.datetime.now()
        details: List[str] = []
        self.log("═" * 54, "header")
        self.log("  ACTIVATE  —  reset + register + lock + block updates", "header")
        self.log("═" * 54, "header")

        self.progress(1, 6, "Resetting trial state")
        self.log("\n[1/6] Resetting trial state …")
        self.reset_trial()

        self.progress(2, 6, "Seeding CLSID keys")
        self.log("\n[2/6] Ensuring CLSID tracking keys exist …")
        self._ensure_clsid_keys()

        self.progress(3, 6, "Locking CLSID keys")
        self.log("\n[3/6] Locking CLSID keys BEFORE IDM first run …")
        keys = self.collect_clsid_targets()
        frozen, failed = self._lock_clsid_targets(keys)
        details.append(f"Locked: {frozen}")

        self.progress(4, 6, "Injecting registration")
        self.log("\n[4/6] Injecting registration …")
        rnd = random.SystemRandom()
        fn = (fname or str(rnd.randint(1000, 9999))).strip()
        ln = (lname or str(rnd.randint(1000, 9999))).strip()
        em = (email or f"{fn}.{ln}@tonec.com").strip()
        key = (serial or generate_serial()).strip().upper()
        dm = r"Software\DownloadManager"
        set_value(winreg.HKEY_CURRENT_USER, dm, "FName", fn, winreg.REG_SZ)
        set_value(winreg.HKEY_CURRENT_USER, dm, "LName", ln, winreg.REG_SZ)
        set_value(winreg.HKEY_CURRENT_USER, dm, "Email", em, winreg.REG_SZ)
        set_value(winreg.HKEY_CURRENT_USER, dm, "Serial", key, winreg.REG_SZ)
        self.log(f"  ✓ Registered as: {fn} {ln} <{em}>", "success")
        self.log(f"  ✓ Serial: {key}", "success")
        details.append(f"Serial: {key}")

        self.progress(5, 6, "Blocking update servers")
        if block_updates:
            self.log("\n[5/6] Blocking update / activation servers (kills the nag at the source) …")
            bu = self.block_updates()
            details.append("updates blocked" if bu.success else f"block failed: {bu.error}")
        else:
            self.log("\n[5/6] Hosts blocking skipped (user choice)", "info")
            details.append("updates NOT blocked")

        self.progress(6, 6, "Seeding IDM + re-locking")
        self.log("\n[6/6] Brief IDM start so it picks up the registration …")
        exe = self._find_exe()
        if exe:
            try:
                subprocess.Popen([exe], creationflags=CREATE_NO_WINDOW)
                time.sleep(3)
            except Exception as e:
                self.log(f"  ! Could not start IDM: {e}", "warning")
            self.kill_idm()
        relock = self.collect_clsid_targets()
        if relock:
            f2, _ = self._lock_clsid_targets(relock)
            if f2:
                details.append(f"Re-locked: {f2}")

        check = get_value(winreg.HKEY_CURRENT_USER, dm, "Serial")
        registered = bool(check and str(check[0]).strip())
        ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
        if registered and frozen > 0:
            self.log("\n  ✓ ACTIVATION COMPLETE — registered, locked, phone-home blocked", "success")
            return ActionResult("activate", True, total=frozen, details=details, duration_ms=ms)
        if registered:
            self.log("\n  · Registered, but CLSID lock incomplete — run Freeze", "warning")
            return ActionResult(
                "activate", False, total=frozen, details=details,
                error="Registration written but CLSID lock incomplete", duration_ms=ms,
            )
        return ActionResult(
            "activate", False, total=frozen, details=details,
            error="Registration could not be written",
        )

    def deactivate(self) -> ActionResult:
        """Inverse of Activate: removes the registration, unfreezes the
        tracker keys, removes the hosts block and leaves a clean day-1
        trial (no serial, no locks, updates allowed)."""
        t0 = datetime.datetime.now()
        self.log("═" * 54, "header")
        self.log("  DEACTIVATE  —  unregister + unfreeze + unblock + reset", "header")
        self.log("═" * 54, "header")
        self.kill_idm()

        self.progress(1, 3, "Unfreezing trackers")
        self.log("\n[1/3] Restoring ACL write access on tracker keys …")
        self.unfreeze_trial()

        self.progress(2, 3, "Removing hosts block")
        self.log("\n[2/3] Removing hosts block (update servers reachable again) …")
        self.unblock_updates()

        self.progress(3, 3, "Resetting to a clean trial")
        self.log("\n[3/3] Full trial reset (removes FName/LName/Email/Serial) …")
        res = self.reset_trial()

        ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
        dm = r"Software\DownloadManager"
        gone = all(
            get_value(winreg.HKEY_CURRENT_USER, dm, v) is None
            for v in ("FName", "LName", "Email", "Serial")
        )
        if res.success and gone:
            self.log(
                "\n  ✓ DEACTIVATED — unregistered, unlocked, clean 30-day trial",
                "success",
            )
            return ActionResult(
                "deactivate", True, details=res.details + ["unregistered"],
                duration_ms=ms,
            )
        return ActionResult(
            "deactivate", False, details=res.details,
            error=res.error or "Registration values still present",
            duration_ms=ms,
        )

    def launch_idm(self) -> ActionResult:
        """Start IDMan.exe (no admin rights needed)."""
        t0 = datetime.datetime.now()
        exe = self._find_exe()
        if not exe:
            return ActionResult("launch", False, error="IDM executable not found")
        try:
            subprocess.Popen([exe], creationflags=CREATE_NO_WINDOW)
            self.log(f"  ✓ Started {exe}", "success")
            return ActionResult(
                "launch", True, details=[exe],
                duration_ms=int((datetime.datetime.now() - t0).total_seconds() * 1000),
            )
        except Exception as e:
            return ActionResult("launch", False, error=str(e))

    def export_diagnostics(self, path: str) -> ActionResult:
        """Write a human-readable status report for support / debugging."""
        t0 = datetime.datetime.now()
        st = self.check_status()
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        trial = "expired" if st.expired else (
            f"{st.days_left} day(s) left" if st.days_left is not None else "no counter"
        )
        lines = [
            f"{APP_NAME} v{VERSION} — diagnostics report",
            f"Generated: {ts}",
            "=" * 62,
            "",
            f"Installed:       {st.installed}",
            f"Binary version:  {st.version}",
            f"idmvers:         {st.idmvers}",
            f"Registered:      {st.registered}"
            + (f"  ({st.registrant})" if st.registered else ""),
            f"Frozen:          {st.frozen}",
            f"Updates blocked: {st.updates_blocked}",
            f"Trial state:     {trial}",
            f"Auto-reset task: {st.auto_reset}",
            f"IDM running:     {st.process_running}",
            f"EXE:             {st.exe_path or '—'}",
            "",
            f"Recommendation:  {st.rec_title}",
            f"  {st.rec_detail}",
            "",
            "Trial markers:",
            f"  {', '.join(st.trial_markers) if st.trial_markers else '(none)'}",
            "",
            "CLSID tracker keys:",
        ]
        lines += [f"  {h}" for h in st.clsid_hits] or ["  (none)"]
        lines += ["", "Details:"]
        lines += [f"  · {d}" for d in st.details]
        lines += ["", f"— {APP_NAME} (engine v{VERSION})", ""]
        try:
            Path(path).write_text("\n".join(lines), encoding="utf-8")
        except Exception as e:
            return ActionResult("diagnostics", False, error=str(e))
        self.log(f"  ✓ Diagnostics report → {path}", "success")
        return ActionResult(
            "diagnostics", True, details=[str(path)],
            duration_ms=int((datetime.datetime.now() - t0).total_seconds() * 1000),
        )

    def _find_exe(self) -> Optional[str]:
        for p in IDM_EXE_CANDIDATES:
            if os.path.isfile(p):
                return p
        v = get_value(winreg.HKEY_CURRENT_USER, r"Software\DownloadManager", "ExePath")
        if v and isinstance(v[0], str) and os.path.isfile(v[0]):
            return v[0]
        return None

    def block_updates(self) -> ActionResult:
        t0 = datetime.datetime.now()
        self.log("═" * 54, "header")
        self.log("  BLOCK UPDATES  —  hosts sinkhole", "header")
        self.log("═" * 54, "header")
        if not HOSTS_PATH.exists():
            return ActionResult("block_updates", False, error="hosts file missing")
        try:
            content = HOSTS_PATH.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ActionResult("block_updates", False, error=str(e))
        if HOSTS_HEADER in content:
            self.log("  · Already blocked", "info")
            return ActionResult("block_updates", True, details=["Already blocked"])

        lines = ["", HOSTS_HEADER, "# Block IDM update / activation servers"]
        added = 0
        for d in IDM_BLOCK_DOMAINS:
            lines.append(f"127.0.0.1 {d}")
            lines.append(f"0.0.0.0 {d}")
            added += 1
        lines += [HOSTS_FOOTER, ""]
        try:
            HOSTS_PATH.write_text(content.rstrip("\n") + "\n" + "\n".join(lines), encoding="utf-8")
            self.log(f"  ✓ Blocked {added} domain(s)", "success")
            _run(["ipconfig", "/flushdns"], timeout=10)
            self.log("  ✓ DNS cache flushed", "success")
        except PermissionError:
            return ActionResult("block_updates", False, error="Access denied — run as Administrator")
        except Exception as e:
            return ActionResult("block_updates", False, error=str(e))
        ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
        return ActionResult("block_updates", True, total=added, details=[f"{added} domains blocked"], duration_ms=ms)

    def unblock_updates(self) -> ActionResult:
        t0 = datetime.datetime.now()
        self.log("═" * 54, "header")
        self.log("  UNBLOCK UPDATES", "header")
        self.log("═" * 54, "header")
        if not HOSTS_PATH.exists():
            return ActionResult("unblock_updates", True, details=["hosts missing"])
        try:
            content = HOSTS_PATH.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ActionResult("unblock_updates", False, error=str(e))
        if HOSTS_HEADER not in content:
            self.log("  · No block section present", "info")
            return ActionResult("unblock_updates", True, details=["Not blocked"])
        pat = re.compile(re.escape(HOSTS_HEADER) + r".*?" + re.escape(HOSTS_FOOTER), re.DOTALL)
        new = re.sub(r"\n{3,}", "\n\n", pat.sub("", content).strip()) + "\n"
        try:
            HOSTS_PATH.write_text(new, encoding="utf-8")
            self.log("  ✓ Removed block section", "success")
            _run(["ipconfig", "/flushdns"], timeout=10)
        except Exception as e:
            return ActionResult("unblock_updates", False, error=str(e))
        ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
        return ActionResult("unblock_updates", True, details=["Block removed"], duration_ms=ms)

    def backup(self, output_dir: str) -> ActionResult:
        t0 = datetime.datetime.now()
        self.log("═" * 54, "header")
        self.log("  BACKUP", "header")
        self.log("═" * 54, "header")
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        bdir = Path(output_dir) / f"idm_backup_{ts}"
        bdir.mkdir(parents=True, exist_ok=True)

        jobs = [
            (r"Software\DownloadManager", str(bdir / "HKCU_DownloadManager.reg"), False),
            (r"Software\Classes\WOW6432Node\CLSID", str(bdir / "HKCU_WOW_CLSID.reg"), False),
            (r"Software\WOW6432Node\Internet Download Manager", str(bdir / "HKLM_WOW_IDM.reg"), True),
        ]
        files: List[str] = []
        for i, (kp, out, hklm) in enumerate(jobs, 1):
            self.progress(i, len(jobs) + 1, Path(out).name)
            ok, msg = reg_export(kp, out, hklm)
            if ok:
                self.log(f"  ✓ {Path(out).name} ({os.path.getsize(out):,} B)", "success")
                files.append(Path(out).name)
            else:
                self.log(f"  · skip {kp}: {msg}", "info")

        ad = appdata_idm()
        self.progress(len(jobs) + 1, len(jobs) + 1, "AppData")
        if ad.exists():
            try:
                shutil.copytree(str(ad), str(bdir / "AppData"), dirs_exist_ok=True)
                self.log("  ✓ AppData tree", "success")
                files.append("AppData")
            except Exception as e:
                self.log(f"  ! AppData: {e}", "warning")

        manifest = {
            "created": ts, "version": VERSION, "app": APP_NAME,
            "idm_version": self._idmvers(), "files": files,
        }
        (bdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.log(f"\n  ✓ Backup → {bdir}", "success")
        ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
        return ActionResult("backup", True, total=len(files), details=files + [str(bdir)], duration_ms=ms)

    def restore(self, backup_dir: str) -> ActionResult:
        t0 = datetime.datetime.now()
        self.log("═" * 54, "header")
        self.log("  RESTORE", "header")
        self.log("═" * 54, "header")
        path = Path(backup_dir)
        if not path.exists():
            return ActionResult("restore", False, error="Folder not found")
        self.kill_idm()
        regs = list(path.glob("*.reg"))
        if not regs:
            return ActionResult("restore", False, error="No .reg files")
        n = 0
        names: List[str] = []
        for i, rf in enumerate(regs, 1):
            self.progress(i, len(regs) + 1, rf.name)
            ok, msg = reg_import(str(rf))
            if ok:
                self.log(f"  ✓ {rf.name}", "success")
                n += 1
                names.append(rf.name)
            else:
                self.log(f"  ✗ {rf.name}: {msg}", "error")
        app_src = path / "AppData"
        if app_src.exists():
            try:
                dest = appdata_idm()
                shutil.copytree(str(app_src), str(dest), dirs_exist_ok=True)
                self.log("  ✓ AppData restored", "success")
                names.append("AppData")
            except Exception as e:
                self.log(f"  ! AppData restore: {e}", "warning")
        ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
        return ActionResult("restore", True, total=n, details=names, duration_ms=ms)

    def setup_auto_reset(self, interval_days: int = 25) -> ActionResult:
        self.log("═" * 54, "header")
        self.log(f"  AUTO-RESET every {interval_days} day(s)", "header")
        self.log("═" * 54, "header")
        task = "IDM Trial Auto Reset"
        _run(f'schtasks /delete /tn "{task}" /f', shell=True, timeout=10)
        script = os.path.abspath(sys.argv[0]).replace("'", "''")
        exe = sys.executable.replace("'", "''")
        arg = f'"{script}" --auto-reset'.replace("'", "''")
        days = max(5, min(29, int(interval_days)))
        ps = f"""
$action = New-ScheduledTaskAction -Execute '{exe}' -Argument '{arg}'
$trigger = New-ScheduledTaskTrigger -Daily -At '09:00AM' -DaysInterval {days}
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName '{task}' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
if ((Get-ScheduledTask -TaskName '{task}' -ErrorAction SilentlyContinue).State -eq 'Ready') {{ 'SUCCESS' }}
"""
        _, out, err = run_powershell(ps, timeout=40)
        if "SUCCESS" in (out or ""):
            self.log(f"  ✓ Scheduled every {days} days at 09:00 (SYSTEM)", "success")
            return ActionResult("auto_reset", True, total=1, details=[f"Every {days} days"])
        return ActionResult("auto_reset", False, error=(err or out or "failed")[:200])

    def remove_auto_reset(self) -> ActionResult:
        code, _, _ = _run('schtasks /delete /tn "IDM Trial Auto Reset" /f', shell=True, timeout=10)
        if code == 0:
            self.log("  ✓ Auto-reset task removed", "success")
            return ActionResult("remove_auto_reset", True, details=["Task removed"])
        self.log("  · No task found", "info")
        return ActionResult("remove_auto_reset", True, details=["No task"])

    def has_auto_reset(self) -> bool:
        code, _, _ = _run('schtasks /query /tn "IDM Trial Auto Reset"', shell=True, timeout=8)
        return code == 0

    def _idmvers(self) -> str:
        v = get_value(winreg.HKEY_CURRENT_USER, r"Software\DownloadManager", "idmvers")
        return str(v[0]) if v else "—"

    def check_status(self) -> IDMStatus:
        st = IDMStatus()
        dm = r"Software\DownloadManager"

        if reg_exists(winreg.HKEY_CURRENT_USER, dm):
            st.installed = True
            st.details.append("HKCU\\Software\\DownloadManager present")

        exe = self._find_exe()
        if exe:
            st.installed = True
            st.exe_path = exe
            st.version = get_file_version(exe) or "Installed"
            st.details.append(f"Binary: {exe}")

        st.idmvers = self._idmvers()
        if st.idmvers and st.idmvers != "—":
            st.details.append(f"idmvers: {st.idmvers}")

        fname = get_value(winreg.HKEY_CURRENT_USER, dm, "FName")
        serial = get_value(winreg.HKEY_CURRENT_USER, dm, "Serial")
        lname = get_value(winreg.HKEY_CURRENT_USER, dm, "LName")
        if fname and (serial and str(serial[0]).strip()):
            st.registered = True
            ln = str(lname[0]) if lname else ""
            st.registrant = f"{fname[0]} {ln}".strip()
        else:
            st.details.append("Trial mode (no serial)")

        markers = []
        for val in ("tvfrdt", "radxcnt", "LastCheckQU", "LstCheck", "CheckUpdtVM",
                    "scansk", "MData", "ptrk_scdt", "cDTvBFquXk0",
                    "bRmGUCfEx", "vCOUFP"):
            if get_value(winreg.HKEY_CURRENT_USER, dm, val) is not None:
                markers.append(val)
        # ConfigTime is written by IDM itself on every fresh start, so its
        # presence is normal mid-trial — report its age as a detail instead.
        if reg_state(winreg.HKEY_CURRENT_USER, rf"{dm}\SpecialData") != "absent":
            markers.append("SpecialData")
        ct = get_value(winreg.HKEY_CURRENT_USER, rf"{dm}\ConfigTime", "")
        if ct is not None:
            try:
                age = max(0, int(time.time()) - int(ct[0]))
                st.details.append(
                    f"Install clock ConfigTime: {age // 86400} day(s) old"
                )
            except (TypeError, ValueError):
                pass
        st.trial_markers = markers
        st.trial_clean = len(markers) == 0
        if markers:
            st.details.append(f"Markers: {', '.join(markers)}")
        else:
            st.details.append("No trial tracking values")

        radx = get_value(winreg.HKEY_CURRENT_USER, dm, "radxcnt")
        if radx is not None:
            try:
                cnt = int(radx[0])
                st.days_left = 30 - cnt
                st.expired = st.days_left <= 0
                st.details.append(
                    f"Trial counter radxcnt={cnt} "
                    + ("(EXPIRED)" if st.expired else f"(~{st.days_left} day(s) left)")
                )
            except (TypeError, ValueError):
                pass

        hits = []
        locked_hits = 0
        for guid in IDM_CLSID_GUIDS:
            for root, base in CLSID_BASES[:2]:
                state = reg_state(root, f"{base}\\{guid}")
                if state == "present":
                    hits.append(f"{hive_label(root)}:{guid[:9]}…")
                elif state == "locked":
                    hits.append(f"{hive_label(root)}:{guid[:9]}…[LOCKED]")
                    locked_hits += 1
        st.clsid_hits = hits
        if hits:
            st.details.append(f"CLSID hits: {len(hits)}")
        if locked_hits:
            st.frozen = True
            st.details.append(
                f"{locked_hits} CLSID key(s) ACL-locked (deny ACE) — "
                "reset/unfreeze will take ownership and clear it"
            )

        if HOSTS_PATH.exists():
            try:
                if HOSTS_HEADER in HOSTS_PATH.read_text(encoding="utf-8", errors="replace"):
                    st.updates_blocked = True
                    st.details.append("Hosts sinkhole active")
            except Exception:
                pass

        # Nag-risk assessment — explains the recurring "trial period is
        # over" popup and what stops it.
        if st.registered:
            sv = get_value(winreg.HKEY_CURRENT_USER, dm, "Serial")
            if sv and str(sv[0]).strip():
                st.details.append(f"Serial: {str(sv[0])}")
            if not st.updates_blocked:
                st.details.append(
                    "Registered but update servers reachable — run Block Updates "
                    "to stop serial revalidation (fake-serial nag)"
                )
            if not st.frozen:
                st.details.append(
                    "Registered but CLSID keys unlocked — run Freeze to stop "
                    "trial-state tracking"
                )
        elif st.frozen:
            st.details.append("Frozen — IDM cannot persist trial state")
        elif not st.trial_clean:
            st.details.append(
                "Trial state present and unlocked — IDM keeps counting and will "
                "nag at expiry; run Freeze (perpetual fresh trial) or Activate "
                "(registered, no nags)"
            )
        if not st.registered and not st.frozen and not st.updates_blocked:
            st.details.append(
                "Update checks open — IDM phones home (can re-flag this machine "
                "and self-update); Block Updates recommended"
            )

        st.auto_reset = self.has_auto_reset()
        if st.auto_reset:
            st.details.append("Auto-reset scheduled task present")

        st.process_running = self.is_idm_running()
        if st.process_running:
            st.details.append("IDM process running")

        recommend(st)
        return st

    def run(self, action: str, **kwargs) -> ActionResult:
        if not isinstance(action, str) or not action:
            return ActionResult(str(action), False, error=f"Unknown action: {action!r}")

        table: Dict[str, Callable[[], ActionResult]] = {
            "reset": self.reset_trial,
            "freeze": self.freeze_trial,
            "unfreeze": self.unfreeze_trial,
            "activate": lambda: self.activate(
                kwargs.get("fname", ""),
                kwargs.get("lname", ""),
                kwargs.get("email", ""),
                serial=kwargs.get("serial", ""),
                block_updates=bool(kwargs.get("block_updates", True)),
            ),
            "deactivate": self.deactivate,
            "launch": self.launch_idm,
            "diagnostics": lambda: self.export_diagnostics(
                kwargs.get("path", str(Path.home() / "idm_diagnostics.txt"))
            ),
            "block_updates": self.block_updates,
            "unblock_updates": self.unblock_updates,
            "backup": lambda: self.backup(kwargs.get("output_dir", str(Path.home()))),
            "restore": lambda: self.restore(kwargs.get("backup_dir", "")),
            "auto_reset": lambda: self.setup_auto_reset(int(kwargs.get("interval", 25))),
            "remove_auto_reset": self.remove_auto_reset,
        }
        fn = table.get(action)
        if not fn:
            return ActionResult(action, False, error=f"Unknown action: {action!r}")
        try:
            return fn()
        except Exception as e:
            self.log(traceback.format_exc(), "error")
            return ActionResult(action, False, error=str(e))
