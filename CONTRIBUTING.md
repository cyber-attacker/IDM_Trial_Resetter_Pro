# Contributing

Thanks for helping improve **IDM Trial Resetter Pro**.

## Ground rules

- Target **Windows 10/11** only.
- Prefer fixes calibrated against **live IDM 6.42 / 6.43+** registry layout over dead public scripts.
- Do not commit built `.exe` files, `__pycache__`, `build/`, or `dist/`.
- Keep UI action wiring free of Qt `clicked(bool)` leakage (`functools.partial` / `*_args` guards).
- No drive-by feature sprawl — small, tested PRs.

## Dev setup

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Build EXE:

```bat
build_exe.bat
```

## Checklist before PR

1. `python -c "import ast; ..."` syntax OK on `app.py` / `engine.py`
2. Engine `check_status()` works on a machine with IDM installed
3. Each Operations card fires the correct string action (`reset`, `freeze`, …)
4. Close window without `QThread: Destroyed while thread is still running`
5. README updated if behavior or keys change

## Reporting issues

Include:

- Windows build (`winver`)
- IDM version (`idmvers` / file version)
- Admin or not
- Console log excerpt
- Whether you used source or EXE
