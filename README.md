# thonnyLite

A minimalist, command-line alternative to Thonny for working with
MicroPython on a Raspberry Pi Pico (or other RP2040/MicroPython board)
over USB.

Thonny requires manually picking files in its GUI and uploading them one
at a time (or via its own project view), which breaks the "edit locally
with your own editor/AI tooling, then just run it on the device" loop.
thonnylite instead uploads straight from your project's working
directory, reboots the board, and drops you into a live console —
so the only thing you ever touch by hand is your editor.

## What it does

1. Detects a connected Pico over USB serial.
2. Asks what to upload from the current directory:
   - **Everything**
   - **Selectively** (pick from a numbered list)
   - **Only files git reports as modified/added/untracked**
3. Uploads the chosen files, mirroring your local subdirectory structure
   onto the device's filesystem (creating directories as needed).
4. Soft-resets the board so `boot.py`/`main.py` run fresh.
5. Streams the live serial console so you can watch output / use the
   REPL for debugging.
6. `Ctrl+]` breaks out of the console back to the upload menu, without
   dropping the USB connection or needing to unplug anything.

## Requirements

- Python 3.8+
- [`pyserial`](https://pypi.org/project/pyserial/) (the only runtime
  dependency)
- `git`, if you want to use the "everything" or "git-modified" upload
  modes (see [Design decisions](#design-decisions) below) — without git,
  file discovery falls back to a plain directory walk and "git-modified"
  is unavailable.

## Install

From this repo:

```
pip install -e .
```

This installs a `thonnylite` command (via a `console_scripts` entry
point), so you can `cd` into any MicroPython project directory — not
just this repo — and just run:

```
thonnylite
```

## Design decisions

**Python 3.x, not a native Xcode/Mac app.** This is a terminal tool that
talks to a USB-serial port; there's no GUI work for Xcode to buy you, and
it would lock the tool to macOS only. Python + pyserial is the same
toolchain Thonny, `mpremote`, `rshell`, and `ampy` are all built on.

**Talks raw MicroPython REPL protocol directly over pyserial**, rather
than shelling out to `mpremote`. This gives full control over the
specific upload → reset → console → break-out loop this tool is built
around:
- Enter raw REPL (`Ctrl-A`), execute code and read output/errors framed
  by `\x04` (`Ctrl-D`), exit back to the friendly REPL (`Ctrl-B`).
- Files are written by opening them in `'wb'` mode on the device and
  streaming base64-encoded chunks through repeated `exec()` calls —
  avoids control-byte collisions between file contents and the REPL
  protocol itself.
- Rebooting is a **soft reset** (`Ctrl-D` at the friendly REPL), not
  `machine.reset()`. This reruns `boot.py`/`main.py` without the USB
  port re-enumerating, so the same serial connection can be reused
  immediately for the console — no reconnect logic needed.

**`Ctrl+]` is the console break-out key**, not `Ctrl+C`. `Ctrl+C` is
passed straight through to the board as a `KeyboardInterrupt` (useful for
stopping a runaway MicroPython program); `Ctrl+]` (the classic
telnet-style escape) is never something a running program sends or
expects, so it's safe to reserve.

**File discovery shells out to `git`** instead of reimplementing
`.gitignore` parsing:
- "Everything" = `git ls-files -co --exclude-standard` (tracked +
  untracked, honoring `.gitignore`).
- "Git-modified" = `git status --porcelain --untracked-files=all`,
  parsed for modified/added/untracked entries. Note the
  `--untracked-files=all` flag specifically — plain `git status
  --porcelain` collapses a brand-new untracked directory into a single
  line (e.g. `?? lib/`) instead of listing the files inside it, which
  would otherwise try to "upload" a directory as if it were a file.
- If the current directory isn't a git repo, both modes fall back to a
  plain directory walk filtered by a small built-in ignore list
  (`.git`, `__pycache__`, `.venv`/`venv`, `node_modules`, `.DS_Store`),
  and "git-modified" is disabled with a message.

**Directory structure is mirrored onto the device** (`lib/foo.py` →
`/lib/foo.py`), rather than flattened into the root — required for any
code using package-style imports like `from lib.foo import bar`.

**Deleted files are not synced.** "Git-modified" mode reports files git
sees as deleted but does not remove them from the device automatically —
first-version scope was upload-only.

## User notes / gotchas

- **This will overwrite files on the device without asking first** — it
  doesn't read/back up existing device content before writing. If your
  Pico is running something you care about and you're not sure what
  local files map onto what's already there, check first (e.g. via
  Thonny's file browser or a quick `os.listdir()` at the REPL) before
  running an "everything" upload.
- If multiple MicroPython-looking boards are plugged in, thonnylite will
  list them and ask you to pick one.
- The console reader/writer needs a real interactive terminal (it puts
  stdin into raw mode via `termios`); it won't behave correctly if run
  with stdin/stdout redirected or piped.
- Currently targets macOS/Linux (uses `termios`/`tty` for the console).
  No Windows support yet.
- Device match is by USB VID `0x2E8A` (Raspberry Pi Foundation) combined
  with a MicroPython-specific PID, plus a fallback match on
  `manufacturer == "MicroPython"` for other RP2040 boards running
  MicroPython.

## Project layout

```
thonnylite/
  device.py           # find/wait for a Pico on serial
  raw_repl.py          # MicroPython raw-REPL protocol + file transfer + reset
  file_selection.py     # "all" / "selective" / "git-modified" file lists
  console.py            # raw-terminal passthrough + Ctrl+] breakout
  cli.py                # the interactive loop tying it together
```
