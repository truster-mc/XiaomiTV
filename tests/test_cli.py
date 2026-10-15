from flask import Flask

from xiaomitv.__main__ import build_app, parse_args


def test_defaults_bind_localhost_only():
    args = parse_args([])
    assert args.host == "127.0.0.1" and args.port == 8080
    assert args.lan is False


def test_lan_flag_binds_all_interfaces():
    assert parse_args(["--lan"]).host == "0.0.0.0"


def test_options_are_parsed():
    args = parse_args(["--tv", "192.168.1.6", "--port", "9000", "--no-browser",
                       "--backup-dir", "b", "--log", "l.log"])
    assert (args.tv, args.port, args.no_browser) == ("192.168.1.6", 9000, True)
    assert str(args.backup_dir) == "b" and str(args.log) == "l.log"


def test_build_app_returns_flask_app():
    assert isinstance(build_app(parse_args([])), Flask)


def test_force_flag_is_off_by_default_and_reaches_the_app():
    assert parse_args([]).force is False
    assert parse_args(["--force"]).force is True


def test_startup_connect_does_not_block_the_server():
    import threading
    from xiaomitv.__main__ import connect_in_background
    from xiaomitv.adb import TvUnreachable

    release = threading.Event()
    seen = []

    class SlowAdb:
        serial = None

        def connect(self, host, port=5555):
            release.wait(5)
            raise TvUnreachable("adb timed out")

    thread = connect_in_background(SlowAdb(), "192.168.1.6", report=seen.append)
    assert thread.is_alive(), "connect_in_background must return before the connect finishes"
    assert seen == []
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    assert any("Could not connect" in line for line in seen)


def test_startup_connect_reports_success():
    from xiaomitv.__main__ import connect_in_background
    from tests.fakes import FakeAdb

    seen = []
    connect_in_background(FakeAdb(), "192.168.1.6", report=seen.append).join(5)
    assert seen == ["Connected to fake:5555"]
