#!/usr/bin/env python3
"""Offline tests; never touch the network."""
import os
import sys
import unittest
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geocode as g


class Helpers(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(g.slugify("Canlis", "Queen Anne"), "canlis-queen-anne")
        self.assertEqual(g.slugify("Café Juanita!"), "caf-juanita")

    def test_maps_url_carries_name_and_address(self):
        r = {"name": "Canlis", "address": "2576 Aurora Ave N"}
        q = parse_qs(urlparse(g.maps_url(r)).query)["query"][0]
        self.assertEqual(q, "Canlis 2576 Aurora Ave N")
        self.assertIn("destination=Canlis", g.directions_url(r))

    def test_query_adds_city_only_when_missing(self):
        self.assertEqual(g.query_for("2576 Aurora Ave N"), "2576 Aurora Ave N, Seattle, WA")
        self.assertEqual(g.query_for("1 Main St, Bellevue, WA"), "1 Main St, Bellevue, WA")

    def test_classify(self):
        hit = {"lat": "47.6459", "lon": "-122.3466", "address": {"house_number": "2576"}}
        self.assertEqual(g.classify(hit, "2576 Aurora Ave N")[2], "high")
        self.assertEqual(g.classify(hit, "2600 Aurora Ave N")[2], "low")
        self.assertIsNone(g.classify({"lat": "45.5", "lon": "-122.6", "address": {}}, "1 Main St"))  # Portland
        self.assertIsNone(g.classify(None, "x"))

    def test_merge_unions_sources_and_keeps_hand_edits(self):
        old = {"name": "Canlis", "description": "mine", "sources": [{"url": "https://a"}]}
        new = {"name": "Canlis", "description": "theirs", "cuisine": "Pacific NW",
               "sources": [{"url": "https://a"}, {"url": "https://b"}]}
        m = g.merge(old, new)
        self.assertEqual(m["description"], "mine")
        self.assertEqual(m["cuisine"], "Pacific NW")
        self.assertEqual([s["url"] for s in m["sources"]], ["https://a", "https://b"])


if __name__ == "__main__":
    unittest.main()
