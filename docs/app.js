const MOVE_OUT_DEADLINE = new Date("2026-07-26T23:59:59+02:00");
const MAP_VISITED_KEY = "housing_map_visited_urls_v1";
const SUPPORT_CLICKED_KEY = "housing_support_clicked_v1";
const COUNTAPI_NS = "vierkeerdehuur";
const COUNTAPI_KEY = "tessa-support";

let __allListings = [];
let __mapLayerGroup = null;

function updateCountdownHtml() {
  const now = Date.now();
  const end = MOVE_OUT_DEADLINE.getTime();
  const diff = Math.max(0, end - now);
  const days = Math.floor(diff / 86400000);
  const hours = Math.floor((diff % 86400000) / 3600000);
  const mins = Math.floor((diff % 3600000) / 60000);
  const secs = Math.floor((diff % 60000) / 1000);
  return `${days}d ${hours}u ${mins}m ${secs}s`;
}

function updateDeadlineRow() {
  const el = document.getElementById("deadline-countdown");
  if (el) el.textContent = updateCountdownHtml();
}

function dash(v) {
  if (v === null || v === undefined || v === "") return "-";
  return v;
}

function formatRentFrom(v) {
  if (!v) return "-";
  const s = String(v).trim();
  if (/geleden/i.test(s)) return "-";
  if (/^\d{4}-\d{2}-\d{2}T/.test(s)) return "-";
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    const d = new Date(`${s}T12:00:00`);
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleDateString("nl-NL", { day: "numeric", month: "short", year: "numeric" });
    }
  }
  const d = new Date(s);
  if (!Number.isNaN(d.getTime()) && s.includes("-")) {
    return d.toLocaleDateString("nl-NL", { day: "numeric", month: "short", year: "numeric" });
  }
  if (s.length > 48) return "-";
  return s;
}

function todayAmsterdamIso() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Amsterdam",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

/** Orange highlight only when platform_listed_date is today (Amsterdam). */
function isListedToday(l) {
  const raw = l.platform_listed_date;
  if (!raw) return false;
  return String(raw).slice(0, 10) === todayAmsterdamIso();
}

function matchTagClass(tag) {
  const t = (tag || "").toLowerCase();
  if (t === "super nice") return "tag tag-super";
  if (t === "nice") return "tag tag-nice";
  if (t === "okay") return "tag tag-okay";
  return "tag tag-meh";
}

function loadVisitedUrls() {
  try {
    const raw = localStorage.getItem(MAP_VISITED_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(arr) ? arr : []);
  } catch {
    return new Set();
  }
}

function addVisitedUrl(url) {
  const s = loadVisitedUrls();
  s.add(url);
  localStorage.setItem(MAP_VISITED_KEY, JSON.stringify([...s]));
  return s;
}

function getActiveTagFilters() {
  const set = new Set();
  document.querySelectorAll(".map-tag-toggle.active").forEach((el) => {
    set.add((el.dataset.tag || "").toLowerCase());
  });
  return set;
}

function tagPassesFilter(listing) {
  const active = window.__activeTagFilters;
  if (!active || active.size === 0) return false;
  const t = (listing.match_tag || "okay").toLowerCase();
  return active.has(t);
}

function listingRow(l) {
  const wijk = dash(l.neighborhood);
  const platform = dash(l.platform || l.provider_name || l.source);
  const newToday = isListedToday(l);
  const newClass = newToday ? " is-new-today" : "";
  const tag = `<span class="${matchTagClass(l.match_tag || "okay")}">${l.match_tag ?? "okay"}</span>`;
  const newBadge = newToday ? ' <span class="tag tag-new">Nieuw vandaag</span>' : "";
  return `
    <div class="listing-row${newClass}">
      <div class="platform-cell"><b>${platform}</b></div>
      <div><b>${l.title}</b><div class="muted">${l.location}</div></div>
      <div>${wijk}</div>
      <div>EUR ${l.rent_eur ?? "?"}</div>
      <div>${l.size_m2 ?? "?"} m²</div>
      <div>${formatRentFrom(l.available_from)}</div>
      <div>${tag}${newBadge}<br/><a href="${l.url}" target="_blank" rel="noopener noreferrer">open</a></div>
    </div>
  `;
}

function renderListingsTable(listings) {
  const el = document.getElementById("listings-table");
  if (!el) return;
  if (!listings.length) {
    el.innerHTML = `<div class="muted listings-empty">Geen matches binnen budget op dit moment.</div>`;
    return;
  }
  el.innerHTML = listings.map(listingRow).join("");
}

function renderStats(stats, maxRent, listingsCount) {
  if (!stats) return;
  const dashEl = document.getElementById("stats-dashboard");
  const subtitle = document.getElementById("stats-subtitle");
  if (subtitle) {
    subtitle.textContent = `Scanners zien ${stats.total_tracked ?? 0} unieke woningen in Eindhoven (alle prijzen) · max huur €${maxRent}`;
  }

  const tags = stats.tag_counts || {};
  const tagTotal = Object.values(tags).reduce((a, b) => a + b, 0) || 1;
  const tagOrder = ["super nice", "nice", "okay", "meh"];
  const tagBars = tagOrder
    .map((name) => {
      const n = tags[name] || 0;
      const pct = Math.round((100 * n) / tagTotal);
      return `
        <div class="stack-bar-row">
          <div class="stack-bar-label">${name}</div>
          <div class="stack-bar-track">
            <div class="stack-bar-fill" style="width:${pct}%"></div>
            <span class="stack-bar-pct">${n}</span>
          </div>
        </div>`;
    })
    .join("");

  const outdoorYes = stats.outdoor_yes_count ?? 0;
  const outdoorText =
    outdoorYes === 0
      ? "Geen met buitenruimte"
      : `${outdoorYes} woning${outdoorYes === 1 ? "" : "en"} gevonden met buitenruimte`;

  const inBudget = listingsCount ?? stats.active_in_budget ?? 0;
  const tracked = stats.total_tracked ?? 0;
  const segTotal = 24;
  const filled = tracked ? Math.min(segTotal, Math.round((inBudget / tracked) * segTotal)) : 0;

  if (dashEl) {
    dashEl.innerHTML = `
      <div class="market-hero-card">
        <div class="market-card-tags">
          <span class="market-pill">live</span>
          <span class="market-pill">eindhoven</span>
          <span class="market-pill">≤ €${maxRent}</span>
        </div>
        <div class="market-card-title">Matches binnen budget</div>
        <hr class="market-card-divider" />
        <p class="market-card-lead">${inBudget} woning${inBudget === 1 ? "" : "en"} passen nu in je filters (≤ €${maxRent}).</p>
        <div class="market-card-metric">
          <span class="market-big">${inBudget}</span>
          <span class="market-trend">binnen budget · ${tracked} uniek gezien door scanners</span>
        </div>
        <p class="market-card-hint muted">“Gezien” = alle woningen die we vinden op Funda, Pararius, enz., ook boven je max huur.</p>
        <div class="market-segments" aria-hidden="true">
          ${Array.from({ length: segTotal }, (_, i) => `<span class="seg${i < filled ? " seg-on" : ""}"></span>`).join("")}
        </div>
      </div>
      <div class="market-metrics-grid">
        <div class="metric-mini"><span class="metric-mini-label">Nieuw deze week</span><span class="metric-mini-val">${stats.new_this_week ?? 0}</span></div>
        <div class="metric-mini"><span class="metric-mini-label">Nieuw vandaag</span><span class="metric-mini-val">${stats.new_on_platform_today ?? 0}</span></div>
        <div class="metric-mini"><span class="metric-mini-label">Gem. huur</span><span class="metric-mini-val">${stats.avg_rent_in_budget != null ? `€${stats.avg_rent_in_budget}` : "—"}</span></div>
        <div class="metric-mini"><span class="metric-mini-label">Mediaan</span><span class="metric-mini-val">${stats.median_rent_all != null ? `€${stats.median_rent_all}` : "—"}</span></div>
        <div class="metric-mini"><span class="metric-mini-label">Goedkoopste</span><span class="metric-mini-val">${stats.cheapest_in_budget != null ? `€${stats.cheapest_in_budget}` : "—"}</span></div>
        <div class="metric-mini"><span class="metric-mini-label">€/m²</span><span class="metric-mini-val">${stats.avg_eur_per_m2 != null ? `€${stats.avg_eur_per_m2}` : "—"}</span></div>
        <div class="metric-mini metric-mini-wide">
          <span class="metric-mini-label">Buitenruimte</span>
          <span class="metric-mini-val metric-mini-val-text">${outdoorText}</span>
        </div>
        <div class="metric-mini"><span class="metric-mini-label">Strijp</span><span class="metric-mini-val">${stats.strijp_in_budget ?? 0}</span></div>
      </div>
      <div class="market-stack-card">
        <h3 class="market-stack-title">Tags (matches)</h3>
        ${tagBars}
      </div>
    `;
  }

  drawPriceChart(stats.price_distribution || []);
  renderPlatformBreakdown(stats.by_platform || {});
}

function drawPriceChart(buckets) {
  const canvas = document.getElementById("price-chart");
  if (!canvas || !buckets.length) return;
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 560;
  const h = 220;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);

  const max = Math.max(...buckets.map((b) => b.count), 1);
  const pad = { l: 36, r: 12, t: 16, b: 48 };
  const chartW = w - pad.l - pad.r;
  const chartH = h - pad.t - pad.b;
  const barW = chartW / buckets.length - 8;

  ctx.font = "12px system-ui, Segoe UI, Arial, sans-serif";
  buckets.forEach((b, i) => {
    const bh = (b.count / max) * chartH;
    const x = pad.l + i * (chartW / buckets.length) + 4;
    const y = pad.t + chartH - bh;
    ctx.fillStyle = i % 2 === 0 ? "#171717" : "#fff";
    ctx.strokeStyle = "#171717";
    ctx.lineWidth = 1;
    ctx.fillRect(x, y, barW, bh);
    if (i % 2 !== 0) ctx.strokeRect(x, y, barW, bh);
    ctx.fillStyle = "#171717";
    ctx.textAlign = "center";
    ctx.fillText(String(b.count), x + barW / 2, y - 4);
    ctx.save();
    ctx.translate(x + barW / 2, h - 8);
    ctx.rotate(-0.35);
    ctx.fillStyle = "#5f5f5f";
    ctx.font = "11px system-ui, Segoe UI, Arial, sans-serif";
    ctx.fillText(b.label, 0, 0);
    ctx.restore();
  });
}

function renderPlatformBreakdown(byPlatform) {
  const el = document.getElementById("platform-breakdown");
  if (!el) return;
  const entries = Object.entries(byPlatform);
  if (!entries.length) {
    el.innerHTML = `<div class="muted">Nog geen data.</div>`;
    return;
  }
  const max = Math.max(...entries.map(([, c]) => c));
  el.innerHTML = entries
    .map(([name, count]) => {
      const pct = max ? Math.round((count / max) * 100) : 0;
      return `
        <div class="platform-row">
          <span class="platform-name">${name}</span>
          <div class="platform-bar"><div class="platform-bar-fill" style="width:${pct}%"></div></div>
          <span class="platform-count">${count}</span>
        </div>`;
    })
    .join("");
}

function initMapTagFilters() {
  const wrap = document.getElementById("map-tag-filters");
  if (!wrap || wrap.dataset.bound) return;
  wrap.dataset.bound = "1";
  wrap.addEventListener("click", (e) => {
    const btn = e.target.closest(".map-tag-toggle");
    if (!btn) return;
    btn.classList.toggle("active");
    window.__activeTagFilters = getActiveTagFilters();
    refreshMapMarkers();
  });
}

function refreshMapMarkers() {
  if (!window.__housingMap || !__mapLayerGroup) return;
  __mapLayerGroup.clearLayers();
  window.__activeTagFilters = getActiveTagFilters();
  const visitedUrls = loadVisitedUrls();
  const filtered = __allListings.filter(tagPassesFilter);
  const usedCoords = new Map();

  for (const listing of filtered) {
    let lat = Number(listing.map_lat);
    let lon = Number(listing.map_lon);
    if (Number.isNaN(lat) || Number.isNaN(lon)) continue;
    const key = `${lat.toFixed(5)},${lon.toFixed(5)}`;
    const offset = usedCoords.get(key) || 0;
    usedCoords.set(key, offset + 1);
    const latAdj = lat + offset * 0.00025;
    const lonAdj = lon + offset * 0.00025;

    const isVisited = visitedUrls.has(listing.url);
    const isNewToday = isListedToday(listing);
    const tag = (listing.match_tag || "okay").toLowerCase();
    const tagColors = {
      "super nice": "#145a2a",
      nice: "#084298",
      okay: "#444",
      meh: "#888",
    };
    const fillColor = isNewToday ? "#e67e22" : isVisited ? "#9ca3af" : tagColors[tag] || "#171717";
    const pinColor = isNewToday ? "#c0392b" : isVisited ? "#4b5563" : "#171717";

    const marker = L.circleMarker([latAdj, lonAdj], {
      radius: isNewToday ? 9 : 8,
      color: pinColor,
      weight: 2,
      fillColor,
      fillOpacity: 1,
    });
    const wijk = dash(listing.neighborhood);
    const platform = dash(listing.platform || listing.source);
    const tagHtml = `<span class="${matchTagClass(listing.match_tag || "okay")}">${listing.match_tag ?? "okay"}</span>`;
    const newLine = isNewToday ? "<b>Nieuw op platform vandaag</b><br/>" : "";
    marker.bindPopup(
      `${newLine}${tagHtml}<br/><b>${listing.title}</b><br/>${platform}${wijk !== "-" ? ` · ${wijk}` : ""}<br/>EUR ${listing.rent_eur ?? "?"} | ${listing.size_m2 ?? "?"} m²`
    );
    marker.on("click", () => {
      addVisitedUrl(listing.url);
      marker.setStyle({ color: "#4b5563", weight: 2, fillColor: "#9ca3af", fillOpacity: 1 });
      showSelectedMatch(listing);
    });
    __mapLayerGroup.addLayer(marker);
  }

  if (filtered.length > 0) {
    try {
      window.__housingMap.fitBounds(__mapLayerGroup.getBounds().pad(0.06));
    } catch (_e) {
      window.__housingMap.setView([51.4416, 5.4697], 13);
    }
  }
}

async function renderMap(listings) {
  __allListings = listings;
  const mapEl = document.getElementById("map");
  if (!mapEl) return;
  if (!window.__housingMap) {
    const map = L.map("map").setView([51.4416, 5.4697], 13);
    window.__housingMap = map;
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      attribution: "&copy; OpenStreetMap &copy; CARTO",
      subdomains: "abcd",
      maxZoom: 20,
    }).addTo(map);
    __mapLayerGroup = L.layerGroup().addTo(map);
    setTimeout(() => map.invalidateSize(), 200);
  }
  window.__activeTagFilters = getActiveTagFilters();
  refreshMapMarkers();
}

function showSelectedMatch(listing) {
  const el = document.getElementById("selected-match");
  if (!el) return;
  const wijk = dash(listing.neighborhood);
  const platform = dash(listing.platform || listing.source);
  el.innerHTML = `
    <span class="${matchTagClass(listing.match_tag || "okay")}">${listing.match_tag ?? "okay"}</span>${isListedToday(listing) ? ' <span class="tag tag-new">Nieuw vandaag</span>' : ""}<br/>
    <b>${listing.title}</b><br/>
    <span class="muted">${platform}</span><br/>
    ${listing.location}${wijk !== "-" ? ` · ${wijk}` : ""}<br/>
    EUR ${listing.rent_eur ?? "?"} | ${listing.size_m2 ?? "?"} m²<br/>
    Huur vanaf: ${formatRentFrom(listing.available_from)}<br/>
    <a href="${listing.url}" target="_blank" rel="noopener noreferrer">open listing</a>
  `;
}

function renderOverviewTable(status) {
  const table = document.getElementById("status-table");
  if (!table) return;
  const sh = status.sociale_huur || {};
  table.innerHTML = `
    <tr><td>Reacties verstuurd</td><td><b>${status.reacties_verstuurd ?? status.applications_sent ?? 46}</b></td></tr>
    <tr><td>Bezichtigingen</td><td><b>${status.bezichtigingen ?? status.viewings ?? 0}</b></td></tr>
    <tr><td>Kijkavonden</td><td><b>${status.kijkavonden ?? 0}</b></td></tr>
    <tr class="overview-section-head"><td colspan="2"><b>Sociale huur (${sh.platform || "Wooniezie"})</b></td></tr>
    <tr><td>Inschrijfduur</td><td>${dash(sh.inschrijfduur)}</td></tr>
    <tr><td>Reacties verstuurd</td><td>${dash(sh.reacties_verstuurd)}</td></tr>
    <tr><td>Actief gezocht</td><td>${dash(sh.actief_gezocht)}</td></tr>
    <tr><td>Bezichtigingen</td><td><b>${sh.bezichtigingen ?? 0}</b></td></tr>
  `;
}

async function ensureCountApi() {
  try {
    await fetch(`https://api.countapi.xyz/create?namespace=${COUNTAPI_NS}&key=${COUNTAPI_KEY}&value=0`);
  } catch {
    /* already exists */
  }
}

async function initSupportButton() {
  const btn = document.getElementById("support-btn");
  const countEl = document.getElementById("support-count");
  if (!btn || !countEl) return;

  await ensureCountApi();

  async function showCount() {
    try {
      const res = await fetch(`https://api.countapi.xyz/get/${COUNTAPI_NS}/${COUNTAPI_KEY}`);
      const data = await res.json();
      countEl.textContent = String(data.value ?? 0);
    } catch {
      countEl.textContent = "0";
    }
  }

  function lockButton() {
    btn.classList.add("support-done");
    btn.disabled = true;
    btn.setAttribute("aria-disabled", "true");
  }

  await showCount();
  if (localStorage.getItem(SUPPORT_CLICKED_KEY)) {
    lockButton();
  }

  btn.addEventListener(
    "click",
    async () => {
      if (btn.disabled || localStorage.getItem(SUPPORT_CLICKED_KEY)) return;
      lockButton();
      localStorage.setItem(SUPPORT_CLICKED_KEY, "1");
      const prev = parseInt(countEl.textContent, 10) || 0;
      countEl.textContent = String(prev + 1);
      try {
        const res = await fetch(`https://api.countapi.xyz/hit/${COUNTAPI_NS}/${COUNTAPI_KEY}`);
        const data = await res.json();
        if (data.value != null) countEl.textContent = String(data.value);
      } catch {
        /* keep optimistic count */
      }
    },
    { once: false }
  );
}

async function loadRun() {
  const res = await fetch("./data/latest_listings.json", { cache: "no-store" });
  const data = await res.json();

  renderOverviewTable(data.application_status || {});
  const updated = document.getElementById("last-updated");
  if (updated) {
    updated.textContent = `Laatste update: ${new Date(data.generated_at_utc).toLocaleString("nl-NL")}`;
  }
  const subtitle = document.getElementById("results-subtitle");
  const listings = data.listings || [];
  if (subtitle) {
    subtitle.textContent = `${listings.length} match${listings.length === 1 ? "" : "es"} · nieuwste eerst · oranje pin = vandaag op platform`;
  }

  renderListingsTable(listings);
  window.__lastMarketStats = data.market_stats;
  renderStats(data.market_stats, data.max_rent, listings.length);
  initMapTagFilters();
  await renderMap(listings);
}

setInterval(updateDeadlineRow, 1000);
updateDeadlineRow();
initSupportButton();
loadRun().catch((err) => {
  const headline = document.getElementById("headline-status");
  if (headline) headline.textContent = `Status: nog steeds geen woning — site error: ${err}`;
});

window.addEventListener("resize", () => {
  const stats = window.__lastMarketStats;
  if (stats) drawPriceChart(stats.price_distribution || []);
  if (window.__housingMap) window.__housingMap.invalidateSize();
});
