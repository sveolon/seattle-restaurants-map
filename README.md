# Seattle Restaurants Map

Restaurants from Seattle Times lists, on a map. Each pin links to Google Maps, to the Seattle Times
article, and to a details panel on the same page.

Static site: `index.html` + `restaurants.js` (generated). Leaflet from cdnjs, OpenStreetMap tiles, no build step.

## Adding restaurants

1. Drop Seattle Times pages (saved HTML) or PDFs in `inbox/`. It is gitignored and never published.
   Many articles are subscriber-only: save them from your own logged-in browser (File > Save Page As, or
   Print > Save as PDF). Claude never fetches seattletimes.com itself and does not work around the paywall;
   it only reads the local copies you provide. Also include the article's URL (and list name/date) with each file,
   since a saved PDF may not carry it.
2. Ask Claude to extract them. Records are added to `data/restaurants.json`: name, address, neighborhood,
   cuisine, price, a short description **in our own words**, and the source (list title, article URL, date).
   A restaurant in several lists stays one record with several sources.
3. Place them and rebuild the map's data file:

       python3 tools/geocode.py run --contact you@example.com --emit restaurants.js

   Only records without coordinates are looked up (Nominatim, 1 request/s, answers cached in
   `data/geocode_cache.json`). Anything not matched to its house number goes to `data/review.csv` and stays
   off the map. Fix it by hand: set `lat`, `lng` and `"geo": {"confidence": "high", "source": "manual"}`
   in `data/restaurants.json`; hand-placed rows are never overwritten.
4. Open `index.html` to check (or `python3 -m http.server`, then http://localhost:8000).

`python3 tools/geocode.py emit` rebuilds `restaurants.js` offline.

## Record format (`data/restaurants.json`)

```json
{
  "id": "canlis-queen-anne",
  "name": "Canlis",
  "rank": 25,
  "address": "2576 Aurora Ave N, Seattle, WA",
  "neighborhood": "Queen Anne",
  "cuisine": "Pacific Northwest",
  "price": "$$$$",
  "description": "One or two sentences in our own words.",
  "sources": [{ "list": "Best restaurants 2026", "title": "Article title", "url": "https://www.seattletimes.com/...", "date": "2026-01-15" }],
  "lat": 47.6459, "lng": -122.3466,
  "geo": { "confidence": "high", "source": "nominatim" }
}
```

## Tests (offline)

    python3 tools/test_geocode.py

## Credits and copyright

The site shows only restaurant facts, our own short descriptions, and links to the Seattle Times articles.
It never reproduces their article text, and the source pages/PDFs stay out of the repo.
The map is unofficial. Restaurant lists and articles belong to The Seattle Times.
