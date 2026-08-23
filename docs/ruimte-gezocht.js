/* Ruimte Gezocht — TikTok-style scroll feed */

const DEFAULT_MULT = 3.5;
const INCOME_SAMPLES = [2400, 2800, 3200, 3500, 3800, 4200, 4500, 5000, 5500, 6000, 7000, 8500];
const ACTIONS_KEY = "rg_listing_actions_v1";

const state = {
  listings: [],
  seekers: [],
  rawListings: [],
  userIncome: 3500,
  userLat: EINDHOVEN_CENTER.lat,
  userLon: EINDHOVEN_CENTER.lon,
  hasLocation: false,
  map: null,
  mapLayer: null,
  mapMode: "all",
  miniMaps: new Map(),
  currentView: "feed",
  hidePassed: true,
};
function $(sel) {
  return document.querySelector(sel);
}

function formatEur(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return `€${Math.round(n).toLocaleString("nl-NL")}`;
}

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function formatDist(km) {
  if (km == null) return "—";
  if (km < 1) return `${Math.round(km * 1000)} m`;
  return `${km.toFixed(1).replace(".", ",")} km`;
}

function formatIncome(l) {
  if (l.income_requirement_label) return l.income_requirement_label;
  if (l.income_multiplier != null && l.rent_eur != null) {
    const m = Number(l.income_multiplier);
    const ml = Number.isInteger(m) ? String(m) : String(m).replace(".", ",");
    const req = l.income_required_eur ?? Math.round(l.rent_eur * m);
    return `${ml}× · ${formatEur(req)}`;
  }
  if (l.income_required_eur != null) return formatEur(l.income_required_eur);
  if (l.rent_eur != null) return `~${formatEur(Math.round(l.rent_eur * DEFAULT_MULT))}`;
  return "—";
}

function formatApps(l) {
  if (l.application_count_label) return l.application_count_label;
  if (l.application_count != null) return String(l.application_count);
  return "—";
}

function formatAvail(raw) {
  if (!raw) return "—";
  const d = new Date(raw);
  if (!Number.isNaN(d.getTime()) && raw.match(/^\d{4}/)) {
    return d.toLocaleDateString("nl-NL", { day: "numeric", month: "short", year: "numeric" });
  }
  return raw;
}

function requiredIncome(l) {
  if (l.income_required_eur != null && l.income_required_eur >= 900) {
    return { amount: l.income_required_eur, known: true };
  }
  const mult = l.income_multiplier != null ? l.income_multiplier : DEFAULT_MULT;
  if (l.rent_eur >= 300) return { amount: Math.round(l.rent_eur * mult), known: l.income_multiplier != null };
  return { amount: null, known: false };
}

function affordability(l, income) {
  const req = requiredIncome(l);
  if (req.amount == null) return { status: "maybe", label: "MISSCHIEN", req };
  if (income >= req.amount) return { status: "reachable", label: "BINNEN BEREIK", req };
  if (income >= req.amount * 0.9) return { status: "almost", label: "BIJNA", req };
  return { status: "no", label: "NIET BINNEN BEREIK", req };
}

function loadActions() {
  try {
    return JSON.parse(localStorage.getItem(ACTIONS_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveActions(actions) {
  localStorage.setItem(ACTIONS_KEY, JSON.stringify(actions));
  updateSavedBadge();
}

function listingAction(url) {
  if (!url) return null;
  return loadActions()[url]?.status || null;
}

function setListingAction(url, status) {
  if (!url) return;
  const actions = loadActions();
  if (status) actions[url] = { status, at: new Date().toISOString() };
  else delete actions[url];
  saveActions(actions);
}

function interestedCount() {
  const actions = loadActions();
  return Object.values(actions).filter((a) => a.status === "interested").length;
}

function updateSavedBadge() {
  const btn = $("#saved-btn");
  const countEl = $("#saved-count");
  const n = interestedCount();
  if (countEl) countEl.textContent = String(n);
  if (btn) {
    btn.hidden = n === 0 && state.currentView !== "saved";
    btn.classList.toggle("active", state.currentView === "saved");
  }
}

function listingsForView(view) {
  const enriched = state.rawListings.map(enrichListing);
  if (view === "saved") {
    const actions = loadActions();
    return enriched.filter((l) => l.url && actions[l.url]?.status === "interested");
  }
  if (state.hidePassed) {
    return enriched.filter((l) => !l.url || listingAction(l.url) !== "passed");
  }
function enrichListing(l) {
  const lat = l.map_lat;
  const lon = l.map_lon;
  const aff = affordability(l, state.userIncome);
  const dist = haversineKm(state.userLat, state.userLon, lat, lon);
  return { ...l, map_lat: lat, map_lon: lon, aff, distKm: dist };
}

function slideHtml(l, idx, total) {
  const wijk = (l.neighborhood || "Eindhoven").toUpperCase();
  const platform = l.platform || l.source || "—";
  const tag = l.match_tag || "—";
  const aff = l.aff;
  const action = listingAction(l.url);
  const slideClass = ["rg-slide", aff.status, action === "interested" ? "interested" : "", action === "passed" ? "passed" : ""]
    .filter(Boolean)
    .join(" ");
  const interestedActive = action === "interested" ? " active" : "";
  const passedActive = action === "passed" ? " active" : "";
  return `
    <article class="${slideClass}" data-url="${l.url || ""}" data-idx="${idx}" id="slide-${idx}">
      <div class="rg-slide-top">
        <span class="rg-slide-platform">${platform}</span>
        <span class="rg-slide-status ${aff.status}">${aff.label}</span>
      </div>
      <div class="rg-slide-wijk">${wijk}</div>
      <div class="rg-slide-rent">${formatEur(l.rent_eur)}</div>
      <div class="rg-slide-meta">${l.size_m2 ?? "?"} m² · ${state.hasLocation ? formatDist(l.distKm) + " van jou" : l.location || "Eindhoven"}</div>
      <div class="rg-mini-map" id="mini-map-${idx}" data-lat="${l.map_lat}" data-lon="${l.map_lon}"></div>
      <dl class="rg-slide-grid">
        <dt>Inkomens eis</dt><dd>${formatIncome(l)}</dd>
        <dt>Jij</dt><dd>${formatEur(state.userIncome)}</dd>
        <dt>Reacties</dt><dd>${formatApps(l)}</dd>
        <dt>Huur vanaf</dt><dd>${formatAvail(l.available_from)}</dd>
        <dt>Tag</dt><dd>${tag}</dd>
        <dt>Vereist</dt><dd>${aff.req.amount != null ? formatEur(aff.req.amount) : "onbekend"}</dd>
      </dl>
      <h3 class="rg-slide-title">${l.title || "—"}</h3>
      <div class="rg-slide-actions">
        <button type="button" class="rg-action-btn interested${interestedActive}" data-action="interested">♥ Interessant</button>
        <button type="button" class="rg-action-btn passed${passedActive}" data-action="passed">✕ Skip</button>
      </div>
      <a class="rg-open-btn" href="${l.url || "#"}" target="_blank" rel="noopener noreferrer">Open listing →</a>
      <p class="rg-slide-counter">${idx + 1} / ${total}</p>
    </article>`;
}

function seekerHtml(p) {
  const kind = p.kind || "unknown";
  const kindLabel = kind === "seeking" ? "zoekt" : kind === "offering" ? "biedt" : "bericht";
  const kindClass =
    kind === "seeking" ? "rg-seeker-tag seek" : kind === "offering" ? "rg-seeker-tag offer" : "rg-seeker-tag";
  const when = p.posted_at ? new Date(p.posted_at).toLocaleDateString("nl-NL") : "";
  const budget = p.budget_eur ? ` · max €${p.budget_eur}` : "";
  const loc = p.location_hint ? ` · ${p.location_hint}` : "";
  const src = p.source === "reddit" && p.group_name ? p.group_name : p.source || "";
  return `
    <article class="rg-slide rg-slide-seeker">
      <div class="rg-slide-top">
        <span class="${kindClass}">${kindLabel}</span>
        <span class="rg-slide-platform">${src}</span>
      </div>
      <h3 class="rg-slide-title">${p.title || "—"}</h3>
      ${p.snippet && p.snippet !== p.title ? `<p class="rg-seeker-snippet">${p.snippet.slice(0, 220)}${p.snippet.length > 220 ? "…" : ""}</p>` : ""}
      ${when || budget || loc ? `<p class="rg-slide-meta">${when}${budget}${loc}</p>` : ""}
      <a class="rg-open-btn" href="${p.url}" target="_blank" rel="noopener noreferrer">Open post →</a>
    </article>`;
}

function renderFeed(view) {
  const feed = $("#feed");
  if (!feed) return;
  const mode = view || state.currentView;
  state.listings = listingsForView(mode === "saved" ? "saved" : "feed");
  state.miniMaps.clear();
  if (!state.listings.length) {
    feed.innerHTML =
      mode === "saved"
        ? `<p class="rg-feed-loading muted">Nog niets opgeslagen. Tik ♥ Interessant op een woning.</p>`
        : `<p class="rg-feed-loading muted">Geen matches geladen.</p>`;
    updateSavedBadge();
    return;
  }
  feed.innerHTML = state.listings.map((l, i) => slideHtml(l, i, state.listings.length)).join("");
  initMiniMapsObserver();
  updateSavedBadge();
}

function handleListingAction(url, action) {
  const current = listingAction(url);
  const next = current === action ? null : action;
  setListingAction(url, next);
  if (state.currentView === "feed" && next === "passed" && state.hidePassed) {
    const slide = document.querySelector(`.rg-slide[data-url="${CSS.escape(url)}"]`);
    if (slide) {
      slide.style.transition = "opacity 0.25s, transform 0.25s";
      slide.style.opacity = "0";
      slide.style.transform = "translateX(-20px)";
      setTimeout(() => {
        renderFeed("feed");
      }, 260);
      return;
    }
  }
  renderFeed(state.currentView);
}

function renderSeekersFeed() {
  const feed = $("#feed");
  if (!feed) return;
  if (!state.seekers.length) {
    feed.innerHTML = `<p class="rg-feed-loading muted">Nog geen zoekers in de feed.</p>`;
    return;
  }
  feed.innerHTML = state.seekers.map(seekerHtml).join("");
}

function initMiniMapsObserver() {
  if (!window.L) return;
  const obs = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (!e.isIntersecting) return;
        const el = e.target;
        const idx = el.id.replace("mini-map-", "");
        if (state.miniMaps.has(idx)) return;
        const lat = parseFloat(el.dataset.lat);
        const lon = parseFloat(el.dataset.lon);
        if (Number.isNaN(lat)) return;
        const map = L.map(el, { zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false }).setView([lat, lon], 15);
        L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", { maxZoom: 18 }).addTo(map);
        L.circleMarker([lat, lon], { radius: 6, color: "#171717", fillColor: "#171717", fillOpacity: 1 }).addTo(map);
        if (state.hasLocation) {
          L.circleMarker([state.userLat, state.userLon], { radius: 4, color: "#888", fillColor: "#888", fillOpacity: 0.8 }).addTo(map);
        }
        state.miniMaps.set(idx, map);
        setTimeout(() => map.invalidateSize(), 100);
      });
    },
    { root: $("#feed"), threshold: 0.3 }
  );
  document.querySelectorAll(".rg-mini-map").forEach((el) => obs.observe(el));
}

function applyFilters() {
  state.userIncome = parseInt($("#income").value, 10) || 3500;
  state.miniMaps.clear();
  renderFeed(state.currentView);
  $("#filter-panel").hidden = true;
  $("#filter-toggle").setAttribute("aria-expanded", "false");
}

function toggleFilters() {
  const panel = $("#filter-panel");
  const open = panel.hidden;
  panel.hidden = !open;
  $("#filter-toggle").setAttribute("aria-expanded", open ? "true" : "false");
}

function requestLocation() {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      state.userLat = pos.coords.latitude;
      state.userLon = pos.coords.longitude;
      state.hasLocation = true;
      applyFilters();
    },
    () => {
      state.hasLocation = false;
    }
  );
}

function initBigMap() {
  if (!window.L || state.map) return;
  state.map = L.map("rg-map", { zoomControl: false }).setView([state.userLat, state.userLon], 13);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: "© OSM © CARTO",
    maxZoom: 18,
  }).addTo(state.map);
  state.mapLayer = L.layerGroup().addTo(state.map);
  refreshBigMap();
}

function refreshBigMap() {
  if (!state.mapLayer) return;
  state.mapLayer.clearLayers();
  const mode = state.mapMode;
  const mapListings = listingsForView("feed");
  mapListings.forEach((l) => {
    const ok = l.aff.status === "reachable";
    const faded = mode === "yours" && !ok;
    const color = ok ? "#171717" : faded ? "#ddd" : "#999";
    L.circleMarker([l.map_lat, l.map_lon], {
      radius: ok ? 7 : 5,
      color,
      fillColor: color,
      fillOpacity: faded ? 0.12 : ok ? 1 : 0.5,
      weight: 1,
    })
      .addTo(state.mapLayer)
      .bindPopup(`<b>${formatEur(l.rent_eur)}</b><br/><a href="${l.url}" target="_blank">open</a>`);
  });
  L.circleMarker([state.userLat, state.userLon], { radius: 6, color: "#888", fillColor: "#888", fillOpacity: 1 }).addTo(state.mapLayer);
  const total = mapListings.length;
  const okN = mapListings.filter((l) => l.aff.status === "reachable").length;
  $("#map-stats").textContent =
    mode === "all"
      ? `${total} woningen op de kaart`
      : `${okN} bereikbaar · ${total - okN} verdwenen uit jouw Eindhoven`;
}

function calcLandlord() {
  const rent = parseInt($("#landlord-rent").value, 10) || 1450;
  const mult = parseFloat($("#landlord-mult").value) || 4;
  const required = Math.round(rent * mult);
  const pct = Math.round((INCOME_SAMPLES.filter((i) => i >= required).length / INCOME_SAMPLES.length) * 100);
  $("#landlord-result").innerHTML = `
    <p>Minimaal bruto per maand:</p>
    <div class="big">${formatEur(required)}</div>
    <p>≈ ${formatEur(required * 12)} per jaar</p>
    <p style="margin-top:16px">Bereikbaar voor <span class="pct">${pct}%</span> van representatieve zoekers.</p>
    <p class="muted">Dit is wat jouw eis betekent — geen beschuldiging.</p>`;
}

function setView(view) {
  state.currentView = view;
  document.querySelectorAll(".rg-nav-btn[data-view]").forEach((b) => {
    b.classList.toggle("active", view !== "saved" && b.dataset.view === view);
  });
  const tagline = $(".rg-tagline");
  if (tagline) {
    const labels = {
      seekers: "Je bent niet alleen — zelfde live feed als het dashboard",
      saved: `${interestedCount()} opgeslagen · jouw shortlist`,
      feed: "Hoeveel Eindhoven blijft er voor jou over?",
    };
    if (labels[view]) tagline.textContent = labels[view];
  }
  $("#map-overlay").hidden = view !== "map";
  const feedEl = $("#feed");
  if (feedEl) feedEl.scrollTop = 0;
  if (view === "map") {
    initBigMap();
    setTimeout(() => state.map && state.map.invalidateSize(), 150);
  }
  if (view === "feed" || view === "saved") renderFeed(view);
  if (view === "seekers") renderSeekersFeed();
  updateSavedBadge();
}

async function loadAll() {
  const cache = await loadGeocodeCache();
  try {
    const res = await fetch("./data/latest_listings.json", { cache: "no-store" });
    const data = await res.json();
    const raw = data.listings || [];
    state.rawListings = attachResolvedCoords(raw, cache);
  } catch {
    state.rawListings = [];
  }
  try {
    const sres = await fetch("./data/seekers_feed.json", { cache: "no-store" });
    if (sres.ok) {
      const sf = await sres.json();
      state.seekers = sf.posts || [];
    }
  } catch {
    state.seekers = [];
  }
  state.listings = listingsForView("feed");
  updateSavedBadge();
  renderFeed("feed");
}

function bindEvents() {
  $("#filter-toggle")?.addEventListener("click", toggleFilters);
  $("#apply-filters")?.addEventListener("click", applyFilters);
  $("#loc-btn")?.addEventListener("click", requestLocation);
  $("#saved-btn")?.addEventListener("click", () => {
    setView(state.currentView === "saved" ? "feed" : "saved");
  });
  $("#feed")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const slide = btn.closest(".rg-slide");
    const url = slide?.dataset.url;
    if (!url) return;
    e.preventDefault();
    handleListingAction(url, btn.dataset.action);
  });
  $("#landlord-open")?.addEventListener("click", () => {
    $("#landlord-panel").hidden = false;
  });
  $("#landlord-close")?.addEventListener("click", () => {
    $("#landlord-panel").hidden = true;
  });
  $("#landlord-calc")?.addEventListener("click", calcLandlord);
  $("#map-close")?.addEventListener("click", () => setView("feed"));
  document.querySelectorAll(".rg-nav-btn[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => setView(btn.dataset.view));
  });
  document.querySelectorAll(".rg-map-toggle button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".rg-map-toggle button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.mapMode = btn.dataset.mapMode;
      refreshBigMap();
    });
  });
}

bindEvents();
loadAll();
