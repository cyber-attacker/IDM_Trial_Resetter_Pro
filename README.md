# IDM Trial Resetter Pro

![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![UI](https://img.shields.io/badge/UI-PySide6-41CD52?logo=qt&logoColor=white)
![Version](https://img.shields.io/badge/version-5.3.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Professional Windows desktop tool to **inspect, reset, freeze, and manage the Internet Download Manager (IDM) trial state**. Dark Fusion UI, live registry calibration for IDM **6.42 / 6.43+**, one-file admin EXE build, backups, and optional trial auto-reset via Task Scheduler.

> **For authorized / personal use only.** Directly modifies Windows registry, ACL locks, hosts file, and scheduled tasks. You are responsible for compliance with local law and IDM’s EULA.

---

## Features

| Feature | Description |
|--------|-------------|
| **Smart advisor (5.3)** | Dashboard health banner analyzes your exact state and tells you the ONE action to run — with a **Fix now** button |
| **Live status dashboard** | Detects install path, version, trial vs registered, trial markers, CLSID hits, freeze / hosts / auto-reset state |
| **Trial reset** | Clears DownloadManager trial values, `ConfigTime` / `SpecialData`, CLSID markers (incl. ACL-locked keys), related HKU / HKLM keys |
| **Freeze / Unfreeze** | Wipes trial state, seeds missing CLSID keys and ACL-locks **all** tracking keys (incl. IDM's rotating GUIDs) so the trial clock can never be persisted — the fix for the recurring "trial period is over" nag |
| **Activate pipeline** | Reset → seed → lock → register with an IAS-format serial → sinkhole update/activation servers → brief IDM start → re-lock. Verified: IDM switches itself to `Full` mode and stops nagging |
| **Deactivate (5.3)** | One-click undo of Activate: removes the serial, unfreezes trackers, removes the hosts block, leaves a clean day-1 trial |
| **Block / Unblock updates** | Tamper-healing hosts sinkhole (IPv4 + IPv6, ACL-hardened) **plus a Windows Firewall backstop** that makes the Tonec server IPs unreachable system-wide — IDM cannot bypass it even though it comments out hosts entries at every start |
| **Open IDM + diagnostics report (5.3)** | Launch IDMan.exe from the dashboard; export a shareable status report |
| **Backup & restore** | Registry + AppData snapshots under `%AppData%\IDMTools\IDMTrialResetterPro` |
| **Auto-reset** | Optional scheduled task for silent headless resets (`--auto-reset`) |
| **Professional UI** | Dashboard, Operations, Backup, History, Settings, Console, system tray |
| **Admin EXE** | Single-file PyInstaller build with embedded `requireAdministrator` UAC manifest |

Calibrated against a live, **expired** IDM **6.43.10** (`v6.43b10 Trial`) install — every key below was verified on disk:

**Trial clock / counters — `HKCU\Software\DownloadManager`:**

| Item | Role |
|------|------|
| `tvfrdt`, `radxcnt` (29 = day 29 of 30), `scansk`, `CheckUpdtVM`, `LastCheckQU`, `LstCheck`, `LastCheck`, `MData`, `ptrk_scdt`, `cDTvBFquXk0` | trial clock, counters, update-check stamps, machine fingerprint |
| `bRmGUCfEx`, `vCOUFP` | **new obfuscated markers added in 6.43.x** |
| `FName`, `LName`, `Email`, `Serial` | registration identity |
| `ConfigTime` subkey | installation clock (`(Default)` = unix timestamp) |
| `SpecialData` subkey | **new 6.43.x state blobs** (`lgfgf.1/.2`, `lgasa.1/.2`) |

**CLSID tracking copies — `HKCU\Software\Classes\[WOW6432Node\]CLSID\{GUID}` (+ `HKU\<SID>_Classes` mirrors):**

- `{07999AC3-058B-40BF-984F-69EB1E554CA7}` — `Model`, `Therad`, `MData`
- `{5ED60779-4DE2-4E07-B862-974CA4FF2E9C}` — frequently carries a **deny-Everyone ACL** (freeze artifact / anti-tamper). A plain `KEY_READ` existence check reports it *absent*, so naive resetters silently skip it and IDM restores the trial from this hidden copy. The resetter enables `SeTakeOwnershipPrivilege`, takes ownership and replaces the whole DACL before deleting it.
- `{7B8E9164-…}`, `{6DDF00DB-…}`, `{D5B91409-…}` — legacy GUIDs, kept for older builds

**Other:**

- `HKLM\SOFTWARE\WOW6432Node\Internet Download Manager\AdvIntDriverEnabled2`
- `%APPDATA%\IDM\idmupdt.exe` — downloaded self-updater payload (removed during reset)
- **ConfigTime watchdog** — IDM 6.43.x's `IDMShellExt64.dll`/`IDMNetMon64.dll` (loaded inside `explorer.exe` and other shell hosts) re-creates `ConfigTime` from a cached copy ~1s after deletion. Verified harmless: with a planted stale `ConfigTime`, IDM still starts a fresh trial (`radxcnt = 1`) and rewrites the clock itself. The resetter detects the restore and re-anchors `ConfigTime` to *now* — the exact state of a fresh install
- Dynamic CLSID discovery heuristics (marker values, numeric/encoded defaults, empty seed keys) so future GUID rotations are still caught

---

## Which action should I run? (latest IDM 6.4x)

**Pick ONE action — never chain them.** Activate already includes a full reset; Freeze already wipes state.

| Your situation | Run this | Result |
|---|---|---|
| Trial is **over / expired** | **Activate** | One click: reset → register with serial → lock every tracker → block phone-home servers. IDM shows `Full`, no expiry, no nag |
| Don't want to register, just never expire | **Freeze** | Wipes state and ACL-locks every tracker key. Trial stays day-1 forever |
| Want a plain, honest 30-day trial | **Reset Trial** | Deep-clean only — no serial, no locks. Trial counts down again and expires in ~30 days |
| Want to undo Activate | **Deactivate** | Removes serial + locks + hosts block → clean day-1 trial |
| Registered but nag returned | **Activate** again (Block Updates now also installs a firewall backstop that IDM cannot tamper with) |
| Fake-serial nag ("registered with a fake Serial Number") | IDM reached its validation server and flagged the serial. Re-run **Activate** — the firewall rule keeps `registeridm.com` / Tonec servers unreachable, so the verdict cannot come back |

The dashboard health banner makes this decision for you and shows a **Fix now** button for the recommended action.

---

## Screenshots

Run the app and open **Dashboard** for live IDM status cards and **Operations** for reset / freeze / activate actions. Console logs every registry and hosts step in real time.

---

## Requirements

- **Windows 10 / 11** (x64)
- **Internet Download Manager** installed (6.42 / 6.43+)
- **Administrator** rights for full registry / hosts / scheduler access
- **Python 3.10+** if running from source (3.14 tested)

---

## Quick start

### Option A — download EXE from GitHub Releases (easiest)

Do **not** commit the `.exe` into git (it is ~50 MB and gitignored). Host it on **Releases** instead:

1. Open your repo → **Releases** → latest tag (e.g. `v5.0.0`)
2. Download **`IDM_Trial_Resetter_Pro.exe`**
3. Double-click → approve **UAC** → use the app

Optional: verify `SHA256.txt` from the same release.

### Option B — build EXE locally

```bat
build_exe.bat
```

Then run:

- `dist\IDM_Trial_Resetter_Pro.exe`, or  
- `IDM_Trial_Resetter_Pro.exe` (copy at project root), or  
- `Launch_IDM_Resetter.bat`

### Option C — from source

```bat
pip install -r requirements.txt
Launch_IDM_Resetter.bat
```

Or elevated Python:

```bat
python app.py
```

Headless scheduled reset:

```bat
python app.py --auto-reset
```

---

## Project layout

```text
IDM_Trial_Resetter_Pro/
├── app.py                      # PySide6 UI (dashboard, ops, settings, tray)
├── engine.py                   # Registry / hosts / backup / freeze engine
├── requirements.txt            # PySide6
├── admin.manifest              # UAC requireAdministrator + DPI
├── IDM_Trial_Resetter_Pro.spec # PyInstaller one-file spec
├── build_exe.bat               # Clean rebuild of the EXE
├── Launch_IDM_Resetter.bat     # Prefer EXE; else elevate + python app.py
├── LICENSE
└── README.md
```

Runtime data (not in git):

```text
%AppData%\IDMTools\IDMTrialResetterPro\
  history.json
  backups\
  app.lock
```

---

## Build the EXE yourself

```bat
pip install -r requirements.txt pyinstaller
build_exe.bat
```

Outputs:

| Path | Notes |
|------|--------|
| `dist\IDM_Trial_Resetter_Pro.exe` | One-file, windowed, ~48 MB |
| Embedded manifest | `requestedExecutionLevel = requireAdministrator` |

Spec highlights (`IDM_Trial_Resetter_Pro.spec`):

- `console=False` — no black console window  
- `uac_admin=True` + custom `admin.manifest`  
- Hidden import: `engine`  
- Excludes bulk unused packages (tkinter, numpy, …)

---

## Publish the EXE with GitHub Releases

**Best practice:** keep source in git; attach the EXE only to a **Release**. Users download from the Assets list — no bloated history.

### 1) Push the repo once

```bat
cd C:\Users\GLH\Desktop\IDM_Trial_Resetter_Pro

:: create empty repo on github.com (no README), then:
git remote add origin https://github.com/YOUR_USER/IDM-Trial-Resetter-Pro.git
git push -u origin main
```

Or with GitHub CLI:

```bat
winget install GitHub.cli
gh auth login
gh repo create IDM-Trial-Resetter-Pro --public --source=. --remote=origin --push
```

### 2A) Automatic release (recommended)

This repo includes [`.github/workflows/build-release.yml`](.github/workflows/build-release.yml).

**Tag a version → Actions builds the EXE → attaches it to the Release:**

```bat
git tag v5.0.0
git push origin v5.0.0
```

Then open: `https://github.com/YOUR_USER/IDM-Trial-Resetter-Pro/releases`

Assets will include:

- `IDM_Trial_Resetter_Pro.exe`
- `IDM_Trial_Resetter_Pro-windows-x64.exe`
- `SHA256.txt`

**Manual run without a tag:** GitHub → **Actions** → **Build & Release EXE** → **Run workflow**.

### 2B) Upload your already-built local EXE

If GitHub CLI is installed and `origin` is set:

```bat
scripts\make_release.bat v5.0.0
```

That script builds if needed, creates/pushes tag `v5.0.0`, and uploads `dist\*.exe` + `SHA256.txt`.

### 2C) Web UI (no CLI)

1. Build locally: `build_exe.bat`
2. GitHub repo → **Releases** → **Draft a new release**
3. Tag: `v5.0.0` (create on publish)
4. Title: `IDM Trial Resetter Pro v5.0.0`
5. Drag-drop `dist\IDM_Trial_Resetter_Pro.exe` (and optional `SHA256.txt`)
6. **Publish release**

Visitors use **Releases** → **Assets** → download EXE. Source stays in the Code tab.

---

## How it works (high level)

1. **Status** reads HKCU DownloadManager, file version of `IDMan.exe`, CLSID trees, hosts block markers, freeze ACLs, and optional scheduled task.
2. **Reset** stops IDM processes, deletes/clears trial REG values and `ConfigTime`, scrubs known CLSID markers across HKCU / HKLM / HKU, and related keys — without wiping your download list / InstallDefaults when those are separate.
3. **Freeze** wipes the trial state, seeds missing CLSID tracker keys and applies deny-ACLs on all of them so IDM cannot persist trial timestamps.
4. **Block updates** appends a managed section to `C:\Windows\System32\drivers\etc\hosts` and flushes DNS.
5. **Backup/restore** snapshots registry exports and relevant AppData folders for rollback.

Engine API surface (`IDMEngine`):

```text
check_status · reset_trial · freeze_trial · unfreeze_trial · activate · deactivate
launch_idm · export_diagnostics · recommend
block_updates · unblock_updates · backup · restore
setup_auto_reset · remove_auto_reset · kill_idm
```

---

## UI notes / fixes

- **Button wiring** uses `functools.partial` so Qt’s `clicked(bool)` never becomes `Unknown action: False`.
- Workers are `wait()`’d on exit to avoid `QThread: Destroyed while thread is still running`.
- File versions like `6, 43, 7, 2` normalize to `6.43.7.2`.

---

## Security & disclaimer

- This tool **requires elevation** and can permanently change system configuration.
- Only use on machines you own or are explicitly authorized to administer.
- Resetting or faking commercial software licenses may violate the vendor EULA; prefer purchasing IDM if you use it long-term.
- No warranty. Use at your own risk. Antivirus may flag packed one-file EXEs (PyInstaller) — build from source if needed.

---

## Development

```bat
git clone https://github.com/<you>/IDM-Trial-Resetter-Pro.git
cd IDM-Trial-Resetter-Pro
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Syntax check:

```bat
python -c "import ast; ast.parse(open('engine.py',encoding='utf-8').read()); ast.parse(open('app.py',encoding='utf-8').read()); print('OK')"
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Actions fail with Access denied | Run EXE / bat as Administrator |
| Status shows not installed | Confirm `IDMan.exe` under Program Files (x86) or (x64) |
| Freeze does nothing | Run reset/activate once so CLSID keys exist, then freeze |
| Fake-serial nag after activation | Run Activate again — the firewall backstop stops IDM from validating the serial online |
| IDM keeps editing the hosts file | Expected (it runs elevated); the firewall rule covers it — see Dashboard status |
| Hosts block fails | Elevation required; ensure `hosts` is not read-only |
| AV quarantines EXE | Add exclusion or run from source |
| Old Python PATH conflict | Use `py -3 app.py` or full path to Python 3.10+ |

---

## Changelog

### 5.3.1

- **Fixed the fake-serial nag** ("IDM has been registered with a fake Serial Number…"). Live root-cause: an elevated IDM component **comments out the hosts block entries** (`#127.0.0.1 registeridm.com`, …) at every start to reach its validation server, which then flags the serial. Verified by `LastCheckQU` updating the moment a check succeeds
- **Windows Firewall phone-home backstop**: Block Updates now also adds a system-wide outbound block on the resolved Tonec / IDM server IPs (dedicated servers — near-zero collateral). No userland process can bypass it, so serial revalidation and silent self-updates are impossible regardless of hosts tampering. The firewall rule is the authoritative protection signal in the status check
- Hosts sinkhole upgraded: IPv6 (`::1`) pins, tamper-healing rewrite on every run, and a hardened protected DACL (SYSTEM/Admins write, everyone else read-only)
- Status now reports hosts tampering honestly ("harmless while the firewall backstop is active") instead of crying wolf
- Unblock Updates removes both the firewall rule and the ACL hardening

### 5.3.0

- **Smart advisor**: `recommend()` decision table + dashboard health banner (● green/yellow/red) that names the exact action to run and offers a one-click **Fix now** button — expired trial → Activate, counting trial → Freeze, registered+unlocked → Freeze, registered+open net → Block Updates, fully protected → "nothing to do"
- Status pills on the dashboard: Registered · Trackers locked · Updates blocked · Trial days left (from `radxcnt`, EXPIRED state in red)
- **Deactivate** action — inverse of Activate: unfreeze → remove hosts block → full reset (drops FName/LName/Email/Serial) → verified unregistered clean trial
- **Open IDM** quick action (launches `IDMan.exe`, no elevation required) and **diagnostics report** export (shareable status/marker/tracker summary)
- Engine: `IDMStatus.days_left` / `expired` computed from `radxcnt`; action cards rewritten to answer "Reset vs Freeze vs Activate" inline
- Non-admin users can now use Open IDM / diagnostics without a UAC prompt

### 5.2.0

- **Fixed the recurring "IDM has not been registered for 30 days / Trial period is over" nag** — root cause: the trial clock is re-derived from the CLSID tracking copies, so a freeze that leaves any tracking key writable fails (observed live: a previous freeze left `{07999AC3-…}` absent, IDM rebuilt the clock inside it and expired anyway)
- **Freeze** now follows the proven IAS flow: wipe DownloadManager state first, **seed missing tracker keys** (`{07999AC3-…}` + `{5ED60779-…}`), then lock every tracking key found — including IDM 6.43's *rotating* GUIDs caught by the dynamic scan
- **Activate** rebuilt IAS-style: lock → register with a generated `XXXXX-XXXXX-XXXXX-XXXXX` serial (random identity defaults) → sinkhole update/activation domains → brief IDM seed → re-lock. Verified live: IDM 6.43b12 accepted the serial and switched `idmvers` from `Trial` to `Full`
- Hosts blocking (16 domains) prevents the online serial revalidation that triggers the fake-serial nag and the update checks that re-flag machines
- HKLM `Internet Download Manager` key fully recreated clean on reset (IAS parity)
- Current-user `HKU\<SID>_Classes` mirrors are recognized as the same physical key as `HKCU\Software\Classes` (IAS 'HKCUsync') — no more duplicate targets / false lock failures
- Status dashboard: nag-risk assessment, serial display, `radxcnt` day counter, locked-key detection

### 5.1.0

- **Fixed the core reset bug on latest IDM**: CLSID keys locked with deny-Everyone ACLs (e.g. `{5ED60779-…}`) were invisible to the old existence check and silently skipped — the resetter now detects them via a tri-state probe (`present` / `locked` / `absent`), enables `SeTakeOwnershipPrivilege` / `SeBackupPrivilege` / `SeRestorePrivilege`, takes ownership and **replaces the whole DACL** (dropping every deny ACE) before deleting
- Added IDM 6.43.x trial markers found live on an expired 6.43.10 install: `bRmGUCfEx`, `vCOUFP`, `SpecialData` subkey (`lgfgf.1/.2`, `lgasa.1/.2` obfuscated blobs)
- Reset now removes `%APPDATA%\IDM\idmupdt.exe` (downloaded self-updater payload)
- Reset verification now includes CLSID targets and reports honest success/failure (no more "COMPLETE" while a locked key survived)
- Dynamic CLSID discovery heuristics (numeric/encoded default values, empty seed keys, `\Version` pattern, locked keys) with real-COM-class exclusion — survives future GUID rotation
- Kill list extended with `idmBroker.exe` / `idmupdt.exe`; site Grabber projects preserved during AppData cleanup
- `check_status` reports the `radxcnt` day counter (e.g. `radxcnt=29 (EXPIRED)`) and flags ACL-locked CLSID keys
- Locale-safe ACL operations via well-known SIDs (`S-1-5-32-544`, `S-1-1-0`) instead of localized `BUILTIN\Administrators` / `Everyone` names

### 5.0.0

- Modular engine calibrated to IDM 6.43.7.2 live registry layout  
- Professional PySide6 multi-page UI + tray  
- Fix `Unknown action: False` (checked-signal leak)  
- QThread clean shutdown + version normalization  
- One-file admin EXE (`requireAdministrator` manifest)  
- Backup / freeze / hosts / auto-reset pipeline  

---

## License

MIT — see [LICENSE](LICENSE).

Internet Download Manager and IDM are trademarks of Tonec Inc. This project is **not** affiliated with or endorsed by Tonec Inc.
