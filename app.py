#!/usr/bin/env python3
"""
IDM Trial Resetter Pro — professional desktop UI
================================================
PySide6 frontend. Button handlers use functools.partial so QPushButton.clicked
never injects its checked=False bool into action names.

Usage:
    python app.py
    python app.py --auto-reset   # silent headless reset (Task Scheduler)

Requires: pip install PySide6
Run as Administrator for full registry / hosts access.
"""
from __future__ import annotations

import os
import sys
import json
import datetime
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if os.name != "nt":
    print("This application requires Microsoft Windows.")
    sys.exit(1)

from PySide6.QtCore import (
    Qt, QThread, Signal, QTimer, QSettings, QSize,
)
from PySide6.QtGui import (
    QFont, QColor, QTextCharFormat, QTextCursor, QAction, QKeySequence,
    QCloseEvent,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QStatusBar, QFrame, QGridLayout,
    QMessageBox, QFileDialog, QLineEdit, QCheckBox, QSpinBox,
    QStackedWidget, QListWidget, QListWidgetItem, QProgressBar,
    QDialog, QDialogButtonBox, QFormLayout, QSystemTrayIcon, QMenu,
    QAbstractItemView, QStyle,
)

from engine import (
    APP_NAME, APP_ORG, VERSION, IDMEngine, ActionResult, IDMStatus,
    is_admin, elevate_and_exit, app_store_dir,
)


# ── Theme ───────────────────────────────────────────────────────────────────
class T:
    BG = "#0b0e14"
    BG2 = "#12171f"
    BG3 = "#1a2130"
    BG4 = "#222b3d"
    LINE = "#2a3448"
    TEXT = "#e8eef7"
    MUTED = "#8b97ab"
    DIM = "#5a6578"
    ACCENT = "#3d8bfd"
    ACCENT2 = "#6ea8fe"
    GREEN = "#3dd68c"
    YELLOW = "#f0b429"
    RED = "#f07178"
    ORANGE = "#ff9e64"
    PURPLE = "#c792ea"


STYLESHEET = f"""
* {{
    font-family: "Segoe UI", "Inter", "SF Pro Text", sans-serif;
    outline: none;
}}
QMainWindow, QDialog {{
    background: {T.BG};
    color: {T.TEXT};
}}
QWidget {{
    background: transparent;
    color: {T.TEXT};
}}
QLabel {{ background: transparent; }}
QScrollArea {{ border: none; background: transparent; }}

QScrollBar:vertical {{
    background: {T.BG};
    width: 10px; margin: 0; border: none;
}}
QScrollBar::handle:vertical {{
    background: {T.LINE}; border-radius: 5px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: {T.DIM}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    height: 0; background: none;
}}

QLineEdit, QSpinBox {{
    background: {T.BG};
    color: {T.TEXT};
    border: 1px solid {T.LINE};
    border-radius: 8px;
    padding: 9px 12px;
    font-size: 13px;
    selection-background-color: {T.ACCENT};
}}
QLineEdit:focus, QSpinBox:focus {{ border: 1px solid {T.ACCENT}; }}

QCheckBox {{
    spacing: 8px; color: {T.TEXT}; font-size: 13px;
}}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 4px;
    border: 1px solid {T.LINE}; background: {T.BG};
}}
QCheckBox::indicator:checked {{
    background: {T.ACCENT}; border-color: {T.ACCENT};
}}

QTextEdit {{
    background: {T.BG};
    color: {T.TEXT};
    border: 1px solid {T.LINE};
    border-radius: 10px;
    padding: 12px;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 12px;
    selection-background-color: {T.ACCENT};
}}

QProgressBar {{
    background: {T.BG};
    border: 1px solid {T.LINE};
    border-radius: 6px;
    text-align: center;
    color: {T.TEXT};
    height: 14px;
    font-size: 10px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {T.ACCENT}, stop:1 {T.PURPLE});
    border-radius: 5px;
}}

QStatusBar {{
    background: {T.BG2};
    color: {T.MUTED};
    border-top: 1px solid {T.LINE};
    font-size: 12px;
    padding: 3px 10px;
}}
QStatusBar::item {{ border: none; }}

QToolTip {{
    background: {T.BG3};
    color: {T.TEXT};
    border: 1px solid {T.LINE};
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 12px;
}}

QMenu {{
    background: {T.BG2};
    color: {T.TEXT};
    border: 1px solid {T.LINE};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 28px 8px 16px;
    border-radius: 6px;
}}
QMenu::item:selected {{ background: {T.BG4}; }}
QMenu::separator {{
    height: 1px; background: {T.LINE}; margin: 4px 8px;
}}

QListWidget {{
    background: {T.BG2};
    border: 1px solid {T.LINE};
    border-radius: 10px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    padding: 10px 12px;
    border-radius: 6px;
    color: {T.MUTED};
}}
QListWidget::item:selected {{ background: {T.BG4}; color: {T.TEXT}; }}
QListWidget::item:hover {{ background: {T.BG3}; }}

QPushButton {{
    background: {T.BG3};
    color: {T.TEXT};
    border: 1px solid {T.LINE};
    border-radius: 8px;
    padding: 9px 16px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: {T.BG4};
    border-color: {T.DIM};
}}
QPushButton:pressed {{ background: {T.BG2}; }}
QPushButton:disabled {{
    color: {T.DIM};
    background: {T.BG2};
    border-color: {T.LINE};
}}

QPushButton[role="primary"] {{
    background: {T.ACCENT};
    color: #ffffff;
    border: none;
}}
QPushButton[role="primary"]:hover {{ background: {T.ACCENT2}; }}
QPushButton[role="primary"]:disabled {{
    background: {T.BG4}; color: {T.DIM};
}}

QPushButton[role="success"] {{
    background: {T.GREEN};
    color: #0b0e14;
    border: none;
}}
QPushButton[role="success"]:hover {{ background: #56e6a0; }}

QPushButton[role="danger"] {{
    background: {T.RED};
    color: #ffffff;
    border: none;
}}
QPushButton[role="danger"]:hover {{ background: #ff8a90; }}

QPushButton[role="ghost"] {{
    background: transparent;
    border: 1px solid {T.LINE};
    color: {T.MUTED};
}}
QPushButton[role="ghost"]:hover {{
    color: {T.TEXT};
    border-color: {T.DIM};
    background: {T.BG3};
}}

QPushButton[role="nav"] {{
    background: transparent;
    border: none;
    border-radius: 10px;
    text-align: left;
    padding: 12px 16px;
    color: {T.MUTED};
    font-weight: 500;
}}
QPushButton[role="nav"]:hover {{
    background: {T.BG3};
    color: {T.TEXT};
}}
QPushButton[role="nav"][active="true"] {{
    background: {T.BG3};
    color: {T.TEXT};
    border-left: 3px solid {T.ACCENT};
    padding-left: 13px;
}}

QFrame[card="true"] {{
    background: {T.BG2};
    border: 1px solid {T.LINE};
    border-radius: 14px;
}}
"""


def set_role(btn: QPushButton, role: str) -> None:
    btn.setProperty("role", role)
    btn.style().unpolish(btn)
    btn.style().polish(btn)
    btn.update()


def polish_active(btn: QPushButton, active: bool) -> None:
    btn.setProperty("active", "true" if active else "false")
    btn.style().unpolish(btn)
    btn.style().polish(btn)
    btn.update()


# ── Workers ─────────────────────────────────────────────────────────────────
class EngineWorker(QThread):
    finished_ok = Signal(object)
    log_msg = Signal(str, str)
    progress = Signal(int, int, str)
    status = Signal(str)

    def __init__(self, action: str, kwargs: Optional[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self.action = action
        self.kwargs = kwargs or {}

    def run(self) -> None:
        engine = IDMEngine(
            log_cb=lambda m, l="info": self.log_msg.emit(m, l),
            progress_cb=lambda c, t, s="": self.progress.emit(c, t, s),
            status_cb=lambda m: self.status.emit(m),
        )
        result = engine.run(self.action, **self.kwargs)
        self.finished_ok.emit(result)


class StatusWorker(QThread):
    done = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self) -> None:
        try:
            self.done.emit(IDMEngine().check_status())
        except Exception:
            self.done.emit(IDMStatus())


# ── Widgets ─────────────────────────────────────────────────────────────────
class StatCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setProperty("card", "true")
        self.setMinimumHeight(100)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(6)

        self.title = QLabel(title.upper())
        self.title.setStyleSheet(
            f"color:{T.MUTED};font-size:10px;font-weight:700;letter-spacing:1.1px;"
        )
        lay.addWidget(self.title)

        self.value = QLabel("—")
        self.value.setStyleSheet(f"color:{T.TEXT};font-size:20px;font-weight:700;")
        lay.addWidget(self.value)

        self.sub = QLabel("")
        self.sub.setStyleSheet(f"color:{T.DIM};font-size:11px;")
        self.sub.setWordWrap(True)
        lay.addWidget(self.sub)
        lay.addStretch()

    def set_state(self, text: str, color: str = T.TEXT, sub: str = "") -> None:
        self.value.setText(text)
        self.value.setStyleSheet(
            f"color:{color};font-size:20px;font-weight:700;background:transparent;"
        )
        self.sub.setText(sub)


class ActionCard(QFrame):
    """Clickable operation card. Emits action key only (never bool)."""
    run_requested = Signal(str)

    def __init__(self, key: str, title: str, desc: str, accent: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setProperty("card", "true")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(120)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(8)

        top = QHBoxLayout()
        t = QLabel(title)
        t.setStyleSheet(f"color:{accent};font-size:15px;font-weight:700;")
        top.addWidget(t)
        top.addStretch()

        self.btn = QPushButton("Run")
        self.btn.setFixedSize(64, 28)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setStyleSheet(
            f"QPushButton{{background:{accent};color:#0b0e14;border:none;"
            f"border-radius:7px;font-size:11px;font-weight:700;}}"
            f"QPushButton:hover{{opacity:0.92;}}"
            f"QPushButton:disabled{{background:{T.LINE};color:{T.DIM};}}"
        )
        # CRITICAL: partial captures key — never bind clicked bool
        self.btn.clicked.connect(partial(self._emit_run))
        top.addWidget(self.btn)
        lay.addLayout(top)

        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet(f"color:{T.MUTED};font-size:12px;line-height:1.35;")
        lay.addWidget(d)
        lay.addStretch()

    def _emit_run(self, *_args) -> None:
        self.run_requested.emit(self.key)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.run_requested.emit(self.key)
        super().mouseReleaseEvent(event)

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self.btn.setEnabled(enabled)


class ActivateDialog(QDialog):
    def __init__(self, fname: str, lname: str, email: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Activate — Registration Profile")
        self.setMinimumWidth(440)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        head = QLabel("Registration profile")
        head.setStyleSheet("font-size:17px;font-weight:700;")
        lay.addWidget(head)
        sub = QLabel("Written to IDM registry before freeze.")
        sub.setStyleSheet(f"color:{T.MUTED};font-size:12px;")
        lay.addWidget(sub)

        form = QFormLayout()
        form.setSpacing(10)
        self.fname = QLineEdit(fname or "User")
        self.lname = QLineEdit(lname or "")
        self.email = QLineEdit(email or "user@email.local")
        form.addRow("First name", self.fname)
        form.addRow("Last name", self.lname)
        form.addRow("Email", self.email)
        lay.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = btns.button(QDialogButtonBox.StandardButton.Ok)
        if ok:
            set_role(ok, "primary")
            ok.setText("Activate")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def values(self) -> Tuple[str, str, str]:
        return (
            self.fname.text().strip(),
            self.lname.text().strip(),
            self.email.text().strip(),
        )


class SchedulerDialog(QDialog):
    def __init__(self, days: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Auto-Reset Scheduler")
        self.setMinimumWidth(420)
        self._action: Optional[str] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)
        lay.addWidget(QLabel("Silent trial reset via Windows Task Scheduler."))

        row = QHBoxLayout()
        row.addWidget(QLabel("Interval"))
        self.spin = QSpinBox()
        self.spin.setRange(5, 29)
        self.spin.setValue(days)
        self.spin.setSuffix(" days")
        row.addWidget(self.spin)
        row.addStretch()
        lay.addLayout(row)

        note = QLabel("Runs as SYSTEM at 09:00 on the interval above.")
        note.setStyleSheet(f"color:{T.MUTED};font-size:12px;")
        lay.addWidget(note)

        btns = QHBoxLayout()
        schedule = QPushButton("Schedule")
        set_role(schedule, "primary")
        remove = QPushButton("Remove")
        set_role(remove, "ghost")
        cancel = QPushButton("Cancel")
        schedule.clicked.connect(partial(self._done, "schedule"))
        remove.clicked.connect(partial(self._done, "remove"))
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(remove)
        btns.addWidget(cancel)
        btns.addWidget(schedule)
        lay.addLayout(btns)

    def _done(self, action: str, *_args) -> None:
        self._action = action
        self.accept()

    def result_action(self) -> Optional[str]:
        return self._action

    def days(self) -> int:
        return self.spin.value()


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setFixedSize(460, 340)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 28)
        lay.setSpacing(10)

        title = QLabel(APP_NAME)
        title.setStyleSheet(f"font-size:22px;font-weight:800;color:{T.ACCENT};")
        lay.addWidget(title)
        ver = QLabel(f"Version {VERSION}")
        ver.setStyleSheet(f"color:{T.MUTED};font-size:13px;")
        lay.addWidget(ver)

        body = QLabel(
            "Professional local toolkit for Internet Download Manager trial "
            "management on systems you own.\n\n"
            "Calibrated for IDM 6.43.x registry layout (verified live on 6.43.10):\n"
            "• DownloadManager trial values + ConfigTime clock + SpecialData blobs\n"
            "• WOW6432Node CLSID markers (Model / Therad / MData)\n"
            "• ACL-locked CLSID keys: ownership takeover + DACL replacement\n"
            "• HKEY_USERS Classes CLSID cleanup, hosts blocking, freeze ACLs"
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"color:{T.TEXT};font-size:13px;")
        lay.addWidget(body)
        lay.addStretch()

        close = QPushButton("Close")
        set_role(close, "primary")
        close.clicked.connect(self.accept)
        lay.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)


# ── Main window ─────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    NAV = [
        ("dashboard", "Dashboard"),
        ("operations", "Operations"),
        ("backup", "Backup"),
        ("history", "History"),
        ("settings", "Settings"),
        ("console", "Console"),
    ]

    ACTIONS = {
        "reset": (
            "Reset Trial",
            "Deep-clean trial markers (tvfrdt, radxcnt, ConfigTime, SpecialData, "
            "bRmGUCfEx, vCOUFP) and CLSID keys — including ACL-locked ones.",
            T.GREEN,
        ),
        "freeze": (
            "Freeze Trial",
            "Deny ACL write on CLSID keys so the trial clock cannot advance.",
            T.ACCENT,
        ),
        "unfreeze": (
            "Unfreeze",
            "Restore normal registry permissions on tracking keys.",
            T.YELLOW,
        ),
        "activate": (
            "Activate",
            "Reset → inject identity → seed CLSID → freeze in one pass.",
            T.ORANGE,
        ),
        "block_updates": (
            "Block Updates",
            "Sinkhole Tonec / IDM domains in the system hosts file.",
            T.RED,
        ),
        "unblock_updates": (
            "Unblock Updates",
            "Remove hosts block section and flush DNS cache.",
            T.MUTED,
        ),
    }

    DESTRUCTIVE = {"reset", "activate", "restore", "unfreeze", "remove_auto_reset"}

    def __init__(self):
        super().__init__()
        self.settings = QSettings(APP_ORG, APP_NAME)
        self.worker: Optional[EngineWorker] = None
        self.status_worker: Optional[StatusWorker] = None
        self._busy = False
        self._history: List[Dict[str, Any]] = []
        self._nav: Dict[str, QPushButton] = {}
        self._cards: Dict[str, ActionCard] = {}
        self._quick_btns: List[QPushButton] = []

        self.setWindowTitle(f"{APP_NAME}  ·  v{VERSION}")
        self.setMinimumSize(1140, 740)
        self.resize(1220, 800)

        self._build_ui()
        self._build_tray()
        self._build_shortcuts()
        self._load_history()
        self._set_page("dashboard")

        if self.settings.value("ui/auto_check_status", True, type=bool):
            QTimer.singleShot(350, self.refresh_status)

    # ── build ───────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._sidebar())

        self.stack = QStackedWidget()
        self.page_ix: Dict[str, int] = {}
        for key, _ in self.NAV:
            self.page_ix[key] = self.stack.addWidget(self._page(key))
        body.addWidget(self.stack, 1)

        wrap = QWidget()
        wrap.setLayout(body)
        outer.addWidget(wrap, 1)

        # progress
        prog = QWidget()
        prog.setStyleSheet(f"background:{T.BG2};border-top:1px solid {T.LINE};")
        pl = QHBoxLayout(prog)
        pl.setContentsMargins(16, 6, 16, 6)
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(f"color:{T.MUTED};font-size:11px;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(14)
        self.progress_label.hide()
        self.progress_bar.hide()
        pl.addWidget(self.progress_label)
        pl.addWidget(self.progress_bar, 1)
        outer.addWidget(prog)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        admin = is_admin()
        self.admin_badge = QLabel("ADMIN" if admin else "STANDARD USER")
        if admin:
            self.admin_badge.setStyleSheet(
                f"color:#0b0e14;background:{T.GREEN};border-radius:8px;"
                f"padding:2px 10px;font-size:10px;font-weight:700;"
            )
        else:
            self.admin_badge.setStyleSheet(
                f"color:{T.YELLOW};border:1px solid {T.YELLOW};border-radius:8px;"
                f"padding:2px 10px;font-size:10px;font-weight:700;"
            )
        self.status_bar.addPermanentWidget(self.admin_badge)
        self.status_bar.showMessage("Ready")

    def _header(self) -> QWidget:
        h = QFrame()
        h.setFixedHeight(60)
        h.setStyleSheet(
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {T.BG2}, stop:1 {T.BG3});border-bottom:1px solid {T.LINE};"
        )
        lay = QHBoxLayout(h)
        lay.setContentsMargins(20, 0, 20, 0)

        brand = QLabel(
            f"<span style='color:{T.ACCENT};font-weight:800;font-size:16px;'>"
            f"{APP_NAME}</span>"
            f"<span style='color:{T.DIM};font-size:12px;'>  v{VERSION}</span>"
        )
        lay.addWidget(brand)
        lay.addStretch()

        self.refresh_btn = QPushButton("Refresh status")
        set_role(self.refresh_btn, "ghost")
        self.refresh_btn.clicked.connect(self.refresh_status)
        lay.addWidget(self.refresh_btn)

        if not is_admin():
            elev = QPushButton("Run as Administrator")
            set_role(elev, "primary")
            elev.clicked.connect(self._elevate)
            lay.addWidget(elev)

        about = QPushButton("About")
        set_role(about, "ghost")
        about.clicked.connect(self._about)
        lay.addWidget(about)
        return h

    def _sidebar(self) -> QWidget:
        side = QFrame()
        side.setFixedWidth(210)
        side.setStyleSheet(f"background:{T.BG2};border-right:1px solid {T.LINE};")
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, 18, 12, 18)
        lay.setSpacing(4)

        lbl = QLabel("NAVIGATION")
        lbl.setStyleSheet(
            f"color:{T.DIM};font-size:10px;font-weight:700;"
            f"letter-spacing:1.2px;padding:0 8px 10px 8px;"
        )
        lay.addWidget(lbl)

        for key, label in self.NAV:
            btn = QPushButton(f"  {label}")
            set_role(btn, "nav")
            polish_active(btn, False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(partial(self._set_page, key))
            self._nav[key] = btn
            lay.addWidget(btn)

        lay.addStretch()
        tip = QLabel("F5  refresh status\nCtrl+L  clear console\nCtrl+Q  quit")
        tip.setStyleSheet(f"color:{T.DIM};font-size:10px;padding:8px;")
        lay.addWidget(tip)
        return side

    def _page(self, key: str) -> QWidget:
        builders = {
            "dashboard": self._page_dashboard,
            "operations": self._page_operations,
            "backup": self._page_backup,
            "history": self._page_history,
            "settings": self._page_settings,
            "console": self._page_console,
        }
        return builders[key]()

    def _shell(self, title: str, subtitle: str) -> Tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)
        h = QLabel(title)
        h.setStyleSheet("font-size:22px;font-weight:800;")
        lay.addWidget(h)
        s = QLabel(subtitle)
        s.setStyleSheet(f"color:{T.MUTED};font-size:13px;")
        s.setWordWrap(True)
        lay.addWidget(s)
        return page, lay

    def _page_dashboard(self) -> QWidget:
        page, lay = self._shell(
            "Dashboard",
            "Live overview of Internet Download Manager on this machine.",
        )
        grid = QGridLayout()
        grid.setSpacing(12)
        self.card_idm = StatCard("IDM")
        self.card_trial = StatCard("Trial")
        self.card_reg = StatCard("Registration")
        self.card_upd = StatCard("Updates")
        self.card_prot = StatCard("Protection")
        self.card_sched = StatCard("Scheduler")
        for i, c in enumerate(
            [self.card_idm, self.card_trial, self.card_reg,
             self.card_upd, self.card_prot, self.card_sched]
        ):
            grid.addWidget(c, i // 3, i % 3)
        lay.addLayout(grid)

        quick = QFrame()
        quick.setProperty("card", "true")
        ql = QVBoxLayout(quick)
        ql.setContentsMargins(18, 16, 18, 16)
        ql.addWidget(QLabel("Quick actions"))
        row = QHBoxLayout()
        for key, label, role in (
            ("reset", "Reset trial", "success"),
            ("freeze", "Freeze", "primary"),
            ("block_updates", "Block updates", "danger"),
            ("backup", "Backup…", "ghost"),
        ):
            b = QPushButton(label)
            set_role(b, role)
            if key == "backup":
                b.clicked.connect(self._do_backup)
            else:
                b.clicked.connect(partial(self.run_action, key))
            self._quick_btns.append(b)
            row.addWidget(b)
        row.addStretch()
        ql.addLayout(row)
        lay.addWidget(quick)

        self.dash_details = QTextEdit()
        self.dash_details.setReadOnly(True)
        self.dash_details.setMaximumHeight(170)
        self.dash_details.setPlaceholderText("Status details appear here…")
        lay.addWidget(self.dash_details)
        lay.addStretch()
        return page

    def _page_operations(self) -> QWidget:
        page, lay = self._shell(
            "Operations",
            "Core trial, freeze, and update-control workflows.",
        )
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, (key, (title, desc, color)) in enumerate(self.ACTIONS.items()):
            card = ActionCard(key, title, desc, color)
            card.run_requested.connect(self.run_action)
            self._cards[key] = card
            grid.addWidget(card, i // 3, i % 3)
        lay.addLayout(grid)
        lay.addStretch()
        return page

    def _page_backup(self) -> QWidget:
        page, lay = self._shell(
            "Backup & Restore",
            "Export or import registry snapshots and AppData for safe rollback.",
        )
        card = QFrame()
        card.setProperty("card", "true")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(12)
        cl.addWidget(QLabel(
            "Create a timestamped backup folder with .reg exports and AppData."
        ))
        row = QHBoxLayout()
        b1 = QPushButton("Create backup…")
        set_role(b1, "primary")
        b1.clicked.connect(self._do_backup)
        b2 = QPushButton("Restore from folder…")
        set_role(b2, "ghost")
        b2.clicked.connect(self._do_restore)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch()
        cl.addLayout(row)

        sched = QPushButton("Configure auto-reset scheduler…")
        set_role(sched, "ghost")
        sched.clicked.connect(self._do_scheduler)
        cl.addWidget(sched, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(card)
        lay.addStretch()
        return page

    def _page_history(self) -> QWidget:
        page, lay = self._shell(
            "History",
            "Recent operations performed by this installation.",
        )
        self.history_list = QListWidget()
        self.history_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        lay.addWidget(self.history_list, 1)
        row = QHBoxLayout()
        clr = QPushButton("Clear history")
        set_role(clr, "ghost")
        clr.clicked.connect(self._clear_history)
        exp = QPushButton("Export console log…")
        set_role(exp, "ghost")
        exp.clicked.connect(self._export_log)
        row.addWidget(clr)
        row.addWidget(exp)
        row.addStretch()
        lay.addLayout(row)
        return page

    def _page_settings(self) -> QWidget:
        page, lay = self._shell("Settings", "Preferences stored per-user via QSettings.")
        card = QFrame()
        card.setProperty("card", "true")
        form = QFormLayout(card)
        form.setContentsMargins(20, 18, 20, 18)
        form.setSpacing(12)

        self.chk_tray = QCheckBox("Minimize to system tray on close")
        self.chk_tray.setChecked(self.settings.value("ui/minimize_to_tray", True, type=bool))
        self.chk_confirm = QCheckBox("Confirm destructive operations")
        self.chk_confirm.setChecked(self.settings.value("ui/confirm_destructive", True, type=bool))
        self.chk_auto = QCheckBox("Check IDM status on startup")
        self.chk_auto.setChecked(self.settings.value("ui/auto_check_status", True, type=bool))

        self.set_fname = QLineEdit(self.settings.value("activate/fname", "User", type=str))
        self.set_lname = QLineEdit(self.settings.value("activate/lname", "", type=str))
        self.set_email = QLineEdit(self.settings.value("activate/email", "", type=str))
        self.set_days = QSpinBox()
        self.set_days.setRange(5, 29)
        self.set_days.setValue(self.settings.value("scheduler/days", 25, type=int))
        self.set_days.setSuffix(" days")

        form.addRow(self.chk_tray)
        form.addRow(self.chk_confirm)
        form.addRow(self.chk_auto)
        form.addRow("Default first name", self.set_fname)
        form.addRow("Default last name", self.set_lname)
        form.addRow("Default email", self.set_email)
        form.addRow("Default auto-reset interval", self.set_days)

        save = QPushButton("Save settings")
        set_role(save, "primary")
        save.clicked.connect(self._save_settings)
        form.addRow(save)
        lay.addWidget(card)
        lay.addStretch()
        return page

    def _page_console(self) -> QWidget:
        page, lay = self._shell("Console", "Detailed engine output for the current session.")
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        lay.addWidget(self.log_area, 1)
        row = QHBoxLayout()
        clr = QPushButton("Clear")
        set_role(clr, "ghost")
        clr.clicked.connect(self.log_area.clear)
        exp = QPushButton("Export…")
        set_role(exp, "ghost")
        exp.clicked.connect(self._export_log)
        row.addStretch()
        row.addWidget(clr)
        row.addWidget(exp)
        lay.addLayout(row)
        return page

    def _build_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        self.tray = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray.setIcon(icon)
        self.setWindowIcon(icon)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        a_show = QAction("Show", self)
        a_show.triggered.connect(self._show_from_tray)
        a_reset = QAction("Reset trial", self)
        a_reset.triggered.connect(partial(self.run_action, "reset"))
        a_quit = QAction("Quit", self)
        a_quit.triggered.connect(self._quit_app)
        menu.addAction(a_show)
        menu.addAction(a_reset)
        menu.addSeparator()
        menu.addAction(a_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _build_shortcuts(self) -> None:
        a1 = QAction(self)
        a1.setShortcut(QKeySequence("F5"))
        a1.triggered.connect(self.refresh_status)
        self.addAction(a1)
        a2 = QAction(self)
        a2.setShortcut(QKeySequence("Ctrl+L"))
        a2.triggered.connect(self._clear_console_nav)
        self.addAction(a2)
        a3 = QAction(self)
        a3.setShortcut(QKeySequence("Ctrl+Q"))
        a3.triggered.connect(self._quit_app)
        self.addAction(a3)

    # ── helpers ─────────────────────────────────────────────────────────────
    def _set_page(self, key: str, *_args) -> None:
        if key not in self.page_ix:
            return
        self.stack.setCurrentIndex(self.page_ix[key])
        for k, btn in self._nav.items():
            polish_active(btn, k == key)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.refresh_btn.setEnabled(not busy)
        for card in self._cards.values():
            card.setEnabled(not busy)
        for b in self._quick_btns:
            b.setEnabled(not busy)
        if busy:
            self.progress_bar.show()
            self.progress_label.show()
            self.progress_bar.setValue(0)
        else:
            self.progress_bar.hide()
            self.progress_label.hide()
            self.progress_bar.setValue(0)
            self.progress_label.setText("")

    def _append_log(self, message: str, level: str = "info") -> None:
        colors = {
            "info": T.TEXT,
            "success": T.GREEN,
            "warning": T.YELLOW,
            "error": T.RED,
            "header": T.ACCENT2,
        }
        color = colors.get(level, T.TEXT)
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        cursor = self.log_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(T.DIM))
        cursor.insertText(f"[{ts}] ", fmt)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if level == "header":
            fmt.setFontWeight(QFont.Weight.Bold)
        cursor.insertText(message + "\n", fmt)
        self.log_area.setTextCursor(cursor)
        self.log_area.ensureCursorVisible()

        max_lines = self.settings.value("log/max_lines", 5000, type=int)
        doc = self.log_area.document()
        if doc.blockCount() > max_lines:
            c = QTextCursor(doc)
            c.movePosition(QTextCursor.MoveOperation.Start)
            for _ in range(doc.blockCount() - max_lines):
                c.select(QTextCursor.SelectionType.BlockUnderCursor)
                c.removeSelectedText()
                c.deleteChar()

    def _history_path(self) -> Path:
        return app_store_dir() / "operation_history.json"

    def _load_history(self) -> None:
        path = self._history_path()
        if path.exists():
            try:
                self._history = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                self._history = []
        self._render_history()

    def _save_history(self) -> None:
        try:
            self._history_path().write_text(
                json.dumps(self._history[-200:], indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def _render_history(self) -> None:
        if not hasattr(self, "history_list"):
            return
        self.history_list.clear()
        for item in reversed(self._history[-100:]):
            ts = item.get("time", "")
            action = item.get("action", "")
            ok = item.get("success", False)
            summary = item.get("summary", "")
            mark = "✓" if ok else "✗"
            text = f"{ts}   {mark}  {action.upper():<18}  {summary}"
            QListWidgetItem(text, self.history_list)

    def _record_history(self, result: ActionResult) -> None:
        self._history.append({
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": result.action,
            "success": result.success,
            "summary": result.summary(),
            "duration_ms": result.duration_ms,
        })
        self._save_history()
        self._render_history()

    # ── actions ─────────────────────────────────────────────────────────────
    def _elevate(self, *_args) -> None:
        self._append_log("Requesting Administrator elevation via UAC…", "warning")
        elevate_and_exit()

    def _about(self, *_args) -> None:
        AboutDialog(self).exec()

    def run_action(self, action: str, *_args, **kwargs) -> None:
        """Run an engine action. Extra Qt args after action are ignored."""
        if self._busy:
            return
        if not isinstance(action, str):
            self._append_log(f"Ignored bad action payload: {action!r}", "error")
            return

        if not is_admin():
            reply = QMessageBox.question(
                self,
                "Administrator required",
                "This operation needs elevated privileges.\n\nElevate now?",
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._elevate()
            return

        if action == "activate" and "fname" not in kwargs:
            dlg = ActivateDialog(
                self.settings.value("activate/fname", "User", type=str),
                self.settings.value("activate/lname", "", type=str),
                self.settings.value("activate/email", "", type=str),
                self,
            )
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            fn, ln, em = dlg.values()
            self.settings.setValue("activate/fname", fn)
            self.settings.setValue("activate/lname", ln)
            self.settings.setValue("activate/email", em)
            kwargs.update(fname=fn, lname=ln, email=em)

        if self.settings.value("ui/confirm_destructive", True, type=bool) and action in self.DESTRUCTIVE:
            meta = self.ACTIONS.get(action, (action, "", T.TEXT))
            if QMessageBox.question(
                self,
                f"Confirm {meta[0]}",
                f"{meta[1]}\n\nContinue with “{meta[0]}”?",
            ) != QMessageBox.StandardButton.Yes:
                return

        self._set_page("console")
        self.log_area.clear()
        self._set_busy(True)
        self.status_bar.showMessage(f"Running {action}…")
        self.worker = EngineWorker(action, kwargs, parent=self)
        self.worker.log_msg.connect(self._append_log)
        self.worker.progress.connect(self._on_progress)
        self.worker.status.connect(self.status_bar.showMessage)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, cur: int, total: int, label: str) -> None:
        if total > 0:
            self.progress_bar.setValue(int(cur / total * 100))
        self.progress_label.setText(label or f"{cur}/{total}")

    def _on_finished(self, result: ActionResult) -> None:
        self._set_busy(False)
        self._record_history(result)
        if result.success:
            self.status_bar.showMessage(
                f"✓ {result.action} complete — {result.summary()} ({result.duration_ms} ms)",
                8000,
            )
            self._append_log(f"\nDone in {result.duration_ms} ms — {result.summary()}", "success")
        else:
            self.status_bar.showMessage(f"✗ {result.action} failed — {result.summary()}", 10000)
            self._append_log(f"\nFailed — {result.summary()}", "error")
        QTimer.singleShot(400, self.refresh_status)

    def _do_backup(self, *_args) -> None:
        start = self.settings.value("paths/last_backup", str(Path.home()), type=str)
        path = QFileDialog.getExistingDirectory(self, "Select backup location", start)
        if not path:
            return
        self.settings.setValue("paths/last_backup", path)
        self.run_action("backup", output_dir=path)

    def _do_restore(self, *_args) -> None:
        start = self.settings.value("paths/last_backup", str(Path.home()), type=str)
        path = QFileDialog.getExistingDirectory(self, "Select backup folder", start)
        if not path:
            return
        self.run_action("restore", backup_dir=path)

    def _do_scheduler(self, *_args) -> None:
        days = self.settings.value("scheduler/days", 25, type=int)
        dlg = SchedulerDialog(days, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        action = dlg.result_action()
        if action == "schedule":
            d = dlg.days()
            self.settings.setValue("scheduler/days", d)
            self.run_action("auto_reset", interval=d)
        elif action == "remove":
            self.run_action("remove_auto_reset")

    def _save_settings(self, *_args) -> None:
        self.settings.setValue("ui/minimize_to_tray", self.chk_tray.isChecked())
        self.settings.setValue("ui/confirm_destructive", self.chk_confirm.isChecked())
        self.settings.setValue("ui/auto_check_status", self.chk_auto.isChecked())
        self.settings.setValue("activate/fname", self.set_fname.text().strip() or "User")
        self.settings.setValue("activate/lname", self.set_lname.text().strip())
        self.settings.setValue("activate/email", self.set_email.text().strip())
        self.settings.setValue("scheduler/days", self.set_days.value())
        self.status_bar.showMessage("Settings saved", 3000)
        QMessageBox.information(self, "Settings", "Preferences saved.")

    def refresh_status(self, *_args) -> None:
        if self.status_worker and self.status_worker.isRunning():
            return
        self.status_bar.showMessage("Checking IDM status…")
        self.status_worker = StatusWorker(parent=self)
        self.status_worker.done.connect(self._apply_status)
        self.status_worker.start()

    def _apply_status(self, st: IDMStatus) -> None:
        if st.installed:
            self.card_idm.set_state(
                "Installed", T.GREEN,
                f"{st.version}  ·  {st.idmvers}" if st.idmvers != "—" else st.version,
            )
        else:
            self.card_idm.set_state("Not found", T.RED, "IDM binary / registry missing")

        if st.frozen:
            self.card_trial.set_state("Frozen", T.ACCENT, "ACL lock active")
        elif st.trial_clean:
            self.card_trial.set_state("Clean", T.GREEN, "No tracking markers")
        else:
            self.card_trial.set_state(
                "Tracking", T.YELLOW,
                ", ".join(st.trial_markers[:5]) or "markers present",
            )
        sub_run = "Process running" if st.process_running else "Idle"
        if self.card_trial.sub.text():
            self.card_trial.sub.setText(self.card_trial.sub.text() + f"  ·  {sub_run}")
        else:
            self.card_trial.sub.setText(sub_run)

        if st.registered:
            self.card_reg.set_state("Registered", T.GREEN, st.registrant)
        else:
            self.card_reg.set_state("Trial mode", T.YELLOW, "No serial in registry")

        if st.updates_blocked:
            self.card_upd.set_state("Blocked", T.RED, "Hosts sinkhole active")
        else:
            self.card_upd.set_state("Open", T.MUTED, "No hosts block section")

        if st.frozen:
            self.card_prot.set_state("Protected", T.ACCENT, f"CLSID hits: {len(st.clsid_hits)}")
        else:
            self.card_prot.set_state(
                "Unlocked", T.MUTED,
                f"CLSID hits: {len(st.clsid_hits)}" if st.clsid_hits else "No CLSID keys",
            )

        if st.auto_reset:
            self.card_sched.set_state("Enabled", T.GREEN, "Task Scheduler job registered")
        else:
            self.card_sched.set_state("Off", T.MUTED, "No auto-reset task")

        lines = [
            f"IDM status @ {datetime.datetime.now():%H:%M:%S}",
            f"Version: {st.version}  |  idmvers: {st.idmvers}",
            f"EXE: {st.exe_path or '—'}",
            f"Markers: {', '.join(st.trial_markers) if st.trial_markers else '(none)'}",
            f"CLSID: {', '.join(st.clsid_hits) if st.clsid_hits else '(none)'}",
            "",
            *st.details,
        ]
        self.dash_details.setPlainText("\n".join(lines))
        self.status_bar.showMessage("Status updated", 4000)

    def _clear_history(self, *_args) -> None:
        if QMessageBox.question(
            self, "Clear history", "Delete all locally stored history?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._history.clear()
        self._save_history()
        self._render_history()

    def _export_log(self, *_args) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export console log",
            f"idm_resetter_{datetime.datetime.now():%Y%m%d_%H%M%S}.log",
            "Log files (*.log);;Text (*.txt)",
        )
        if not path:
            return
        try:
            Path(path).write_text(self.log_area.toPlainText(), encoding="utf-8")
            self.status_bar.showMessage(f"Log exported → {path}", 5000)
        except Exception as e:
            QMessageBox.warning(self, "Export failed", str(e))

    def _clear_console_nav(self, *_args) -> None:
        self._set_page("console")
        self.log_area.clear()

    def _show_from_tray(self, *_args) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _stop_workers(self, timeout_ms: int = 4000) -> None:
        for worker in (self.worker, self.status_worker):
            if worker is None:
                continue
            try:
                if worker.isRunning():
                    worker.quit()
                    if not worker.wait(timeout_ms):
                        worker.terminate()
                        worker.wait(1000)
            except Exception:
                pass
        self.worker = None
        self.status_worker = None

    def _quit_app(self, *_args) -> None:
        self._stop_workers()
        if self.tray:
            self.tray.hide()
        QApplication.instance().quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        if (
            self.tray
            and self.tray.isVisible()
            and self.settings.value("ui/minimize_to_tray", True, type=bool)
        ):
            self.hide()
            self.tray.showMessage(
                APP_NAME, "Still running in the tray.",
                QSystemTrayIcon.MessageIcon.Information, 2000,
            )
            event.ignore()
            return
        self._stop_workers()
        event.accept()


def run_headless_auto_reset() -> int:
    print(f"[{APP_NAME}] Auto-reset starting…")
    eng = IDMEngine(
        log_cb=lambda m, l="info": print(f"[{l}] {m}"),
    )
    eng.kill_idm()
    result = eng.reset_trial()
    print(f"Result: success={result.success}  {result.summary()}")
    return 0 if result.success else 1


def main() -> int:
    if "--auto-reset" in sys.argv:
        return run_headless_auto_reset()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)

    # Single-instance soft lock via lockfile
    lock = app_store_dir() / "app.lock"
    try:
        if lock.exists():
            # stale ok — not hard lockenforce
            pass
        lock.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass

    win = MainWindow()
    win.show()
    code = app.exec()
    try:
        if lock.exists():
            lock.unlink(missing_ok=True)
    except Exception:
        pass
    return code


if __name__ == "__main__":
    sys.exit(main())
