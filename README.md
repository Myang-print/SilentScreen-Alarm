# SilentScreen Alarm

A silent Windows desktop alarm app built with Python and Tkinter. It supports persistent weekly alarms, one-off focus timers, and full-screen always-on-top reminders without sound.

**GitHub description:** Silent Windows alarm app with persistent alarms, temporary focus timers, and full-screen no-sound reminders.

## Run

```powershell
python alarm.py
```

## Build A Windows App

The project includes a lightweight PyInstaller build script for Windows:

```powershell
.\build_windows.ps1 -InstallPyInstaller
```

After the first build, if PyInstaller is already installed, use:

```powershell
.\build_windows.ps1
```

The executable is created at:

```text
release\SilentScreenAlarm.exe
```

The build script also generates a small alarm-clock `.ico` file and uses it as the executable icon. Persistent alarm data is stored as `alarms.json` next to the executable.

## Features

- Persistent alarms are saved locally to `alarms.json`
- Persistent alarms support once-only and weekly repeat modes
- Persistent alarms can be enabled, disabled, edited, deleted, and batch-deleted with Ctrl multi-select
- Temporary alarms are managed in the main window and are not saved
- Temporary alarms support quick timer presets: 5, 25, 45, and 60 minutes
- Quick timer presets require confirmation before they start
- Temporary alarms support custom hour/minute countdowns
- Temporary alarms support 24-hour `HH:MM` input, such as `09:30` or `23:05`
- Temporary alarms can be viewed and batch-deleted with Ctrl multi-select
- Past `HH:MM` inputs are scheduled for the same time tomorrow
- The main window shows the current date, weekday, time, and next alarm
- Full-screen reminder supports dismiss, 5-minute snooze, and 10-minute snooze

## Data

Persistent alarms are stored in `alarms.json` next to the script. Temporary alarms and snoozed reminders only exist while the app is running.

## Limits

- The computer must stay powered on, signed in, and the app must keep running
- Reminders are not guaranteed during lock screen, sleep, hibernation, exclusive full-screen games, or similar system states
- No sound, system notifications, tray icon, or system wake support
