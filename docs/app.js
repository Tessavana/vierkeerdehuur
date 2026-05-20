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

function matchTagClass(tag) {
  const t = (tag || "").toLowerCase();
  if (t === "super nice") return "tag tag-super";
  if (t === "nice") return "tag tag-nice";
  if (t === "okay") return "tag tag-okay";
  return "tag tag-meh";
}

function formatSeen(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m geleden`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `${hours}u geleden`;
  const days = Math.floor(hours / 24);
  if (days < 14) return `${days}d geleden`;
  return d.toLocaleDateString("nl-NL", { day: "numeric", month: "short" });
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

function tagPassesFilter(listing) {
  const active = window.__activeTagFilters;
  if (!active || active.size === 0) return true;
  const t = (listing.match_tag || "okay").toLowerCase();
  return active.has(t);
}

function listingRow(l) {
  const wijk = dash(l.neighborhood);
  const platform = dash(l.platform || l.provider_name || l.source);
  const newClass = l.is_new_today ? " is-new-today" : "";
  const tag = `<span class="${matchTagClass(l.match_tag || "okay")}">${l.match_tag ?? "okay"}</span>`;
  const newBadge = l.is_new_today ? ' <span class="tag tag-new">Nieuw vandaag</span>' : "";
  return `
    <div class="listing-row${newClass}">
      <div class="platform-cell"><b>${platform}</b></div>
      <div><b>${l.title}</b><div class="muted">${l.location}</div></div>
      <div>${wijk}</div>
      <div>EUR ${l.rent_eur ?? "?"}</div>
      <div>${l.size_m2 ?? "?"} m²</div>
      <div>${dash(l.available_from)}</div>
      <div>${tag}${newBadge}<br/><a href="${l.url}" target="_blank" rel="noopener noreferrer">open</a></div>
    </div>
  `;
}

function renderListingsTable(listings) {
  const el = document.getElementById("listings-table");
  if (!el) return;
  if (!listings.length) {
    el.innerHTML = `<div class="muted">Geen matches binnen budget op dit moment.</div>`;
    return;
  }
  el.innerHTML = listings.map(listingRow).join("");
}

function renderStats(stats, maxRent) {
  if (!stats) return;
  const cards = document.getElementById("stats-cards");
  const fun = document.getElementById("fun-stats");
  const subtitle = document.getElementById("stats-subtitle");
  if (subtitle) {
    subtitle.textContent = `${stats.total_tracked ?? 0} woningen gevolgd in de markt · max huur €${maxRent}`;
  }
  if (cards) {
    const items = [
      ["Nieuw deze week", stats.new_this_week ?? 0],
      ["Nieuw op platform vandaag", stats.new_on_platform_today ?? stats.new_today ?? 0],
      ["Gem. huur (alles)", stats.avg_rent_all != null ? `€${stats.avg_rent_all}` : "-"],
      ["Mediaan huur", stats.median_rent_all != null ? `€${stats.median_rent_all}` : "-"],
      ["Gem. huur (budget)", stats.avg_rent_in_budget != null ? `€${stats.avg_rent_in_budget}` : "-"],
      ["Goedkoopste match", stats.cheapest_in_budget != null ? `€${stats.cheapest_in_budget}` : "-"],
      ["Gem. m²", stats.avg_size_m2 != null ? `${stats.avg_size_m2} m²` : "-"],
      ["€/m² gemiddeld", stats.avg_eur_per_m2 != null ? `€${stats.avg_eur_per_m2}` : "-"],
      ["Boven budget", `${stats.pct_above_budget ?? 0}%`],
      ["Strijp (budget)", stats.strijp_in_budget ?? 0],
      ["Met buitenruimte", `${stats.outdoor_pct ?? 0}%`],
    ];
    cards.innerHTML = items
      .map(([label, val]) => `<div class="stat-card"><div class="stat-label">${label}</div><div class="stat-value">${val}</div></div>`)
      .join("");
  }
  drawPriceChart(stats.price_distribution || []);
  renderPlatformBreakdown(stats.by_platform || {});
  if (fun) {
    const reasons = stats.excluded_by_reason || {};
    const reasonLine = Object.entries(reasons)
      .map(([k, v]) => `${k}: ${v}`)
      .join(" · ");
    fun.innerHTML = `
      <p><b>Leuk om te weten:</b> er staan nu <b>${stats.active_in_budget ?? 0}</b> woningen binnen budget live,
      terwijl de scanners <b>${stats.total_tracked ?? 0}</b> unieke adressen zagen (inclusief dure parels).
      ${stats.priciest_in_budget != null ? `Duurste match binnen budget: <b>€${stats.priciest_in_budget}</b>.` : ""}
      ${reasonLine ? `<br/><span class="muted">Waarom buiten budget: ${reasonLine}</span>` : ""}
      </p>
    `;
  }
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

  ctx.fillStyle = "#171717";
  ctx.font = "12px Segoe UI, Arial, sans-serif";
  buckets.forEach((b, i) => {
    const bh = (b.count / max) * chartH;
    const x = pad.l + i * (chartW / buckets.length) + 4;
    const y = pad.t + chartH - bh;
    ctx.fillStyle = "#0b4ea2";
    ctx.fillRect(x, y, barW, bh);
    ctx.fillStyle = "#171717";
    ctx.textAlign = "center";
    ctx.fillText(String(b.count), x + barW / 2, y - 4);
    ctx.save();
    ctx.translate(x + barW / 2, h - 8);
    ctx.rotate(-0.35);
    ctx.fillStyle = "#5f5f5f";
    ctx.font = "11px Segoe UI, Arial, sans-serif";
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

function getActiveTagFilters() {
  const set = new Set();
  document.querySelectorAll(".tag-filter:checked").forEach((el) => {
    set.add((el.dataset.tag || "").toLowerCase());
  });
  return set;
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
    const isNewToday = Boolean(listing.is_new_today);
    const pinColor = isNewToday ? "#e67e22" : isVisited ? "#4b5563" : "#000";
    const fillColor = isNewToday ? "#f39c12" : isVisited ? "#9ca3af" : "#000";
    const marker = L.circleMarker([latAdj, lonAdj], {
      radius: isNewToday ? 9 : 8,
      color: pinColor,
      weight: 2,
      fillColor,
      fillOpacity: 1,
    });
    const wijk = dash(listing.neighborhood);
    const platform = dash(listing.platform || listing.source);
    const newLine = isNewToday ? "<b>Nieuw op platform vandaag</b><br/>" : "";
    marker.bindPopup(
      `${newLine}<b>${listing.title}</b><br/>${platform}${wijk !== "-" ? ` · ${wijk}` : ""}<br/>EUR ${listing.rent_eur ?? "?"} | ${listing.size_m2 ?? "?"} m²`
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
      window.__housingMap.fitBounds(__mapLayerGroup.getBounds().pad(0.12));
    } catch (_e) {
      window.__housingMap.setView([51.4416, 5.4697], 12);
    }
  }
}

async function renderMap(listings) {
  __allListings = listings;
  const mapEl = document.getElementById("map");
  if (!mapEl) return;
  if (window.__housingMap) {
    window.__housingMap.remove();
    window.__housingMap = null;
  }
  const map = L.map("map").setView([51.4416, 5.4697], 12);
  window.__housingMap = map;
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    subdomains: "abcd",
    maxZoom: 20,
  }).addTo(map);
  __mapLayerGroup = L.layerGroup().addTo(map);
  window.__activeTagFilters = getActiveTagFilters();
  refreshMapMarkers();
  setTimeout(() => map.invalidateSize(), 200);
}

function showSelectedMatch(listing) {
  const el = document.getElementById("selected-match");
  if (!el) return;
  const wijk = dash(listing.neighborhood);
  const platform = dash(listing.platform || listing.source);
  el.innerHTML = `
    <b>${listing.title}</b><br/>
    <span class="muted">${platform}</span><br/>
    ${listing.location}${wijk !== "-" ? ` · ${wijk}` : ""}<br/>
    EUR ${listing.rent_eur ?? "?"} | ${listing.size_m2 ?? "?"} m²<br/>
    Huur vanaf: ${dash(listing.available_from)}<br/>
    <span class="${matchTagClass(listing.match_tag || "okay")}">${listing.match_tag ?? "okay"}</span>${listing.is_new_today ? ' <span class="tag tag-new">Nieuw vandaag</span>' : ""}<br/>
    <a href="${listing.url}" target="_blank" rel="noopener noreferrer">open listing</a>
  `;
}

function renderOverviewTable(status) {
  const table = document.getElementById("status-table");
  if (!table) return;
  const rejected = (status.rejected_addresses || []).join(", ");
  table.innerHTML = `
    <tr><td>Reacties verstuurd</td><td><b>${status.reacties_verstuurd ?? status.applications_sent ?? 46}</b></td></tr>
    <tr><td>Bezichtigingen</td><td><b>${status.bezichtigingen ?? status.viewings ?? 0}</b></td></tr>
    <tr><td>Kijkavonden</td><td><b>${status.kijkavonden ?? 0}</b></td></tr>
    <tr><td>Deadline 26 juli</td><td><b id="deadline-countdown">${updateCountdownHtml()}</b></td></tr>
    <tr><td>Afwijzingen tot nu toe</td><td>${rejected || "-"}</td></tr>
  `;
}

async function initSupportButton() {
  const btn = document.getElementById("support-btn");
  const countEl = document.getElementById("support-count");
  if (!btn || !countEl) return;

  async function showCount() {
    try {
      const res = await fetch(`https://api.countapi.xyz/get/${COUNTAPI_NS}/${COUNTAPI_KEY}`);
      const data = await res.json();
      countEl.textContent = String(data.value ?? 0);
    } catch {
      countEl.textContent = "—";
    }
  }

  await showCount();
  if (localStorage.getItem(SUPPORT_CLICKED_KEY)) {
    btn.classList.add("support-done");
    btn.disabled = true;
  }

  btn.addEventListener("click", async () => {
    if (localStorage.getItem(SUPPORT_CLICKED_KEY)) return;
    try {
      const res = await fetch(`https://api.countapi.xyz/hit/${COUNTAPI_NS}/${COUNTAPI_KEY}`);
      const data = await res.json();
      countEl.textContent = String(data.value ?? 0);
      localStorage.setItem(SUPPORT_CLICKED_KEY, "1");
      btn.classList.add("support-done");
      btn.disabled = true;
    } catch {
      countEl.textContent = "?";
    }
  });
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
  if (subtitle) {
    const n = (data.listings || []).length;
    subtitle.textContent = `${n} match${n === 1 ? "" : "es"} · nieuwste eerst · oranje = vandaag op het platform geplaatst`;
  }

  renderListingsTable(data.listings || []);
  window.__lastMarketStats = data.market_stats;
  renderStats(data.market_stats, data.max_rent);
  await renderMap(data.listings || []);
}

document.querySelectorAll(".tag-filter").forEach((el) => {
  el.addEventListener("change", () => refreshMapMarkers());
});

setInterval(updateDeadlineRow, 1000);
initSupportButton();
loadRun().catch((err) => {
  const headline = document.getElementById("headline-status");
  if (headline) headline.textContent = `Status: nog steeds geen woning — site error: ${err}`;
});

window.addEventListener("resize", () => {
  const stats = window.__lastMarketStats;
  if (stats) drawPriceChart(stats.price_distribution || []);
});
