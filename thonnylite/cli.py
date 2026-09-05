"""Interactive loop: find Pico -> choose files -> upload -> reboot -> console."""

import os

import serial

from . import device, file_selection
from .console import run_console
from .raw_repl import RawRepl, RawReplError

MENU = """
What would you like to upload from {root}?
  1) Everything
  2) Selective
  3) Only git-modified files
  4) Skip upload, just watch console
  q) Quit
"""


def choose_files(root, choice):
    if choice == "1":
        return file_selection.list_all_files(root)

    if choice == "2":
        all_files = file_selection.list_all_files(root)
        if not all_files:
            print("No files found.")
            return []
        return file_selection.prompt_selective(all_files)

    if choice == "3":
        result = file_selection.list_git_modified_files(root)
        if result is None:
            print("Not a git repository; can't determine modified files.")
            return []
        modified, deleted = result
        if deleted:
            print("Note: these were deleted locally and won't be removed from the board:")
            for d in deleted:
                print(f"  - {d}")
        if not modified:
            print("No modified files reported by git.")
        return modified

    return []


def upload_and_reset(port, root, files):
    repl = RawRepl(port)
    try:
        repl.enter_raw_repl()
        for rel_path in files:
            local_path = os.path.join(root, rel_path)
            remote_path = "/" + rel_path
            print(f"  uploading {rel_path} -> {remote_path}")
            repl.put_file(local_path, remote_path)
        print("Rebooting board...")
        repl.soft_reset()
    except RawReplError:
        repl.close()
        raise
    return repl.serial


def main():
    root = os.getcwd()
    port = device.wait_for_pico()
    print(f"Found Pico on {port}")

    try:
        while True:
            print(MENU.format(root=root))
            choice = input("> ").strip().lower()

            if choice == "q":
                break

            if choice == "4":
                ser = serial.Serial(port, baudrate=115200, timeout=0.1)
                run_console(ser)
                ser.close()

            elif choice in ("1", "2", "3"):
                files = choose_files(root, choice)
                if not files:
                    continue
                try:
                    ser = upload_and_reset(port, root, files)
                except RawReplError as e:
                    print(f"Error talking to board: {e}")
                    continue
                run_console(ser)
                ser.close()

            else:
                print("Unrecognized choice.")
                continue

            # Re-detect in case the board was unplugged while we watched the console.
            new_port = device.find_pico_port()
            port = new_port if new_port else device.wait_for_pico()
    except KeyboardInterrupt:
        print("\nExiting.")


if __name__ == "__main__":
    main()
