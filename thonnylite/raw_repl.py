"""MicroPython raw-REPL protocol: exec code, transfer files, reset the board.

Protocol reference: this mirrors what mpremote/ampy/rshell do against the
same MicroPython raw REPL (Ctrl-A to enter, Ctrl-D to execute a buffer,
Ctrl-B to exit back to the friendly REPL).
"""

import ast
import base64
import time

import serial


class RawReplError(Exception):
    pass


class RawRepl:
    def __init__(self, port, baudrate=115200, timeout=10):
        self.serial = serial.Serial(port, baudrate=baudrate, timeout=0.1)
        self._read_timeout = timeout
        self._buf = b""

    def close(self):
        self.serial.close()

    # -- low-level helpers ------------------------------------------------

    def _read_until(self, ending, timeout=None):
        """Read (and consume) up to and including `ending`.

        A single serial read can return more than one terminator's worth of
        data, so matching against a persistent buffer (rather than just
        checking the tail of each new chunk) is required.
        """
        timeout = self._read_timeout if timeout is None else timeout
        deadline = time.time() + timeout
        while ending not in self._buf and time.time() < deadline:
            chunk = self.serial.read(self.serial.in_waiting or 1)
            if chunk:
                self._buf += chunk
        idx = self._buf.find(ending)
        if idx == -1:
            data, self._buf = self._buf, b""
            raise RawReplError(f"Timed out waiting for {ending!r}; got {data!r}")
        end = idx + len(ending)
        data, self._buf = self._buf[:end], self._buf[end:]
        return data

    # -- REPL mode switches -------------------------------------------------

    def enter_raw_repl(self):
        self.serial.write(b"\r\x03\x03")  # interrupt any running program
        self.serial.reset_input_buffer()
        self.serial.write(b"\r\x01")  # Ctrl-A: enter raw REPL
        self._read_until(b"raw REPL; CTRL-B to exit\r\n>")

    def exit_raw_repl(self):
        self.serial.write(b"\r\x02")  # Ctrl-B: back to friendly REPL

    def soft_reset(self):
        """Exit raw REPL and soft-reset so boot.py/main.py run again."""
        self.exit_raw_repl()
        self._read_until(b">>> ", timeout=5)
        self.serial.write(b"\x04")  # Ctrl-D at the friendly REPL: soft reset

    # -- code execution -----------------------------------------------------

    def exec(self, code, timeout=None):
        self.serial.write(code.encode("utf-8"))
        self.serial.write(b"\x04")  # Ctrl-D: run the buffer
        ack = self._read_until(b"OK", timeout=timeout)
        if not ack.endswith(b"OK"):
            raise RawReplError(f"Board did not accept command: {ack!r}")
        out = self._read_until(b"\x04", timeout=timeout)[:-1]
        err = self._read_until(b"\x04", timeout=timeout)[:-1]
        if err:
            raise RawReplError(err.decode("utf-8", "replace"))
        return out

    # -- filesystem operations -----------------------------------------------

    def mkdirs(self, remote_dir):
        """Create remote_dir (and parents) on the board, ignoring existing ones."""
        remote_dir = remote_dir.strip("/")
        if not remote_dir:
            return
        path = ""
        for part in remote_dir.split("/"):
            path += "/" + part
            self.exec(
                "try:\n"
                "    import os\n"
                f"    os.mkdir({path!r})\n"
                "except OSError:\n"
                "    pass\n"
            )

    def put_file(self, local_path, remote_path, chunk_size=256):
        remote_dir = remote_path.rsplit("/", 1)[0] if "/" in remote_path else ""
        if remote_dir:
            self.mkdirs(remote_dir)

        with open(local_path, "rb") as f:
            data = f.read()

        self.exec("import ubinascii")
        self.exec(f"f = open({remote_path!r}, 'wb')")
        try:
            for i in range(0, len(data), chunk_size):
                chunk = data[i : i + chunk_size]
                encoded = base64.b64encode(chunk).decode("ascii")
                self.exec(f"f.write(ubinascii.a2b_base64({encoded!r}))")
            if not data:
                # exec at least once so the empty file is actually created/truncated.
                pass
        finally:
            self.exec("f.close()")

    def remove_file(self, remote_path):
        self.exec("import os\n" f"os.remove({remote_path!r})\n")

    def list_files(self, remote_dir="/"):
        """Recursively list plain files (not directories) under remote_dir.

        Returns absolute paths like "/main.py", "/lib/foo.py". Directories
        themselves are walked but not included in the result.
        """
        out = self.exec(
            "import os\n"
            "def _tl_walk(path):\n"
            "    found = []\n"
            "    for name in os.listdir(path):\n"
            "        full = path.rstrip('/') + '/' + name\n"
            "        try:\n"
            "            is_dir = os.stat(full)[0] & 0x4000\n"
            "        except OSError:\n"
            "            continue\n"
            "        if is_dir:\n"
            "            found.extend(_tl_walk(full))\n"
            "        else:\n"
            "            found.append(full)\n"
            "    return found\n"
            f"print(_tl_walk({remote_dir!r}))\n"
        )
        return sorted(ast.literal_eval(out.decode("utf-8").strip()))
