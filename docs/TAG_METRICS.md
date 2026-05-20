# Match tags: meh → super nice

Tags are based on the **score** from `score_rental()` in `src/filters.py`:

| Tag | Minimum score |
|-----|----------------|
| **super nice** | 50 |
| **nice** | 30 |
| **okay** | 12 |
| **meh** | below 12 |

## What the score measures

| Factor | Points | How to judge |
|--------|--------|----------------|
| **Strijp** | +25 | Title/location contains “strijp” (incl. Strijp-S) |
| **Preferred wijk** | +20 | centrum, bergen, vonderkwartier, engelsbergen, schrijversbuurt |
| **Rent within budget** | +15 | `rent_eur` ≤ your `MAX_RENT` in `.env` |
| **Size (m²)** | +5 to +20 | At `MIN_SIZE`: +5; +8 m²: +10; +15 m²: +15; +25 m²: +20 |
| **Outdoor space** | +15 | balcony/garden/terrace mentioned (NL or EN keywords) |
| **Noord Eindhoven** | −40 | “noord” in title/location (hard-excluded from shortlist anyway) |

## Suggested personal weights (optional future tweaks)

Use these when you manually override a tag:

1. **Location** — Strijp / centrum / walkability to work
2. **Rent vs budget** — headroom under 4× income rule
3. **Outdoor** — balcony or garden (your +15 already)
5. **Availability date** — fits your July 26 move-out timeline
6. **Contract** — indefinite vs temporary (temporary is filtered out)
7. **Energy label / building year** — running costs
8. **Source quality** — direct landlord (Vesteda, VB&T, Rotsvast, NMG) vs aggregator
9. **Response odds** — how fast listings disappear on that platform
10. **Commute** — bike time to daily destinations

Hard filters (not scored, listing dropped): above max rent, too small, student-only, newcomer-only schemes, inactive/archived text, outside Eindhoven, missing rent or m².
