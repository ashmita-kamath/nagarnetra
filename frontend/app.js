const COLORS = { High: "#d62828", Medium: "#f77f00", Low: "#2a9d8f" };
const LABELS = { pothole: "Pothole", garbage: "Garbage dump", streetlight: "Streetlight", waterlogging: "Waterlogging", other: "Other" };

const $ = (s) => document.querySelector(s);
const state = { lat: null, lng: null, pick: null, resolveId: null, reports: [] };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function ago(iso) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 3500);
}

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  let body = null;
  try { body = await res.json(); } catch (_) { }
  if (!res.ok) throw new Error((body && body.detail) || `Request failed (${res.status})`);
  return body;
}

/* ---------- map ---------- */
const map = L.map("map", { zoomControl: true }).setView([20.59, 78.96], 5);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);
const markers = L.layerGroup().addTo(map);

function setLocation(lat, lng, zoom) {
  state.lat = lat;
  state.lng = lng;
  if (state.pick) state.pick.setLatLng([lat, lng]);
  else state.pick = L.marker([lat, lng], { title: "Issue location" }).addTo(map);
  $("#loc-text").textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
  if (zoom) map.setView([lat, lng], zoom);
}

map.on("click", (e) => {
  if ($("#tab-report").classList.contains("active")) setLocation(e.latlng.lat, e.latlng.lng);
});

$("#locate").addEventListener("click", () => {
  if (!navigator.geolocation) return toast("Location not supported on this device");
  $("#loc-text").textContent = "Finding you...";
  navigator.geolocation.getCurrentPosition(
    (p) => setLocation(p.coords.latitude, p.coords.longitude, 17),
    () => { $("#loc-text").textContent = "or tap the map"; toast("Couldn't get location - tap the map instead"); },
    { enableHighAccuracy: true, timeout: 10000 }
  );
});

/* ---------- tabs ---------- */
document.querySelectorAll(".tab-btn").forEach((btn) =>
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${btn.dataset.tab}`));
    if (btn.dataset.tab === "stats") loadStats();
    if (btn.dataset.tab === "issues") loadReports();
  })
);

/* ---------- report form ---------- */
$("#photo").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const img = $("#preview");
  img.src = URL.createObjectURL(file);
  img.hidden = false;
  $("#drop-text").hidden = true;
});

function boxesHtml(dets) {
  return dets.map((d) => {
    const [x1, y1, x2, y2] = d.box;
    return `<div class="box" style="left:${x1 * 100}%;top:${y1 * 100}%;width:${(x2 - x1) * 100}%;height:${(y2 - y1) * 100}%">
      <span>${esc(d.label)} ${Math.round(d.confidence * 100)}%</span></div>`;
  }).join("");
}

function badge(r) {
  return `<span class="badge" style="background:${COLORS[r.severity_label]}">${r.severity_label} &middot; ${r.severity_score}</span>`;
}

function renderResult({ merged, report: r }) {
  const el = $("#result");
  const aiLine = r.ai_used
    ? `AI found <strong>${r.detections.length}</strong> damaged area${r.detections.length === 1 ? "" : "s"}.`
    : "AI model not loaded - severity estimated from category.";
  el.innerHTML = `
    <div class="result-card">
      <h3>${merged ? "Already reported here - your voice was added" : "Issue reported"}</h3>
      <figure class="annotated"><img src="${r.image_url}" alt="Reported issue">${boxesHtml(r.detections)}</figure>
      <p>${badge(r)} <strong>${LABELS[r.category] || r.category}</strong> &middot; ${r.reports_count} citizen report${r.reports_count === 1 ? "" : "s"}</p>
      <p class="muted small">${aiLine}</p>
      <div class="actions">
        <a class="ghost" href="${r.share_url}" target="_blank" rel="noopener">Share card</a>
        <button class="ghost" data-action="focus" data-id="${r.id}">Show on map</button>
        <button class="primary" id="report-another">Report another</button>
      </div>
    </div>`;
  el.hidden = false;
  $("#report-form").hidden = true;
  $("#report-another").addEventListener("click", resetForm);
}

function resetForm() {
  $("#report-form").reset();
  $("#report-form").hidden = false;
  $("#result").hidden = true;
  $("#preview").hidden = true;
  $("#drop-text").hidden = false;
}

$("#report-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (state.lat === null) return toast("Add a location: tap the map or use your location");
  const fd = new FormData(e.target);
  fd.append("lat", state.lat);
  fd.append("lng", state.lng);
  const btn = $("#submit-btn");
  btn.disabled = true;
  btn.textContent = "AI is analysing...";
  try {
    const data = await api("/api/reports", { method: "POST", body: fd });
    renderResult(data);
    await loadReports();
  } catch (err) {
    toast(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Report issue";
  }
});

/* ---------- issues ---------- */
function popupHtml(r) {
  const img = r.comparison_url
    ? `<img src="${r.comparison_url}" alt="Before and after">`
    : `<img src="${r.thumb_url}" alt="">`;
  const actions = r.status === "open"
    ? `<button data-action="upvote" data-id="${r.id}">Me too (${r.reports_count})</button>
       <button data-action="resolve" data-id="${r.id}">Mark fixed</button>`
    : `<span class="fixed">Fixed ${r.resolved_at ? ago(r.resolved_at) : ""}</span>`;
  return `<div class="popup">${img}
    <p>${badge(r)} <strong>${LABELS[r.category] || r.category}</strong></p>
    ${r.description ? `<p class="small">${esc(r.description)}</p>` : ""}
    <p class="muted small">Reported ${ago(r.created_at)} &middot; priority ${r.priority}</p>
    <div class="actions">${actions}</div></div>`;
}

function renderMarkers(items) {
  markers.clearLayers();
  items.forEach((r) => {
    const m = L.circleMarker([r.lat, r.lng], {
      radius: 8 + Math.min(r.reports_count, 6) * 1.5,
      color: "#fff",
      weight: 2,
      fillColor: r.status === "open" ? COLORS[r.severity_label] : "#6c757d",
      fillOpacity: 0.9,
    }).bindPopup(popupHtml(r), { maxWidth: 280 });
    m.reportId = r.id;
    markers.addLayer(m);
  });
}

function renderList(items) {
  const ul = $("#issue-list");
  if (!items.length) {
    ul.innerHTML = `<li class="empty muted">No issues here yet.</li>`;
    return;
  }
  ul.innerHTML = items.map((r, i) => `
    <li class="issue" data-action="focus" data-id="${r.id}">
      <img src="${r.thumb_url}" alt="" loading="lazy">
      <div>
        <p><span class="rank">#${i + 1}</span> <strong>${LABELS[r.category] || r.category}</strong> ${badge(r)}</p>
        <p class="muted small">${r.reports_count} report${r.reports_count === 1 ? "" : "s"} &middot; ${ago(r.created_at)}${r.status === "resolved" ? " &middot; fixed" : ""}</p>
      </div>
    </li>`).join("");
}

async function loadReports() {
  const status = $("#filter-status").value;
  const sort = $("#filter-sort").value;
  try {
    state.reports = await api(`/api/reports?status=${status}&sort=${sort}`);
    renderList(state.reports);
    renderMarkers(state.reports);
  } catch (err) {
    toast(err.message);
  }
}
$("#filter-status").addEventListener("change", loadReports);
$("#filter-sort").addEventListener("change", loadReports);

function focusReport(id) {
  markers.eachLayer((m) => {
    if (m.reportId === id) {
      map.setView(m.getLatLng(), 17);
      m.openPopup();
    }
  });
}

document.addEventListener("click", async (e) => {
  const el = e.target.closest("[data-action]");
  if (!el) return;
  const id = Number(el.dataset.id);
  const action = el.dataset.action;
  if (action === "focus") focusReport(id);
  if (action === "upvote") {
    try {
      await api(`/api/reports/${id}/upvote`, { method: "POST" });
      toast("Thanks - your report raises its priority");
      await loadReports();
      focusReport(id);
    } catch (err) { toast(err.message); }
  }
  if (action === "resolve") {
    state.resolveId = id;
    $("#resolve-photo").click();
  }
});

$("#resolve-photo").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file || !state.resolveId) return;
  const key = prompt("Municipal admin key:");
  if (!key) return;
  const fd = new FormData();
  fd.append("image", file);
  try {
    await api(`/api/reports/${state.resolveId}/resolve`, { method: "POST", body: fd, headers: { "X-Admin-Key": key } });
    toast("Marked as fixed - before/after saved");
    await loadReports();
    focusReport(state.resolveId);
  } catch (err) { toast(err.message); }
});

/* ---------- stats ---------- */
async function loadStats() {
  try {
    const [s, h] = await Promise.all([api("/api/stats"), api("/api/health")]);
    const tiles = [
      ["Open issues", s.open],
      ["High severity", s.high_open],
      ["Fixed", s.resolved],
      ["Citizen reports", s.citizen_reports],
    ];
    $("#stats").innerHTML = tiles.map(([k, v]) => `<div class="tile"><span>${v}</span><p>${k}</p></div>`).join("") +
      `<div class="cats">${Object.entries(s.by_category).map(([c, n]) => `<span>${LABELS[c] || c}: <strong>${n}</strong></span>`).join("")}</div>`;
    $("#health").textContent = `Cloudinary: ${h.cloudinary ? "connected" : "not configured"} · AI model: ${h.model.loaded ? "loaded (" + h.model.classes.join(", ") + ")" : "not loaded"}`;
  } catch (err) { toast(err.message); }
}

loadReports().then(() => {
  if (state.reports.length) {
    map.fitBounds(L.latLngBounds(state.reports.map((r) => [r.lat, r.lng])).pad(0.3), { maxZoom: 15 });
  }
});
