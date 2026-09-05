"""Interactive loop: find Pico -> choose files -> upload -> reboot -> console."""

import os

import serial

from . import device, file_selection
from .console import run_console
from .raw_repl import RawRepl, RawReplError

MENU = """
What would you like to do? (working directory: {root})
  1) Upload everything
  2) Upload selectively
  3) Upload only git-modified files
  4) Skip upload, just watch console
  5) Delete files from the device
  6) Run a local script on the device (not saved as main.py)
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


def delete_files(port):
    repl = RawRepl(port)
    try:
        repl.enter_raw_repl()
        remote_files = repl.list_files()
        if not remote_files:
            print("No files found on the device.")
            return
        print("Files on device:")
        print("Enter numbers/ranges to delete (e.g. 1-3,7), or blank to cancel:")
        selected = file_selection.prompt_selection_or_none(remote_files)
        if not selected:
            print("Cancelled.")
            return
        print("About to delete:")
        for f in selected:
            print(f"  - {f}")
        if input("Type 'yes' to confirm: ").strip().lower() != "yes":
            print("Cancelled.")
            return
        for f in selected:
            print(f"  removing {f}")
            repl.remove_file(f)
        repl.exit_raw_repl()
    except RawReplError as e:
        print(f"Error talking to board: {e}")
    finally:
        repl.close()


def run_local_script(port, root):
    py_files = [f for f in file_selection.list_all_files(root) if f.endswith(".py")]
    if not py_files:
        print("No local .py files found.")
        return
    print("Pick one script to run on the device (output prints below; it is")
    print("executed directly and not saved to the device's filesystem):")
    selected = file_selection.prompt_selection_or_none(py_files)
    if not selected:
        print("Cancelled.")
        return
    rel_path = selected[0]
    with open(os.path.join(root, rel_path), "r") as f:
        code = f.read()

    repl = RawRepl(port)
    try:
        repl.enter_raw_repl()
        print(f"--- running {rel_path} on device ---")
        out = repl.exec(code, timeout=30)
        print(out.decode("utf-8", "replace"))
        print(f"--- {rel_path} finished ---")
        repl.exit_raw_repl()
    except RawReplError as e:
        print(f"Error running script: {e}")
    finally:
        repl.close()


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

            elif choice == "5":
                delete_files(port)

            elif choice == "6":
                run_local_script(port, root)

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
