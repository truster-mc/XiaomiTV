import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "xiaomitv" / "static" / "recipe_plan.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def run(recipe, rows, step=None):
    code = (f"const {{planTick}} = require({json.dumps(str(SCRIPT))});"
            f"console.log(JSON.stringify(planTick({json.dumps(recipe)}, {json.dumps(rows)}, "
            f"{json.dumps(step)})));")
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def row(pkg, enabled=True, selectable=True):
    return {"package": pkg, "enabled": enabled, "selectable": selectable}


RECIPE = {"steps": [
    {"title": "a", "manual": False, "packages": ["com.a.one", "com.a.gone", "com.a.off", "com.a.locked"]},
    {"title": "b", "manual": False, "packages": ["com.a.one", "com.a.two"]},
    {"title": "c", "manual": True, "packages": ["com.a.launcher", "com.a.two"]},
]}
ROWS = [row("com.a.one"), row("com.a.two"), row("com.a.off", enabled=False, selectable=False),
        row("com.a.locked", selectable=False), row("com.a.launcher", selectable=False)]


def test_whole_recipe_ticks_everything_found_and_explains_the_rest():
    plan = run(RECIPE, ROWS)
    assert sorted(plan["tick"]) == ["com.a.one", "com.a.two"]          # deduped
    assert plan["skipped"]["not_on_tv"] == ["com.a.gone"]
    assert plan["skipped"]["disabled"] == ["com.a.off"]
    assert plan["skipped"]["locked"] == ["com.a.locked"]
    assert plan["skipped"]["manual"] == ["com.a.launcher"]              # com.a.two is ticked elsewhere


def test_single_step_only_looks_at_that_step():
    plan = run(RECIPE, ROWS, 1)
    assert sorted(plan["tick"]) == ["com.a.one", "com.a.two"]
    assert plan["skipped"] == {"not_on_tv": [], "disabled": [], "locked": [], "manual": []}


def test_manual_step_ticks_nothing():
    plan = run(RECIPE, ROWS, 2)
    assert plan["tick"] == []
    assert sorted(plan["skipped"]["manual"]) == ["com.a.launcher", "com.a.two"]


def test_no_rows_means_everything_is_not_on_tv():
    plan = run(RECIPE, [])
    assert plan["tick"] == [] and len(plan["skipped"]["not_on_tv"]) == 5


def pick(device, filters):
    code = (f"const {{pickFilters}} = require({json.dumps(str(SCRIPT))});"
            f"console.log(JSON.stringify(pickFilters({json.dumps(device)}, {json.dumps(filters)})));")
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


FILTERS = {"models": ["BeyondTV4", "MiTV-MOOR2"], "android": ["11"]}


def test_pick_filters_prefers_the_model_then_the_codename():
    assert pick({"model": "MiTV-MOOR2", "device": "x", "android": "11"}, FILTERS) == \
        {"model": "MiTV-MOOR2", "android": "11"}
    # TCL reports the generic model "Smart TV", so the codename picks the recipe
    assert pick({"model": "Smart TV", "device": "BeyondTV4", "android": "11"}, FILTERS) == \
        {"model": "BeyondTV4", "android": "11"}


def test_pick_filters_falls_back_to_all():
    assert pick({"model": "Other", "device": "Unknown", "android": "9"}, FILTERS) == \
        {"model": "", "android": ""}
    assert pick({"model": "mitv-moor2", "android": "11"}, FILTERS)["model"] == "MiTV-MOOR2"
    assert pick(None, FILTERS) == {"model": "", "android": ""}
