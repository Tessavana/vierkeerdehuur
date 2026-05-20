const MOVE_OUT_DEADLINE = new Date("2026-07-26T23:59:59+02:00");

function updateClock() {
  const el = document.getElementById("clock");
  if (el) el.textContent = new Date().toLocaleTimeString();
}

function updateCountdown() {
  const el = document.getElementById("countdown");
  if (!el) return;
  const now = Date.now();
  const end = MOVE_OUT_DEADLINE.getTime();
  const diff = Math.max(0, end - now);
  const days = Math.floor(diff / 86400000);
  const hours = Math.floor((diff % 86400000) / 3600000);
  const mins = Math.floor((diff % 3600000) / 60000);
  const secs = Math.floor((diff % 60000) / 1000);
  el.textContent = `${days}d ${hours}u ${mins}m ${secs}s tot 26 juli`;
}

function groupByProvider(listings) {
  const out = {};
  listings.forEach((item) => {
    if (!out[item.provider]) out[item.provider] = [];
    out[item.provider].push(item);
  });
  return out;
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

const MAP_VISITED_KEY = "housing_map_visited_urls_v1";

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

/** Matches src/map_geocode.py _hash_fallback_coords when Web Crypto is available (HTTPS). */
async function mapCoordsForListing(listing) {
  const key = `${listing.url}|${listing.location}|${listing.title}`;
  try {
    if (globalThis.crypto?.subtle) {
      const buf = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(key));
      const hex = Array.from(new Uint8Array(buf))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("")
        .slice(0, 12);
      const h = parseInt(hex, 16);
      const dlat = (h % 2000) / 2000 * 0.035 - 0.0175;
      const dlon = (Math.floor(h / 2000) % 2000) / 2000 * 0.05 - 0.025;
      return { lat: 51.4416 + dlat, lon: 5.4697 + dlon };
    }
  } catch (_e) {
    /* http://localhost has no subtle crypto */
  }
  let h = 2166136261;
  for (let j = 0; j < key.length; j++) h = Math.imul(h ^ key.charCodeAt(j), 16777619);
  h = Math.abs(h) >>> 0;
  const dlat = (h % 2000) / 2000 * 0.035 - 0.0175;
  const dlon = (Math.floor(h / 2000) % 2000) / 2000 * 0.05 - 0.025;
  return { lat: 51.4416 + dlat, lon: 5.4697 + dlon };
}

async function loadRun() {
  const res = await fetch("./data/latest_listings.json", { cache: "no-store" });
  const data = await res.json();

  const status = data.application_status || {};
  renderOverviewTables(status);
  const subtitle = document.getElementById("results-subtitle");
  if (subtitle) subtitle.textContent = `Alle woningen gevonden op ${new Date(data.generated_at_utc).toLocaleString()}`;
  const headline = document.getElementById("headline-status");
  if (headline) headline.innerHTML = `Laatste update: ${new Date(data.generated_at_utc).toLocaleTimeString()}<br/>Nog steeds geen woning🙂`;

  renderProviders(data);
  await renderMap(data.listings);
}

function renderOverviewTables(status) {
  const left = document.getElementById("status-table-left");
  const right = document.getElementById("status-table-right");
  if (!left || !right) return;
  const rejected = (status.rejected_addresses || []).join(", ");
  const sh = status.sociale_huur || {};
  left.innerHTML = `
    <tr><td>Applications sent</td><td><b>${status.applications_sent ?? 5}</b></td></tr>
    <tr><td>Viewings</td><td><b>${status.viewings ?? 0}</b></td></tr>
    <tr><td>Rejections</td><td><b>${status.rejections ?? 3}</b></td></tr>
    <tr><td>No response</td><td><b>${status.no_response ?? 4}</b></td></tr>
    <tr><td>Afwijzingen tot nu toe</td><td>${rejected || "-"}</td></tr>
  `;
  right.innerHTML = `
    <tr><td>Sociale huur via</td><td>${sh.platform ?? "Wooniezie"}</td></tr>
    <tr><td>Inschrijfduur</td><td>${sh.inschrijfduur ?? "4 jaar en 3 maanden"}</td></tr>
    <tr><td>Reacties verstuurd</td><td>${sh.reacties_verstuurd ?? "230+"}</td></tr>
    <tr><td>Actief gezocht</td><td>${sh.actief_gezocht ?? "2 jaar"}</td></tr>
    <tr><td>Aantal bezichtigingen</td><td>${sh.bezichtigingen ?? 0}</td></tr>
  `;
}

function renderProviders(data) {
  const providersEl = document.getElementById("providers");
  if (!providersEl) return;
  providersEl.innerHTML = "";
  const suitableByProvider = groupByProvider(data.listings);
  const excludedByProvider = groupByProvider(data.excluded_listings || []);

  data.provider_results.forEach((p) => {
    const block = document.createElement("div");
    block.className = "provider-block";
    const suitable = suitableByProvider[p.provider] || [];
    const excluded = excludedByProvider[p.provider] || [];
    const sectionId = `excluded-${p.provider}`;
    const displayName = p.provider_name || p.provider.replace("Provider", "");
    const errLine = p.error ? `<div class="muted"><span class="status-error">error:</span> ${p.error}</div>` : "";
    const statusLine =
      p.status === "error"
        ? `<div class="muted"><span class="status-error">mislukt</span></div>`
        : "";
    block.innerHTML = `
      <div><b>${displayName}</b></div>
      ${statusLine}
      <div class="muted">parsed=${p.parsed} | suitable=${p.suitable} | excluded=${p.excluded ?? 0}</div>
      ${errLine}
      <div class="listing-header">
        <div>Woning</div>
        <div>Wijk</div>
        <div>Huur</div>
        <div>m²</div>
        <div>Huur vanaf</div>
        <div>Tag / link</div>
      </div>
      <div id="suitable-${p.provider}"></div>
      <button class="toggle-btn" data-target="${sectionId}">Show excluded (${excluded.length})</button>
      <div id="${sectionId}" class="hidden"></div>
    `;
    providersEl.appendChild(block);

    const suitableEl = block.querySelector(`#suitable-${CSS.escape(p.provider)}`);
    suitable.slice(0, 25).forEach((l) => {
      suitableEl.innerHTML += listingRow(l, false);
    });
    if (!suitable.length) suitableEl.innerHTML = `<div class="muted">No suitable listings from this provider right now.</div>`;

    const excludedEl = block.querySelector(`#${CSS.escape(sectionId)}`);
    excluded.slice(0, 50).forEach((l) => {
      excludedEl.innerHTML += listingRow(l, true);
    });
    if (!excluded.length) excludedEl.innerHTML = `<div class="muted">No excluded listings stored.</div>`;
  });

  providersEl.querySelectorAll(".toggle-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = document.getElementById(btn.dataset.target);
      if (!target) return;
      target.classList.toggle("hidden");
      btn.textContent = target.classList.contains("hidden") ? "Show excluded" : "Hide excluded";
    });
  });
}

function listingRow(l, excluded) {
  const wijk = dash(l.neighborhood);
  const avail = dash(l.available_from);
  const newClass = !excluded && l.is_new_today ? " is-new-today" : "";
  const reason = excluded
    ? `<span class="muted">${l.reason ?? "excluded"}</span>`
    : `<span class="${matchTagClass(l.match_tag || "okay")}">${l.match_tag ?? "okay"}</span>`;
  const newBadge = !excluded && l.is_new_today ? ' <span class="tag tag-new">Nieuw vandaag</span>' : "";
  return `
    <div class="listing-row${newClass}">
      <div><b>${l.title}</b><div class="muted">${l.location}</div></div>
      <div>${wijk}</div>
      <div>EUR ${l.rent_eur ?? "?"}</div>
      <div>${l.size_m2 ?? "?"} m2</div>
      <div>${avail}</div>
      <div>${reason}${newBadge}<br/><a href="${l.url}" target="_blank" rel="noopener noreferrer">open</a></div>
    </div>
  `;
}

async function renderMap(listings) {
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

  const usedCoords = new Map();
  const layerGroup = L.layerGroup().addTo(map);
  const visitedUrls = loadVisitedUrls();

  for (const listing of listings) {
    let lat = listing.map_lat != null ? Number(listing.map_lat) : null;
    let lon = listing.map_lon != null ? Number(listing.map_lon) : null;
    if (lat == null || lon == null || Number.isNaN(lat) || Number.isNaN(lon)) {
      const c = await mapCoordsForListing(listing);
      lat = c.lat;
      lon = c.lon;
    }
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
    const newLine = isNewToday ? "<b>Nieuw vandaag</b><br/>" : "";
    marker.bindPopup(
      `${newLine}<b>${listing.title}</b><br/>${wijk !== "-" ? `${wijk} · ` : ""}EUR ${listing.rent_eur ?? "?"} | ${listing.size_m2 ?? "?"} m²<br/>${listing.available_from ? `Vanaf ${listing.available_from}<br/>` : ""}`
    );
    marker.on("click", () => {
      addVisitedUrl(listing.url);
      marker.setStyle({ color: "#4b5563", weight: 2, fillColor: "#9ca3af", fillOpacity: 1 });
      showSelectedMatch(listing);
    });
    layerGroup.addLayer(marker);
  }

  if (listings.length > 0) {
    try {
      map.fitBounds(layerGroup.getBounds().pad(0.12));
    } catch (_e) {
      map.setView([51.4416, 5.4697], 12);
    }
  }
  setTimeout(() => {
    map.invalidateSize();
  }, 200);
}

function showSelectedMatch(listing) {
  const el = document.getElementById("selected-match");
  if (!el) return;
  const wijk = dash(listing.neighborhood);
  el.innerHTML = `
    <b>${listing.title}</b><br/>
    ${listing.location}${wijk !== "-" ? ` · ${wijk}` : ""}<br/>
    EUR ${listing.rent_eur ?? "?"} | ${listing.size_m2 ?? "?"} m2<br/>
    Huur vanaf: ${dash(listing.available_from)}<br/>
    <span class="${matchTagClass(listing.match_tag || "okay")}">${listing.match_tag ?? "okay"}</span>${listing.is_new_today ? ' <span class="tag tag-new">Nieuw vandaag</span>' : ""}<br/>
    <a href="${listing.url}" target="_blank" rel="noopener noreferrer">open listing</a>
  `;
}

updateClock();
updateCountdown();
setInterval(updateClock, 1000);
setInterval(updateCountdown, 1000);
loadRun().catch((err) => {
  const headline = document.getElementById("headline-status");
  if (headline) {
    headline.textContent = `Nog steeds geen woning. Ook de website had issues: ${err}`;
  }
});
