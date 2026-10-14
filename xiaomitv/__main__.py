import argparse
import threading
import webbrowser
from pathlib import Path

from xiaomitv.adb import Adb, AdbError
from xiaomitv.server import create_app


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="xiaomitv", description="Scan and debloat a Xiaomi TV over ADB.")
    p.add_argument("--tv", help="TV address to connect to at startup, e.g. 192.168.1.6")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--lan", action="store_true",
                   help="listen on all network interfaces (anyone on your network can then change the TV)")
    p.add_argument("--no-browser", action="store_true", help="do not open the browser")
    p.add_argument("--backup-dir", type=Path, default=Path("backups"))
    p.add_argument("--log", type=Path, default=Path("changes.log"))
    args = p.parse_args(argv)
    args.host = "0.0.0.0" if args.lan else "127.0.0.1"
    return args


def build_app(args, adb=None):
    return create_app(adb or Adb(), args.backup_dir, args.log)


def main(argv=None) -> None:
    args = parse_args(argv)
    adb = Adb()
    if args.tv:
        try:
            adb.connect(args.tv)
            print(f"Connected to {adb.serial}")
        except AdbError as exc:
            print(f"Could not connect to {args.tv}: {exc}\n{exc.hint}")
    if args.lan:
        print("WARNING: --lan lets anyone on your network disable apps on the TV. "
              "There is no password.")
    app = build_app(args, adb)
    url = f"http://{'127.0.0.1' if not args.lan else args.host}:{args.port}"
    print(f"Open {url}")
    if not args.no_browser:
        threading.Timer(0.8, webbrowser.open, args=[url]).start()
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
