# Changelog

All notable changes to the **Windows 11 System Monitor** project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## How to View Previous Commit Changes

You can inspect the history of this project at any time using Git:

```bash
# Show all commits (one line each)
git log --oneline

# Show full details of a specific commit
git show <commit-hash>

# Show what changed between two commits
git diff <old-commit-hash> <new-commit-hash>

# Show all changes introduced by the last commit
git show HEAD

# Show all changes introduced by the second-to-last commit
git show HEAD~1

# List changed files between two commits
git diff --stat <old-commit-hash> <new-commit-hash>

# Check out the state of the repository at a previous commit (read-only)
git checkout <commit-hash>

# Return to the latest commit on your branch
git checkout main
```

> **Tip:** Copy any commit hash from `git log --oneline` and paste it into `git show <hash>` to see exactly what was added, changed, or removed in that commit.

---

## [Unreleased]

### Planned
- Additional display themes
- Linux/macOS compatibility layer
- Plugin API for custom metrics

---

## [1.0.0] — 2025-09-24

### Added
- Initial release of the **Windows 11 System Monitor – Enhanced Edition**
- Extra-large battery percentage icons in the Windows taskbar (color-coded by charge level)
- Semi-transparent overlay with five display modes:
  - **Compact View** — essential metrics in a small window
  - **Detailed View** — comprehensive system information
  - **FPS View** — real-time frames per second and frame times
  - **Network View** — upload/download speeds and statistics
  - **System View** — hardware specifications and system details
- Real-time **CPU monitoring** — overall usage and per-core utilization with frequency
- Real-time **Memory monitoring** — RAM usage with detailed metrics
- **Disk usage** tracking for all drives
- **Network speed monitor** — upload and download rates
- **FPS counter** — frames per second and frame time (milliseconds)
- **GPU monitoring** — usage, temperature, and memory (NVIDIA/AMD supported)
- **System uptime** display
- **Notification system** — configurable alerts for low battery and high resource usage
- **Single-instance management** using dual socket and file-locking to prevent duplicate processes
- **Automatic startup** option via Windows Registry
- **Settings dialog** with four configuration tabs (General, Display, Appearance, Advanced)
- Adaptive monitoring that reduces update frequency when running on battery power
- `launcher.py` — dependency auto-installer and application launcher
- `Run_System_Monitor.bat` — one-click Windows launcher script
- `debug.bat` — debug mode launcher
- `fix_drawline_errors.py` — utility to patch draw-line rendering issues
- `fix_fps_counter.py` — utility to fix FPS counter accuracy
- `fix_fps_timer.py` — utility to improve FPS timer precision
- Battery icon assets for 0 %, 25 %, 50 %, 75 %, and 100 % (charging and discharging states)
