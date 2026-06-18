"""
Servo Arm Control Panel
========================
Python GUI for the 4-DOF MG90S servo arm controlled by Arduino UNO R3.

Serial protocol (matches arm_control.ino):
    h                       - show help
    s                       - query all servo angles
    <id> <angle>            - set one servo (id: 0-3)
    <a0> <a1> <a2> <a3>     - batch set all 4 servos
    All commands end with newline.

Servo limits (per current .ino, v2 with S3 limited to 0-90):
    S0  0-180  init  90    S1  0-90  init 45
    S2  0-90   init  45    S3  0-90  init  0

New in v2: a single value (e.g. "90") sets all 4 servos to that angle.
"""

import re
import threading
import time
import tkinter as tk
from collections import deque
from datetime import datetime
from tkinter import ttk

import serial
from serial.tools import list_ports


# ===================== Configuration =====================
BAUD_RATE = 9600
SLIDER_DEBOUNCE_MS = 60
SERIAL_READ_TIMEOUT = 0.2
INIT_DELAY_MS = 500
LOG_MAX_LINES = 300
LIVE_RX_WINDOW_S = 2.0

# Matches the current arm_control.ino (no S4, S3 init 0, S1/S2 range 0-90 init 45).
SERVOS = [
    {"name": "S0", "label": "Base",     "min": 0, "max": 180, "init": 90, "color": "#5C6BC0"},
    {"name": "S1", "label": "Shoulder", "min": 0, "max": 90,  "init": 45, "color": "#26A69A"},
    {"name": "S2", "label": "Elbow",    "min": 0, "max": 90,  "init": 45, "color": "#EF6C00"},
    {"name": "S3", "label": "Gripper",    "min": 0, "max": 90,  "init": 0,  "color": "#7E57C2"},
]

HOME_POS = [s["init"] for s in SERVOS]   # [90, 45, 45, 0]


# ===================== Theme =====================
COLOR_BG         = "#F3F4F6"
COLOR_CARD       = "#FFFFFF"
COLOR_BORDER     = "#E5E7EB"
COLOR_TEXT       = "#111827"
COLOR_TEXT_DIM   = "#6B7280"
COLOR_PRIMARY    = "#2563EB"
COLOR_PRIMARY_DK = "#1D4ED8"
COLOR_SUCCESS    = "#10B981"
COLOR_SUCCESS_DK = "#047857"
COLOR_WARNING    = "#F59E0B"
COLOR_WARNING_DK = "#B45309"
COLOR_DANGER     = "#EF4444"
COLOR_DANGER_DK  = "#B91C1C"
COLOR_LOG_BG     = "#0F172A"
COLOR_LOG_FG     = "#E2E8F0"
COLOR_LOG_DIM    = "#94A3B8"
COLOR_SEND       = "#93C5FD"
COLOR_RECV       = "#6EE7B7"
COLOR_INFO       = "#E2E8F0"
COLOR_WARN       = "#FCD34D"
COLOR_ERR        = "#FCA5A5"
COLOR_STATUS_BG  = "#E5E7EB"


# ===================== Main App =====================
class ServoControlApp:

    def __init__(self, root):
        self.root = root
        self.root.title("Servo Arm Control Panel")
        self.root.geometry("1000x720")
        self.root.minsize(880, 600)
        self.root.configure(bg=COLOR_BG)

        # Serial state
        self.serial_conn = None
        self.connected = False
        self._reader_stop = threading.Event()
        self._reader_thread = None
        self._last_rx_time = 0.0
        self._pending_send = {}
        self._suppress_slider_cb = False

        # Per-servo UI refs
        self.sliders = {}
        self.entries = {}
        self.target_labels = {}
        self.reset_btns = {}

        # Log buffer (text widget is built in _build_log_panel)
        self._log_lines = deque(maxlen=LOG_MAX_LINES)
        self.log_text = None

        self._build_styles()
        self._build_header()
        self._build_connection_bar()
        self._build_body()
        self._build_servo_panels(self._body_left)
        self._build_custom_command(self._body_right)
        self._build_log_panel(self._body_right)
        self._build_status_bar()

        self._tick_status()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.bind("<Control-q>", lambda e: self._on_closing())
        self.root.bind("<Control-c>", lambda e: self._toggle_connect())

        self._log("info", "Ready. Connect to the Arduino to begin.")

    # ---------------- Styles ----------------
    def _build_styles(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass

        # Base
        s.configure(".", background=COLOR_BG, foreground=COLOR_TEXT, font=("Segoe UI", 10))
        s.configure("TFrame", background=COLOR_BG)
        s.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=("Segoe UI", 10))

        # Header
        s.configure("Header.TLabel", background=COLOR_BG, foreground=COLOR_TEXT,
                    font=("Segoe UI", 16, "bold"))
        s.configure("Sub.TLabel", background=COLOR_BG, foreground=COLOR_TEXT_DIM,
                    font=("Segoe UI", 9))

        # Card
        s.configure("Card.TFrame", background=COLOR_CARD, relief="flat", borderwidth=0)
        s.configure("Card.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT, font=("Segoe UI", 10))
        s.configure("CardDim.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT_DIM, font=("Segoe UI", 9))
        s.configure("Target.TLabel", background=COLOR_CARD, foreground=COLOR_PRIMARY,
                    font=("Consolas", 22, "bold"))
        s.configure("Unit.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT_DIM,
                    font=("Segoe UI", 11))
        s.configure("Range.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT_DIM, font=("Segoe UI", 9))

        for i, servo in enumerate(SERVOS):
            s.configure(f"ServoName{i}.TLabel",
                        background=COLOR_CARD, foreground=servo["color"],
                        font=("Segoe UI", 13, "bold"))
            s.configure(f"ServoSub{i}.TLabel",
                        background=COLOR_CARD, foreground=COLOR_TEXT_DIM, font=("Segoe UI", 9))

        s.configure("Horizontal.TScale", background=COLOR_CARD, troughcolor="#E5E7EB",
                    borderwidth=0, lightcolor=COLOR_CARD, darkcolor=COLOR_CARD)

        # Buttons
        s.configure("TButton", font=("Segoe UI", 10), padding=(14, 8), borderwidth=0, relief="flat")
        for name, bg, abg, fg in [
            ("Primary", COLOR_PRIMARY, COLOR_PRIMARY_DK, "#FFFFFF"),
            ("Success", COLOR_SUCCESS, COLOR_SUCCESS_DK, "#FFFFFF"),
            ("Warning", COLOR_WARNING, COLOR_WARNING_DK, "#FFFFFF"),
            ("Danger",  COLOR_DANGER,  COLOR_DANGER_DK,  "#FFFFFF"),
            ("Ghost",   "#FFFFFF",     "#F3F4F6",        COLOR_TEXT),
        ]:
            s.configure(f"{name}.TButton", background=bg, foreground=fg, font=("Segoe UI", 10, "bold"))
            s.map(
                f"{name}.TButton",
                background=[("active", abg), ("disabled", "#9CA3AF"), ("!disabled", bg)],
                foreground=[("disabled", "#F9FAFB"), ("!disabled", fg)],
            )

        # Entry
        s.configure("TEntry", fieldbackground="#F9FAFB", borderwidth=1, relief="solid", padding=4)

    # ---------------- Header ----------------
    def _build_header(self):
        f = ttk.Frame(self.root, padding=(20, 16, 20, 4))
        f.pack(fill=tk.X)
        ttk.Label(f, text="Servo Arm Control Panel", style="Header.TLabel").pack(side=tk.LEFT)
        ttk.Label(f, text="Arduino UNO R3   4x MG90S   2x Dual-axis Joystick",
                  style="Sub.TLabel").pack(side=tk.LEFT, padx=12, pady=4)

    # ---------------- Connection Bar ----------------
    def _build_connection_bar(self):
        outer = ttk.Frame(self.root, padding=(20, 4, 20, 4))
        outer.pack(fill=tk.X)
        card = tk.Frame(outer, bg=COLOR_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1)
        card.pack(fill=tk.X)
        inner = ttk.Frame(card, padding=12)
        inner.pack(fill=tk.X)

        ttk.Label(inner, text="Port", style="Card.TLabel",
                  font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        self.port_combo = ttk.Combobox(inner, width=14, state="readonly", font=("Consolas", 10))
        self._refresh_ports()
        self.port_combo.pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(inner, text="Refresh", style="Ghost.TButton", width=8,
                   command=self._refresh_ports).pack(side=tk.LEFT, padx=(0, 8))
        self.connect_btn = ttk.Button(inner, text="Connect", style="Primary.TButton", width=12,
                                      command=self._toggle_connect)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.status_pill = tk.Label(
            inner, text="  Disconnected  ", font=("Segoe UI", 10, "bold"),
            bg="#F3F4F6", fg=COLOR_TEXT_DIM, padx=4, pady=4,
            highlightbackground=COLOR_BORDER, highlightthickness=1,
        )
        self.status_pill.pack(side=tk.LEFT)


    # ---------------- Body (two columns) ----------------
    def _build_body(self):
        container = ttk.Frame(self.root, padding=(20, 0, 20, 0))
        container.pack(fill=tk.BOTH, expand=True)

        self._paned = tk.PanedWindow(
            container, orient=tk.HORIZONTAL,
            sashwidth=6, sashpad=2, borderwidth=0,
            bg=COLOR_BG, relief="flat",
        )
        self._paned.pack(fill=tk.BOTH, expand=True)

        self._body_left = ttk.Frame(self._paned)
        self._body_right = ttk.Frame(self._paned)
        self._paned.add(self._body_left, minsize=420)
        self._paned.add(self._body_right, minsize=320)

        # Initial divider position (set after layout has happened)
        self.root.after(50, lambda: self._paned.sash_place(0, 600, 0))
    # ---------------- Servo Panels ----------------
    def _build_servo_panels(self, parent):
        outer = ttk.Frame(parent, padding=(20, 8, 20, 4))
        outer.pack(fill=tk.BOTH, expand=True)
        for i, servo in enumerate(SERVOS):
            self._build_servo_card(outer, i, servo)

    def _build_servo_card(self, parent, idx, servo):
        card = tk.Frame(parent, bg=COLOR_CARD,
                        highlightbackground=COLOR_BORDER, highlightthickness=1)
        card.pack(fill=tk.X, pady=5)

        # Top row
        top = ttk.Frame(card, padding=(14, 10, 14, 4))
        top.pack(fill=tk.X)
        ttk.Label(top, text=servo["name"], style=f"ServoName{idx}.TLabel").pack(side=tk.LEFT)
        ttk.Label(top, text=servo["label"], style=f"ServoSub{idx}.TLabel").pack(side=tk.LEFT, padx=8, pady=4)
        ttk.Label(top, text=f"range {servo['min']}-{servo['max']}deg",
                  style="Range.TLabel").pack(side=tk.RIGHT)

        # Middle row: slider + target + entry
        mid = ttk.Frame(card, padding=(14, 0, 14, 6))
        mid.pack(fill=tk.X)
        slider = ttk.Scale(
            mid, from_=servo["min"], to=servo["max"], value=servo["init"],
            orient=tk.HORIZONTAL,
            command=lambda v, i=idx: self._on_slider(i, v),
        )
        slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12))
        self.sliders[idx] = slider

        target = ttk.Label(mid, text=f"{servo['init']}", style="Target.TLabel")
        target.pack(side=tk.LEFT)
        self.target_labels[idx] = target
        ttk.Label(mid, text="deg", style="Unit.TLabel").pack(side=tk.LEFT, padx=(0, 12))

        entry = ttk.Entry(mid, width=5, justify="center", font=("Consolas", 11))
        entry.insert(0, str(servo["init"]))
        entry.pack(side=tk.LEFT)
        entry.bind("<Return>", lambda e, i=idx: self._on_entry(i))
        entry.bind("<FocusIn>", lambda e, ent=entry: ent.selection_range(0, tk.END))
        self.entries[idx] = entry

        # Bottom row
        bot = ttk.Frame(card, padding=(14, 0, 14, 10))
        bot.pack(fill=tk.X)
        reset_btn = ttk.Button(
            bot, text="\u21bb Reset", style="Ghost.TButton",
            command=lambda i=idx: self._reset_servo(i),
        )
        reset_btn.pack(side=tk.RIGHT)
        self.reset_btns[idx] = reset_btn

    # ---------------- Log Panel ----------------
    def _build_log_panel(self, parent):
        outer = ttk.Frame(parent, padding=(0, 8, 0, 4))
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X)
        ttk.Label(header, text="Serial Log", font=("Segoe UI", 10, "bold"),
                  background=COLOR_BG, foreground=COLOR_TEXT).pack(side=tk.LEFT)
        ttk.Button(header, text="Copy",  width=6, command=self._copy_log).pack(side=tk.RIGHT, padx=2)
        ttk.Button(header, text="Clear", width=6, command=self._clear_log).pack(side=tk.RIGHT, padx=2)

        log_frame = tk.Frame(outer, bg=COLOR_LOG_BG,
                             highlightbackground=COLOR_BORDER, highlightthickness=1)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        self.log_text = tk.Text(
            log_frame, height=7, bg=COLOR_LOG_BG, fg=COLOR_LOG_FG,
            font=("Consolas", 9), relief="flat", wrap="word",
            insertbackground=COLOR_LOG_FG, state="disabled",
            padx=10, pady=8,
        )
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.log_text.tag_configure("ts",   foreground=COLOR_LOG_DIM)
        self.log_text.tag_configure("send", foreground=COLOR_SEND)
        self.log_text.tag_configure("recv", foreground=COLOR_RECV)
        self.log_text.tag_configure("info", foreground=COLOR_INFO)
        self.log_text.tag_configure("warn", foreground=COLOR_WARN)
        self.log_text.tag_configure("err",  foreground=COLOR_ERR)

    # ---------------- Custom Command ----------------
    def _build_custom_command(self, parent):
        outer = ttk.Frame(parent, padding=(0, 4, 0, 4))
        outer.pack(fill=tk.X)

        card = tk.Frame(outer, bg=COLOR_LOG_BG,
                        highlightbackground=COLOR_BORDER, highlightthickness=1)
        card.pack(fill=tk.X)

        # Title
        ttk.Label(card, text="Custom Command",
                  font=("Segoe UI", 10, "bold"),
                  background=COLOR_LOG_BG, foreground=COLOR_LOG_FG).pack(
            anchor="w", padx=12, pady=(8, 4)
        )

        # Input row: entry (expand) + Send button
        input_frame = tk.Frame(card, bg=COLOR_LOG_BG)
        input_frame.pack(fill=tk.X, padx=12, pady=(0, 4))

        self.custom_cmd_var = tk.StringVar()
        self.custom_cmd_entry = tk.Entry(
            input_frame,
            textvariable=self.custom_cmd_var,
            bg="#020617", fg=COLOR_LOG_FG,
            insertbackground=COLOR_LOG_FG,
            font=("Consolas", 11), relief="flat",
            highlightthickness=1,
            highlightbackground="#1E293B",
            highlightcolor=COLOR_PRIMARY,
        )
        self.custom_cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 8))
        self.custom_cmd_entry.bind("<Return>", lambda e: self._send_custom())
        self.custom_cmd_entry.bind("<FocusIn>", lambda e: self.custom_cmd_entry.selection_range(0, tk.END))

        self.custom_cmd_send_btn = ttk.Button(
            input_frame, text="Send", style="Primary.TButton",
            width=8, command=self._send_custom,
        )
        self.custom_cmd_send_btn.pack(side=tk.LEFT)

        # Last sent
        self.custom_cmd_last = tk.Label(
            card, text="", font=("Consolas", 10),
            bg=COLOR_LOG_BG, fg=COLOR_SEND, anchor="w",
        )
        self.custom_cmd_last.pack(fill=tk.X, padx=12, pady=(2, 2))

        # Examples
        tk.Label(
            card, text="Examples: 90  |  0 60  |  0 90 90 90 40",
            font=("Consolas", 9), bg=COLOR_LOG_BG, fg=COLOR_LOG_DIM, anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(0, 8))

    def _send_custom(self):
        cmd = self.custom_cmd_var.get().strip()
        if not cmd:
            return
        if self._send_line(cmd):
            self.custom_cmd_last.config(text=f"\u2192 {cmd}")
            self.custom_cmd_var.set("")

    def _build_status_bar(self):
        bar = tk.Frame(self.root, bg=COLOR_STATUS_BG, height=24)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)
        self.status_bar_label = tk.Label(
            bar, text="Disconnected", font=("Segoe UI", 9),
            bg=COLOR_STATUS_BG, fg=COLOR_TEXT_DIM, padx=12,
        )
        self.status_bar_label.pack(side=tk.LEFT)
        tk.Label(
            bar, text="Ctrl+C Connect/Disconnect   Ctrl+Q Quit   Enter: Send custom cmd",
            font=("Segoe UI", 9), bg=COLOR_STATUS_BG, fg=COLOR_TEXT_DIM,
        ).pack(side=tk.RIGHT, padx=12)

    # ---------------- Port discovery ----------------
    def _list_serial_ports(self):
        try:
            return sorted({p.device for p in list_ports.comports()})
        except Exception as exc:
            self._log("err", f"Port scan failed: {exc}")
            return []

    def _refresh_ports(self):
        ports = self._list_serial_ports()
        current = self.port_combo.get() if hasattr(self, "port_combo") else None
        self.port_combo["values"] = ports if ports else ["(no ports)"]
        if current in ports:
            self.port_combo.set(current)
        elif ports:
            self.port_combo.current(0)
        else:
            self.port_combo.set("(no ports)")

    # ---------------- Connect / Disconnect ----------------
    def _toggle_connect(self):
        if self.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        port = self.port_combo.get()
        if not port or port == "(no ports)":
            self._log("warn", "No serial port selected.")
            return
        try:
            self.serial_conn = serial.Serial(port, BAUD_RATE, timeout=SERIAL_READ_TIMEOUT)
            self.serial_conn.reset_input_buffer()
            self.serial_conn.reset_output_buffer()
        except Exception as exc:
            self._log("err", f"Connect failed on {port}: {exc}")
            self.serial_conn = None
            return

        self.connected = True
        self._log("info", f"Connected to {port} @ {BAUD_RATE} baud.")
        self._set_status("connected_idle", f"Connected  {port}")
        self.connect_btn.config(text="Disconnect", style="Danger.TButton")
        self.port_combo.config(state="disabled")

        self._reader_stop.clear()
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        self.root.after(INIT_DELAY_MS, lambda: self._send_line("s"))

    def _disconnect(self):
        self._reader_stop.set()
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except Exception as exc:
                self._log("err", f"Disconnect error: {exc}")
        self.serial_conn = None
        self.connected = False
        self._log("info", "Disconnected.")
        self._set_status("disconnected", "Disconnected")
        self.connect_btn.config(text="Connect", style="Primary.TButton")
        self.port_combo.config(state="readonly")
    def _on_serial_error(self, msg):
        self._log("err", f"Serial error: {msg}")
        if self.connected:
            self._disconnect()

    # ---------------- Serial I/O ----------------
    def _send_line(self, line):
        if not (self.serial_conn and self.serial_conn.is_open):
            self._log("warn", "Not connected.")
            return False
        try:
            payload = (line.rstrip("\r\n") + "\n").encode("utf-8")
            self.serial_conn.write(payload)
            self._log("send", line)
            return True
        except Exception as exc:
            self._on_serial_error(str(exc))
            return False

    def _send_set(self, servo_id, angle):
        self._send_line(f"{servo_id} {angle}")

    def _send_batch(self, angles):
        self._send_line(" ".join(str(a) for a in angles))

    def _send_set_all(self, angle):
        # New firmware feature: one value applies to all 4 servos.
        self._send_line(str(int(angle)))

    def _read_loop(self):
        buf = ""
        while not self._reader_stop.is_set():
            try:
                if not self.serial_conn:
                    break
                chunk = self.serial_conn.read(256)
                if not chunk:
                    continue
                buf += chunk.decode("utf-8", errors="ignore")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.rstrip("\r").strip()
                    if not line:
                        continue
                    self._last_rx_time = time.time()
                    self.root.after(0, self._handle_line, line)
            except Exception as exc:
                if not self._reader_stop.is_set():
                    self.root.after(0, self._on_serial_error, str(exc))
                break

    def _handle_line(self, line):
        self._log("recv", line)

        # "All servos set target to 90"  (new firmware)
        m = re.match(r"^All servos set target to\s+(\d+)\s*$", line)
        if m:
            val = int(m.group(1))
            return

        # Single servo echo: "S0 target = 60"
        m = re.match(r"^S\s*(\d+)\s+target\s*=\s*(\d+)\s*$", line)
        if m:
            idx, ang = int(m.group(1)), int(m.group(2))
            return

        # Batch / Status: any line with "x,y,z,w" after a colon
        m = re.search(r":\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)", line)
        if m:
            vals = [int(m.group(i)) for i in range(1, 5)]
            pass

    # ---------------- UI updates from user input ----------------
    def _on_slider(self, idx, value):
        if self._suppress_slider_cb:
            return
        ang = int(round(float(value)))
        self.target_labels[idx].config(text=f"{ang}")
        entry = self.entries[idx]
        if entry.get() != str(ang):
            entry.delete(0, tk.END)
            entry.insert(0, str(ang))
        self._cancel_pending(idx)
        self._pending_send[idx] = self.root.after(
            SLIDER_DEBOUNCE_MS, lambda i=idx, a=ang: self._flush_slider(i, a)
        )

    def _flush_slider(self, idx, ang):
        self._pending_send.pop(idx, None)
        if self.connected:
            self._send_set(idx, ang)

    def _cancel_pending(self, idx):
        if idx in self._pending_send:
            try:
                self.root.after_cancel(self._pending_send[idx])
            except Exception:
                pass
            self._pending_send.pop(idx, None)

    def _on_entry(self, idx):
        try:
            ang = int(self.entries[idx].get())
        except ValueError:
            return
        servo = SERVOS[idx]
        ang = max(servo["min"], min(servo["max"], ang))
        self.entries[idx].delete(0, tk.END)
        self.entries[idx].insert(0, str(ang))
        self.target_labels[idx].config(text=f"{ang}")
        self._cancel_pending(idx)
        self.sliders[idx].set(ang)

    def _set_all_targets(self, angles, send=True):
        self._suppress_slider_cb = True
        try:
            for i, ang in enumerate(angles):
                ang = max(SERVOS[i]["min"], min(SERVOS[i]["max"], ang))
                self._cancel_pending(i)
                self.sliders[i].set(ang)
                self.target_labels[i].config(text=f"{ang}")
                self.entries[i].delete(0, tk.END)
                self.entries[i].insert(0, str(ang))
        finally:
            self._suppress_slider_cb = False
        if send and self.connected:
            self._send_batch(angles)

    def _initialize(self):
        self._log("info", "Initialize: set all servos to home (90 45 45 0)")
        self._set_all_targets(HOME_POS, send=True)

    def _reset_servo(self, idx):
        servo = SERVOS[idx]
        init = servo["init"]
        self._cancel_pending(idx)
        self.sliders[idx].set(init)
        self.target_labels[idx].config(text=f"{init}")
        self.entries[idx].delete(0, tk.END)
        self.entries[idx].insert(0, str(init))
        self._log("info", f"S{idx} reset to {init} (send {idx} {init})")
        if self.connected:
            self._send_set(idx, init)

    # ---------------- Logging ----------------
    def _log(self, kind, message):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_lines.append((ts, kind, message))
        if not self.log_text:
            return
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"{ts}  ", ("ts",))
        prefix = {"send": ">>", "recv": "<<", "info": "  ", "warn": "!!", "err": "XX"}.get(kind, "  ")
        self.log_text.insert("end", f" {prefix}  ", (kind,))
        self.log_text.insert("end", f"{message}\n", (kind,))
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self._log_lines.clear()
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _copy_log(self):
        text = "\n".join(f"{ts}  {msg}" for ts, _, msg in self._log_lines)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    # ---------------- Status pill ----------------
    def _set_status(self, state, text):
        color_map = {
            "disconnected":   COLOR_TEXT_DIM,
            "connected_idle": COLOR_WARNING,
            "connected_live": COLOR_SUCCESS,
            "error":          COLOR_DANGER,
        }
        self.status_pill.config(text=f"  {text}  ", fg=color_map.get(state, COLOR_TEXT_DIM))
        self.status_bar_label.config(text=text)

    def _tick_status(self):
        if self.connected:
            if self._last_rx_time and (time.time() - self._last_rx_time) < LIVE_RX_WINDOW_S:
                self._set_status("connected_live", f"Live  {self.port_combo.get()}")
            else:
                self._set_status("connected_idle", f"Connected  {self.port_combo.get()}")
        self.root.after(400, self._tick_status)

    # ---------------- Lifecycle ----------------
    def _on_closing(self):
        try:
            self._disconnect()
        except Exception as exc:
            print(f"Closing error: {exc}")
        try:
            self.root.destroy()
        except Exception:
            pass


def main():
    root = tk.Tk()
    ServoControlApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
