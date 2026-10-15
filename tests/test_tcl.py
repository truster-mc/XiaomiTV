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
UNDOCUMENTED = ["com.tcl.versionUpdateApp", "com.tcl.xian.StartandroidService",
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
    assert {"com.tcl.gallery", "com.google.android.partnersetup", "com.google.android.katniss"} <= ticked
    assert not ({"com.tcl.tv", "com.tcl.suspension", "com.google.android.gms"} & ticked)
    assert "com.tcl.messagebox" not in ticked          # already disabled on this TV


def test_moor2_recipe_does_not_match_the_tcl_tv():
    assert [r.id for r in filter_recipes(load_recipes(), "BeyondTV4")] == ["tcl-beyondtv4-android11"]
    assert "tcl-beyondtv4-android11" not in [r.id for r in filter_recipes(load_recipes(), "MiTV-MOOR2")]


def test_tcl_recipe_is_also_found_by_the_marketing_model():
    assert [r.id for r in filter_recipes(load_recipes(), "43P635")] == ["tcl-beyondtv4-android11"]
    assert [r.id for r in filter_recipes(load_recipes(), "43p635", "11")] == ["tcl-beyondtv4-android11"]


def tcl_recipe():
    return next(r for r in load_recipes() if r.id == "tcl-beyondtv4-android11")


def test_tcl_recipe_has_a_measured_result():
    r = tcl_recipe().result
    assert 0 < r["before_mb"] < r["after_mb"]
    assert "reboot" in r["note"].lower() and "swap" in r["note"].lower()


def test_netflix_is_not_ticked_by_default_because_of_its_remote_button():
    auto = {p for s in tcl_recipe().steps if not s.manual for p in s.packages}
    assert "com.netflix.ninja" not in auto
    text = " ".join(s.notes for s in tcl_recipe().steps)
    assert "Netflix" in text and "button" in text


def test_tcl_recipe_orders_the_steps_safest_first_and_ends_with_the_manual_launcher_step():
    steps = tcl_recipe().steps
    assert [s.manual for s in steps] == [False, False, False, False, True]
    assert "com.google.android.katniss" in steps[3].packages     # assistant and accessibility step
    assert "official" in steps[-1].notes.lower()
    assert "setupwraith" in steps[-1].notes


def test_tcl_recipe_records_what_to_test_and_the_lessons():
    text = " ".join(tcl_recipe().tried_and_failed)
    assert "load average" in text.lower()
    assert "HDMI" in " ".join(s.notes for s in tcl_recipe().steps)


def test_tcl_recipe_records_the_decompiled_findings():
    step2, step5 = tcl_recipe().steps[1].notes, tcl_recipe().steps[-1].notes
    assert "Listen Alone" in step2 and "Bluetooth" in step2
    assert "com.tcl.bi is TCL's usage analytics" in step5
    assert "accepts any TLS certificate" in step5
    assert "bluetooth" in KB["com.tcl.t_solo"].tradeoff.lower()


def test_tcl_bi_is_a_selectable_tradeoff_that_is_never_preticked(tcl_scan):
    r = rows(tcl_scan)["com.tcl.bi"]
    assert r.rating == "tradeoff" and r.selectable and not r.preticked
    assert "not tested" in r.tradeoff.lower()
    auto = {p for s in tcl_recipe().steps if not s.manual for p in s.packages}
    assert "com.tcl.bi" not in auto


def test_tcl_recipe_says_guard_was_already_disabled_on_the_tested_tv():
    text = " ".join(s.notes for s in tcl_recipe().steps) + " " + " ".join(tcl_recipe().tried_and_failed)
    assert "com.tcl.guard was already disabled" in text


def test_tcl_recipe_says_disabling_guard_does_not_stop_its_process():
    text = " ".join(s.notes for s in tcl_recipe().steps) + " " + " ".join(tcl_recipe().tried_and_failed)
    assert "does not stop it" in text and "persistent" in text


def test_tcl_guard_is_locked_with_the_reason_disabling_does_not_help(tcl_scan):
    assert KB["com.tcl.guard"].rating == "keep"
    reason = KB["com.tcl.guard"].reason.lower()
    assert "persistent" in reason and "does not stop it" in reason
    assert not rows(tcl_scan)["com.tcl.guard"].selectable
