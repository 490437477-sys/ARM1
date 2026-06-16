import re
import threading
import time
import tkinter as tk
from tkinter import ttk

import serial
from serial.tools import list_ports

BAUD_RATE = 9600

SLIDER_DEBOUNCE_MS = 60
SERIAL_READ_TIMEOUT = 0.2
INIT_DELAY_MS = 500

SERVOS = [
    {"name": "S0", "min": 0, "max": 90, "init": 45},
    {"name": "S1", "min": 0, "max": 90, "init": 45},
    {"name": "S2", "min": 0, "max": 90, "init": 0},
    {"name": "S3", "min": 0, "max": 180, "init": 90},
]


class ServoControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Servo Control")
        self.root.geometry("470x580")
        self.root.resizable(False, False)

        self.serial_conn = None
        self.sliders = {}
        self.entries = {}
        self.labels = {}
        self.actual_labels = {}
        self.connected = False
        self.actual_angles = [None] * 4
        self._pending_send = {}
        self._reader_stop = threading.Event()
        self._reader_thread = None
        self._last_rx_time = 0.0

        self.create_connect_ui()
        self._tick_status()

    def get_serial_ports(self):
        try:
            ports = sorted({p.device for p in list_ports.comports()})
            return ports
        except Exception as e:
            print(f"Port scan failed: {e}")
            return []

    def refresh_ports(self):
        ports = self.get_serial_ports()
        current = self.combo.get()
        self.combo["values"] = ports if ports else ["(no ports)"]
        if current in ports:
            self.combo.set(current)
        elif ports:
            self.combo.current(0)
        else:
            self.combo.set("(no ports)")

    def connect(self):
        port = self.combo.get()
        if port == "(no ports)":
            self.status_label.config(text="No ports", foreground="#f44336")
            return
        try:
            self.serial_conn = serial.Serial(port, BAUD_RATE, timeout=SERIAL_READ_TIMEOUT)
            self.serial_conn.reset_input_buffer()
            self.serial_conn.reset_output_buffer()
        except Exception as e:
            print(f"Connect failed: {e}")
            self.status_label.config(text="Failed", foreground="#f44336")
            self.serial_conn = None
            return

        self.connected = True
        self.status_label.config(text="Connected", foreground="#FF9800")
        self.connect_btn.config(text="Disconnect", command=self.disconnect)
        self.combo.config(state="disabled")
        self.refresh_btn.config(state="disabled")

        self._reader_stop.clear()
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

        self.root.after(INIT_DELAY_MS, self.zero_all)

    def disconnect(self):
        self._reader_stop.set()
        if self.serial_conn:
            try:
                self.serial_conn.close()
            except Exception as e:
                print(f"Disconnect error: {e}")
        self.serial_conn = None
        self.connected = False
        self.status_label.config(text="Disconnected", foreground="#888")
        self.connect_btn.config(text="Connect", command=self.connect)
        self.combo.config(state="readonly")
        self.refresh_btn.config(state="normal")

    def send_command(self, servo_index, angle):
        if not (self.serial_conn and self.serial_conn.is_open):
            return
        cmd = f"{servo_index} {angle}\n"
        try:
            self.serial_conn.write(cmd.encode())
        except Exception as e:
            print(f"Send failed: {e}")

    def update_from_slider(self, index, value):
        angle = int(float(value))
        self.labels[index]["text"] = f"{angle} deg"
        self.entries[index].delete(0, tk.END)
        self.entries[index].insert(0, str(angle))
        self._cancel_pending(index)
        self._pending_send[index] = self.root.after(
            SLIDER_DEBOUNCE_MS, lambda i=index, a=angle: self._flush_slider(i, a)
        )

    def _cancel_pending(self, index):
        if index in self._pending_send:
            try:
                self.root.after_cancel(self._pending_send[index])
            except Exception:
                pass
            self._pending_send.pop(index, None)

    def _flush_slider(self, index, angle):
        self._pending_send.pop(index, None)
        self.send_command(index, angle)

    def update_from_entry(self, index):
        try:
            angle = int(self.entries[index].get())
        except ValueError:
            return
        servo = SERVOS[index]
        angle = max(servo["min"], min(servo["max"], angle))
        self.sliders[index].set(angle)
        self.labels[index]["text"] = f"{angle} deg"
        self._cancel_pending(index)
        self.send_command(index, angle)

    def focus_entry(self, event, index):
        self.entries[index].select_all()

    def zero_all(self):
        for i, servo in enumerate(SERVOS):
            self._cancel_pending(i)
            self.sliders[i].set(servo["init"])
            self.labels[i]["text"] = f"{servo['init']} deg"
            self.entries[i].delete(0, tk.END)
            self.entries[i].insert(0, str(servo["init"]))
            self._flush_slider(i, servo["init"])

    def query_all(self):
        if not (self.serial_conn and self.serial_conn.is_open):
            return
        try:
            self.serial_conn.write(b"A\n")
        except Exception as e:
            print(f"Query failed: {e}")

    def _read_loop(self):
        while not self._reader_stop.is_set():
            if not (self.serial_conn and self.serial_conn.is_open):
                break
            try:
                line = self.serial_conn.readline()
                if not line:
                    continue
                text = line.decode("utf-8", errors="ignore").strip()
                if not text:
                    continue
                self._last_rx_time = time.time()
                self.root.after(0, self._handle_line, text)
            except Exception as e:
                if not self._reader_stop.is_set():
                    print(f"Read error: {e}")
                break

    def _handle_line(self, line):
        m = re.match(r"S\s*(\d+)\s*->\s*(\d+)", line)
        if m:
            idx, angle = int(m.group(1)), int(m.group(2))
            if 0 <= idx < 4:
                self.actual_angles[idx] = angle
                self.actual_labels[idx]["text"] = f"actual:{angle}"
            return
        for m in re.finditer(r"S\s*(\d+)\s*:\s*(\d+)", line):
            idx, angle = int(m.group(1)), int(m.group(2))
            if 0 <= idx < 4:
                self.actual_angles[idx] = angle
                self.actual_labels[idx]["text"] = f"actual:{angle}"

    def _tick_status(self):
        if self.connected:
            if self._last_rx_time and (time.time() - self._last_rx_time) < 2.0:
                self.status_label.config(text="Connected (live)", foreground="#4CAF50")
            else:
                self.status_label.config(text="Connected (no response)", foreground="#FF9800")
        self.root.after(500, self._tick_status)

    def create_connect_ui(self):
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Servo Control Panel", font=("Arial", 16, "bold")).pack(pady=(0, 15))

        connect_frame = ttk.Frame(main_frame)
        connect_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(connect_frame, text="Port:").pack(side=tk.LEFT)
        self.combo = ttk.Combobox(connect_frame, width=12, state="readonly")
        ports = self.get_serial_ports()
        self.combo["values"] = ports if ports else ["(no ports)"]
        if ports:
            self.combo.current(0)
        else:
            self.combo.set("(no ports)")
        self.combo.pack(side=tk.LEFT, padx=5)

        self.refresh_btn = ttk.Button(connect_frame, text="Refresh", command=self.refresh_ports, width=6)
        self.refresh_btn.pack(side=tk.LEFT, padx=2)

        self.connect_btn = ttk.Button(connect_frame, text="Connect", command=self.connect, width=8)
        self.connect_btn.pack(side=tk.LEFT, padx=5)

        self.status_label = ttk.Label(connect_frame, text="Disconnected", foreground="#888")
        self.status_label.pack(side=tk.LEFT, padx=10)

        for i, servo in enumerate(SERVOS):
            servo_frame = ttk.Frame(main_frame)
            servo_frame.pack(fill=tk.X, pady=6)

            name_label = ttk.Label(servo_frame, text=servo["name"], width=4, font=("Arial", 12, "bold"))
            name_label.pack(side=tk.LEFT)

            slider = ttk.Scale(
                servo_frame,
                from_=servo["min"],
                to=servo["max"],
                value=servo["init"],
                orient=tk.HORIZONTAL,
                length=130,
                command=lambda v, idx=i: self.update_from_slider(idx, v)
            )
            slider.pack(side=tk.LEFT, padx=6)
            self.sliders[i] = slider

            angle_label = ttk.Label(servo_frame, text=f"{servo['init']} deg", width=7, font=("Arial", 11))
            angle_label.pack(side=tk.LEFT)
            self.labels[i] = angle_label

            entry = ttk.Entry(servo_frame, width=5, font=("Arial", 11), justify="center")
            entry.insert(0, str(servo["init"]))
            entry.pack(side=tk.LEFT, padx=(6, 0))
            entry.bind("<Return>", lambda e, idx=i: self.update_from_entry(idx))
            entry.bind("<FocusIn>", lambda e, idx=i: self.focus_entry(e, idx))
            self.entries[i] = entry

            actual_label = ttk.Label(
                servo_frame, text="actual:--", width=9,
                font=("Arial", 10), foreground="#666"
            )
            actual_label.pack(side=tk.LEFT, padx=(6, 0))
            self.actual_labels[i] = actual_label

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=20)

        ttk.Button(button_frame, text="Reset", command=self.zero_all, width=8).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_frame, text="Query", command=self.query_all, width=8).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_frame, text="Exit", command=self.on_closing, width=8).pack(side=tk.LEFT, padx=4)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        try:
            self.disconnect()
        except Exception as e:
            print(f"Closing error: {e}")
        try:
            self.root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    root = tk.Tk()
    app = ServoControlApp(root)
    root.mainloop()