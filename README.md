# XiaomiTV Debloat

A local web page that connects to a Xiaomi TV over ADB, shows what is running, recommends
apps to disable, and backs up the TV's app state before every change.

Built and tested on a `MiTV-MOOR2` (Xiaomi MI TV A2 family, Google TV, Android 11).
Other Xiaomi TVs should work, but the ratings come from forum reports for this model.

## Install

```bash
sudo apt install adb
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Prepare the TV

1. Settings → Device Preferences → About: click **Build** 7 times.
2. Settings → Device Preferences → Developer options: turn on **USB debugging** (ADB debugging).
3. Note the TV's IP address (Settings → Network). The TV and computer must be on the same network.
4. The first time you connect, accept the **Allow USB debugging?** prompt on the TV.

## Run

```bash
.venv/bin/python -m xiaomitv --tv 192.168.1.6
```

Opens `http://127.0.0.1:8080`. Click **Scan**, review the table, tick apps, click **Apply**.
`--lan` makes the page reachable from other devices on your network; there is no password,
so leave it off unless you need it.

## Recipes

A recipe is a tested list of changes for one TV model and Android version: which apps to disable
and why, what it costs, what did not work, and how to undo it. The **Recipes** card in the page shows
them.

### Using a recipe

1. Connect and **Scan**. The **Model** and **Android** filters preselect your TV; choose "All" to see
   every recipe.
2. Click a recipe. The apps table replaces its selection with every app from the recipe that your
   TV has, that is still enabled, and that is not locked. The line above the list says how many were
   skipped and why (not on this TV, already disabled, locked, or in a manual step).
3. Open **Steps, undo and sources** to read each step. **Tick this step** adds one step's apps to
   the current selection. Manual steps, like swapping the launcher, are text only and never ticked.
4. Review the table, untick anything you want to keep, then **Apply**. The usual confirm, backup and
   Restore still apply, and locked ("keep") apps stay locked.

A recipe is a starting point from one TV. Firmware differs, so check what each step costs and test
your TV after applying it (reboot, then try the HDMI inputs, remote buttons and your apps).

### Included recipes

| Recipe | TV | Android | Result |
|---|---|---|---|
| `mitv-moor2-android11` | Xiaomi MiTV-MOOR2 (MI TV A2 family), Google TV | 11 | free RAM 822 MB to about 1,016 MB |
| `tcl-beyondtv4-android11` | TCL 43P635 Google TV (codename `BeyondTV4`) | 11 | not measured yet; built from forum reports |

### Adding a recipe

Recipes are YAML files in `xiaomitv/data/recipes/`. Copy
`mitv-moor2-android11.yaml` and change:

```yaml
id: my-tv-android11          # unique
title: Human readable title
models: [MiTV-MOOR2]         # `getprop ro.product.model`, or the codename `ro.product.device`
                             # when the brand reports a generic model (TCL says "Smart TV")
android: ["11"]              # as reported by `getprop ro.build.version.release`
summary: One or two sentences.
result: {before_mb: 822, after_mb: 1016, note: what was measured}
steps:
  - title: "1. Safe apps"
    notes: Why, and what it costs.
    packages: [com.example.app]
  - title: "2. A manual step"
    notes: Things the tool cannot do for you.
    manual: true             # shown as text, never ticked
tried_and_failed: ["What did not work or broke, and the fix."]
undo: ["How to put it back."]
sources: [{title: Forum thread, url: "https://example.org"}]
```

Package names must be valid Android package names, and a recipe needs at least one model, one
Android version and one step. `python -m pytest` checks every bundled recipe. A recipe can only
tick apps that the knowledge base does not lock, so also add or adjust the matching entries in
`xiaomitv/data/apps.yaml` when you learn that an app is safe or breaks something.

## Ratings

- **safe**: telemetry, promo and setup leftovers. Pre-ticked.
- **trade-off**: works, but something stops working (shown in the row). Not pre-ticked.
- **keep**: the TV needs it, or the tool does not know it. Locked.

Apps tied to remote-control buttons are marked "disable only": uninstalling them breaks
button remapping, and this tool never uninstalls anything.

## Safety

- Only `pm disable-user --user 0` and `pm enable --user 0` are used. No root, no uninstall.
- A backup snapshot (`backups/`) is saved before every apply and every tweak change.
  **Restore** re-enables the apps that were enabled in that snapshot and reverts tweaks.
- Every change is logged to `changes.log`.
- Reboot the TV before judging any lag change. Firmware updates can bring removed apps
  back; scan again and the page flags them as "came back".
- Turn USB debugging off when you are finished.

## Tests

```bash
.venv/bin/python -m pytest
```

The tests use real output captured from the target TV in `tests/fixtures/`.
