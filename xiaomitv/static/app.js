"use strict";
const $ = (id) => document.getElementById(id);
let rows = [];
let cameBack = new Set();

function banner(message, hint, info) {
  const el = $("status-banner");
  el.className = info ? "banner info" : "banner";
  el.textContent = message;
  if (hint) {
    const h = document.createElement("span");
    h.className = "hint";
    h.textContent = hint;
    el.appendChild(h);
  }
  el.hidden = !message;
}

async function api(url, body) {
  const opts = body === undefined
    ? {}
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  let resp;
  try {
    resp = await fetch(url, opts);
  } catch (e) {
    throw { error: "Cannot reach the local server.", hint: "Is xiaomitv still running?" };
  }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw data;
  return data;
}

function report(err) {
  banner(err.error || "Something went wrong", err.hint || "", false);
}

const mb = (kb) => Math.round(kb / 1024) + " MB";
const gb = (kb) => (kb / 1048576).toFixed(1) + " GB";

function selectedPackages() {
  return [...document.querySelectorAll("#apps-table input[data-pkg]:checked")].map((c) => c.dataset.pkg);
}

function updateSummary() {
  const n = selectedPackages().length;
  $("apply-summary").textContent = n
    ? `${n} app${n === 1 ? "" : "s"} will be disabled, a backup snapshot will be saved first`
    : "Nothing selected";
  $("apply-btn").disabled = n === 0;
}

function renderRows() {
  const body = $("apps-table").querySelector("tbody");
  body.textContent = "";
  const showLocked = $("show-locked").checked;
  for (const r of rows) {
    if (r.rating === "keep" && !showLocked) continue;
    const tr = document.createElement("tr");
    if (!r.enabled) tr.className = "off";

    const c0 = document.createElement("td");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.dataset.pkg = r.package;
    box.disabled = !r.selectable;
    box.checked = r.selectable && (r.preticked || cameBack.has(r.package));
    box.addEventListener("change", updateSummary);
    c0.appendChild(box);

    const c1 = document.createElement("td");
    c1.className = "pkg";
    c1.textContent = r.package;
    if (!r.enabled) c1.appendChild(tag("disabled"));
    if (cameBack.has(r.package)) c1.appendChild(tag("came back"));
    if (r.button_bound) c1.appendChild(tag("disable only"));

    const c2 = document.createElement("td");
    c2.className = "num";
    c2.textContent = r.ram_kb ? mb(r.ram_kb) : "-";

    const c3 = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "badge " + r.rating;
    badge.textContent = r.rating === "tradeoff" ? "trade-off" : r.rating;
    c3.appendChild(badge);

    const c4 = document.createElement("td");
    c4.textContent = r.reason;
    if (r.tradeoff) {
      const t = document.createElement("span");
      t.className = "tradeoff-text";
      t.textContent = r.tradeoff;
      c4.appendChild(t);
    }
    tr.append(c0, c1, c2, c3, c4);
    body.appendChild(tr);
  }
  updateSummary();
}

function tag(text) {
  const s = document.createElement("span");
  s.className = "tag";
  s.textContent = text;
  return s;
}

function renderTweaks(tweaks) {
  const box = $("tweaks-list");
  box.textContent = "";
  $("tweaks-section").hidden = tweaks.length === 0;
  for (const t of tweaks) {
    const div = document.createElement("div");
    div.className = "tweak";
    const title = document.createElement("strong");
    title.textContent = t.name + (t.enabled ? " (on)" : " (off)");
    const desc = document.createElement("div");
    desc.textContent = t.description;
    const warn = document.createElement("div");
    warn.className = "warn";
    warn.textContent = t.warning;
    const btn = document.createElement("button");
    btn.textContent = t.enabled ? "Turn off" : "Turn on";
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        const res = await api("/api/tweaks/" + encodeURIComponent(t.id),
                              { action: t.enabled ? "disable" : "enable" });
        banner(res.reboot_required ? "Tweak changed. Reboot the TV for it to take effect." : "Tweak changed.", "", true);
        await scan();
      } catch (e) { report(e); btn.disabled = false; }
    });
    div.append(title, desc, warn, btn);
    box.appendChild(div);
  }
}

async function loadBackups() {
  const list = $("backups-list");
  try {
    const { backups } = await api("/api/backups");
    list.textContent = "";
    if (!backups.length) {
      const li = document.createElement("li");
      li.className = "note";
      li.textContent = "None yet.";
      list.appendChild(li);
    }
    for (const b of backups) {
      const li = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = `${b.created.replace("T", " ")} - ${b.packages_disabled} apps were disabled`;
      const btn = document.createElement("button");
      btn.textContent = "Restore";
      btn.addEventListener("click", () => restore(b.id));
      li.append(label, btn);
      list.appendChild(li);
    }
  } catch (e) { report(e); }
}

async function restore(id) {
  if (!confirm("Re-enable the apps that were enabled in this backup?")) return;
  try {
    const res = await api("/api/restore", { id });
    const failed = res.reenabled.filter((r) => !r.ok).length;
    banner(`Re-enabled ${res.reenabled.length - failed} apps` + (failed ? `, ${failed} failed` : "") +
           (res.tweaks_reverted.length ? "; tweaks reverted" : "") + ". Reboot the TV.", "", true);
    await scan();
  } catch (e) { report(e); }
}

async function connect() {
  banner("");
  $("connect-btn").disabled = true;
  try {
    const res = await api("/api/connect", { host: $("host").value.trim() });
    banner("Connected to " + res.serial, "", true);
    $("scan-btn").disabled = false;
    await scan();
  } catch (e) { report(e); }
  $("connect-btn").disabled = false;
}

async function scan() {
  $("scan-btn").disabled = true;
  try {
    const d = await api("/api/scan", {});
    rows = d.rows;
    cameBack = new Set(d.reenabled_since_backup);
    $("ram-summary").textContent =
      `Memory: ${mb(d.memory.available_kb)} free of ${mb(d.memory.total_kb)}` +
      ` (about ${mb(d.reclaimable_kb)} could be freed)`;
    $("storage-summary").textContent =
      `Storage: ${gb(d.storage.free_kb)} free of ${gb(d.storage.total_kb)}`;
    renderRows();
    renderTweaks(d.tweaks);
    await loadBackups();
  } catch (e) { report(e); }
  $("scan-btn").disabled = false;
}

async function applySelected() {
  const packages = selectedPackages();
  if (!packages.length) return;
  if (!confirm(`Disable ${packages.length} app(s)? A backup snapshot is saved first and you can restore it.`)) return;
  const before = Number(($("ram-summary").textContent.match(/(\d+) MB free/) || [0, 0])[1]);
  const list = $("progress-list");
  list.textContent = "";
  $("apply-btn").disabled = true;
  try {
    const resp = await fetch("/api/apply", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ packages, force: false }),
    });
    if (!resp.ok) throw await resp.json();
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (line) handleLine(JSON.parse(line), list, before);
      }
    }
  } catch (e) { report(e); }
  await scan();
}

function handleLine(msg, list, before) {
  const li = document.createElement("li");
  if (msg.snapshot) {
    li.textContent = "Backup saved: " + msg.snapshot;
  } else if (msg.done) {
    const after = Math.round(msg.memory_available_kb / 1024);
    li.textContent = `Done. Free memory ${before} MB -> ${after} MB (it may rise after a reboot).`;
    $("reminders").hidden = false;
  } else {
    const name = document.createElement("span");
    name.textContent = msg.package;
    const status = document.createElement("span");
    status.className = msg.ok ? "ok" : "fail";
    status.textContent = msg.ok ? "disabled" : "failed: " + msg.message;
    li.append(name, status);
  }
  list.appendChild(li);
}

$("connect-btn").addEventListener("click", connect);
$("scan-btn").addEventListener("click", scan);
$("apply-btn").addEventListener("click", applySelected);
$("show-locked").addEventListener("change", renderRows);
$("host").addEventListener("keydown", (e) => { if (e.key === "Enter") connect(); });
loadBackups();
