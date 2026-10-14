from xiaomitv.adb import AdbError


class FakeAdb:
    """Stands in for Adb: answers shell commands from a dict and records every call."""

    serial = "fake:5555"

    def __init__(self, responses: dict[str, str] | None = None,
                 fail: dict[str, Exception] | None = None):
        self.responses = responses or {}
        self.fail = fail or {}
        self.calls: list[str] = []

    def connect(self, host: str, port: int = 5555) -> None:
        self.calls.append(f"connect {host}:{port}")

    def shell(self, command: str) -> str:
        self.calls.append(command)
        if command in self.fail:
            raise self.fail[command]
        return self.responses.get(command, "")
