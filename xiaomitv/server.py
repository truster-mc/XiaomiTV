import dataclasses
import json
import re
import threading
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from xiaomitv import collector, tweaks
from xiaomitv.actions import PACKAGE_RE, disable_packages, enable_packages
from xiaomitv.adb import AdbError
from xiaomitv.analyzer import analyze, load_knowledge
from xiaomitv.recipes import filter_recipes, load_recipes
from xiaomitv.backup import (BackupError, create_snapshot, list_snapshots,
                             load_snapshot, packages_to_reenable)

_HOST_RE = re.compile(r"^[A-Za-z0-9.\-]{1,253}$")


def create_app(adb, backup_dir: Path, log_path: Path, knowledge=None,
               allow_force: bool = False) -> Flask:
    app = Flask(__name__, static_folder=str(Path(__file__).parent / "static"),
                static_url_path="/static")
    kb = knowledge if knowledge is not None else load_knowledge()
    all_recipes = load_recipes()
    state = {"scan": None, "analysis": None}
    lock = threading.Lock()
    backup_dir = Path(backup_dir)
    log_path = Path(log_path)

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.errorhandler(AdbError)
    def adb_error(exc):
        return jsonify(error=str(exc), hint=exc.hint), 502

    @app.errorhandler(BackupError)
    def backup_error(exc):
        return jsonify(error=str(exc)), 404

    def bad(message, status=400):
        return jsonify(error=message), status

    def tweak_states() -> dict[str, dict]:
        return {t.id: tweaks.read_state(adb, t) for t in tweaks.TWEAKS.values()}

    def came_back(scan) -> list[str]:
        if not log_path.exists():
            return []
        last: dict[str, dict] = {}
        for line in log_path.read_text().splitlines():
            try:
                entry = json.loads(line)
                last[entry["package"]] = entry
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        enabled = {p.name for p in scan.packages if p.enabled}
        return sorted(pkg for pkg, e in last.items()
                      if e.get("action") == "disable" and e.get("ok") is True
                      and pkg in enabled)

    @app.get("/api/recipes")
    def recipes():
        found = filter_recipes(all_recipes, request.args.get("model"), request.args.get("android"))
        return jsonify(
            recipes=[{"id": r.id, "title": r.title, "models": r.models, "android": r.android,
                      "summary": r.summary, "result": r.result, "step_count": len(r.steps),
                      "package_count": len({p for s in r.steps for p in s.packages})}
                     for r in found],
            filters={"models": sorted({m for r in all_recipes for m in r.models}),
                     "android": sorted({a for r in all_recipes for a in r.android})})

    @app.get("/api/recipes/<recipe_id>")
    def recipe(recipe_id):
        for r in all_recipes:
            if r.id == recipe_id:
                return jsonify(dataclasses.asdict(r))
        return bad("Unknown recipe", 404)

    @app.post("/api/connect")
    def connect():
        host = (request.get_json(silent=True) or {}).get("host", "")
        if not _HOST_RE.match(host):
            return bad("Enter the TV's IP address, for example 192.168.1.6")
        adb.connect(host)
        return jsonify(ok=True, serial=adb.serial)

    @app.post("/api/scan")
    def scan():
        scan_ = collector.collect(adb)
        analysis = analyze(scan_, kb)
        state["scan"], state["analysis"] = scan_, analysis
        states = tweak_states()
        return jsonify(
            device=scan_.device,
            memory={"total_kb": scan_.mem_total_kb, "available_kb": scan_.mem_available_kb},
            storage={"total_kb": scan_.data_total_kb, "free_kb": scan_.data_free_kb},
            launcher=scan_.launcher,
            reclaimable_kb=analysis.reclaimable_kb,
            rows=[dataclasses.asdict(r) for r in analysis.rows],
            reenabled_since_backup=came_back(scan_),
            tweaks=[{"id": t.id, "name": t.name, "description": t.description,
                     "warning": t.warning, "reboot_required": t.reboot_required,
                     "enabled": tweaks.is_enabled(t, states[t.id])}
                    for t in tweaks.TWEAKS.values()])

    @app.post("/api/apply")
    def apply_():
        if state["analysis"] is None:
            return bad("Run a scan first", 409)
        body = request.get_json(silent=True) or {}
        packages = body.get("packages")
        force = allow_force and body.get("force") is True
        if not isinstance(packages, list) or not packages:
            return bad("Select at least one app")
        rows = {r.package: r for r in state["analysis"].rows}
        for pkg in packages:
            if not isinstance(pkg, str) or not PACKAGE_RE.match(pkg):
                return bad(f"Invalid package name: {pkg!r}")
            if pkg not in rows:
                return bad(f"{pkg} was not found on the TV")
            if not rows[pkg].enabled:
                return bad(f"{pkg} is already disabled")
            if rows[pkg].rating == "keep" and not force:
                return bad(f"{pkg} is rated keep and is locked")
        with lock:
            snapshot = create_snapshot(state["scan"], tweak_states(), backup_dir)

            def stream():
                yield json.dumps({"snapshot": snapshot}) + "\n"
                with lock:
                    reported = set()
                    try:
                        for result in disable_packages(adb, packages, log_path):
                            reported.add(result.package)
                            yield json.dumps(dataclasses.asdict(result)) + "\n"
                    except Exception as exc:
                        yield json.dumps({"error": f"{type(exc).__name__}: {exc}",
                                          "hint": "The batch stopped early."}) + "\n"
                        for pkg in packages:
                            if pkg not in reported:
                                yield json.dumps({"package": pkg, "ok": False,
                                                  "message": "Not attempted: the batch stopped early"}) + "\n"
                    try:
                        _, available = collector.parse_proc_meminfo(
                            adb.shell(collector.PROC_MEMINFO))
                    except AdbError:
                        available = 0
                yield json.dumps({"done": True, "memory_available_kb": available}) + "\n"

        return Response(stream(), mimetype="application/x-ndjson")

    @app.get("/api/backups")
    def backups():
        return jsonify(backups=list_snapshots(backup_dir))

    @app.post("/api/restore")
    def restore():
        snapshot = load_snapshot(backup_dir, (request.get_json(silent=True) or {}).get("id", ""))
        with lock:
            current = collector.collect(adb)
            results = list(enable_packages(adb, packages_to_reenable(snapshot, current.packages),
                                           log_path))
            reverted = []
            for tweak_id, saved in snapshot.get("tweaks", {}).items():
                tweak = tweaks.TWEAKS.get(tweak_id)
                if tweak and tweaks.read_state(adb, tweak) != saved:
                    tweaks.revert(adb, tweak, saved)
                    reverted.append(tweak_id)
        return jsonify(reenabled=[dataclasses.asdict(r) for r in results],
                       tweaks_reverted=reverted)

    @app.post("/api/tweaks/<tweak_id>")
    def tweak(tweak_id):
        t = tweaks.TWEAKS.get(tweak_id)
        if t is None:
            return bad("Unknown tweak", 404)
        action = (request.get_json(silent=True) or {}).get("action")
        if action not in ("enable", "disable"):
            return bad("action must be enable or disable")
        with lock:
            # the state to go back to: the newest snapshot taken while the tweak was off
            previous = {s.key: None for s in t.settings}
            for info in list_snapshots(backup_dir):
                saved = load_snapshot(backup_dir, info["id"]).get("tweaks", {}).get(tweak_id)
                if saved is not None and not tweaks.is_enabled(t, saved):
                    previous = saved
                    break
            snapshot = create_snapshot(collector.collect(adb), tweak_states(), backup_dir)
            if action == "enable":
                tweaks.apply(adb, t)
            else:
                tweaks.revert(adb, t, previous)
            enabled = tweaks.is_enabled(t, tweaks.read_state(adb, t))
        return jsonify(snapshot=snapshot, enabled=enabled,
                       reboot_required=t.reboot_required)

    return app
