import json
import sys
import re
import uuid
import tkinter as tk
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable


# A strict 24-hour time input keeps scheduling rules predictable and easy to test.
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
REPEAT_ONCE = "once"
REPEAT_WEEKLY = "weekly"
WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WINDOWS_APP_ID = "SilentScreen.Alarm.Desktop"


def default_data_file() -> Path:
    """Store data next to the script in source mode and next to the exe when packaged."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).with_name("alarms.json")
    return Path(__file__).with_name("alarms.json")


DATA_FILE = default_data_file()


@dataclass(eq=True)
class Alarm:
    """Persistent alarm configuration stored in alarms.json."""

    id: str
    name: str
    time_text: str
    repeat_type: str = REPEAT_ONCE
    weekdays: list[int] = field(default_factory=list)
    enabled: bool = True

    def next_trigger_after(self, now: datetime) -> datetime | None:
        """Return the next scheduled datetime after now, or None if inactive."""
        if not self.enabled or not TIME_PATTERN.match(self.time_text):
            return None

        hour, minute = map(int, self.time_text.split(":"))
        if self.repeat_type == REPEAT_WEEKLY:
            days = sorted(day for day in self.weekdays if 0 <= day <= 6)
            if not days:
                return None
            # Look ahead one full week. Offset 0 allows "later today" matches.
            for offset in range(8):
                candidate_day = now + timedelta(days=offset)
                if candidate_day.weekday() not in days:
                    continue
                candidate = candidate_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if candidate > now:
                    return candidate
            return None

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target

    @property
    def repeat_label(self) -> str:
        if self.repeat_type == REPEAT_WEEKLY:
            if not self.weekdays:
                return "No weekdays"
            return ", ".join(WEEKDAY_LABELS[index] for index in sorted(self.weekdays))
        return "Once"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Alarm":
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            name=str(data.get("name") or "Alarm"),
            time_text=str(data.get("time_text") or "09:00"),
            repeat_type=str(data.get("repeat_type") or REPEAT_ONCE),
            weekdays=[int(day) for day in data.get("weekdays", []) if isinstance(day, int)],
            enabled=bool(data.get("enabled", True)),
        )


def load_alarms(path: Path = DATA_FILE) -> list[Alarm]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    alarms: list[Alarm] = []
    for item in raw:
        if isinstance(item, dict):
            alarms.append(Alarm.from_dict(item))
    return alarms


def save_alarms(path: Path, alarms: list[Alarm]) -> None:
    path.write_text(
        json.dumps([alarm.to_dict() for alarm in alarms], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def target_from_duration(now: datetime, hours: int = 0, minutes: int = 0) -> datetime:
    return now + timedelta(hours=max(0, hours), minutes=max(0, minutes))


def target_from_time_text(value: str, now: datetime | None = None) -> datetime | None:
    if not TIME_PATTERN.match(value):
        return None
    base = now or datetime.now()
    hour, minute = map(int, value.split(":"))
    target = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= base:
        target += timedelta(days=1)
    return target


@dataclass
class RuntimeAlarm:
    """In-memory alarm used for temporary timers and snoozed reminders."""

    target: datetime
    label: str
    persistent_id: str | None = None


def remove_runtime_alarm(alarms: list[RuntimeAlarm], index: int) -> list[RuntimeAlarm]:
    return [alarm for current, alarm in enumerate(alarms) if current != index]


def remove_items_by_indexes[T](items: list[T], indexes: list[int]) -> list[T]:
    removed = set(indexes)
    return [item for index, item in enumerate(items) if index not in removed]


def configure_windows_app_identity() -> None:
    """Set a stable Windows taskbar identity before Tk creates the main window."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except (AttributeError, OSError):
        pass


class RoundedPanel(tk.Frame):
    """Canvas-backed rounded container for card-like Tkinter sections."""

    def __init__(
        self,
        parent: tk.Widget,
        fill: str = "#ffffff",
        background: str = "#eef1f5",
        radius: int = 16,
        padding: int = 14,
        height: int | None = None,
    ) -> None:
        super().__init__(parent, bg=background, highlightthickness=0)
        self.fill = fill
        self.radius = radius
        self.padding = padding
        canvas_options: dict[str, object] = {"bg": background, "highlightthickness": 0, "bd": 0}
        if height is not None:
            canvas_options["height"] = height
        self.canvas = tk.Canvas(self, **canvas_options)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.content = tk.Frame(self.canvas, bg=fill, highlightthickness=0)
        self.window_id = self.canvas.create_window(
            (self.padding, self.padding),
            window=self.content,
            anchor="nw",
        )
        self.canvas.bind("<Configure>", self._redraw)

    def _redraw(self, event: tk.Event) -> None:
        width = max(1, event.width)
        height = max(1, event.height)
        self.canvas.delete("panel")
        self._rounded_rect(1, 1, width - 1, height - 1, self.radius, fill=self.fill, outline="#d9e0ea", tags="panel")
        self.canvas.tag_lower("panel")
        self.canvas.itemconfigure(self.window_id, width=max(1, width - self.padding * 2), height=max(1, height - self.padding * 2))

    def _rounded_rect(self, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs: object) -> None:
        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        self.canvas.create_polygon(points, smooth=True, **kwargs)


class AlarmApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("SilentScreen Alarm")
        self.root.geometry("1040x720")
        self.root.minsize(760, 560)

        self.alarms = load_alarms()
        self.runtime_alarms: list[RuntimeAlarm] = []
        # Prevent persistent alarms from firing repeatedly within the same minute.
        self.fired_alarm_keys: set[tuple[str, str]] = set()
        self.tick_job: str | None = None
        self.alert_window: tk.Toplevel | None = None

        self.clock_var = tk.StringVar()
        self.next_var = tk.StringVar(value="Next alarm: none")
        self.status_var = tk.StringVar(value="Persistent alarms are saved automatically. Temporary alarms only last for this session.")
        self.name_var = tk.StringVar(value="Alarm")
        self.time_var = tk.StringVar(value=(datetime.now() + timedelta(minutes=1)).strftime("%H:%M"))
        self.repeat_var = tk.StringVar(value=REPEAT_ONCE)
        self.weekday_vars = [tk.BooleanVar(value=False) for _ in WEEKDAY_LABELS]
        self.temp_hours_var = tk.StringVar(value="0")
        self.temp_minutes_var = tk.StringVar(value="25")
        self.temp_time_var = tk.StringVar(value=(datetime.now() + timedelta(minutes=30)).strftime("%H:%M"))
        self.quick_choice_var = tk.StringVar(value="Selected: 25 minutes")
        self.editing_id: str | None = None
        self.current_page = "long"
        self.tab_canvases: dict[str, tk.Canvas] = {}
        self.app_icon = self._create_app_icon()
        self.root.iconphoto(True, self.app_icon)

        self._configure_style()
        self._build_main_window()
        self._refresh_alarm_list()
        self._refresh_runtime_list()
        self._tick()

    def _configure_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#eef1f5")
        style.configure("Surface.TFrame", background="#ffffff")
        style.configure("TLabel", background="#eef1f5", foreground="#1f2937", font=("Microsoft YaHei UI", 10))
        style.configure("Surface.TLabel", background="#ffffff", foreground="#1f2937", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", background="#eef1f5", font=("Microsoft YaHei UI", 17, "bold"), foreground="#0f172a")
        style.configure("BrandSub.TLabel", background="#eef1f5", foreground="#64748b", font=("Microsoft YaHei UI", 9))
        style.configure("Section.TLabel", background="#ffffff", font=("Microsoft YaHei UI", 12, "bold"), foreground="#111827")
        style.configure("Clock.TLabel", background="#ffffff", font=("Consolas", 20, "bold"), foreground="#0f172a")
        style.configure("Next.TLabel", background="#ffffff", foreground="#475569", font=("Microsoft YaHei UI", 9))
        style.configure("Muted.TLabel", background="#ffffff", foreground="#64748b", font=("Microsoft YaHei UI", 9))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(10, 6))
        style.configure("TRadiobutton", background="#ffffff", foreground="#1f2937", font=("Microsoft YaHei UI", 10))
        style.configure("TCheckbutton", background="#ffffff", foreground="#1f2937", font=("Microsoft YaHei UI", 10))
        style.configure("Accent.TButton", background="#2563eb", foreground="#ffffff")
        style.configure("Danger.TButton", background="#ef4444", foreground="#ffffff")
        style.configure("Treeview", rowheight=30, font=("Microsoft YaHei UI", 10), background="#ffffff", fieldbackground="#ffffff")
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Accent.TButton", background=[("active", "#1d4ed8")])
        style.map("Danger.TButton", background=[("active", "#dc2626")])

    def _create_app_icon(self) -> tk.PhotoImage:
        return self._build_icon_image()

    @staticmethod
    def _build_icon_image() -> tk.PhotoImage:
        image = tk.PhotoImage(width=48, height=48)
        # Build a small alarm-clock icon directly in memory so packaging stays single-file.
        for y in range(48):
            for x in range(48):
                dx = x - 24
                dy = y - 26
                color = ""
                if (x - 12) ** 2 + (y - 11) ** 2 <= 36 or (x - 36) ** 2 + (y - 11) ** 2 <= 36:
                    color = "#93c5fd"
                if dx * dx + dy * dy <= 256:
                    color = "#2563eb"
                if dx * dx + dy * dy <= 100:
                    color = "#ffffff"
                if 22 <= x <= 26 and 18 <= y <= 27:
                    color = "#0f172a"
                if 24 <= x <= 32 and 28 <= y <= 32 and abs((y - 28) - (x - 24) * 0.5) <= 2:
                    color = "#0f172a"
                if color:
                    image.put(color, (x, y))
        return image

    def _build_main_window(self) -> None:
        shell = ttk.Frame(self.root, padding=12)
        shell.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(shell)
        header.pack(fill=tk.X)
        tk.Label(header, image=self.app_icon, bg="#eef1f5").pack(side=tk.LEFT, padx=(0, 10))
        brand = ttk.Frame(header)
        brand.pack(side=tk.LEFT)
        ttk.Label(brand, text="SilentScreen Alarm", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(brand, text="Silent full-screen reminders", style="BrandSub.TLabel").pack(anchor=tk.W)

        summary_panel = RoundedPanel(shell, padding=12, height=66)
        summary = summary_panel.content
        summary_panel.pack(fill=tk.X, pady=(8, 8))
        ttk.Label(summary, textvariable=self.clock_var, style="Clock.TLabel").pack(anchor=tk.W)
        ttk.Label(summary, textvariable=self.next_var, style="Next.TLabel").pack(anchor=tk.W, pady=(2, 0))

        self.tab_bar = ttk.Frame(shell)
        self.tab_bar.pack(fill=tk.X, pady=(0, 8))
        self.tab_bar.columnconfigure(0, weight=7)
        self.tab_bar.columnconfigure(1, weight=3)
        self._build_page_tab(self.tab_bar, "long", "Persistent Alarms", 0)
        self._build_page_tab(self.tab_bar, "temp", "Temporary Alarms", 1)

        self.page_container = ttk.Frame(shell)
        self.page_container.pack(fill=tk.BOTH, expand=True)
        self.page_container.rowconfigure(0, weight=1)
        self.page_container.columnconfigure(0, weight=1)

        self.long_page = ttk.Frame(self.page_container, padding=0)
        self.temp_page = ttk.Frame(self.page_container, padding=0)
        self._build_long_alarm_page(self.long_page)
        self._build_temp_alarm_page(self.temp_page)
        self.long_page.grid(row=0, column=0, sticky="nsew")
        self.temp_page.grid(row=0, column=0, sticky="nsew")
        self._select_page("long")

        ttk.Label(shell, textvariable=self.status_var, foreground="#64748b").pack(anchor=tk.W, pady=(8, 0))

    def _build_page_tab(self, parent: tk.Widget, page: str, title: str, column: int) -> None:
        canvas = tk.Canvas(parent, height=42, bg="#eef1f5", highlightthickness=0, bd=0, cursor="hand2")
        canvas.grid(row=0, column=column, sticky="ew", padx=(0, 8 if column == 0 else 0))
        canvas.bind("<Button-1>", lambda _event: self._select_page(page))
        canvas.bind("<Configure>", lambda _event, key=page, text=title: self._draw_page_tab(key, text))
        self.tab_canvases[page] = canvas

    def _select_page(self, page: str) -> None:
        self.current_page = page
        # The active tab takes 70% of the title bar and the inactive tab takes 30%.
        self.tab_bar.columnconfigure(0, weight=7 if page == "long" else 3)
        self.tab_bar.columnconfigure(1, weight=7 if page == "temp" else 3)
        if page == "long":
            self.long_page.tkraise()
        else:
            self.temp_page.tkraise()
        self._draw_page_tab("long", "Persistent Alarms")
        self._draw_page_tab("temp", "Temporary Alarms")

    def _draw_page_tab(self, page: str, title: str) -> None:
        canvas = self.tab_canvases.get(page)
        if canvas is None:
            return
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        active = page == self.current_page
        fill = "#2563eb" if active else "#dbeafe"
        text_fill = "#ffffff" if active else "#64748b"
        font = ("Microsoft YaHei UI", 12 if active else 10, "bold")
        canvas.delete("all")
        self._draw_rounded_rect(canvas, 1, 1, width - 1, height - 1, 14, fill=fill, outline="")
        canvas.create_text(width // 2, height // 2, text=title, fill=text_fill, font=font)

    @staticmethod
    def _draw_rounded_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs: object) -> None:
        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        canvas.create_polygon(points, smooth=True, **kwargs)

    def _build_long_alarm_page(self, parent: tk.Widget) -> None:
        parent.columnconfigure(0, weight=3, minsize=300)
        parent.columnconfigure(1, weight=2, minsize=220)
        parent.rowconfigure(0, weight=1)

        list_shell = RoundedPanel(parent)
        list_shell.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        list_panel = list_shell.content
        list_panel.rowconfigure(1, weight=1)
        list_panel.columnconfigure(0, weight=1)
        ttk.Label(list_panel, text="Persistent Alarms", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W)

        columns = ("time", "name", "repeat", "enabled")
        self.alarm_tree = ttk.Treeview(list_panel, columns=columns, show="headings", height=12, selectmode="extended")
        for key, title, width in (
            ("time", "Time", 80),
            ("name", "Name", 130),
            ("repeat", "Repeat", 180),
            ("enabled", "Status", 70),
        ):
            self.alarm_tree.heading(key, text=title)
            self.alarm_tree.column(key, width=width, anchor=tk.W)
        self.alarm_tree.grid(row=1, column=0, sticky="nsew", pady=(10, 10))
        self.alarm_tree.bind("<<TreeviewSelect>>", lambda _event: self._load_selected_alarm())

        actions = ttk.Frame(list_panel, style="Surface.TFrame")
        actions.grid(row=2, column=0, sticky="ew")
        ttk.Button(actions, text="Enable / Disable", command=self.toggle_selected_alarm).pack(side=tk.LEFT)
        ttk.Button(actions, text="Delete Selected", style="Danger.TButton", command=self.delete_selected_alarm).pack(side=tk.LEFT, padx=(8, 0))

        form_shell = RoundedPanel(parent, padding=14)
        form_shell.grid(row=0, column=1, sticky="nsew")
        form = form_shell.content
        ttk.Label(form, text="Add / Edit", style="Section.TLabel").pack(anchor=tk.W)
        self._form_label(form, "Name")
        ttk.Entry(form, textvariable=self.name_var, width=24).pack(fill=tk.X)
        self._form_label(form, "Time HH:MM")
        ttk.Entry(form, textvariable=self.time_var, width=24, font=("Consolas", 12)).pack(fill=tk.X)

        self._form_label(form, "Type")
        ttk.Radiobutton(form, text="Once", value=REPEAT_ONCE, variable=self.repeat_var).pack(anchor=tk.W)
        ttk.Radiobutton(form, text="Repeat weekly", value=REPEAT_WEEKLY, variable=self.repeat_var).pack(anchor=tk.W)

        week_grid = ttk.Frame(form, style="Surface.TFrame")
        week_grid.pack(fill=tk.X, pady=(6, 8))
        for index, label in enumerate(WEEKDAY_LABELS):
            ttk.Checkbutton(week_grid, text=label, variable=self.weekday_vars[index]).grid(
                row=index // 2, column=index % 2, sticky=tk.W, padx=(0, 8), pady=1
            )

        ttk.Button(form, text="Save Alarm", style="Accent.TButton", command=self.save_form_alarm).pack(fill=tk.X, pady=(2, 6))
        ttk.Button(form, text="Clear Form", command=self.reset_form).pack(fill=tk.X)

    def _build_temp_alarm_page(self, parent: tk.Widget) -> None:
        parent.columnconfigure(0, weight=1, minsize=260)
        parent.columnconfigure(1, weight=1, minsize=260)
        parent.rowconfigure(1, weight=1)

        quick_shell = RoundedPanel(parent)
        quick_shell.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        quick_panel = quick_shell.content
        ttk.Label(quick_panel, text="Quick Timers", style="Section.TLabel").pack(anchor=tk.W)
        quick_grid = ttk.Frame(quick_panel, style="Surface.TFrame")
        quick_grid.pack(fill=tk.X, pady=(10, 0))
        for index, minutes in enumerate((5, 25, 45, 60)):
            button = ttk.Button(quick_grid, text=f"{minutes} min", command=lambda m=minutes: self._select_quick_duration(m))
            button.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 8), pady=(0, 8))
        quick_grid.columnconfigure(0, weight=1)
        quick_grid.columnconfigure(1, weight=1)
        ttk.Label(quick_panel, textvariable=self.quick_choice_var, style="Muted.TLabel").pack(anchor=tk.W, pady=(2, 8))
        ttk.Button(quick_panel, text="Start Selected Timer", style="Accent.TButton", command=self._confirm_quick_duration).pack(fill=tk.X)

        custom_shell = RoundedPanel(parent)
        custom_shell.grid(row=0, column=1, sticky="nsew", pady=(0, 10))
        custom_panel = custom_shell.content
        ttk.Label(custom_panel, text="Custom", style="Section.TLabel").pack(anchor=tk.W)
        duration = ttk.Frame(custom_panel, style="Surface.TFrame")
        duration.pack(fill=tk.X, pady=(10, 8))
        ttk.Entry(duration, textvariable=self.temp_hours_var, width=6).pack(side=tk.LEFT)
        ttk.Label(duration, text="hours", style="Surface.TLabel").pack(side=tk.LEFT, padx=(5, 12))
        ttk.Entry(duration, textvariable=self.temp_minutes_var, width=6).pack(side=tk.LEFT)
        ttk.Label(duration, text="minutes", style="Surface.TLabel").pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(custom_panel, text="Start Countdown", style="Accent.TButton", command=self._add_temp_duration_from_vars).pack(
            fill=tk.X, pady=(2, 12)
        )
        ttk.Label(custom_panel, text="Specific Time HH:MM", style="Muted.TLabel").pack(anchor=tk.W)
        ttk.Entry(custom_panel, textvariable=self.temp_time_var, font=("Consolas", 12)).pack(fill=tk.X, pady=(6, 8))
        ttk.Button(custom_panel, text="Start at Time", command=lambda: self._add_temp_time(self.temp_time_var.get().strip())).pack(
            fill=tk.X
        )

        runtime_shell = RoundedPanel(parent)
        runtime_shell.grid(row=1, column=0, columnspan=2, sticky="nsew")
        runtime_panel = runtime_shell.content
        runtime_panel.rowconfigure(1, weight=1)
        runtime_panel.columnconfigure(0, weight=1)
        ttk.Label(runtime_panel, text="Active Temporary Alarms", style="Section.TLabel").grid(row=0, column=0, sticky=tk.W)
        self.runtime_tree = ttk.Treeview(runtime_panel, columns=("label", "target"), show="headings", height=6, selectmode="extended")
        self.runtime_tree.heading("label", text="Name")
        self.runtime_tree.heading("target", text="Target Time")
        self.runtime_tree.column("label", width=220, anchor=tk.W)
        self.runtime_tree.column("target", width=200, anchor=tk.W)
        self.runtime_tree.grid(row=1, column=0, sticky="nsew", pady=(10, 10))
        ttk.Button(runtime_panel, text="Delete Selected Temporary Alarms", style="Danger.TButton", command=self.delete_selected_runtime_alarm).grid(
            row=2, column=0, sticky=tk.W
        )

    @staticmethod
    def _form_label(parent: tk.Widget, text: str) -> None:
        ttk.Label(parent, text=text, style="Surface.TLabel").pack(anchor=tk.W, pady=(9, 2))

    def _tick(self) -> None:
        now = datetime.now()
        self.clock_var.set(now.strftime("%Y-%m-%d %A %H:%M:%S"))
        due = self._find_due_alarm(now)
        if due is not None:
            self._handle_due_alarm(due)
        self._refresh_next_label(now)
        self.tick_job = self.root.after(1000, self._tick)

    def _find_due_alarm(self, now: datetime) -> RuntimeAlarm | None:
        """Check temporary alarms first, then persistent alarms for the current tick."""
        for runtime in self.runtime_alarms:
            if runtime.target <= now:
                return runtime
        for alarm in self.alarms:
            target = self._due_target_for_alarm(alarm, now)
            if target is not None:
                return RuntimeAlarm(target=target, label=alarm.name, persistent_id=alarm.id)
        return None

    def _due_target_for_alarm(self, alarm: Alarm, now: datetime) -> datetime | None:
        """Detect whether a persistent alarm is due during the current minute."""
        if not alarm.enabled or not TIME_PATTERN.match(alarm.time_text):
            return None
        hour, minute = map(int, alarm.time_text.split(":"))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if not (target <= now < target + timedelta(minutes=1)):
            return None
        if alarm.repeat_type == REPEAT_WEEKLY and now.weekday() not in alarm.weekdays:
            return None
        key = (alarm.id, target.strftime("%Y-%m-%d %H:%M"))
        if key in self.fired_alarm_keys:
            return None
        self.fired_alarm_keys.add(key)
        return target

    def _handle_due_alarm(self, runtime: RuntimeAlarm) -> None:
        self.runtime_alarms = [item for item in self.runtime_alarms if item is not runtime]
        self._refresh_runtime_list()
        if runtime.persistent_id is not None:
            alarm = self._alarm_by_id(runtime.persistent_id)
            if alarm and alarm.repeat_type == REPEAT_ONCE:
                # One-time alarms remain in the list but turn off after firing.
                alarm.enabled = False
                save_alarms(DATA_FILE, self.alarms)
                self._refresh_alarm_list()
        self._show_alert(runtime.label)

    def _refresh_next_label(self, now: datetime | None = None) -> None:
        base = now or datetime.now()
        # Merge both alarm sources so the summary always shows the true next reminder.
        candidates = [(runtime.target, runtime.label) for runtime in self.runtime_alarms]
        for alarm in self.alarms:
            target = alarm.next_trigger_after(base)
            if target is not None:
                candidates.append((target, alarm.name))
        if not candidates:
            self.next_var.set("Next alarm: none")
            return
        target, label = min(candidates, key=lambda item: item[0])
        remaining = self._format_remaining(target - base)
        self.next_var.set(f"Next alarm: {label} / {target:%Y-%m-%d %H:%M} / in {remaining}")

    def _refresh_alarm_list(self) -> None:
        for item in self.alarm_tree.get_children():
            self.alarm_tree.delete(item)
        for alarm in sorted(self.alarms, key=lambda item: item.time_text):
            self.alarm_tree.insert(
                "",
                tk.END,
                iid=alarm.id,
                values=(alarm.time_text, alarm.name, alarm.repeat_label, "Enabled" if alarm.enabled else "Disabled"),
            )

    def _refresh_runtime_list(self) -> None:
        for item in self.runtime_tree.get_children():
            self.runtime_tree.delete(item)
        for index, alarm in enumerate(sorted(self.runtime_alarms, key=lambda item: item.target)):
            self.runtime_tree.insert("", tk.END, iid=str(index), values=(alarm.label, alarm.target.strftime("%Y-%m-%d %H:%M")))

    def save_form_alarm(self) -> None:
        time_text = self.time_var.get().strip()
        if not TIME_PATTERN.match(time_text):
            messagebox.showerror("Invalid time", "Enter HH:MM, for example 09:30 or 23:05.")
            return
        weekdays = [index for index, var in enumerate(self.weekday_vars) if var.get()]
        repeat_type = self.repeat_var.get()
        if repeat_type == REPEAT_WEEKLY and not weekdays:
            messagebox.showerror("Missing weekdays", "Select at least one day for weekly repeats.")
            return
        name = self.name_var.get().strip() or "Alarm"
        alarm = Alarm(
            id=self.editing_id or uuid.uuid4().hex,
            name=name,
            time_text=time_text,
            repeat_type=repeat_type,
            weekdays=weekdays,
            enabled=True,
        )
        existing = self._alarm_by_id(alarm.id)
        if existing:
            self.alarms[self.alarms.index(existing)] = alarm
        else:
            self.alarms.append(alarm)
        save_alarms(DATA_FILE, self.alarms)
        self.status_var.set(f"Saved persistent alarm: {alarm.name} {alarm.time_text}")
        self.reset_form()
        self._refresh_alarm_list()
        self._refresh_next_label()

    def reset_form(self) -> None:
        self.editing_id = None
        self.name_var.set("Alarm")
        self.time_var.set((datetime.now() + timedelta(minutes=1)).strftime("%H:%M"))
        self.repeat_var.set(REPEAT_ONCE)
        for var in self.weekday_vars:
            var.set(False)

    def _load_selected_alarm(self) -> None:
        # Multi-select is reserved for batch deletion; editing requires one selected row.
        if len(self.alarm_tree.selection()) != 1:
            return
        selected = self._selected_alarm()
        if not selected:
            return
        self.editing_id = selected.id
        self.name_var.set(selected.name)
        self.time_var.set(selected.time_text)
        self.repeat_var.set(selected.repeat_type)
        for index, var in enumerate(self.weekday_vars):
            var.set(index in selected.weekdays)

    def toggle_selected_alarm(self) -> None:
        selected = self._selected_alarm()
        if not selected:
            return
        selected.enabled = not selected.enabled
        save_alarms(DATA_FILE, self.alarms)
        self._refresh_alarm_list()
        self._refresh_next_label()

    def delete_selected_alarm(self) -> None:
        selected_ids = list(self.alarm_tree.selection())
        if not selected_ids:
            return
        selected_set = set(selected_ids)
        self.alarms = [alarm for alarm in self.alarms if alarm.id not in selected_set]
        save_alarms(DATA_FILE, self.alarms)
        self.reset_form()
        self._refresh_alarm_list()
        self._refresh_next_label()
        self.status_var.set(f"Deleted {len(selected_ids)} persistent alarm(s).")

    def _selected_alarm(self) -> Alarm | None:
        selected = self.alarm_tree.selection()
        if not selected:
            return None
        return self._alarm_by_id(selected[0])

    def _alarm_by_id(self, alarm_id: str) -> Alarm | None:
        return next((alarm for alarm in self.alarms if alarm.id == alarm_id), None)

    def _select_quick_duration(self, minutes: int) -> None:
        # Quick presets fill the custom countdown fields but do not start automatically.
        self.temp_hours_var.set(str(minutes // 60))
        self.temp_minutes_var.set(str(minutes % 60))
        self.quick_choice_var.set(f"Selected: {minutes} minutes")
        self.status_var.set("Quick timer selected. Click start to run it.")

    def _confirm_quick_duration(self) -> None:
        self._add_temp_duration_from_vars()

    def _add_temp_duration_from_vars(self) -> None:
        try:
            hours = int(self.temp_hours_var.get() or "0")
            minutes = int(self.temp_minutes_var.get() or "0")
        except ValueError:
            messagebox.showerror("Invalid input", "Hours and minutes must be numbers.")
            return
        self._add_temp_duration(hours, minutes)

    def _add_temp_duration(self, hours: int, minutes: int) -> None:
        if hours <= 0 and minutes <= 0:
            messagebox.showerror("Invalid input", "Temporary alarms must be longer than 0 minutes.")
            return
        target = target_from_duration(datetime.now(), hours, minutes)
        label = self._duration_label(hours, minutes)
        self.runtime_alarms.append(RuntimeAlarm(target=target, label=f"Temporary Alarm {label}"))
        self.status_var.set(f"Temporary alarm set: {target:%Y-%m-%d %H:%M}")
        self._refresh_next_label()
        self._refresh_runtime_list()

    def _add_temp_time(self, value: str) -> None:
        target = target_from_time_text(value)
        if target is None:
            messagebox.showerror("Invalid time", "Enter HH:MM, for example 09:30 or 23:05.")
            return
        self.runtime_alarms.append(RuntimeAlarm(target=target, label=f"Temporary Alarm {value}"))
        self.status_var.set(f"Temporary alarm set: {target:%Y-%m-%d %H:%M}")
        self._refresh_next_label()
        self._refresh_runtime_list()

    def delete_selected_runtime_alarm(self) -> None:
        selected = self.runtime_tree.selection()
        if not selected:
            return
        sorted_alarms = sorted(self.runtime_alarms, key=lambda item: item.target)
        selected_indexes = [int(item) for item in selected]
        self.runtime_alarms = remove_items_by_indexes(sorted_alarms, selected_indexes)
        self.status_var.set(f"Deleted {len(selected_indexes)} temporary alarm(s).")
        self._refresh_runtime_list()
        self._refresh_next_label()

    @staticmethod
    def _duration_label(hours: int, minutes: int) -> str:
        parts: list[str] = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        return " ".join(parts)

    def _show_alert(self, label: str) -> None:
        if self.alert_window is not None and self.alert_window.winfo_exists():
            self.alert_window.lift()
            self.alert_window.focus_force()
            return

        # The reminder window intentionally uses tk widgets for reliable full-screen styling.
        alert = tk.Toplevel(self.root)
        self.alert_window = alert
        alert.title("Time")
        alert.configure(bg="#111827")
        alert.attributes("-fullscreen", True)
        alert.attributes("-topmost", True)
        alert.protocol("WM_DELETE_WINDOW", self.dismiss_alert)

        container = tk.Frame(alert, bg="#111827")
        container.pack(fill=tk.BOTH, expand=True)
        tk.Label(container, text="Time", font=("Microsoft YaHei UI", 58, "bold"), fg="#ffffff", bg="#111827").pack(
            pady=(120, 18)
        )
        tk.Label(container, text=label, font=("Microsoft YaHei UI", 28, "bold"), fg="#bfdbfe", bg="#111827").pack(pady=(0, 18))
        tk.Label(
            container,
            text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            font=("Consolas", 26),
            fg="#d1d5db",
            bg="#111827",
        ).pack(pady=(0, 64))

        row = tk.Frame(container, bg="#111827")
        row.pack()
        self._alert_button(row, "Snooze 5 min", lambda: self.snooze(label, 5)).pack(side=tk.LEFT, padx=12)
        self._alert_button(row, "Snooze 10 min", lambda: self.snooze(label, 10)).pack(side=tk.LEFT, padx=12)
        self._alert_button(row, "Dismiss", self.dismiss_alert).pack(side=tk.LEFT, padx=12)
        alert.lift()
        alert.focus_force()
        alert.grab_set()

    @staticmethod
    def _alert_button(parent: tk.Widget, text: str, command: Callable[[], None]) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            font=("Microsoft YaHei UI", 18, "bold"),
            padx=28,
            pady=14,
            bg="#f9fafb",
            fg="#111827",
            activebackground="#e5e7eb",
            relief=tk.FLAT,
        )

    def snooze(self, label: str, minutes: int) -> None:
        self._close_alert_window()
        target = datetime.now() + timedelta(minutes=minutes)
        self.runtime_alarms.append(RuntimeAlarm(target=target, label=f"{label} (snoozed)"))
        self.status_var.set(f"Snoozed for {minutes} minutes.")
        self._refresh_next_label()
        self._refresh_runtime_list()

    def dismiss_alert(self) -> None:
        self._close_alert_window()
        self.status_var.set("Alarm dismissed.")

    def _close_alert_window(self) -> None:
        if self.alert_window is not None:
            try:
                self.alert_window.grab_release()
                self.alert_window.destroy()
            except tk.TclError:
                pass
            self.alert_window = None

    @staticmethod
    def _format_remaining(delta: timedelta) -> str:
        total_seconds = max(0, int(delta.total_seconds()))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def main() -> None:
    configure_windows_app_identity()
    root = tk.Tk()
    AlarmApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
