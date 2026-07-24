"""IDM Trial Resetter Pro — core engine (IDM 6.42 / 6.43+).

Calibrated against live registry on IDM 6.43.7.2 (v6.43b07 Trial):
  HKCU\\Software\\DownloadManager values: tvfrdt, radxcnt, LastCheckQU, CheckUpdtVM, LstCheck
  HKCU\\Software\\DownloadManager\\ConfigTime (subkey — installation clock)
  HKCU\\Software\\Classes\\WOW6432Node\\CLSID\\{07999AC3-058B-40BF-984F-69EB1E554CA7}
      Model, Therad
  HKEY_USERS\\*_Classes\\WOW6432Node\\CLSID\\{07999AC3-...} and {5ED60779-...}
  HKLM\\SOFTWARE\\WOW6432Node\\Internet Download Manager\\AdvIntDriverEnabled2
"""
from __future__ import annotations

import os
import sys
import re
import json
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

VERSION = "5.0.0"
APP_NAME = "IDM Trial Resetter Pro"
APP_ORG = "IDMTools"

DM_TRIAL_VALUES = [
    "FName", "LName", "Email", "Serial",
    "tvfrdt", "radxcnt", "scansk", "CheckUpdtVM",
    "LastCheck", "LastCheckQU", "LstCheck", "MData",
    "ptrk_scdt", "cDTvBFquXk0", "auto_reset_trial",
]

DM_TRIAL_SUBKEYS = ["ConfigTime"]

IDM_CLSID_GUIDS = [
    "{07999AC3-058B-40BF-984F-69EB1E554CA7}",
    "{7B8E9164-324D-4A2E-A46D-0165FB2000EC}",
    "{6DDF00DB-1234-46EC-8356-27E7B2051192}",
    "{D5B91409-A8CA-4973-9A0B-59F713D25671}",
    "{5ED60779-4DE2-4E07-B862-974CA4FF2E9C}",
]

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
]

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
    trial_markers: List[str] = field(default_factory=list)
    clsid_hits: List[str] = field(default_factory=list)
    details: List[str] = field(default_factory=list)

    def trial_label(self) -> str:
        if self.frozen:
            return "Frozen"
        if self.trial_clean:
            return "Clean trial"
        return "Tracking active"


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
            if not reg_exists(root, full):
                return
            seen.add(key)
            label = f"{hive_label(root)}\\...\\{full.split(chr(92))[-1][:28]}"
            if note:
                label += f" ({note})"
            found.append((root, full, label))
            self.log(f"  · {label}")

        for guid in IDM_CLSID_GUIDS:
            for root, base in CLSID_BASES:
                add(root, f"{base}\\{guid}", "known")

        try:
            for sid in enum_keys(winreg.HKEY_USERS, ""):
                if not sid.endswith("_Classes"):
                    continue
                for sub in (rf"{sid}\CLSID", rf"{sid}\WOW6432Node\CLSID"):
                    for guid in IDM_CLSID_GUIDS:
                        add(winreg.HKEY_USERS, f"{sub}\\{guid}", "HKU")
        except Exception as e:
            self.log(f"  ! HKU known scan: {e}", "warning")

        for root, base in CLSID_BASES:
            if not reg_exists(root, base):
                continue
            for guid in enum_keys(root, base):
                if guid in IDM_CLSID_GUIDS:
                    continue
                full = f"{base}\\{guid}"
                vals = enum_values(root, full)
                if any(m in vals for m in CLSID_MARKERS):
                    add(root, full, "dynamic")

        try:
            for sid in enum_keys(winreg.HKEY_USERS, ""):
                if not sid.endswith("_Classes"):
                    continue
                for sub in (rf"{sid}\CLSID", rf"{sid}\WOW6432Node\CLSID"):
                    if not reg_exists(winreg.HKEY_USERS, sub):
                        continue
                    for guid in enum_keys(winreg.HKEY_USERS, sub):
                        if guid in IDM_CLSID_GUIDS:
                            continue
                        full = f"{sub}\\{guid}"
                        vals = enum_values(winreg.HKEY_USERS, full)
                        if any(m in vals for m in CLSID_MARKERS):
                            add(winreg.HKEY_USERS, full, "HKU-dyn")
        except Exception as e:
            self.log(f"  ! HKU dynamic scan: {e}", "warning")

        return found

    def _force_take_ownership(self, root: int, full: str) -> None:
        if root == winreg.HKEY_USERS:
            ps = f"""
$p = 'Registry::HKEY_USERS\\{full.replace("'", "''")}'
try {{
  $acl = Get-Acl $p
  $admin = New-Object System.Security.Principal.NTAccount('BUILTIN','Administrators')
  $acl.SetOwner($admin)
  Set-Acl -Path $p -AclObject $acl
  $acl = Get-Acl $p
  $rule = New-Object System.Security.AccessControl.RegistryAccessRule(
    'Everyone','FullControl','ContainerInherit,ObjectInherit','None','Allow')
  $acl.SetAccessRule($rule)
  $acl.SetAccessRuleProtection($false,$true)
  Set-Acl -Path $p -AclObject $acl
  'OK'
}} catch {{ $_.Exception.Message }}
"""
            run_powershell(ps, timeout=20)
            return
        if root == winreg.HKEY_CURRENT_USER:
            ps_root = "CurrentUser"
        elif root == winreg.HKEY_LOCAL_MACHINE:
            ps_root = "LocalMachine"
        else:
            return
        path_esc = full.replace("'", "''")
        ps = f"""
$path = '{path_esc}'
$root = [Microsoft.Win32.Registry]::{ps_root}
try {{
  $key = $root.OpenSubKey($path, 'ReadWriteSubTree', 'TakeOwnership')
  if ($key) {{
    $acl = New-Object System.Security.AccessControl.RegistrySecurity
    $admin = [System.Security.Principal.NTAccount]('BUILTIN\\Administrators')
    $acl.SetOwner($admin)
    $key.SetAccessControl($acl); $key.Close()
  }}
  $key = $root.OpenSubKey($path, 'ReadWriteSubTree', 'ChangePermissions')
  if ($key) {{
    $acl = $key.GetAccessControl()
    $acl.SetAccessRuleProtection($false, $true)
    $rule = New-Object System.Security.AccessControl.RegistryAccessRule(
      'Everyone','FullControl','ContainerInherit,ObjectInherit','None','Allow')
    $acl.SetAccessRule($rule)
    $key.SetAccessControl($acl); $key.Close()
  }}
  'OK'
}} catch {{ $_.Exception.Message }}
"""
        run_powershell(ps, timeout=20)

    def reset_trial(self) -> ActionResult:
        t0 = datetime.datetime.now()
        details: List[str] = []
        self.log("═" * 54, "header")
        self.log("  RESET TRIAL  —  full 30-day restoration", "header")
        self.log("═" * 54, "header")
        self.kill_idm()
        steps = 7

        self.progress(1, steps, "Cleaning DownloadManager trial values")
        self.log("\n[1/7] HKCU\\Software\\DownloadManager trial values …")
        dm = r"Software\DownloadManager"
        n = 0
        for val in DM_TRIAL_VALUES:
            ok, msg = delete_value(winreg.HKEY_CURRENT_USER, dm, val)
            if ok:
                n += 1
                self.log(f"  ✓ {msg}", "success")
        self.log(f"  → {n} value(s) removed")
        details.append(f"DM values: {n}")

        self.progress(2, steps, "Removing ConfigTime")
        self.log("\n[2/7] ConfigTime installation clock …")
        ok, msg = delete_key_tree(winreg.HKEY_CURRENT_USER, rf"{dm}\ConfigTime")
        if ok:
            self.log("  ✓ Deleted ConfigTime subkey", "success")
            details.append("ConfigTime removed")
        else:
            self.log(f"  · ConfigTime: {msg}", "info")

        self.progress(3, steps, "Removing CLSID tracking keys")
        self.log("\n[3/7] CLSID tracking keys …")
        targets = self.collect_clsid_targets()
        removed = 0
        denied = 0
        for root, full, label in targets:
            ok, msg = delete_key_tree(root, full)
            if not ok and "DENIED" in msg.upper():
                self._force_take_ownership(root, full)
                ok, msg = delete_key_tree(root, full)
            if ok:
                removed += 1
                self.log(f"  ✓ Removed {label}", "success")
            elif "Not found" not in msg:
                denied += 1
                self.log(f"  ! {label}: {msg}", "warning")
        self.log(f"  → {removed} key(s) removed" + (f", {denied} denied" if denied else ""))
        details.append(f"CLSID removed: {removed}")

        self.progress(4, steps, "HKEY_USERS DownloadManager")
        self.log("\n[4/7] HKEY_USERS DownloadManager values …")
        hku_n = 0
        try:
            for sid in enum_keys(winreg.HKEY_USERS, ""):
                if sid.endswith("_Classes") or sid in ("S-1-5-18", "S-1-5-19", "S-1-5-20"):
                    continue
                user_dm = rf"{sid}\Software\DownloadManager"
                if not reg_exists(winreg.HKEY_USERS, user_dm):
                    continue
                for val in DM_TRIAL_VALUES:
                    ok, _ = delete_value(winreg.HKEY_USERS, user_dm, val)
                    if ok:
                        hku_n += 1
                delete_key_tree(winreg.HKEY_USERS, rf"{user_dm}\ConfigTime")
        except Exception as e:
            self.log(f"  ! HKU DM: {e}", "warning")
        self.log(f"  → {hku_n} user value(s) cleaned")
        details.append(f"HKU DM: {hku_n}")

        self.progress(5, steps, "HKLM cleanup")
        self.log("\n[5/7] HKLM machine keys …")
        hklm_n = 0
        for root, path in HKLM_IDM_PATHS:
            if reg_exists(root, path):
                for val in ("FName", "LName", "Email", "Serial"):
                    ok, _ = delete_value(root, path, val)
                    if ok:
                        hklm_n += 1
                        self.log(f"  ✓ Cleared {hive_label(root)}\\…\\{val}", "success")
        try:
            flag_path = r"Software\WOW6432Node\Internet Download Manager"
            with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, flag_path) as k:
                winreg.SetValueEx(k, "AdvIntDriverEnabled2", 0, winreg.REG_DWORD, 1)
            self.log("  ✓ AdvIntDriverEnabled2 = 1", "success")
        except PermissionError:
            self.log("  ! Could not set AdvIntDriverEnabled2 (need admin)", "warning")
        except OSError as e:
            self.log(f"  ! AdvIntDriverEnabled2: {e}", "warning")
        details.append(f"HKLM cleaned: {hklm_n}")

        self.progress(6, steps, "AppData cache (safe)")
        self.log("\n[6/7] AppData cache (preserving active downloads) …")
        ad = appdata_idm()
        if ad.exists():
            skip_dirs = {"DwnlData", "Scheduler"}
            for child in list(ad.iterdir()):
                if child.name in skip_dirs:
                    self.log(f"  · Preserved {child.name}/")
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
        for val in ("tvfrdt", "radxcnt", "LastCheckQU", "LstCheck"):
            if get_value(winreg.HKEY_CURRENT_USER, dm, val) is not None:
                remaining.append(val)
        if reg_exists(winreg.HKEY_CURRENT_USER, rf"{dm}\ConfigTime"):
            remaining.append("ConfigTime")
        if remaining:
            self.log(f"  ! Still present: {', '.join(remaining)}", "warning")
            details.append(f"leftover: {','.join(remaining)}")
        else:
            self.log("  ✓ Core trial markers cleared", "success")
            details.append("markers clean")

        ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
        self.log("\n" + "═" * 54, "header")
        self.log("  ✓ TRIAL RESET COMPLETE — restart IDM for a fresh 30 days", "success")
        self.log("═" * 54, "header")
        return ActionResult("reset", True, total=removed + n, details=details, duration_ms=ms)

    def freeze_trial(self) -> ActionResult:
        t0 = datetime.datetime.now()
        self.log("═" * 54, "header")
        self.log("  FREEZE TRIAL  —  lock CLSID keys via ACL deny", "header")
        self.log("═" * 54, "header")
        self.kill_idm()

        self.progress(1, 3, "Locating CLSID keys")
        self.log("\n[1/3] Locating CLSID keys …")
        keys = self.collect_clsid_targets()
        if not keys:
            self.log("  ! No CLSID keys. Run Reset first, launch IDM once, then Freeze.", "warning")
            return ActionResult("freeze", False, error="No CLSID keys found")

        self.log(f"\n[2/3] Freezing {len(keys)} key(s) …")
        self.progress(2, 3, "Applying ACL locks")

        blocks = []
        for root, full, label in keys:
            safe = label.replace("'", "")
            if root == winreg.HKEY_USERS:
                blocks.append(self._ps_freeze_hku(full, safe))
                continue
            if root == winreg.HKEY_CURRENT_USER:
                root_expr = "[Microsoft.Win32.Registry]::CurrentUser"
            elif root == winreg.HKEY_LOCAL_MACHINE:
                root_expr = "[Microsoft.Win32.Registry]::LocalMachine"
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
  $acl.SetOwner([System.Security.Principal.NTAccount]('BUILTIN\\Administrators'))
  $key.SetAccessControl($acl); $key.Close()

  $key = $rootKey.OpenSubKey($path, 'ReadWriteSubTree', 'ChangePermissions')
  if ($null -eq $key) {{ Write-Output 'FAILED: {safe} perms'; continue }}
  $acl = $key.GetAccessControl()
  $rule = New-Object System.Security.AccessControl.RegistryAccessRule(
    'Everyone','FullControl','ContainerInherit,ObjectInherit','None','Deny')
  $acl.ResetAccessRule($rule)
  $key.SetAccessControl($acl); $key.Close()

  $key = $rootKey.OpenSubKey($path, 'ReadWriteSubTree', 'TakeOwnership')
  if ($key) {{
    $acl = New-Object System.Security.AccessControl.RegistrySecurity
    $acl.SetOwner((New-Object System.Security.Principal.SecurityIdentifier('S-1-0-0')))
    $key.SetAccessControl($acl); $key.Close()
  }}
  Write-Output 'FROZEN: {safe}'
}} catch {{ Write-Output ("FAILED: {safe} - " + $_.Exception.Message) }}
""")

        _, stdout, stderr = run_powershell("\n".join(blocks), timeout=120)
        frozen = failed = 0
        for line in (stdout or "").splitlines():
            line = line.strip()
            if line.startswith("FROZEN:"):
                frozen += 1
                self.log(f"  ✓ {line[7:].strip()}", "success")
            elif line.startswith("FAILED:"):
                failed += 1
                self.log(f"  ✗ {line}", "error")

        self.progress(3, 3, "Done")
        ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
        if frozen > 0:
            self.log(f"\n  ✓ Frozen {frozen} key(s) — trial clock locked", "success")
            return ActionResult(
                "freeze", True, total=frozen,
                details=[f"Frozen: {frozen}", f"Failed: {failed}"], duration_ms=ms,
            )
        return ActionResult(
            "freeze", False, details=[f"Failed: {failed}"],
            error=(stderr or "No keys frozen — run as Administrator")[:200],
            duration_ms=ms,
        )

    def _ps_freeze_hku(self, full: str, safe: str) -> str:
        path = full.replace("'", "''")
        return f"""
try {{
  $p = 'Registry::HKEY_USERS\\{path}'
  $acl = Get-Acl $p
  $acl.SetOwner([System.Security.Principal.NTAccount]('BUILTIN\\Administrators'))
  Set-Acl -Path $p -AclObject $acl
  $acl = Get-Acl $p
  $rule = New-Object System.Security.AccessControl.RegistryAccessRule(
    'Everyone','FullControl','ContainerInherit,ObjectInherit','None','Deny')
  $acl.ResetAccessRule($rule)
  Set-Acl -Path $p -AclObject $acl
  Write-Output 'FROZEN: {safe}'
}} catch {{ Write-Output ("FAILED: {safe} - " + $_.Exception.Message) }}
"""

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
            if root == winreg.HKEY_USERS:
                path = full.replace("'", "''")
                blocks.append(f"""
try {{
  $p = 'Registry::HKEY_USERS\\{path}'
  $acl = Get-Acl $p -ErrorAction Stop
  $acl.SetOwner([System.Security.Principal.NTAccount]('BUILTIN\\Administrators'))
  $acl.SetAccessRuleProtection($false, $true)
  foreach ($ace in @($acl.GetAccessRules($true,$true,[System.Security.Principal.NTAccount]))) {{
    if ($ace.AccessControlType -eq 'Deny') {{ $acl.RemoveAccessRule($ace) | Out-Null }}
  }}
  $rule = New-Object System.Security.AccessControl.RegistryAccessRule(
    'Everyone','FullControl','ContainerInherit,ObjectInherit','None','Allow')
  $acl.SetAccessRule($rule)
  Set-Acl -Path $p -AclObject $acl
  Write-Output 'UNFROZEN'
}} catch {{ Write-Output ("FAILED: {safe} - " + $_.Exception.Message) }}
""")
                continue
            ps_root = "CurrentUser" if root == winreg.HKEY_CURRENT_USER else "LocalMachine"
            path = full.replace("'", "''")
            blocks.append(f"""
$root = [Microsoft.Win32.Registry]::{ps_root}
$path = '{path}'
try {{
  $key = $root.OpenSubKey($path, 'ReadWriteSubTree', 'TakeOwnership')
  if ($key) {{
    $acl = New-Object System.Security.AccessControl.RegistrySecurity
    $acl.SetOwner([System.Security.Principal.NTAccount]('BUILTIN\\Administrators'))
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
      'Everyone','FullControl','ContainerInherit,ObjectInherit','None','Allow')
    $acl.SetAccessRule($rule)
    $key.SetAccessControl($acl); $key.Close()
    Write-Output 'UNFROZEN'
  }} else {{ Write-Output 'SKIP' }}
}} catch {{ Write-Output ("FAILED: {safe} - " + $_.Exception.Message) }}
""")
        _, stdout, _ = run_powershell("\n".join(blocks) if blocks else "''", timeout=120)
        unfrozen = sum(1 for l in (stdout or "").splitlines() if "UNFROZEN" in l)
        ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
        self.log(f"  ✓ Unfrozen {unfrozen} key(s)", "success" if unfrozen else "info")
        return ActionResult(
            "unfreeze", True, total=unfrozen,
            details=[f"Unfrozen: {unfrozen}"], duration_ms=ms,
        )

    def activate(self, fname: str = "User", lname: str = "", email: str = "") -> ActionResult:
        t0 = datetime.datetime.now()
        self.log("═" * 54, "header")
        self.log("  ACTIVATE  —  reset + identity + freeze", "header")
        self.log("═" * 54, "header")

        self.progress(1, 3, "Resetting")
        self.reset_trial()

        self.progress(2, 3, "Injecting registration")
        self.log("\n[2/3] Injecting registration identity …")
        dm = r"Software\DownloadManager"
        fn = (fname or "User").strip()
        ln = (lname or fn).strip()
        em = (email or f"{fn.lower().replace(' ', '')}@email.local").strip()
        set_value(winreg.HKEY_CURRENT_USER, dm, "FName", fn, winreg.REG_SZ)
        set_value(winreg.HKEY_CURRENT_USER, dm, "LName", ln, winreg.REG_SZ)
        set_value(winreg.HKEY_CURRENT_USER, dm, "Email", em, winreg.REG_SZ)
        set_value(winreg.HKEY_CURRENT_USER, dm, "Serial", "", winreg.REG_SZ)
        self.log(f"  ✓ Identity: {fn} {ln} <{em}>", "success")

        self.log("  · Seeding CLSID keys (brief IDM start) …")
        exe = self._find_exe()
        if exe:
            try:
                subprocess.Popen([exe], creationflags=CREATE_NO_WINDOW)
                time.sleep(3)
            except Exception as e:
                self.log(f"  ! Could not start IDM: {e}", "warning")
            self.kill_idm()

        self.progress(3, 3, "Freezing")
        fr = self.freeze_trial()
        ms = int((datetime.datetime.now() - t0).total_seconds() * 1000)
        self.log("\n  ✓ ACTIVATION PIPELINE COMPLETE", "success")
        return ActionResult(
            "activate", fr.success, total=fr.total,
            details=["Identity injected", f"Frozen: {fr.total}"],
            error=fr.error, duration_ms=ms,
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
        for val in ("tvfrdt", "radxcnt", "LastCheckQU", "LstCheck", "CheckUpdtVM", "scansk", "MData"):
            if get_value(winreg.HKEY_CURRENT_USER, dm, val) is not None:
                markers.append(val)
        if reg_exists(winreg.HKEY_CURRENT_USER, rf"{dm}\ConfigTime"):
            markers.append("ConfigTime")
        st.trial_markers = markers
        st.trial_clean = len(markers) == 0
        if markers:
            st.details.append(f"Markers: {', '.join(markers)}")
        else:
            st.details.append("No trial tracking values")

        hits = []
        for guid in IDM_CLSID_GUIDS:
            for root, base in CLSID_BASES[:2]:
                full = f"{base}\\{guid}"
                if reg_exists(root, full):
                    hits.append(f"{hive_label(root)}:{guid[:9]}…")
        st.clsid_hits = hits
        if hits:
            st.details.append(f"CLSID hits: {len(hits)}")

        freeze_probed = False
        guid0 = IDM_CLSID_GUIDS[0]
        full = rf"Software\Classes\WOW6432Node\CLSID\{guid0}"
        if reg_exists(winreg.HKEY_CURRENT_USER, full):
            freeze_probed = True
            ok, _ = set_value(winreg.HKEY_CURRENT_USER, full, "_idmtr_probe", 1, winreg.REG_DWORD)
            if not ok:
                st.frozen = True
                st.details.append("CLSID ACL frozen (write denied)")
            else:
                delete_value(winreg.HKEY_CURRENT_USER, full, "_idmtr_probe")

        if not freeze_probed:
            full2 = rf"Software\Classes\WOW6432Node\CLSID\{IDM_CLSID_GUIDS[-1]}"
            if reg_exists(winreg.HKEY_CURRENT_USER, full2):
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, full2, 0, winreg.KEY_READ):
                        pass
                except PermissionError:
                    st.frozen = True
                    st.details.append("CLSID access restricted")

        if HOSTS_PATH.exists():
            try:
                if HOSTS_HEADER in HOSTS_PATH.read_text(encoding="utf-8", errors="replace"):
                    st.updates_blocked = True
                    st.details.append("Hosts sinkhole active")
            except Exception:
                pass

        st.auto_reset = self.has_auto_reset()
        if st.auto_reset:
            st.details.append("Auto-reset scheduled task present")

        st.process_running = self.is_idm_running()
        if st.process_running:
            st.details.append("IDM process running")

        return st

    def run(self, action: str, **kwargs) -> ActionResult:
        if not isinstance(action, str) or not action:
            return ActionResult(str(action), False, error=f"Unknown action: {action!r}")

        table: Dict[str, Callable[[], ActionResult]] = {
            "reset": self.reset_trial,
            "freeze": self.freeze_trial,
            "unfreeze": self.unfreeze_trial,
            "activate": lambda: self.activate(
                kwargs.get("fname", "User"),
                kwargs.get("lname", ""),
                kwargs.get("email", ""),
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
