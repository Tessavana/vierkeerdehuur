function updateClock() {
  const el = document.getElementById("clock");
  if (el) el.textContent = new Date().toLocaleTimeString();
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
  if (tag === "Twijfelgeval") return "tag tag-twijfel";
  if (tag === "Instant reageren") return "tag tag-instant";
  return "tag tag-kans";
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
  const reason = excluded
    ? `<span class="muted">${l.reason ?? "excluded"}</span>`
    : `<span class="${matchTagClass(l.match_tag || "Kansrijk")}">${l.match_tag ?? "Kansrijk"}</span>`;
  return `
    <div class="listing-row">
      <div><b>${l.title}</b><div class="muted">${l.location}</div></div>
      <div>${wijk}</div>
      <div>EUR ${l.rent_eur ?? "?"}</div>
      <div>${l.size_m2 ?? "?"} m2</div>
      <div>${avail}</div>
      <div>${reason}<br/><a href="${l.url}" target="_blank" rel="noopener noreferrer">open</a></div>
    </div>
  `;
}

async function renderMap(listings) {
  const mapEl = document.getElementById("map");
  if (!mapEl) return;
  const map = L.map("map").setView([51.4416, 5.4697], 12);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    subdomains: "abcd",
    maxZoom: 20,
  }).addTo(map);
  const shown = listings.slice(0, 20);
  const usedCoords = new Map();
  for (const listing of shown) {
    const hint = listing.title.split(",")[0].trim();
    const q = encodeURIComponent(`${hint}, Eindhoven, Netherlands`);
    try {
      const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${q}`);
      const rows = await res.json();
      if (!rows.length) continue;
      const lat = Number(rows[0].lat);
      const lon = Number(rows[0].lon);
      const key = `${lat.toFixed(4)},${lon.toFixed(4)}`;
      const offset = usedCoords.get(key) || 0;
      usedCoords.set(key, offset + 1);
      const latAdj = lat + offset * 0.00035;
      const lonAdj = lon + offset * 0.00035;

      const marker = L.circleMarker([latAdj, lonAdj], {
        radius: 8,
        color: "#000",
        weight: 2,
        fillColor: "#000",
        fillOpacity: 1,
      }).addTo(map);
      const wijk = dash(listing.neighborhood);
      marker.bindPopup(
        `<b>${listing.title}</b><br/>${wijk !== "-" ? `${wijk} · ` : ""}EUR ${listing.rent_eur ?? "?"} | ${listing.size_m2 ?? "?"} m²<br/>${listing.available_from ? `Vanaf ${listing.available_from}<br/>` : ""}`
      );
      marker.on("click", () => {
        showSelectedMatch(listing);
      });
    } catch (_err) {
      // ignore map geocoding failures
    }
  }
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
    <span class="${matchTagClass(listing.match_tag || "Kansrijk")}">${listing.match_tag ?? "Kansrijk"}</span><br/>
    <a href="${listing.url}" target="_blank" rel="noopener noreferrer">open listing</a>
  `;
}

updateClock();
setInterval(updateClock, 1000);
loadRun().catch((err) => {
  const headline = document.getElementById("headline-status");
  if (headline) {
    headline.textContent = `Nog steeds geen woning. Ook de website had issues: ${err}`;
  }
});
