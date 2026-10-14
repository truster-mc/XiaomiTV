IDS = ["host", "connect-btn", "status-banner", "ram-summary", "storage-summary",
       "scan-btn", "apps-table", "apply-btn", "apply-summary", "progress-list",
       "tweaks-section", "backups-list"]


def test_index_has_every_element_the_script_needs(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    for element_id in IDS:
        assert f'id="{element_id}"' in html, element_id


def test_static_assets_are_served(client):
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_script_uses_every_page_id_and_every_endpoint(client):
    js = client.get("/static/app.js").get_data(as_text=True)
    for element_id in IDS:
        assert element_id in js, element_id
    for endpoint in ["/api/connect", "/api/scan", "/api/apply", "/api/backups",
                     "/api/restore", "/api/tweaks/"]:
        assert endpoint in js, endpoint


RECIPE_IDS = ["recipes-section", "recipe-model", "recipe-android", "recipes-list", "recipe-note"]


def test_page_has_recipe_elements_and_script_uses_them(client):
    html = client.get("/").get_data(as_text=True)
    js = client.get("/static/app.js").get_data(as_text=True)
    for element_id in RECIPE_IDS:
        assert f'id="{element_id}"' in html, element_id
        assert element_id in js, element_id
    assert "/api/recipes" in js
    assert "innerHTML" not in js
