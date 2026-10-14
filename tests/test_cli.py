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
