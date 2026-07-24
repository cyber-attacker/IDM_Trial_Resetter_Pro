# IDM Trial Resetter Pro

![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![UI](https://img.shields.io/badge/UI-PySide6-41CD52?logo=qt&logoColor=white)
![Version](https://img.shields.io/badge/version-5.0.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Professional Windows desktop tool to **inspect, reset, freeze, and manage the Internet Download Manager (IDM) trial state**. Dark Fusion UI, live registry calibration for IDM **6.42 / 6.43+**, one-file admin EXE build, backups, and optional trial auto-reset via Task Scheduler.

> **For authorized / personal use only.** Directly modifies Windows registry, ACL locks, hosts file, and scheduled tasks. You are responsible for compliance with local law and IDM’s EULA.

---

## Features

| Feature | Description |
|--------|-------------|
| **Live status dashboard** | Detects install path, version, trial vs registered, trial markers, CLSID hits, freeze / hosts / auto-reset state |
| **Trial reset** | Clears DownloadManager trial values, `ConfigTime`, CLSID markers, related HKU / HKLM keys |
| **Freeze / Unfreeze** | ACL-locks or restores IDM tracking CLSID keys so the trial clock cannot advance |
| **Activate pipeline** | Reset → inject registration identity → seed CLSID → freeze |
| **Block / Unblock updates** | Sinkholes IDM update domains in the system `hosts` file + DNS flush |
| **Backup & restore** | Registry + AppData snapshots under `%AppData%\IDMTools\IDMTrialResetterPro` |
| **Auto-reset** | Optional scheduled task for silent headless resets (`--auto-reset`) |
| **Professional UI** | Dashboard, Operations, Backup, History, Settings, Console, system tray |
| **Admin EXE** | Single-file PyInstaller build with embedded `requireAdministrator` UAC manifest |

Calibrated against live IDM **6.43.7.2** (`v6.43b07 Trial`), including:

- `HKCU\Software\DownloadManager` — `tvfrdt`, `radxcnt`, `LastCheckQU`, `LstCheck`, `CheckUpdtVM`, `ConfigTime`, …
- `HKCU\Software\Classes\WOW6432Node\CLSID\{07999AC3-058B-40BF-984F-69EB1E554CA7}` (`Model`, `Therad`, …)
- Additional known CLSID GUIDs and HKLM IDM paths

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

### Option A — one-file EXE (recommended)

1. Build (once):

   ```bat
   build_exe.bat
   ```

2. Run either:

   - `IDM_Trial_Resetter_Pro.exe` (project root, after build copies it), or  
   - `dist\IDM_Trial_Resetter_Pro.exe`, or  
   - `Launch_IDM_Resetter.bat` (prefers the EXE)

3. Approve the **UAC** prompt. The EXE requests Administrator by design.

### Option B — from source

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

## How it works (high level)

1. **Status** reads HKCU DownloadManager, file version of `IDMan.exe`, CLSID trees, hosts block markers, freeze ACLs, and optional scheduled task.
2. **Reset** stops IDM processes, deletes/clears trial REG values and `ConfigTime`, scrubs known CLSID markers across HKCU / HKLM / HKU, and related keys — without wiping your download list / InstallDefaults when those are separate.
3. **Freeze** applies restrictive ACLs on tracking CLSID keys so IDM cannot rewrite trial timestamps.
4. **Block updates** appends a managed section to `C:\Windows\System32\drivers\etc\hosts` and flushes DNS.
5. **Backup/restore** snapshots registry exports and relevant AppData folders for rollback.

Engine API surface (`IDMEngine`):

```text
check_status · reset_trial · freeze_trial · unfreeze_trial · activate
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
| Hosts block fails | Elevation required; ensure `hosts` is not read-only |
| AV quarantines EXE | Add exclusion or run from source |
| Old Python PATH conflict | Use `py -3 app.py` or full path to Python 3.10+ |

---

## Changelog

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
