/** Geocoding via PDOK + cache. Eindhoven-only coords. */
const EINDHOVEN_CENTER = { lat: 51.4416, lon: 5.4697 };
const EINDHOVEN_BBOX = { minLat: 51.39, maxLat: 51.52, minLon: 5.39, maxLon: 5.58 };
const PDOK_FREE = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free";
const CLIENT_CACHE_KEY = "housing_geocode_client_v1";

const POSTCODE_WIJK = {
  5611: "Centrum",
  5612: "Woensel",
  5613: "Strijp",
  5614: "Strijp",
  5615: "Strijp",
  5616: "Gestel",
  5617: "Strijp-S",
  5618: "Gestel",
  5629: "Meerhoven",
  5630: "Meerhoven",
  5621: "Woensel",
  5622: "Woensel",
  5623: "Woensel",
  5625: "Woensel",
  5626: "Woensel",
  5627: "Woensel",
  5628: "Woensel",
  5631: "Woensel",
  5632: "Woensel",
  5633: "Woensel",
  5641: "Tongelre",
  5642: "Tongelre",
  5643: "Tongelre",
  5644: "Tongelre",
  5645: "Tongelre",
  5646: "Tongelre",
  5651: "Woensel",
  5652: "Woensel",
  5653: "Woensel",
  5654: "Woensel",
  5655: "Woensel",
  5656: "Woensel",
  5657: "Woensel",
  5658: "Woensel",
};

function wijkFromPostcode(pc) {
  if (!pc || pc.length < 4) return "";
  const prefix = parseInt(pc.slice(0, 4), 10);
  return POSTCODE_WIJK[prefix] || "";
}

function resolveNeighborhood(l) {
  if (l.neighborhood) return l.neighborhood;
  const blob = `${l.title || ""} ${l.location || ""} ${l.notes || ""}`;
  const pc = blob.match(/\b(\d{4})\s*([A-Za-z]{2})\b/) || blob.match(/\b(\d{4})([A-Za-z]{2})\b/);
  if (pc) {
    const w = wijkFromPostcode(`${pc[1]}${pc[2].toUpperCase()}`);
    if (w) return w;
  }
  const lower = blob.toLowerCase();
  const keys = [
    ["strijp-s", "Strijp-S"],
    ["strijp-r", "Strijp-R"],
    ["blixembosch", "Blixembosch"],
    ["regentekwartier", "Centrum"],
    ["oud-strijp", "Oud-Strijp"],
    ["meerhoven", "Meerhoven"],
    ["strijp", "Strijp"],
    ["woensel", "Woensel"],
    ["tongelre", "Tongelre"],
    ["gestel", "Gestel"],
    ["stratum", "Stratum"],
    ["centrum", "Centrum"],
  ];
  for (const [k, v] of keys) {
    if (lower.includes(k)) return v;
  }
  return "Eindhoven";
}

function emptyVal() {
  return "";
}

function hashStr(s) {
  let h = 0;
  for (let i = 0; i < (s || "").length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function extractPostcode(text) {
  const m = (text || "").match(/\b(\d{4})\s*([A-Za-z]{2})\b/);
  return m ? `${m[1]}${m[2].toUpperCase()}` : null;
}

function isCityCenter(lat, lon) {
  return Math.abs(lat - EINDHOVEN_CENTER.lat) < 0.0005 && Math.abs(lon - EINDHOVEN_CENTER.lon) < 0.0005;
}

function inEindhoven(lat, lon) {
  return lat >= EINDHOVEN_BBOX.minLat && lat <= EINDHOVEN_BBOX.maxLat && lon >= EINDHOVEN_BBOX.minLon && lon <= EINDHOVEN_BBOX.maxLon;
}

function parseStreet(listing) {
  const blob = `${listing.location || ""} ${listing.title || ""} ${(listing.notes || "").slice(0, 800)}`;
  const loc = (listing.location || "").trim();
  const title = (listing.title || "").trim();
  const pc = extractPostcode(blob);

  for (const raw of [loc, title.replace(/\s+(in|te huur).*$/i, "").trim(), title]) {
    if (!raw) continue;
    const cleaned = raw.replace(/^Te huur\s+\w+\s+/i, "").replace(/\s+in Eindhoven.*$/i, "").trim();
    const m = cleaned.match(/^([A-Za-zÀ-ÿ\s.'-]+?)\s+(\d+[A-Za-z0-9\-]*(?:\s*[-/]\s*\d+[A-Za-z0-9\-]*)?)\b/);
    if (m) return { street: m[1].trim(), number: m[2].replace(/\s/g, ""), pc };
    const parts = cleaned.split(",");
    const head = parts[0].trim();
    if (head && !/\d/.test(head)) return { street: head, number: "", pc };
  }
  return { street: "", number: "", pc };
}

function coordsFromDoc(doc) {
  const c = doc.centroide_ll || "";
  const m = c.match(/POINT\(([-\d.]+)\s+([-\d.]+)\)/);
  if (!m) return null;
  const lon = parseFloat(m[1]);
  const lat = parseFloat(m[2]);
  if (!inEindhoven(lat, lon)) return null;
  const wijk = (doc.wijknaam || doc.buurtnaam || "").trim();
  const pc = (doc.postcode || "").slice(0, 4);
  return { lat, lon, wijk: wijk || POSTCODE_WIJK[pc] || "" };
}

function jitterFromUrl(url, lat, lon) {
  const h = hashStr(url || "x");
  const a = (h % 1000) / 80000;
  const b = ((h * 7) % 1000) / 80000;
  return { lat: lat + a - 0.006, lon: lon + b - 0.006 };
}

function loadClientCache() {
  try {
    return JSON.parse(localStorage.getItem(CLIENT_CACHE_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveClientCacheEntry(url, entry) {
  if (!url) return;
  const c = loadClientCache();
  c[url] = entry;
  localStorage.setItem(CLIENT_CACHE_KEY, JSON.stringify(c));
}

async function queryPdok(q, adresOnly) {
  const params = new URLSearchParams({ q, rows: "3", fq: "gemeentenaam:Eindhoven" });
  if (adresOnly) params.set("fq", "type:adres AND gemeentenaam:Eindhoven");
  const res = await fetch(`${PDOK_FREE}?${params}`);
  if (!res.ok) return null;
  const data = await res.json();
  const docs = data.response?.docs || [];
  for (const doc of docs) {
    if (adresOnly && doc.type !== "adres" && doc.type !== "postcode" && doc.type !== "weg") continue;
    const c = coordsFromDoc(doc);
    if (c) return c;
  }
  return null;
}

function buildQueries(listing) {
  const { street, number, pc } = parseStreet(listing);
  const qs = [];
  if (street && number && pc) qs.push({ q: `${street} ${number}, ${pc.slice(0, 4)} ${pc.slice(4)}, Eindhoven`, strict: true });
  if (street && pc) qs.push({ q: `${street}, ${pc.slice(0, 4)} ${pc.slice(4)}, Eindhoven`, strict: false });
  if (street) qs.push({ q: `${street}, Eindhoven`, strict: false });
  if (pc) qs.push({ q: `${pc.slice(0, 4)} ${pc.slice(4)}, Eindhoven`, strict: false });
  return qs;
}

function resolveListingCoords(listing, cache) {
  const url = listing.url || "";
  const merged = { ...(cache || {}), ...loadClientCache() };
  if (url && merged[url]?.lat != null && inEindhoven(merged[url].lat, merged[url].lon)) {
    return { lat: merged[url].lat, lon: merged[url].lon, wijk: merged[url].wijk || "" };
  }

  let lat = listing.map_lat;
  let lon = listing.map_lon;
  if (lat != null && lon != null && !isCityCenter(lat, lon) && inEindhoven(lat, lon)) {
    return { lat, lon, wijk: listing.neighborhood || "" };
  }

  return null;
}

async function geocodeListing(listing, cache) {
  const existing = resolveListingCoords(listing, cache);
  if (existing) return existing;

  const url = listing.url || "";
  for (const { q, strict } of buildQueries(listing)) {
    try {
      const hit = await queryPdok(q, strict);
      if (hit) {
        if (url) saveClientCacheEntry(url, hit);
        return hit;
      }
    } catch {
      /* next query */
    }
    await new Promise((r) => setTimeout(r, 120));
  }

  const { pc } = parseStreet(listing);
  if (pc) {
    try {
      const hit = await queryPdok(`${pc.slice(0, 4)} ${pc.slice(4)}, Eindhoven`, false);
      if (hit) {
        const j = jitterFromUrl(url, hit.lat, hit.lon);
        const out = { lat: j.lat, lon: j.lon, wijk: hit.wijk || POSTCODE_WIJK[parseInt(pc.slice(0, 4), 10)] || "" };
        if (url) saveClientCacheEntry(url, out);
        return out;
      }
    } catch {
      /* fallback below */
    }
  }

  const j = jitterFromUrl(url, EINDHOVEN_CENTER.lat, EINDHOVEN_CENTER.lon);
  return { lat: j.lat, lon: j.lon, wijk: listing.neighborhood || "" };
}

let _geoCachePromise = null;

function loadGeocodeCache() {
  if (!_geoCachePromise) {
    _geoCachePromise = fetch("./data/geocode_cache.json", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : {}))
      .catch(() => ({}));
  }
  return _geoCachePromise;
}

function attachResolvedCoords(listings, cache) {
  return listings.map((l) => {
    const c = resolveListingCoords(l, cache);
    if (c) {
      return { ...l, map_lat: c.lat, map_lon: c.lon, neighborhood: resolveNeighborhood({ ...l, neighborhood: l.neighborhood || c.wijk || "" }) };
    }
    return { ...l };
  });
}

async function attachResolvedCoordsAsync(listings, cache) {
  const out = [];
  for (const l of listings) {
    const c = resolveListingCoords(l, cache) || (await geocodeListing(l, cache));
    out.push({
      ...l,
      map_lat: c.lat,
      map_lon: c.lon,
      neighborhood: resolveNeighborhood({ ...l, neighborhood: l.neighborhood || c.wijk || "" }),
    });
  }
  return out;
}
