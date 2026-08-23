/* Ruimte Gezocht — mobile exhibition demo */

const EINDHOVEN = { lat: 51.4416, lon: 5.4697 };
const DEFAULT_MULT = 3.5;
const WIJK_COORDS = {
  strijp: { lat: 51.451, lon: 5.484 },
  centrum: { lat: 51.441, lon: 5.479 },
  woensel: { lat: 51.448, lon: 5.462 },
  tongelre: { lat: 51.435, lon: 5.505 },
  gestel: { lat: 51.428, lon: 5.488 },
  stratum: { lat: 51.433, lon: 5.472 },
  meerrijk: { lat: 51.455, lon: 5.448 },
  bergen: { lat: 51.438, lon: 5.455 },
};

// Representative seeker incomes for landlord reachability estimate
const INCOME_SAMPLES = [2400, 2800, 3200, 3500, 3800, 4200, 4500, 5000, 5500, 6000, 7000, 8500];

const state = {
  listings: [],
  userIncome: 3500,
  household: 1,
  userLat: EINDHOVEN.lat,
  userLon: EINDHOVEN.lon,
  hasLocation: false,
  swipeIndex: 0,
  viewed: 0,
  reachableCount: 0,
  almostCount: 0,
  maybeCount: 0,
  requiredIncomes: [],
  map: null,
  mapLayer: null,
  mapMode: "all",
};

function $(sel) {
  return document.querySelector(sel);
}

function showScreen(name) {
  document.querySelectorAll(".rg-screen").forEach((el) => {
    el.classList.toggle("active", el.dataset.screen === name);
  });
  if (name === "map") initMap();
  if (name === "stats") renderStats();
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
  if (km == null) return "";
  if (km < 1) return `${Math.round(km * 1000)} m van jou`;
  return `${km.toFixed(1).replace(".", ",")} km van jou`;
}

function coordsForListing(l) {
  if (l.map_lat != null && l.map_lon != null) {
    return { lat: l.map_lat, lon: l.map_lon };
  }
  const w = (l.neighborhood || l.location || l.title || "").toLowerCase();
  for (const [key, c] of Object.entries(WIJK_COORDS)) {
    if (w.includes(key)) {
      const jitter = (hashStr(l.url || l.title) % 100) / 5000;
      return { lat: c.lat + jitter, lon: c.lon - jitter };
    }
  }
  const j = hashStr(l.url || l.title) % 200;
  return {
    lat: EINDHOVEN.lat + (j - 100) / 8000,
    lon: EINDHOVEN.lon + ((j * 7) % 200 - 100) / 8000,
  };
}

function hashStr(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function requiredIncome(l) {
  if (l.income_required_eur != null && l.income_required_eur >= 900) {
    return { amount: l.income_required_eur, known: true, mult: l.income_multiplier };
  }
  const mult = l.income_multiplier != null ? l.income_multiplier : DEFAULT_MULT;
  if (l.rent_eur != null && l.rent_eur >= 300) {
    return { amount: Math.round(l.rent_eur * mult), known: l.income_multiplier != null, mult };
  }
  return { amount: null, known: false, mult: null };
}

function affordability(l, income) {
  const req = requiredIncome(l);
  if (req.amount == null) return { status: "maybe", req, label: "MISSCHIEN" };
  if (income >= req.amount) return { status: "reachable", req, label: "BINNEN BEREIK" };
  if (income >= req.amount * 0.92) return { status: "almost", req, label: "BIJNA" };
  if (income >= req.amount * 0.75) return { status: "almost", req, label: "BIJNA" };
  return { status: "no", req, label: "NIET BINNEN BEREIK" };
}

function enrichListing(l) {
  const coords = coordsForListing(l);
  const aff = affordability(l, state.userIncome);
  const dist = haversineKm(state.userLat, state.userLon, coords.lat, coords.lon);
  return { ...l, ...coords, aff, distKm: dist };
}

function normalizeListings(data) {
  const inBudget = data.listings || [];
  const excluded = (data.excluded_listings || []).filter(
    (l) =>
      l.rent_eur != null &&
      l.rent_eur >= 300 &&
      l.size_m2 != null &&
      l.size_m2 >= 15 &&
      /eindhoven|veldhoven/i.test(`${l.location || ""} ${l.title || ""}`)
  );
  const seen = new Set();
  const merged = [];
  for (const l of [...inBudget, ...excluded]) {
    const key = (l.url || l.title || "").toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(l);
  }
  return merged.sort((a, b) => (b.rent_eur || 0) - (a.rent_eur || 0));
}

async function loadData() {
  try {
    const res = await fetch("./data/latest_listings.json", { cache: "no-store" });
    if (!res.ok) throw new Error("fetch failed");
    const data = await res.json();
    state.listings = normalizeListings(data).map(enrichListing);
    state.rawMarket = data.market_stats || {};
    const el = $("#rg-data-count");
    if (el) el.textContent = state.listings.length;
  } catch {
    state.listings = [];
  }
}

function renderCard(listing) {
  if (!listing) {
    return `<div class="rg-card rg-card-empty muted">Geen woningen meer. Bekijk je statistieken.</div>`;
  }
  const wijk = (listing.neighborhood || "Eindhoven").toUpperCase();
  const aff = listing.aff;
  const reqLabel =
    aff.req.amount != null ? formatEur(aff.req.amount) : aff.req.known ? "onbekend" : `~${formatEur(listing.rent_eur * DEFAULT_MULT)}`;

  return `
    <article class="rg-card ${aff.status === "reachable" ? "reachable" : ""}" data-url="${listing.url || ""}">
      <div class="rg-card-wijk">${wijk}</div>
      <div class="rg-card-rent">${formatEur(listing.rent_eur)}</div>
      <div class="rg-card-size">${listing.size_m2 ?? "?"} m²</div>
      <div class="rg-card-dist">${state.hasLocation ? formatDist(listing.distKm) : listing.location || "Eindhoven"}</div>
      <div class="rg-card-divider"></div>
      <div class="rg-card-income-row"><span>Inkomen vereist</span><strong>${reqLabel}</strong></div>
      <div class="rg-card-income-row"><span>Jij</span><strong>${formatEur(state.userIncome)}</strong></div>
      <div class="rg-card-status ${aff.status}">${aff.label}</div>
    </article>`;
}

function updateSwipeUI() {
  const total = state.listings.length;
  const idx = state.swipeIndex;
  $("#swipe-counter").textContent = total ? `${Math.min(idx + 1, total)} / ${total}` : "0 / 0";
  const stack = $("#card-stack");
  stack.innerHTML = renderCard(state.listings[idx]);
  updateNearbyBanner();
}

function updateNearbyBanner() {
  const el = $("#nearby-banner");
  if (!el || !state.hasLocation) {
    if (el) el.textContent = "";
    return;
  }
  const nearby = state.listings.filter((l) => l.distKm <= 1);
  const reachableNearby = nearby.filter((l) => l.aff.status === "reachable");
  if (nearby.length === 0) {
    el.textContent = "";
    return;
  }
  if (reachableNearby.length === 0) {
    el.innerHTML = `<strong>Je staat naast ${nearby.length} huurwoning${nearby.length === 1 ? "" : "en"}.</strong> Geen daarvan is bereikbaar met jouw inkomen.`;
  } else {
    el.innerHTML = `Hier in de buurt: ${nearby.length} beschikbaar · ${reachableNearby.length} binnen jouw bereik`;
  }
}

function nextSwipe() {
  const listing = state.listings[state.swipeIndex];
  if (listing) {
    state.viewed += 1;
    if (listing.aff.req.amount != null) state.requiredIncomes.push(listing.aff.req.amount);
    if (listing.aff.status === "reachable") state.reachableCount += 1;
    else if (listing.aff.status === "almost") state.almostCount += 1;
    else if (listing.aff.status === "maybe") state.maybeCount += 1;
  }

  const card = $("#card-stack .rg-card");
  if (card && !card.classList.contains("rg-card-empty")) {
    card.classList.add("swipe-out");
    setTimeout(() => {
      state.swipeIndex += 1;
      if (state.swipeIndex >= state.listings.length) state.swipeIndex = 0;
      state.listings = state.listings.map(enrichListing);
      updateSwipeUI();
    }, 220);
  } else {
    state.swipeIndex += 1;
    updateSwipeUI();
  }
}

function renderStats() {
  const avgReq =
    state.requiredIncomes.length > 0
      ? Math.round(state.requiredIncomes.reduce((a, b) => a + b, 0) / state.requiredIncomes.length)
      : null;
  const totalReachable = state.listings.filter((l) => l.aff.status === "reachable").length;

  $("#session-stats").innerHTML = `
    <p>Je bekeek <strong>${state.viewed}</strong> woningen.</p>
    <span class="big">${state.reachableCount}</span>
    <p>waren binnen bereik tijdens deze sessie.</p>
    ${avgReq ? `<p>Gemiddeld vereist inkomen:<br/><strong>${formatEur(avgReq)} bruto</strong></p>` : ""}
    <p>Jij: <strong>${formatEur(state.userIncome)}</strong></p>
    <hr style="border:none;border-top:1px solid #e5e5e5;margin:16px 0"/>
    <p>In totaal op dit moment:<br/>
    <strong>${totalReachable}</strong> van <strong>${state.listings.length}</strong> woningen bereikbaar voor jou.</p>
  `;

  $("#evil-stat").textContent =
    state.viewed >= 5 && state.reachableCount <= state.viewed * 0.15
      ? "Ruimte Gezocht zegt: hier is nog een woning die je niet kunt hebben. Swipe."
      : "";
}

function initMap() {
  if (!window.L) return;
  const mapEl = $("#rg-map");
  if (!mapEl) return;

  if (!state.map) {
    state.map = L.map("rg-map", { zoomControl: false }).setView([state.userLat, state.userLon], 13);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      attribution: "© OSM © CARTO",
      maxZoom: 18,
    }).addTo(state.map);
    state.mapLayer = L.layerGroup().addTo(state.map);
    L.circleMarker([state.userLat, state.userLon], {
      radius: 8,
      color: "#171717",
      fillColor: "#171717",
      fillOpacity: 1,
      weight: 2,
    })
      .addTo(state.map)
      .bindPopup("Jij bent hier");
  }

  setTimeout(() => state.map.invalidateSize(), 100);
  refreshMapMarkers();
  updateMapStats();
}

function refreshMapMarkers() {
  if (!state.mapLayer) return;
  state.mapLayer.clearLayers();
  const mode = state.mapMode;

  state.listings.forEach((l) => {
    const reachable = l.aff.status === "reachable";
    const faded = mode === "yours" && !reachable;
    const color = reachable ? "#171717" : faded ? "#ddd" : "#999";
    const opacity = faded ? 0.15 : reachable ? 1 : 0.55;
    const radius = reachable ? 7 : 5;

    L.circleMarker([l.lat, l.lon], {
      radius,
      color,
      fillColor: color,
      fillOpacity: opacity,
      weight: 1,
    })
      .addTo(state.mapLayer)
      .bindPopup(
        `<b>${formatEur(l.rent_eur)}</b> · ${l.size_m2}m²<br/>${l.aff.label}<br/><a href="${l.url}" target="_blank">open</a>`
      );
  });
}

function updateMapStats() {
  const total = state.listings.length;
  const reachable = state.listings.filter((l) => l.aff.status === "reachable").length;
  const pct = total ? Math.round((100 * (total - reachable)) / total) : 0;
  const mode = state.mapMode;

  $("#map-stats").innerHTML =
    mode === "all"
      ? `<span>Alle beschikbare woningen</span><strong>${total} op de kaart</strong>`
      : `<span>Jouw Eindhoven</span><strong>${reachable} bereikbaar</strong>
         <span class="muted">${pct}% verdwenen — niet bereikbaar met ${formatEur(state.userIncome)}</span>`;
}

function calcLandlord() {
  const rent = parseInt($("#landlord-rent").value, 10) || 1450;
  const mult = parseFloat($("#landlord-mult").value) || 4;
  const required = Math.round(rent * mult);
  const yearly = required * 12;

  const reachablePct =
    Math.round((INCOME_SAMPLES.filter((i) => i >= required).length / INCOME_SAMPLES.length) * 100);

  let salaryContext = "";
  if (required >= 5800) {
    salaryContext = "Dat is meer dan een gemiddeld modaal inkomen (≈ €3.800 bruto).";
  } else if (required >= 4500) {
    salaryContext = "Vergelijkbaar met een HBO-startsalis of ervaren MBO'er in regio Eindhoven.";
  } else if (required >= 3500) {
    salaryContext = "Rond modaal — veel alleenstaanden, niet elk stel.";
  } else {
    salaryContext = "Relatief toegankelijk voor modale inkomens.";
  }

  const marketTotal = state.listings.length || state.rawMarket?.total_tracked || 0;
  const cheaperReachable = state.listings.filter((l) => {
    const r = requiredIncome(l);
    return r.amount != null && r.amount <= required;
  }).length;
  const marketPct = marketTotal ? Math.round((100 * cheaperReachable) / marketTotal) : reachablePct;

  $("#landlord-result").innerHTML = `
    <p>Om jouw woning te mogen huren moet iemand minimaal:</p>
    <div class="big">${formatEur(required)} bruto per maand</div>
    <p>≈ ${formatEur(yearly)} per jaar</p>
    <div class="rg-salary-context">${salaryContext}</div>
    <hr style="border:none;border-top:1px solid #e5e5e5;margin:20px 0"/>
    <p>Voor hoeveel woningzoekenden in onze geobserveerde dataset is jouw woning bereikbaar?</p>
    <div class="pct">${reachablePct}%</div>
    <p class="muted">Op basis van ${INCOME_SAMPLES.length} representatieve bruto-maandinkomens (${formatEur(2400)} – ${formatEur(8500)}).</p>
    <p>Ter vergelijking: ${marketPct}% van alle getrackte Eindhoven-aanbod vraagt een lager inkomen dan jouw eis.</p>
  `;
  showScreen("landlord-result");
}

function startSeeker() {
  state.userIncome = parseInt($("#seeker-income").value, 10) || 3500;
  state.household = parseInt($("#seeker-household").value, 10) || 1;
  state.swipeIndex = 0;
  state.viewed = 0;
  state.reachableCount = 0;
  state.almostCount = 0;
  state.maybeCount = 0;
  state.requiredIncomes = [];
  state.listings = state.listings.map(enrichListing);
  showScreen("location");
}

function beginSwipe() {
  showScreen("swipe");
  updateSwipeUI();
}

function requestLocation(thenSwipe) {
  if (!navigator.geolocation) {
    state.hasLocation = false;
    if (thenSwipe) beginSwipe();
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      state.userLat = pos.coords.latitude;
      state.userLon = pos.coords.longitude;
      state.hasLocation = true;
      state.listings = state.listings.map(enrichListing);
      if (thenSwipe) beginSwipe();
    },
    () => {
      state.hasLocation = false;
      state.userLat = EINDHOVEN.lat;
      state.userLon = EINDHOVEN.lon;
      if (thenSwipe) beginSwipe();
    },
    { enableHighAccuracy: true, timeout: 12000 }
  );
}

function bindEvents() {
  document.querySelectorAll("[data-go]").forEach((el) => {
    el.addEventListener("click", () => showScreen(el.dataset.go));
  });

  document.querySelectorAll("[data-back]").forEach((el) => {
    el.addEventListener("click", () => showScreen(el.dataset.back));
  });

  $("#seeker-start")?.addEventListener("click", startSeeker);
  $("#location-allow")?.addEventListener("click", () => requestLocation(true));
  $("#location-skip")?.addEventListener("click", () => {
    state.hasLocation = false;
    state.userLat = EINDHOVEN.lat;
    state.userLon = EINDHOVEN.lon;
    beginSwipe();
  });

  $("#landlord-calc")?.addEventListener("click", calcLandlord);

  document.querySelectorAll(".rg-map-toggle button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".rg-map-toggle button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.mapMode = btn.dataset.mapMode;
      refreshMapMarkers();
      updateMapStats();
    });
  });

  const stack = $("#card-stack");
  let touchY = 0;
  stack?.addEventListener(
    "touchstart",
    (e) => {
      touchY = e.touches[0].clientY;
    },
    { passive: true }
  );
  stack?.addEventListener(
    "touchend",
    (e) => {
      const dy = touchY - e.changedTouches[0].clientY;
      if (dy > 60) nextSwipe();
    },
    { passive: true }
  );
  stack?.addEventListener("click", () => nextSwipe());

  document.addEventListener("keydown", (e) => {
    if ($('[data-screen="swipe"].active')) {
      if (e.key === "ArrowUp" || e.key === " ") {
        e.preventDefault();
        nextSwipe();
      }
    }
  });
}

async function init() {
  bindEvents();
  await loadData();
}

init();
