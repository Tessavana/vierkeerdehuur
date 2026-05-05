function updateClock() {
  const el = document.getElementById("clock");
  el.textContent = new Date().toLocaleTimeString();
}

function groupByProvider(listings) {
  const out = {};
  listings.forEach((item) => {
    if (!out[item.provider]) out[item.provider] = [];
    out[item.provider].push(item);
  });
  return out;
}

async function loadRun() {
  const res = await fetch("./data/latest_listings.json", { cache: "no-store" });
  const data = await res.json();

  const status = data.application_status || {};
  const stats = document.getElementById("status-stats");
  stats.innerHTML = `
    <li>Applications sent: <b>${status.applications_sent ?? 0}</b></li>
    <li>Viewings: <b>${status.viewings ?? 0}</b></li>
    <li>Rejections: <b>${status.rejections ?? 0}</b></li>
    <li>No response: <b>${status.no_response ?? 0}</b></li>
  `;
  document.getElementById("run-meta").textContent =
    `Laatste run: ${new Date(data.generated_at_utc).toLocaleString()} | ${
      data.listings.length
    } shortlist match(es).`;

  const rej = document.getElementById("rejected-list");
  rej.innerHTML = "";
  (status.rejected_addresses || []).forEach((addr) => {
    const li = document.createElement("li");
    li.textContent = addr;
    rej.appendChild(li);
  });

  renderProviders(data);
  await renderMap(data.listings);
}

function renderProviders(data) {
  const providersEl = document.getElementById("providers");
  providersEl.innerHTML = "";
  const suitableByProvider = groupByProvider(data.listings);
  const excludedByProvider = groupByProvider(data.excluded_listings || []);

  data.provider_results.forEach((p) => {
    const block = document.createElement("div");
    block.className = "provider-block";
    const cls = p.status === "ok" ? "status-ok" : "status-error";
    const suitable = suitableByProvider[p.provider] || [];
    const excluded = excludedByProvider[p.provider] || [];
    const sectionId = `excluded-${p.provider}`;
    block.innerHTML = `
      <div><b>${p.provider}</b> <span class="${cls}">${p.status}</span></div>
      <div class="muted">parsed=${p.parsed} | suitable=${p.suitable} | excluded=${p.excluded ?? 0}</div>
      ${p.error ? `<div class="muted">error: ${p.error}</div>` : ""}
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
      target.classList.toggle("hidden");
      btn.textContent = target.classList.contains("hidden") ? "Show excluded" : "Hide excluded";
    });
  });
}

function listingRow(l, excluded) {
  const reason = excluded ? `<span class="muted">${l.reason ?? "excluded"}</span>` : `<span>score=${l.score}</span>`;
  return `
    <div class="listing-row">
      <div><b>${l.title}</b><div class="muted">${l.location}</div></div>
      <div>EUR ${l.rent_eur ?? "?"}</div>
      <div>${l.size_m2 ?? "?"} m2</div>
      <div>${reason}<br/><a href="${l.url}" target="_blank" rel="noopener noreferrer">open</a></div>
    </div>
  `;
}

async function renderMap(listings) {
  const map = L.map("map").setView([51.4416, 5.4697], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);
  const shown = listings.slice(0, 10);
  for (const listing of shown) {
    const q = encodeURIComponent(`${listing.location}, Eindhoven, Netherlands`);
    try {
      const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${q}`);
      const rows = await res.json();
      if (!rows.length) continue;
      const lat = Number(rows[0].lat);
      const lon = Number(rows[0].lon);
      L.marker([lat, lon]).addTo(map).bindPopup(
        `<b>${listing.title}</b><br/>EUR ${listing.rent_eur ?? "?"} | ${listing.size_m2 ?? "?"} m2`
      );
    } catch (_err) {
      // ignore map geocoding failures
    }
  }
}

updateClock();
setInterval(updateClock, 1000);
loadRun().catch((err) => {
  document.getElementById("headline-status").textContent = `Nog steeds geen woning. Ook de website had issues: ${err}`;
});
