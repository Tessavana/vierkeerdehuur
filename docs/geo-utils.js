/** Client-side coords: geocode cache + postcode centroids (Eindhoven). */
const EINDHOVEN_CENTER = { lat: 51.4416, lon: 5.4697 };

const POSTCODE_CENTER = {
  5611: [51.441, 5.479],
  5612: [51.438, 5.482],
  5613: [51.448, 5.453],
  5614: [51.451, 5.441],
  5615: [51.455, 5.435],
  5616: [51.422, 5.497],
  5621: [51.452, 5.468],
  5622: [51.456, 5.472],
  5623: [51.459, 5.476],
  5625: [51.463, 5.481],
  5626: [51.467, 5.485],
  5627: [51.471, 5.489],
  5628: [51.475, 5.493],
  5631: [51.479, 5.497],
  5632: [51.483, 5.501],
  5633: [51.487, 5.505],
  5641: [51.432, 5.512],
  5642: [51.428, 5.516],
  5643: [51.424, 5.520],
  5644: [51.420, 5.524],
  5645: [51.416, 5.528],
  5646: [51.412, 5.532],
  5651: [51.448, 5.432],
  5652: [51.444, 5.428],
  5653: [51.440, 5.424],
  5654: [51.436, 5.420],
  5655: [51.432, 5.416],
  5656: [51.428, 5.412],
  5657: [51.424, 5.408],
  5658: [51.420, 5.404],
};

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

function jitterFromUrl(url, lat, lon) {
  const h = hashStr(url || "x");
  const a = (h % 1000) / 80000;
  const b = ((h * 7) % 1000) / 80000;
  return { lat: lat + a - 0.006, lon: lon + b - 0.006 };
}

function resolveListingCoords(listing, cache) {
  const url = listing.url || "";
  if (cache && url && cache[url] && cache[url].lat != null) {
    return { lat: cache[url].lat, lon: cache[url].lon, wijk: cache[url].wijk || "" };
  }

  let lat = listing.map_lat;
  let lon = listing.map_lon;
  if (lat != null && lon != null && !isCityCenter(lat, lon)) {
    return { lat, lon, wijk: listing.neighborhood || "" };
  }

  const blob = `${listing.title || ""} ${listing.location || ""} ${listing.notes || ""}`;
  const pc = extractPostcode(blob);
  if (pc) {
    const prefix = parseInt(pc.slice(0, 4), 10);
    const center = POSTCODE_CENTER[prefix];
    if (center) {
      const j = jitterFromUrl(url || blob, center[0], center[1]);
      return { lat: j.lat, lon: j.lon, wijk: listing.neighborhood || "" };
    }
  }

  if (lat != null && lon != null) {
    const j = jitterFromUrl(url, lat, lon);
    return { lat: j.lat, lon: j.lon, wijk: listing.neighborhood || "" };
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
    return { ...l, map_lat: c.lat, map_lon: c.lon, neighborhood: l.neighborhood || c.wijk || l.neighborhood };
  });
}
