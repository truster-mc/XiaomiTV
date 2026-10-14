import subprocess


class AdbError(Exception):
    hint = ""

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        if hint:
            self.hint = hint


class AdbNotInstalled(AdbError):
    hint = "Install adb with: sudo apt install adb"


class TvUnreachable(AdbError):
    hint = ("Check the TV is on, on the same network, and USB/ADB debugging "
            "is enabled in Developer options.")


class Unauthorized(AdbError):
    hint = ("Accept the 'Allow USB debugging?' prompt on the TV with the remote "
            "(tick 'Always allow'). Allow USB debugging, then connect again.")


class Adb:
    def __init__(self, binary: str = "adb", timeout: float = 30.0):
        self.binary = binary
        self.timeout = timeout
        self.serial: str | None = None

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        try:
            return subprocess.run([self.binary, *args], capture_output=True, text=True,
                                  errors="replace", timeout=self.timeout)
        except FileNotFoundError:
            raise AdbNotInstalled("adb is not installed")
        except subprocess.TimeoutExpired:
            raise TvUnreachable("adb timed out")
        except OSError as exc:
            raise AdbError(f"Could not run adb: {exc}",
                           hint="Check that the adb binary is executable.")

    def connect(self, host: str, port: int = 5555) -> None:
        serial = f"{host}:{port}"
        out = self._run(["connect", serial])
        text = out.stdout + out.stderr
        devices = self._run(["devices"]).stdout
        state = next((line.split("\t")[1] for line in devices.splitlines()
                      if line.startswith(serial + "\t")), None)
        if state == "unauthorized":
            raise Unauthorized("TV has not authorized this computer")
        if state == "device":
            self.serial = serial
            return
        if "failed to authenticate" in text:
            raise Unauthorized("TV has not authorized this computer")
        raise TvUnreachable(text.strip() or f"could not connect to {serial}")

    def shell(self, command: str) -> str:
        if not self.serial:
            raise AdbError("Not connected to a TV", hint="Connect first.")
        out = self._run(["-s", self.serial, "shell", command])
        if out.returncode != 0:
            message = (out.stderr or out.stdout).strip() or "adb shell failed"
            lowered = message.lower()
            if "unauthorized" in lowered:
                raise Unauthorized(message)
            if any(word in lowered for word in ("not found", "offline", "no devices", "closed")):
                raise TvUnreachable(message, hint=TvUnreachable.hint +
                                    " Then press Connect again.")
            raise AdbError(message)
        return out.stdout
