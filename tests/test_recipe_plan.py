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
