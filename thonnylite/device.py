"""Find a Raspberry Pi Pico (MicroPython) on a serial port."""

import time

import serial.tools.list_ports as list_ports

# Raspberry Pi Foundation vendor ID, used by the Pico's MicroPython USB CDC port.
PICO_VID = 0x2E8A
# PID for the MicroPython REPL/filesystem serial port (confirmed on-device).
PICO_PIDS = {0x0005}


def _is_pico(port_info) -> bool:
    if port_info.vid == PICO_VID and port_info.pid in PICO_PIDS:
        return True
    if (port_info.manufacturer or "").strip() == "MicroPython":
        return True
    return False


def find_all_pico_ports():
    return [p for p in list_ports.comports() if _is_pico(p)]


def find_pico_port():
    """Return the device path of a single connected Pico, or None."""
    candidates = find_all_pico_ports()
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0].device
    return _choose_among(candidates)


def _choose_among(candidates):
    print("Multiple MicroPython boards found:")
    for i, c in enumerate(candidates, start=1):
        print(f"  {i}. {c.device}  ({c.description})")
    while True:
        choice = input(f"Select a board [1-{len(candidates)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(candidates):
            return candidates[int(choice) - 1].device
        print("Invalid selection.")


def wait_for_pico(poll_interval=0.5, message="Waiting for a Pico to be connected..."):
    """Block until a Pico is found, printing `message` once if not immediately present."""
    port = find_pico_port()
    if port:
        return port
    print(message)
    while True:
        time.sleep(poll_interval)
        port = find_pico_port()
        if port:
            return port
