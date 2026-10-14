import dataclasses

from xiaomitv.analyzer import analyze, load_knowledge

LAUNCHERX = "com.google.android.apps.tv.launcherx"
# apps.yaml also covers other firmware builds; these safe entries are not on the target TV.
SAFE_ABSENT_ON_TARGET = {"com.xiaomi.floatingframe", "com.google.android.videos"}


def rows_by_name(scan, kb=None):
    analysis = analyze(scan, kb or load_knowledge())
    return analysis, {r.package: r for r in analysis.rows}


def test_unknown_package_is_keep_and_not_preticked(scan):
    _, rows = rows_by_name(scan)
    row = rows["com.mitv.toolhouse"]
    assert row.rating == "keep"
    assert not row.preticked and not row.selectable
    assert "not in the knowledge base" in row.reason.lower()


def test_already_disabled_package_is_unselectable(scan):
    _, rows = rows_by_name(scan)
    row = rows["com.mitv.tvhome.mitvplus"]
    assert not row.enabled and not row.selectable and not row.preticked


def test_safe_package_is_preticked_with_ram(scan):
    _, rows = rows_by_name(scan)
    row = rows["com.miui.tv.analytics"]
    assert row.rating == "safe"
    assert row.preticked and row.selectable
    assert row.ram_kb == 17882


def test_patchwall_safe_only_with_another_active_launcher(scan):
    kb = load_knowledge()
    _, rows = rows_by_name(scan, kb)
    assert rows["com.mitv.tvhome.atv"].rating == "safe"
    for launcher in (None, "com.mitv.tvhome.atv"):
        _, rows = rows_by_name(dataclasses.replace(scan, launcher=launcher), kb)
        assert rows["com.mitv.tvhome.atv"].rating == "keep"
        assert "launcher" in rows["com.mitv.tvhome.atv"].reason.lower()


def test_core_packages_are_keep(scan):
    _, rows = rows_by_name(scan)
    assert rows["com.google.android.katniss"].rating == "keep"
    assert rows["com.mitv.livetv"].rating == "keep"
    assert rows[LAUNCHERX].rating == "keep"


def test_tradeoff_rows_are_not_preticked_and_explain_cost(scan):
    _, rows = rows_by_name(scan)
    row = rows["com.mediatek.tv.service"]
    assert row.rating == "tradeoff"
    assert row.selectable and not row.preticked
    assert row.tradeoff


def test_button_bound_streaming_apps_flagged(scan):
    _, rows = rows_by_name(scan)
    assert rows["com.netflix.ninja"].button_bound


def test_rows_sorted_by_rating_then_ram(scan):
    analysis, _ = rows_by_name(scan)
    order = {"safe": 0, "tradeoff": 1, "keep": 2}
    keys = [(order[r.rating], -r.ram_kb) for r in analysis.rows]
    assert keys == sorted(keys)


def test_reclaimable_is_sum_of_enabled_safe_rows(scan):
    analysis, _ = rows_by_name(scan)
    expected = sum(r.ram_kb for r in analysis.rows if r.rating == "safe" and r.enabled)
    assert analysis.reclaimable_kb == expected > 0


def test_uninstalled_knowledge_entries_produce_no_rows(scan):
    analysis, _ = rows_by_name(scan)
    installed = {p.name for p in scan.packages}
    assert {r.package for r in analysis.rows} == installed


def test_safe_entries_match_target_tv_package_names(scan):
    kb = load_knowledge()
    installed = {p.name for p in scan.packages}
    missing = {n for n, e in kb.items() if e.rating == "safe"} - installed
    assert missing == SAFE_ABSENT_ON_TARGET


def test_every_entry_has_valid_rating_and_reason():
    for name, entry in load_knowledge().items():
        assert entry.rating in {"safe", "tradeoff", "keep"}, name
        assert entry.reason, name
        if entry.rating == "tradeoff":
            assert entry.tradeoff, name
