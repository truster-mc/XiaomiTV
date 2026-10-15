import pytest

from xiaomitv.analyzer import analyze, load_knowledge
from xiaomitv.recipes import filter_recipes, load_recipes

KB = load_knowledge()

NEVER_TOUCH = [
    "com.tcl.tv", "com.tcl.tvinput", "com.tcl.suspension", "com.tcl.ttvs",
    "com.tcl.tcl_bt_rcu_service", "com.tcl.autopair", "com.android.location.fused",
    "com.google.android.gsf", "com.tcl.system.server", "com.tcl.factory.view",
    "com.tcl.providers.config", "com.tcl.settings", "com.tcl.initsetup", "com.tvos",
    "com.tcl.android.webview",
]
REPORTED_REMOVABLE = [
    "com.tcl.gallery", "com.tcl.ui_mediaCenter", "com.tcl.dashboard", "com.tcl.imageplayer",
    "com.tcl.videoplayer", "com.tcl.micmanager", "com.tcl.t_solo", "com.tcl.useragreement",
    "com.tcl.usercenter",
]
UNDOCUMENTED = ["com.tcl.bi", "com.tcl.versionUpdateApp", "com.tcl.xian.StartandroidService",
                "com.tcl.overseasappshow"]


def rows(scan):
    return {r.package: r for r in analyze(scan, KB).rows}


@pytest.mark.parametrize("pkg", NEVER_TOUCH)
def test_never_touch_packages_are_locked(pkg):
    assert KB[pkg].rating == "keep", pkg


def test_never_touch_reasons_name_what_breaks():
    assert "power button" in KB["com.tcl.tv"].reason.lower()
    assert "source" in KB["com.tcl.suspension"].reason.lower()
    assert "update" in KB["com.tcl.ttvs"].reason.lower()


def test_forum_reported_tcl_apps_are_tradeoffs_that_say_so(tcl_scan):
    r = rows(tcl_scan)
    for pkg in REPORTED_REMOVABLE:
        assert r[pkg].rating == "tradeoff", pkg
        assert r[pkg].selectable and not r[pkg].preticked, pkg
        assert r[pkg].tradeoff, pkg


def test_partnersetup_is_safe_and_partnercustomizer_warns_about_buttons(tcl_scan):
    r = rows(tcl_scan)
    assert r["com.google.android.partnersetup"].rating == "safe"
    assert "button" in KB["com.tcl.partnercustomizer"].tradeoff.lower()


def test_undocumented_tcl_background_services_stay_locked(tcl_scan):
    r = rows(tcl_scan)
    for pkg in UNDOCUMENTED:
        assert r[pkg].rating == "keep", pkg
        assert "not in the knowledge base" in r[pkg].reason.lower(), pkg


def test_every_recipe_only_ticks_known_unlocked_apps():
    for recipe in load_recipes():
        for step in recipe.steps:
            if step.manual:
                continue
            for pkg in step.packages:
                assert pkg in KB and KB[pkg].rating != "keep", (recipe.id, pkg)


def test_tcl_recipe_matches_the_codename_and_ticks_expected_apps(tcl_scan):
    recipes = filter_recipes(load_recipes(), "BeyondTV4", "11")
    assert [r.id for r in recipes] == ["tcl-beyondtv4-android11"]
    r = rows(tcl_scan)
    ticked = {p for s in recipes[0].steps if not s.manual for p in s.packages
              if p in r and r[p].enabled and r[p].selectable}
    assert {"com.tcl.gallery", "com.google.android.partnersetup", "com.netflix.ninja"} <= ticked
    assert not ({"com.tcl.tv", "com.tcl.suspension", "com.google.android.gms"} & ticked)
    assert "com.tcl.messagebox" not in ticked          # already disabled on this TV


def test_moor2_recipe_does_not_match_the_tcl_tv():
    assert [r.id for r in filter_recipes(load_recipes(), "BeyondTV4")] == ["tcl-beyondtv4-android11"]
    assert "tcl-beyondtv4-android11" not in [r.id for r in filter_recipes(load_recipes(), "MiTV-MOOR2")]


def test_tcl_recipe_is_also_found_by_the_marketing_model():
    assert [r.id for r in filter_recipes(load_recipes(), "43P635")] == ["tcl-beyondtv4-android11"]
    assert [r.id for r in filter_recipes(load_recipes(), "43p635", "11")] == ["tcl-beyondtv4-android11"]
