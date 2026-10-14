import pytest

from xiaomitv.actions import PACKAGE_RE
from xiaomitv.recipes import Recipe, filter_recipes, load_recipes


def write(tmp_path, name, body):
    (tmp_path / name).write_text(body)


GOOD = """
id: r1
title: Test recipe
models: [MiTV-MOOR2]
android: ["11"]
summary: A summary.
result: {before_mb: 800, after_mb: 900, note: fresh reboot}
steps:
  - title: Step one
    notes: Do it.
    packages: [com.a.one, com.a.two]
  - title: Manual step
    notes: By hand.
    manual: true
tried_and_failed: ["freezer resets"]
undo: ["pm enable"]
sources: [{title: Forum, url: "https://example.org"}]
"""


def test_bundled_recipes_are_valid():
    recipes = load_recipes()
    assert recipes, "at least the MiTV-MOOR2 recipe ships"
    assert len({r.id for r in recipes}) == len(recipes)
    for r in recipes:
        assert r.models and r.android and r.steps, r.id
        for step in r.steps:
            for pkg in step.packages:
                assert PACKAGE_RE.match(pkg), (r.id, pkg)


def test_moor2_recipe_covers_known_changes():
    r = next(r for r in load_recipes() if "MiTV-MOOR2" in r.models)
    assert "11" in r.android
    packages = {p for s in r.steps for p in s.packages}
    assert {"com.miui.tv.analytics", "com.mitv.tvhome.atv",
            "com.google.android.katniss", "com.google.android.apps.tv.launcherx"} <= packages
    assert any(s.manual for s in r.steps)


def test_load_parses_fields(tmp_path):
    write(tmp_path, "r1.yaml", GOOD)
    (r,) = load_recipes(tmp_path)
    assert isinstance(r, Recipe)
    assert r.steps[0].packages == ["com.a.one", "com.a.two"] and not r.steps[0].manual
    assert r.steps[1].manual and r.steps[1].packages == []
    assert r.result["after_mb"] == 900


def test_invalid_package_name_is_rejected(tmp_path):
    write(tmp_path, "bad.yaml", GOOD.replace("com.a.two", "com.x; reboot"))
    with pytest.raises(ValueError, match="com.x; reboot"):
        load_recipes(tmp_path)


def test_missing_models_or_duplicate_ids_are_rejected(tmp_path):
    write(tmp_path, "a.yaml", GOOD.replace("models: [MiTV-MOOR2]", "models: []"))
    with pytest.raises(ValueError):
        load_recipes(tmp_path)
    (tmp_path / "a.yaml").unlink()
    write(tmp_path, "b.yaml", GOOD)
    write(tmp_path, "c.yaml", GOOD)
    with pytest.raises(ValueError, match="duplicate"):
        load_recipes(tmp_path)


def test_filter_by_model_and_android(tmp_path):
    write(tmp_path, "r1.yaml", GOOD)
    write(tmp_path, "r2.yaml", GOOD.replace("id: r1", "id: r2")
          .replace("MiTV-MOOR2", "MiTV-OTHER").replace('["11"]', '["10"]'))
    recipes = load_recipes(tmp_path)
    ids = lambda **kw: sorted(r.id for r in filter_recipes(recipes, **kw))
    assert ids() == ["r1", "r2"]
    assert ids(model="mitv-moor2") == ["r1"]          # case-insensitive
    assert ids(android="10") == ["r2"]
    assert ids(model="MiTV-MOOR2", android="10") == []
    assert ids(model="", android="") == ["r1", "r2"]
