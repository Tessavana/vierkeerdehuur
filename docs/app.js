const MOVE_OUT_DEADLINE = new Date("2026-07-26T23:59:59+02:00");
const MAP_VISITED_KEY = "housing_map_visited_urls_v1";
const SEEKERS_SEEN_KEY = "housing_seekers_seen_v1";

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
  const iso = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (iso) {
    const d = new Date(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]));
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleDateString("nl-NL", { day: "numeric", month: "short", year: "numeric" });
    }
  }
  const eu = s.match(/(?:per\s+)?(\d{1,2})[-/](\d{1,2})[-/](\d{4})/i);
  if (eu) {
    const d = new Date(Number(eu[3]), Number(eu[2]) - 1, Number(eu[1]));
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleDateString("nl-NL", { day: "numeric", month: "short", year: "numeric" });
    }
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

function formatApplications(l) {
  if (l.application_count_label) return l.application_count_label;
  if (l.application_count != null) return String(l.application_count);
  return "—";
}

function applicationsClass(l) {
  const n = l.application_count ?? (l.application_count_label ? parseInt(String(l.application_count_label), 10) : null);
  if (n != null && n >= 5) return "listing-applications hot";
  if (l.application_count_label || l.application_count != null) return "listing-applications";
  return "muted";
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
      <div class="${applicationsClass(l)}">${formatApplications(l)}</div>
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
  const inBudget = listingsCount ?? stats.active_in_budget ?? 0;
  const foundWeek = stats.new_this_week ?? stats.total_tracked ?? 0;

  if (dashEl) {
    dashEl.innerHTML = `
      <div class="market-summary-card">
        <p class="market-summary-line">
          <span class="market-summary-num">${inBudget}</span> matches binnen budget.
          van de <span class="market-summary-num">${foundWeek}</span> woningen gevonden deze week.
        </p>
      </div>
      <div class="market-metrics-grid">
        <div class="metric-mini"><span class="metric-mini-label">Nieuw vandaag</span><span class="metric-mini-val">${stats.new_on_platform_today ?? 0}</span></div>
        <div class="metric-mini"><span class="metric-mini-label">Gem. huur (markt)</span><span class="metric-mini-val">${stats.avg_rent_all != null ? `€${stats.avg_rent_all}` : "—"}</span></div>
        <div class="metric-mini"><span class="metric-mini-label">Mediaan (markt)</span><span class="metric-mini-val">${stats.median_rent_all != null ? `€${stats.median_rent_all}` : "—"}</span></div>
        <div class="metric-mini"><span class="metric-mini-label">Gem. m²</span><span class="metric-mini-val">${stats.avg_size_m2 != null ? `${stats.avg_size_m2} m²` : "—"}</span></div>
        <div class="metric-mini"><span class="metric-mini-label">€/m² (markt)</span><span class="metric-mini-val">${stats.avg_eur_per_m2 != null ? `€${stats.avg_eur_per_m2}` : "—"}</span></div>
        <div class="metric-mini"><span class="metric-mini-label">Goedkoopste match</span><span class="metric-mini-val">${stats.cheapest_in_budget != null ? `€${stats.cheapest_in_budget}` : "—"}</span></div>
        <div class="metric-mini metric-mini-wide outdoor-stat">
          <span class="outdoor-stat-num">${outdoorYes}</span>
          <span class="outdoor-stat-text">woningen gevonden met buitenruimte</span>
        </div>
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
    const fillColor = isNewToday ? "#e67e22" : isVisited ? "#9ca3af" : "#171717";
    const pinColor = isNewToday ? "#c0392b" : isVisited ? "#6b7280" : "#171717";

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

function formatSeekerAuthor(raw) {
  if (!raw) return "";
  const cleaned = String(raw).replace(/^\/u\//, "").replace(/^u\//, "");
  return cleaned ? `@${cleaned}` : "";
}

function seekerPostId(p) {
  return p.id || p.url || `${p.source}-${p.title}`;
}

function loadSeenSeekers() {
  try {
    return new Set(JSON.parse(sessionStorage.getItem(SEEKERS_SEEN_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function saveSeenSeekers(ids) {
  sessionStorage.setItem(SEEKERS_SEEN_KEY, JSON.stringify([...ids].slice(-120)));
}

function seekerCardHtml(p, idx, seenSet) {
  const kind = p.kind || "unknown";
  const kindLabel = kind === "seeking" ? "zoekt" : kind === "offering" ? "biedt" : "bericht";
  const kindClass =
    kind === "seeking" ? "seeker-tag seeker-tag-seek" : kind === "offering" ? "seeker-tag seeker-tag-offer" : "seeker-tag";
  const when = formatSeekerTime(p.posted_at);
  const budget = p.budget_eur ? ` · max €${p.budget_eur}` : "";
  const loc = p.location_hint ? ` · ${p.location_hint}` : "";
  const group = p.group_name || p.source || "";
  const author = formatSeekerAuthor(p.author);
  const pid = seekerPostId(p);
  const isNew = !seenSet.has(pid);
  const delay = Math.min(idx, 12) * 70;
  const sourceIcon =
    p.source === "reddit" ? "🔴" : p.source === "marktplaats" ? "🟡" : p.source === "facebook" ? "🔵" : "•";
  return `
    <article class="seeker-card seeker-card-enter${isNew ? " seeker-card-new" : ""}" data-seeker-id="${pid}" style="animation-delay:${delay}ms">
      <div class="seeker-card-glow" aria-hidden="true"></div>
      <div class="seeker-card-top">
        <span class="${kindClass}">${kindLabel}</span>
        <span class="seeker-source">${sourceIcon} ${group}${author ? `<span class="seeker-author muted">${author}</span>` : ""}</span>
        ${when.relative ? `<span class="seeker-time" title="${when.full}">${when.relative}</span>` : ""}
      </div>
      ${when.full ? `<div class="seeker-datetime muted">${when.full}</div>` : ""}
      <h3 class="seeker-title">${p.title || "—"}</h3>
      ${p.snippet && p.snippet !== p.title ? `<p class="seeker-snippet muted">${p.snippet.slice(0, 220)}${p.snippet.length > 220 ? "…" : ""}</p>` : ""}
      <div class="seeker-meta muted">${budget}${loc}</div>
      <a class="seeker-link" href="${p.url}" target="_blank" rel="noopener noreferrer">open bron →</a>
    </article>`;
}

function renderSeekersLiveStrip(posts, seenSet) {
  const strip = document.getElementById("seekers-live-strip");
  if (!strip || !posts.length) {
    if (strip) strip.innerHTML = "";
    return;
  }
  const fresh = posts.filter((p) => !seenSet.has(seekerPostId(p))).slice(0, 4);
  const items = (fresh.length ? fresh : posts.slice(0, 4)).map((p) => {
    const when = formatSeekerTime(p.posted_at);
    const isNew = !seenSet.has(seekerPostId(p));
    return `<a class="seekers-live-chip${isNew ? " seekers-live-chip-new" : ""}" href="${p.url}" target="_blank" rel="noopener noreferrer">${p.title.slice(0, 52)}${p.title.length > 52 ? "…" : ""}<span class="muted">${when.relative ? ` · ${when.relative}` : ""}</span></a>`;
  });
  strip.innerHTML = `<div class="seekers-live-label"><span class="live-dot"></span> binnenkomend</div><div class="seekers-live-track">${items.join("")}</div>`;
}

function formatSeekerTime(iso) {
  if (!iso) return { relative: "", full: "" };
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return { relative: "", full: "" };
  const full = d.toLocaleString("nl-NL", {
    timeZone: "Europe/Amsterdam",
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  let relative = full;
  if (mins < 1) relative = "zojuist";
  else if (mins < 60) relative = `${mins} min geleden`;
  else if (mins < 48 * 60) relative = `${Math.floor(mins / 60)} uur geleden`;
  else relative = `${Math.floor(mins / 1440)} d geleden`;
  return { relative, full };
}

function renderRedditOverview(overview) {
  const el = document.getElementById("reddit-overview");
  if (!el || !overview || !overview.total_relevant) {
    if (el) el.innerHTML = "";
    return;
  }
  const kindLabel = (k) =>
    k === "seeking" ? "zoekt" : k === "offering" ? "biedt" : "bericht";
  const renderLine = (a) => {
    const t = formatSeekerTime(a.posted_at);
    const budget = a.budget_eur ? ` · ≤€${a.budget_eur}` : "";
    const loc = a.location_hint ? ` · ${a.location_hint}` : "";
    const tag = a.kind ? `<span class="seeker-tag seeker-tag-${a.kind === "seeking" ? "seek" : a.kind === "offering" ? "offer" : "unknown"}">${kindLabel(a.kind)}</span>` : "";
    return `<li>${tag}<a href="${a.url}" target="_blank" rel="noopener noreferrer">${a.title}</a><span class="muted"> · ${t.relative} (${t.full})${budget}${loc}</span></li>`;
  };
  const asks = overview.recent_asks || [];
  const recent = overview.recent_posts || asks;
  const askLines = recent.map(renderLine).join("");
  el.innerHTML = `
    <div class="reddit-overview-card">
      <div class="reddit-overview-head">
        <strong>${overview.subreddit || "Reddit"}</strong>
        <span class="muted">wonen in Eindhoven · titels gefilterd op relevantie</span>
      </div>
      <p class="reddit-overview-stats">
        <span class="reddit-stat"><b>${overview.seeking ?? 0}</b> zoekt</span>
        <span class="reddit-stat"><b>${overview.offering ?? 0}</b> biedt</span>
        <span class="reddit-stat"><b>${overview.total_relevant ?? 0}</b> relevant</span>
      </p>
      ${recent.length ? `<ul class="reddit-ask-list">${askLines}</ul>` : ""}
    </div>`;
}

function renderSeekersFeed(feed) {
  const el = document.getElementById("seekers-feed");
  const subtitle = document.getElementById("seekers-subtitle");
  if (!el) return;
  renderRedditOverview(feed && feed.reddit_overview);
  const posts = (feed && feed.posts) || [];
  const sources = (feed && feed.sources_active) || [];
  const seenSet = loadSeenSeekers();
  if (subtitle) {
    const src = sources.length ? sources.join(" · ") : "—";
    const newCount = posts.filter((p) => !seenSet.has(seekerPostId(p))).length;
    const newLabel = newCount ? ` · ${newCount} nieuw` : "";
    subtitle.textContent = `${posts.length} zoekers · bronnen: ${src}${newLabel}`;
  }
  renderSeekersLiveStrip(posts, seenSet);
  if (!posts.length) {
    el.innerHTML = `<div class="muted">Nog geen zoekers gevonden in Eindhoven. Reddit en Marktplaats worden elke scan bijgewerkt.</div>`;
    return;
  }
  el.innerHTML = posts.map((p, idx) => seekerCardHtml(p, idx, seenSet)).join("");
  posts.forEach((p) => seenSet.add(seekerPostId(p)));
  saveSeenSeekers(seenSet);
}

async function loadSeekersFeed() {
  try {
    const res = await fetch("./data/seekers_feed.json", { cache: "no-store" });
    if (res.ok) return res.json();
  } catch {
    /* fallback below */
  }
  return null;
}

async function loadRun() {
  // Seekers first so a chart/map error never blanks the feed.
  try {
    const seekers = await loadSeekersFeed();
    if (seekers) renderSeekersFeed(seekers);
  } catch (err) {
    console.error("seekers feed failed", err);
    renderSeekersFeed(null);
  }

  const res = await fetch("./data/latest_listings.json", { cache: "no-store" });
  const data = await res.json();

  if (!document.getElementById("seekers-feed")?.innerHTML) {
    renderSeekersFeed(data.seekers_feed || null);
  }

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
  try {
    renderStats(data.market_stats, data.max_rent, listings.length);
  } catch (err) {
    console.error("stats render failed", err);
  }
  initMapTagFilters();
  await renderMap(listings);
}

setInterval(updateDeadlineRow, 1000);
updateDeadlineRow();
loadRun().catch((err) => {
  const headline = document.getElementById("headline-status");
  if (headline) headline.textContent = `Status: nog steeds geen woning — site error: ${err}`;
});

window.addEventListener("resize", () => {
  const stats = window.__lastMarketStats;
  if (stats) drawPriceChart(stats.price_distribution || []);
  if (window.__housingMap) window.__housingMap.invalidateSize();
});
