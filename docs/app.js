async function loadRun() {
  const res = await fetch("./data/latest_listings.json", { cache: "no-store" });
  const data = await res.json();

  const meta = document.getElementById("meta");
  meta.textContent = `Updated ${new Date(data.generated_at_utc).toLocaleString()} | City: ${data.city} | Max rent: EUR ${data.max_rent}`;

  const providersEl = document.getElementById("providers");
  providersEl.innerHTML = "";
  data.provider_results.forEach((p) => {
    const item = document.createElement("div");
    item.className = "provider-item";
    const cls = p.status === "ok" ? "ok" : "err";
    item.innerHTML = `
      <div><b>${p.provider}</b> <span class="${cls}">${p.status}</span></div>
      <div class="muted">parsed=${p.parsed} suitable=${p.suitable}</div>
      ${p.error ? `<div class="muted">error: ${p.error}</div>` : ""}
    `;
    providersEl.appendChild(item);
  });

  const listingsEl = document.getElementById("listings");
  listingsEl.innerHTML = "";
  data.listings.slice(0, 30).forEach((l) => {
    const item = document.createElement("div");
    item.className = "listing-item";
    item.innerHTML = `
      <div><b>${l.title}</b></div>
      <div class="muted">${l.source} | ${l.location}</div>
      <div class="muted">rent=${l.rent_eur ?? "?"} | size=${l.size_m2 ?? "?"}m2 | score=${l.score}</div>
      <a href="${l.url}" target="_blank" rel="noopener noreferrer">Open listing</a>
    `;
    listingsEl.appendChild(item);
  });
}

loadRun().catch((err) => {
  const meta = document.getElementById("meta");
  meta.textContent = `Could not load listings: ${err}`;
});
