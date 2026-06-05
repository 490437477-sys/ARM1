import serial
import tkinter as tk
from tkinter import ttk

BAUD_RATE = 9600

SERVOS = [
    {'name': 'S0', 'min': 0, 'max': 90, 'init': 45},
    {'name': 'S1', 'min': 0, 'max': 90, 'init': 45},
    {'name': 'S2', 'min': 0, 'max': 90, 'init': 0},
    {'name': 'S3', 'min': 0, 'max': 180, 'init': 90},
]

class ServoControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("舵机控制")
        self.root.geometry("420x520")
        self.root.resizable(False, False)

        self.serial_conn = None
        self.sliders = {}
        self.entries = {}
        self.labels = {}
        self.connected = False

        self.create_connect_ui()

    def get_serial_ports(self):
        ports = []
        for i in range(256):
            try:
                s = serial.Serial(f'COM{i+1}')
                ports.append(f'COM{i+1}')
                s.close()
            except:
                pass
        return ports if ports else ['COM3']

    def refresh_ports(self):
        ports = self.get_serial_ports()
        current = self.combo.get()
        self.combo['values'] = ports
        if current in ports:
            self.combo.set(current)
        else:
            self.combo.current(0)

    def connect(self):
        port = self.combo.get()
        try:
            self.serial_conn = serial.Serial(port, BAUD_RATE, timeout=1)
            self.serial_conn.flushInput()
            self.connected = True
            self.status_label.config(text="已连接", foreground="#4CAF50")
            self.connect_btn.config(text="断开", command=self.disconnect)
            self.combo.config(state='disabled')
            self.refresh_btn.config(state='disabled')
            self.zero_all()
        except Exception as e:
            self.status_label.config(text="连接失败", foreground="#f44336")

    def disconnect(self):
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        self.connected = False
        self.status_label.config(text="未连接", foreground="#888")
        self.connect_btn.config(text="连接", command=self.connect)
        self.combo.config(state='readonly')
        self.refresh_btn.config(state='normal')

    def send_command(self, servo_index, angle):
        if self.serial_conn and self.serial_conn.is_open:
            cmd = f"{servo_index} {angle}\n"
            self.serial_conn.write(cmd.encode())
            self.serial_conn.flush()

    def update_from_slider(self, index, value):
        angle = int(float(value))
        self.labels[index]['text'] = f"{angle}°"
        self.entries[index].delete(0, tk.END)
        self.entries[index].insert(0, str(angle))
        self.send_command(index, angle)

    def update_from_entry(self, index):
        try:
            angle = int(self.entries[index].get())
            servo = SERVOS[index]
            angle = max(servo['min'], min(servo['max'], angle))
            self.sliders[index].set(angle)
            self.labels[index]['text'] = f"{angle}°"
            self.send_command(index, angle)
        except ValueError:
            pass

    def focus_entry(self, event, index):
        self.entries[index].select_all()

    def zero_all(self):
        for i, servo in enumerate(SERVOS):
            self.sliders[i].set(servo['init'])
            self.labels[i]['text'] = f"{servo['init']}°"
            self.entries[i].delete(0, tk.END)
            self.entries[i].insert(0, str(servo['init']))
            self.send_command(i, servo['init'])

    def create_connect_ui(self):
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="舵机控制面板", font=('Arial', 16, 'bold')).pack(pady=(0, 15))

        connect_frame = ttk.Frame(main_frame)
        connect_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(connect_frame, text="端口:").pack(side=tk.LEFT)
        self.combo = ttk.Combobox(connect_frame, width=10, state='readonly')
        self.combo['values'] = self.get_serial_ports()
        self.combo.current(0)
        self.combo.pack(side=tk.LEFT, padx=5)

        self.refresh_btn = ttk.Button(connect_frame, text="刷新", command=self.refresh_ports, width=6)
        self.refresh_btn.pack(side=tk.LEFT, padx=2)

        self.connect_btn = ttk.Button(connect_frame, text="连接", command=self.connect, width=8)
        self.connect_btn.pack(side=tk.LEFT, padx=5)

        self.status_label = ttk.Label(connect_frame, text="未连接", foreground="#888")
        self.status_label.pack(side=tk.LEFT, padx=10)

        for i, servo in enumerate(SERVOS):
            servo_frame = ttk.Frame(main_frame)
            servo_frame.pack(fill=tk.X, pady=6)

            name_label = ttk.Label(servo_frame, text=servo['name'], width=4, font=('Arial', 12, 'bold'))
            name_label.pack(side=tk.LEFT)

            slider = ttk.Scale(
                servo_frame,
                from_=servo['min'],
                to=servo['max'],
                value=servo['init'],
                orient=tk.HORIZONTAL,
                length=160,
                command=lambda v, idx=i: self.update_from_slider(idx, v)
            )
            slider.pack(side=tk.LEFT, padx=8)
            self.sliders[i] = slider

            angle_label = ttk.Label(servo_frame, text=f"{servo['init']}°", width=5, font=('Arial', 12))
            angle_label.pack(side=tk.LEFT)
            self.labels[i] = angle_label

            entry = ttk.Entry(servo_frame, width=5, font=('Arial', 12), justify='center')
            entry.insert(0, str(servo['init']))
            entry.pack(side=tk.LEFT, padx=(8, 0))
            entry.bind('<Return>', lambda e, idx=i: self.update_from_entry(idx))
            entry.bind('<FocusIn>', lambda e, idx=i: self.focus_entry(e, idx))
            self.entries[i] = entry

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=25)

        ttk.Button(button_frame, text="归零", command=self.zero_all, width=10).pack(side=tk.LEFT, padx=8)
        ttk.Button(button_frame, text="退出", command=self.on_closing, width=10).pack(side=tk.LEFT, padx=8)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        self.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = ServoControlApp(root)
    root.mainloop()