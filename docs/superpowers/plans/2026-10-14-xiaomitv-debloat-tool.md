# XiaomiTV Debloat Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local Flask web app that connects to a Xiaomi TV over ADB, scans apps/memory/storage, recommends apps to disable, backs up state before every change, and applies or restores changes.

**Architecture:** Small single-purpose modules under `xiaomitv/` (adb wrapper, collector, analyzer + `apps.yaml`, backup, actions, tweaks) behind a thin Flask JSON API and a static HTML/JS page. All TV access goes through one `Adb` object so tests use a `FakeAdb` fed with real output captured from the target TV.

**Tech Stack:** Python 3.12, Flask, PyYAML, pytest, system `adb` (already installed, `/usr/bin/adb`), plain HTML/JS (no build step).

**Spec:** `docs/superpowers/specs/2026-10-14-xiaomitv-debloat-design.md`

## Global Constraints

- Server binds `127.0.0.1:8080` by default; `--lan` (binds `0.0.0.0`) is opt-in and prints a warning.
- The only app-changing commands are `pm disable-user --user 0 <pkg>` and `pm enable --user 0 <pkg>`. Never `pm uninstall`, `pm clear`, root, or flashing.
- Packages not in `apps.yaml` are rated `keep`. `keep` rows cannot be applied unless the request has `force: true`.
- A backup snapshot is written before every apply and before every tweak change.
- Every package name reaching `adb shell` must match `PACKAGE_RE` and appear in the last scan (shell-injection guard).
- Ratings are exactly `safe`, `tradeoff`, `keep`. Only enabled `safe` rows are pre-ticked.
- Target TV for fixtures and the live check: `192.168.1.6:5555` (Android 11, `MiTV-MOOR2`). Raw scans live in `scans/` (gitignored); tests use committed copies in `tests/fixtures/`.
- `backups/` and `changes.log` are gitignored (they contain device data).

## Review Focus

1. Process names with suffixes (`com.google.android.katniss:interactor`, `system`, `dtv_svc_eu`) must be attributed to the base package or ignored, never crash the PSS parser.
2. A package name containing shell metacharacters (`com.x; reboot`) in an `/api/apply` request must be rejected without running anything.
3. `adb` missing, TV unreachable, or "unauthorized" must produce a JSON error with a fix hint, not a stack trace.
4. Connection drops halfway through an apply: results so far stay in `changes.log` and the snapshot; remaining packages are reported failed, not silently skipped.
5. An already-disabled package (`com.mitv.tvhome.mitvplus`) must appear as disabled and unselectable, never as a candidate.
6. Restoring a missing or corrupt snapshot id returns a clear error and changes nothing.

## File Structure

```
pyproject.toml, requirements.txt, README.md, .gitignore (modify)
xiaomitv/__init__.py
xiaomitv/models.py        # dataclasses shared by all modules
xiaomitv/adb.py           # Adb wrapper + error types
xiaomitv/collector.py     # parse adb output, collect(adb) -> Scan
xiaomitv/analyzer.py      # load_knowledge, analyze(scan, kb) -> Analysis
xiaomitv/data/apps.yaml   # knowledge base
xiaomitv/backup.py        # snapshots
xiaomitv/actions.py       # disable/enable batches + changes.log
xiaomitv/tweaks.py        # optional system settings registry
xiaomitv/server.py        # create_app(...)
xiaomitv/__main__.py      # CLI entry
xiaomitv/static/index.html, app.js, style.css
tests/fakes.py, tests/fixtures/*, tests/test_*.py
```

---

### Task 1: Project scaffold and ADB wrapper

**Files:**
- Create: `pyproject.toml`, `requirements.txt` (`flask`, `pyyaml`, `pytest`), `xiaomitv/__init__.py`, `xiaomitv/adb.py`, `tests/fakes.py`, `tests/test_adb.py`
- Modify: `.gitignore` (add `backups/`, `changes.log`, `.venv/`, `__pycache__/`)

**Interfaces:**
- Produces (`xiaomitv/adb.py`):
  - `class AdbError(Exception)` with attribute `hint: str`
  - `class AdbNotInstalled(AdbError)`, `class TvUnreachable(AdbError)`, `class Unauthorized(AdbError)`
  - `class Adb:` `__init__(self, binary: str = "adb", timeout: float = 30.0)`; `serial: str | None`; `connect(self, host: str, port: int = 5555) -> None`; `shell(self, command: str) -> str`
- Produces (`tests/fakes.py`): `class FakeAdb` with `__init__(self, responses: dict[str, str] | None = None, fail: dict[str, Exception] | None = None)`; `shell(command) -> str` returns `responses[command]` (exact match, else `""`), raises `fail[command]` if present; records every command in `self.calls: list[str]`; `serial = "fake:5555"`.

- [ ] **Step 1: Write failing tests in `tests/test_adb.py`** using `monkeypatch` on `subprocess.run`:
  - `test_connect_ok`: stdout `connected to 1.2.3.4:5555` and `adb devices` listing `1.2.3.4:5555\tdevice` sets `serial == "1.2.3.4:5555"`.
  - `test_connect_unauthorized`: `adb devices` lists `\tunauthorized` → raises `Unauthorized`, `hint` mentions "Allow USB debugging" on the TV.
  - `test_connect_unreachable`: stdout `failed to connect` / `Connection refused` → `TvUnreachable`.
  - `test_missing_binary`: `subprocess.run` raises `FileNotFoundError` → `AdbNotInstalled`, hint contains `sudo apt install adb`.
  - `test_shell_builds_command`: `shell("pm list packages")` runs `["adb","-s",serial,"shell","pm list packages"]`.
  - `test_shell_nonzero_raises_adberror`.
- [ ] **Step 2: Run** `python -m pytest tests/test_adb.py -v` → FAIL (module missing).
- [ ] **Step 3: Implement `Adb`** with `subprocess.run(..., capture_output=True, text=True, timeout=...)`. Map failures to the error classes above, each with a one-line `hint`. Create `FakeAdb` in `tests/fakes.py`. Create a venv and install requirements.
- [ ] **Step 4: Run** `python -m pytest tests/test_adb.py -v` → PASS.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: scaffold project and adb wrapper"`.

### Task 2: Collector

**Files:**
- Create: `xiaomitv/models.py`, `xiaomitv/collector.py`, `tests/test_collector.py`, `tests/fixtures/` (see step 1)

**Interfaces:**
- Produces (`models.py`, all `@dataclass`):
  - `Package(name: str, path: str, system: bool, enabled: bool)`
  - `Scan(device: dict[str, str], mem_total_kb: int, mem_available_kb: int, data_total_kb: int, data_free_kb: int, packages: list[Package], pss_kb: dict[str, int], launcher: str | None)`
- Produces (`collector.py`): `parse_packages(system_out, user_out, disabled_out) -> list[Package]`; `parse_proc_meminfo(text) -> tuple[int, int]` (total, available kB); `parse_pss(text) -> dict[str, int]` (package/process → kB); `parse_df(text) -> tuple[int, int]` (total, free kB); `parse_home(text) -> str | None`; `collect(adb) -> Scan`.

- [ ] **Step 1: Capture fixtures** (read-only) into `tests/fixtures/`: copy `scans/system_packages.txt`, `user_packages.txt`, `disabled_packages.txt`, `meminfo.txt`; add `proc_meminfo.txt` (`cat /proc/meminfo`), `df.txt` (`df -k /data`), `home.txt` (`cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME`), `props.txt` (`getprop ro.product.model`, `ro.product.manufacturer`, `ro.build.version.release`, `ro.build.version.sdk`, one per line in that order). Commands via `adb -s 192.168.1.6:5555 shell ...`.
- [ ] **Step 2: Write failing tests** against fixtures:
  - `parse_packages` → 132 packages (129 system + 3 user); `com.mitv.tvhome.mitvplus`, `com.amazon.amazonvideo.livingroom`, `com.google.android.youtube.tvmusic` have `enabled=False`; `org.videolan.vlc` has `system=False`.
  - `parse_pss` → `"com.mitv.livetv" == 120422`; `"com.google.android.katniss" == 72890` (suffix `:interactor` folded into base package, summed if the base also appears); a process line with no package form (`system`) is kept under its own name and does not raise.
  - `parse_proc_meminfo` → `(1830516, <available>)`; `parse_df` → `(4200992, 1767320)`; `parse_home` → `"com.google.android.apps.tv.launcherx"`; `parse_home("")` → `None`.
  - `collect(FakeAdb(...))` keyed by the exact commands in the module (expose them as module constants) returns a `Scan` with `device["model"] == "MiTV-MOOR2"`.
- [ ] **Step 3: Run** `python -m pytest tests/test_collector.py -v` → FAIL.
- [ ] **Step 4: Implement** the parsers and `collect`. `pm list packages -f -s` lines are `package:<path>=<name>` (split on the last `=`); `-3` and `-d` lines are `package:<name>`; PSS lines look like `    120,935K: name (pid 774 / activities)`.
- [ ] **Step 5: Run** the tests → PASS. **Step 6: Commit** `feat: collector parses TV scan output`.

### Task 3: Knowledge base and analyzer

**Files:**
- Create: `xiaomitv/data/apps.yaml`, `xiaomitv/analyzer.py`, `tests/test_analyzer.py`

**Interfaces:**
- Consumes: `Scan`, `Package` from Task 2.
- Produces (`analyzer.py`):
  - `@dataclass Entry(rating: str, reason: str, tradeoff: str | None = None, button_bound: bool = False, needs_other_launcher: bool = False)`
  - `load_knowledge(path: Path | None = None) -> dict[str, Entry]` (defaults to bundled `data/apps.yaml`)
  - `@dataclass Row(package: str, rating: str, reason: str, tradeoff: str | None, button_bound: bool, ram_kb: int, enabled: bool, selectable: bool, preticked: bool)`
  - `@dataclass Analysis(rows: list[Row], reclaimable_kb: int)` where `reclaimable_kb` sums `ram_kb` of enabled `safe` rows
  - `analyze(scan: Scan, kb: dict[str, Entry]) -> Analysis`
- `apps.yaml` format: top-level mapping `package: {rating, reason, tradeoff?, button_bound?, needs_other_launcher?}`.

- [ ] **Step 1: Write `apps.yaml`** with the spec's three tiers, package names exactly as listed in the spec's Ratings section, each with a one-line `reason`; `tradeoff` text for every `tradeoff` entry; `com.mitv.tvhome.atv` has `needs_other_launcher: true`; regional streaming apps (`com.netflix.ninja`, `com.amazon.amazonvideo.livingroom`, `ru.mts.mtstv`, `tv.more.play`, `ru.rt.video.app.tv`, `ru.rutube.app`, `com.vk.tv`) are `tradeoff` with `button_bound: true`. Include `keep` entries for both Live TV package spellings (`com.mitv.livetv`, `com.mitv.livetv.ci_mediatek`, `com.mitv.livetv.ci.mediatek`, `com.mediatek.wwtv.tvcenter`, `com.mediatek.wwtv.setupwizard`).
- [ ] **Step 2: Write failing tests** on a scan built from the Task 2 fixtures:
  - unknown package (`com.mitv.toolhouse`) → `rating == "keep"`, `selectable` unaffected by enabled state but `preticked False`, reason says it is not in the knowledge base.
  - `com.mitv.tvhome.mitvplus` (disabled) → `enabled False`, `selectable False`, `preticked False`.
  - `com.miui.tv.analytics` → `safe`, `preticked True`, `ram_kb == 17882`.
  - `com.mitv.tvhome.atv` is `safe` when `scan.launcher == "com.google.android.apps.tv.launcherx"`; with `launcher=None` or equal to itself it becomes `keep` with a reason mentioning launcher.
  - `com.google.android.katniss` → `keep`; `com.mitv.livetv` → `keep`.
  - rows sorted: `safe`, then `tradeoff`, then `keep`; ties by `ram_kb` descending. `reclaimable_kb` equals the sum over enabled `safe` rows.
  - every key in `apps.yaml` that is also in the fixture exists in the fixture (guards typos).
- [ ] **Step 3: Run** → FAIL. **Step 4: Implement** `analyze` (pure function). **Step 5: Run** → PASS. **Step 6: Commit** `feat: knowledge base and analyzer`.

### Task 4: Backup snapshots

**Files:**
- Create: `xiaomitv/backup.py`, `tests/test_backup.py`

**Interfaces:**
- Consumes: `Scan`.
- Produces:
  - `class BackupError(Exception)`
  - `create_snapshot(scan: Scan, tweak_states: dict[str, dict[str, str | None]], directory: Path, now: datetime | None = None) -> str` returns snapshot id (`YYYYMMDD-HHMMSS`); writes `<directory>/<id>.json` with keys `version`, `created`, `device`, `mem_available_kb`, `packages` (`{name: enabled}`), `tweaks`; creates the directory.
  - `list_snapshots(directory: Path) -> list[dict]` newest first, each `{id, created, packages_disabled: int}`; skips unreadable files.
  - `load_snapshot(directory: Path, snapshot_id: str) -> dict` raises `BackupError` on missing, corrupt, or an id not matching `^\d{8}-\d{6}$`.
  - `packages_to_reenable(snapshot: dict, current: list[Package]) -> list[str]` — packages enabled in the snapshot but disabled now.

- [ ] **Step 1: Failing tests:** round trip create → load equals saved data; two snapshots listed newest first; corrupt JSON file is skipped by `list_snapshots` and raises `BackupError` from `load_snapshot`; id `../etc/passwd` raises `BackupError`; `packages_to_reenable` returns only packages that were enabled then and disabled now (package already disabled in the snapshot is not returned).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** `feat: backup snapshots`.

### Task 5: Actions

**Files:**
- Create: `xiaomitv/actions.py`, `tests/test_actions.py`

**Interfaces:**
- Consumes: `Adb`/`FakeAdb.shell`, `AdbError`.
- Produces:
  - `PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")`
  - `@dataclass Result(package: str, ok: bool, message: str)`
  - `disable_packages(adb, packages: list[str], log_path: Path) -> Iterator[Result]` — generator, so the server can stream. Runs `pm disable-user --user 0 <pkg>`; ok when output contains `new state: disabled-user`.
  - `enable_packages(adb, packages: list[str], log_path: Path) -> Iterator[Result]` — `pm enable --user 0 <pkg>`; ok when output contains `new state: enabled`.
  - Each result is appended to `log_path` as one JSON line (`time`, `action`, `package`, `ok`, `message`) **before** the next command runs.

- [ ] **Step 1: Failing tests:** command string is exactly `pm disable-user --user 0 com.miui.tv.analytics`; a name failing `PACKAGE_RE` yields `ok False` and no command is sent (`fake.calls == []`); an `AdbError` on the second of three packages yields `ok False` for it and the third still runs; if every remaining command raises `TvUnreachable`, remaining packages are reported `ok False` with the error message; log file has one JSON line per result and the line for package N exists before package N+1's command is recorded (use a `FakeAdb` that asserts the log line count inside `shell`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** `feat: disable/enable actions with change log`.

### Task 6: Tweaks

**Files:**
- Create: `xiaomitv/tweaks.py`, `tests/test_tweaks.py`

**Interfaces:**
- Produces:
  - `@dataclass Setting(kind: str, namespace: str | None, key: str, on_value: str)` — `kind` is `"settings_global"` or `"device_config"`
  - `@dataclass Tweak(id: str, name: str, description: str, warning: str, settings: list[Setting], reboot_required: bool)`
  - `TWEAKS: dict[str, Tweak]` containing `"cached-app-freezer"` with settings: `settings_global cached_apps_freezer=enabled`, `device_config activity_manager_native_boot use_freezer=true`, `device_config activity_manager_native_boot freeze_debounce_timeout=1000`; `reboot_required=True`; warning states kernel support is unverified.
  - `read_state(adb, tweak: Tweak) -> dict[str, str | None]` keyed by `Setting.key`; the literal output `null` or empty becomes `None`.
  - `is_enabled(tweak: Tweak, state: dict) -> bool` — true only when every setting equals its `on_value`.
  - `apply(adb, tweak: Tweak) -> None`; `revert(adb, tweak: Tweak, previous: dict[str, str | None]) -> None` — restores the previous value, or deletes the key (`settings delete global <key>` / `device_config delete <namespace> <key>`) when it was `None`.

- [ ] **Step 1: Verify delete syntax** read-only: `adb -s 192.168.1.6:5555 shell 'device_config help; settings help' | grep -i delete` — expected output shows both `delete` forms; if not, adjust the revert commands and note it in the commit message.
- [ ] **Step 2: Failing tests:** `read_state` with `FakeAdb` answering `null` gives all `None` and `is_enabled False`; `apply` sends exactly the three `put` commands; `revert` with all-`None` previous sends the three delete commands; `revert` with a previous `"disabled"` for `cached_apps_freezer` puts that value back; `is_enabled` is false when only two of three are set.
- [ ] **Step 3: Run** → FAIL. **Step 4: Implement.** **Step 5: Run** → PASS. **Step 6: Commit** `feat: optional tweaks registry (cached-app freezer)`.

### Task 7: Flask API

**Files:**
- Create: `xiaomitv/server.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `create_app(adb, backup_dir: Path, log_path: Path, knowledge: dict[str, Entry] | None = None) -> Flask`. State (last `Scan`, last `Analysis`) lives in `app.config`; a `threading.Lock` serializes `/api/apply`, `/api/restore`, `/api/tweaks/<id>`.
- Endpoints (all JSON):
  - `POST /api/connect {"host": str}` → `{ok: true, serial}`; errors via `AdbError`
  - `POST /api/scan` → `{device, memory: {total_kb, available_kb}, storage: {total_kb, free_kb}, launcher, reclaimable_kb, rows: [Row as dict], reenabled_since_backup: [package], tweaks: [{id, name, description, warning, reboot_required, enabled}]}` — `reenabled_since_backup` lists packages that the newest snapshot shows as enabled, that the last `changes.log` entry for that package disabled, and that are enabled now (empty when there is no log or snapshot).
  - `POST /api/apply {"packages": [...], "force": bool}` → `application/x-ndjson` stream: first line `{"snapshot": id}`, then one `{"package", "ok", "message"}` per package, last line `{"done": true, "memory_available_kb": int}`
  - `GET /api/backups` → `{backups: [...]}`; `POST /api/restore {"id": str}` → `{reenabled: [Result as dict], tweaks_reverted: [ids]}`
  - `POST /api/tweaks/<id> {"action": "enable"|"disable"}` → `{snapshot, enabled}`; creates a snapshot first; disable uses `revert` with the tweak state stored in the newest snapshot, else the all-`None` defaults.
- Error mapping: `AdbError` → HTTP 502 `{error, hint}`; validation failure → 400 `{error}`; `BackupError` → 404 `{error}`; no scan yet → 409 `{error: "Run a scan first"}`.

- [ ] **Step 1: Failing tests with `app.test_client()` and a `FakeAdb`** seeded from fixtures:
  - scan returns `rows`, `reclaimable_kb > 0`, `tweaks[0].id == "cached-app-freezer"`, `tweaks[0].enabled False`, `reenabled_since_backup == []`.
  - after a logged successful disable of `com.miui.tv.analytics` in `changes.log`, a scan where that package is enabled again returns it in `reenabled_since_backup`.
  - `/api/apply` before any scan → 409; with `["com.x; reboot"]` → 400 and `fake.calls` has no `pm disable-user`; with a `keep` package and no `force` → 400; with `com.mitv.tvhome.mitvplus` (already disabled) → 400; with two `safe` packages → stream has a snapshot line, two result lines, a done line, and a snapshot file exists in `tmp_path`.
  - `AdbNotInstalled` during scan → 502 with `hint` containing `apt install adb`.
  - `/api/restore` with unknown id → 404; with a valid snapshot re-enables only packages disabled since.
  - tweak enable then disable sends the expected commands and creates a snapshot each time.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5: Commit** `feat: flask API`.

### Task 8: Web page

**Files:**
- Create: `xiaomitv/static/index.html`, `xiaomitv/static/app.js`, `xiaomitv/static/style.css`, `tests/test_static.py`
- Modify: `xiaomitv/server.py` (serve `/` and `/static/*`)

**Interfaces:**
- Consumes: the Task 7 endpoints.
- Page element ids (the test and `app.js` rely on them): `host`, `connect-btn`, `status-banner`, `ram-summary`, `storage-summary`, `scan-btn`, `apps-table`, `apply-btn`, `apply-summary`, `progress-list`, `tweaks-section`, `backups-list`.

- [ ] **Step 1: Failing test:** `GET /` returns 200 and the HTML contains every id above; `GET /static/app.js` returns 200.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement the page** with plain JS (`fetch`, no libraries), following the spec's page section: host field prefilled `192.168.1.6`; error banner shows `error` and `hint`; table columns name, RAM (MB), rating badge, reason (+ trade-off text, and a "disable only" tag when `button_bound`); `safe` + enabled rows pre-ticked, and packages in `reenabled_since_backup` get a "came back" badge and are pre-ticked; `keep` and disabled rows have disabled checkboxes; Apply shows "N apps will be disabled, snapshot will be saved" and requires a confirm dialog; `/api/apply` is read as an NDJSON stream into `progress-list`; after `done`, show RAM before → after and the reminders (reboot the TV, re-check after firmware updates, turn USB debugging off when finished); tweaks section with enable/disable buttons and the warning text; backups list with a Restore button. Use CSS variables with a `prefers-color-scheme: dark` override and a layout that works at 375px width.
- [ ] **Step 4: Run** the full suite `python -m pytest -v` → PASS. **Step 5: Commit** `feat: web page`.

### Task 9: CLI entry, README, live read-only check

**Files:**
- Create: `xiaomitv/__main__.py`, `README.md`
- Modify: `pyproject.toml` (console script `xiaomitv`)

**Interfaces:**
- Produces: `python -m xiaomitv [--tv HOST] [--port 8080] [--lan] [--no-browser] [--backup-dir backups] [--log changes.log]`. `--tv` pre-connects at startup if given. `--lan` binds `0.0.0.0` and prints a warning that anyone on the network can change the TV.

- [ ] **Step 1: Failing test** `tests/test_cli.py`: `parse_args(["--lan"])` gives host `0.0.0.0`; default gives `127.0.0.1`; `build_app(args)` returns a Flask app.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** `parse_args`, `build_app`, `main`. Write `README.md`: install (`sudo apt install adb`, venv, `pip install -r requirements.txt`), enabling ADB on the TV, running, what each rating means, how to restore, and the safety rules.
- [ ] **Step 4: Run** `python -m pytest -v` → all PASS.
- [ ] **Step 5: Live read-only check** (no `/api/apply`, no tweak change): start `python -m xiaomitv --no-browser --tv 192.168.1.6`, then `curl -s -X POST localhost:8080/api/scan | python -m json.tool | head -60`. Expected: model `MiTV-MOOR2`, `launcher` `com.google.android.apps.tv.launcherx`, `com.mitv.tvhome.mitvplus` disabled and unselectable, `com.miui.tv.analytics` `safe` and pre-ticked. Open `http://127.0.0.1:8080` in the browser pane and confirm the table renders and no console errors. Stop the server.
- [ ] **Step 6: Commit** `feat: CLI entry and README`. Then ask the user before the first real apply.

---

## Self-Review

- **Spec coverage:** adb wrapper (T1), collector incl. launcher (T2), analyzer + three ratings + launcher condition + button-bound + matching on scan names (T3), backup before every apply (T4, T7), actions with per-app log (T5), tweaks incl. snapshot revert (T6, T7), `--lan` and localhost (T9), error hints (T1, T7), streamed live status and RAM before/after (T7, T8), reboot / firmware / USB-debugging reminders (T8), re-scan flags apps that came back via `reenabled_since_backup` (T7) shown as a "came back" badge with a re-disable tick in the page (T8).
- **Open item from spec** (how to confirm the freezer took effect): not solved by this plan; the page shows the setting values only and says the effect is unverified.
- **Not built (out of scope per spec):** `pm compile`, stub-APK tricks, region trick, multi-device.
- **Type check:** `Scan`, `Package`, `Row`, `Analysis`, `Result`, `Tweak`, `Setting` names are used identically in every task.
