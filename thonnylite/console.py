"""Live serial console with a Ctrl+] escape back to the upload menu."""

import os
import select
import sys
import termios
import threading
import tty

BREAK_OUT_BYTE = 0x1D  # Ctrl+]


def _reader_loop(ser, stop_event):
    while not stop_event.is_set():
        try:
            data = ser.read(ser.in_waiting or 1)
        except Exception:
            break
        if data:
            os.write(sys.stdout.fileno(), data)


def run_console(ser):
    """Passthrough stdin<->serial until Ctrl+] is pressed. Returns to caller after."""
    print("\n--- console (Ctrl+] to return to upload menu) ---\n")
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    stop_event = threading.Event()
    reader = threading.Thread(target=_reader_loop, args=(ser, stop_event), daemon=True)
    try:
        tty.setraw(fd)
        reader.start()
        while True:
            ready, _, _ = select.select([fd], [], [], 0.1)
            if not ready:
                continue
            byte = os.read(fd, 1)
            if not byte:
                continue
            if byte[0] == BREAK_OUT_BYTE:
                break
            ser.write(byte)
    finally:
        stop_event.set()
        reader.join(timeout=1)
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print("\n--- back to upload menu ---\n")
