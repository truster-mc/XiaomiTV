import json

from tests.fakes import FakeAdb
from xiaomitv.actions import PACKAGE_RE, disable_packages, enable_packages
from xiaomitv.adb import AdbError, TvUnreachable

DISABLED = "Package {} new state: disabled-user"
ENABLED = "Package {} new state: enabled"


def cmd(pkg):
    return f"pm disable-user --user 0 {pkg}"


def log_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_disable_sends_exact_command_and_reports_ok(tmp_path):
    fake = FakeAdb({cmd("com.miui.tv.analytics"): DISABLED.format("com.miui.tv.analytics")})
    results = list(disable_packages(fake, ["com.miui.tv.analytics"], tmp_path / "log"))
    assert fake.calls == ["pm disable-user --user 0 com.miui.tv.analytics"]
    assert results[0].ok and results[0].package == "com.miui.tv.analytics"


def test_enable_sends_exact_command(tmp_path):
    fake = FakeAdb({"pm enable --user 0 com.x.y": ENABLED.format("com.x.y")})
    results = list(enable_packages(fake, ["com.x.y"], tmp_path / "log"))
    assert fake.calls == ["pm enable --user 0 com.x.y"]
    assert results[0].ok


def test_invalid_names_never_reach_the_shell(tmp_path):
    fake = FakeAdb()
    bad = ["com.x; reboot", "com.x && id", "$(id)", "nodots", "", "com.x y"]
    results = list(disable_packages(fake, bad, tmp_path / "log"))
    assert fake.calls == []
    assert [r.ok for r in results] == [False] * len(bad)
    assert not PACKAGE_RE.match("com.x; reboot")
    assert PACKAGE_RE.match("com.google.android.apps.tv.launcherx")


def test_unexpected_output_is_a_failure(tmp_path):
    fake = FakeAdb({cmd("com.a.b"): "Exception: Unknown package"})
    result = list(disable_packages(fake, ["com.a.b"], tmp_path / "log"))[0]
    assert not result.ok and "Unknown package" in result.message


def test_failure_does_not_stop_the_batch(tmp_path):
    fake = FakeAdb(
        {cmd("com.a.one"): DISABLED.format("com.a.one"),
         cmd("com.a.three"): DISABLED.format("com.a.three")},
        fail={cmd("com.a.two"): AdbError("boom")})
    results = list(disable_packages(fake, ["com.a.one", "com.a.two", "com.a.three"],
                                    tmp_path / "log"))
    assert [r.ok for r in results] == [True, False, True]
    assert results[1].message == "boom"


def test_connection_drop_reports_every_remaining_package_failed(tmp_path):
    fake = FakeAdb(
        {cmd("com.a.one"): DISABLED.format("com.a.one")},
        fail={cmd("com.a.two"): TvUnreachable("offline"),
              cmd("com.a.three"): TvUnreachable("offline")})
    results = list(disable_packages(fake, ["com.a.one", "com.a.two", "com.a.three"],
                                    tmp_path / "log"))
    assert [r.ok for r in results] == [True, False, False]
    assert "offline" in results[2].message
    assert len(log_lines(tmp_path / "log")) == 3


def test_each_result_is_logged_before_the_next_command_runs(tmp_path):
    log = tmp_path / "changes.log"
    seen = []

    class Watching(FakeAdb):
        def shell(self, command):
            seen.append(len(log.read_text().splitlines()) if log.exists() else 0)
            return DISABLED.format(command.split()[-1])

    list(disable_packages(Watching(), ["com.a.one", "com.a.two", "com.a.three"], log))
    assert seen == [0, 1, 2]
    entry = log_lines(log)[0]
    assert entry["action"] == "disable" and entry["package"] == "com.a.one" and entry["ok"]
    assert "time" in entry


def test_unexpected_exception_is_a_failed_result_and_batch_continues(tmp_path):
    fake = FakeAdb(
        {cmd("com.a.one"): DISABLED.format("com.a.one"),
         cmd("com.a.three"): DISABLED.format("com.a.three")},
        fail={cmd("com.a.two"): RuntimeError("weird")})
    results = list(disable_packages(fake, ["com.a.one", "com.a.two", "com.a.three"],
                                    tmp_path / "log"))
    assert [r.ok for r in results] == [True, False, True]
    assert "weird" in results[1].message
    assert len(log_lines(tmp_path / "log")) == 3


def test_unwritable_log_does_not_drop_results(tmp_path):
    log = tmp_path / "log-is-a-directory"
    log.mkdir()
    fake = FakeAdb({cmd("com.a.one"): DISABLED.format("com.a.one")})
    results = list(disable_packages(fake, ["com.a.one"], log))
    assert results[0].ok
