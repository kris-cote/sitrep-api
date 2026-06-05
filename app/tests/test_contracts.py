import json
import os
import unittest
from urllib.request import urlopen, Request

BASE = os.environ.get("BASE_URL", "http://localhost:9000")

def get_json(path: str, timeout: int = 10):
    req = Request(f"{BASE}{path}", headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as r:
        data = r.read().decode("utf-8")
        return r.status, json.loads(data)

class ContractsTest(unittest.TestCase):
    def test_health(self):
        status, body = get_json("/api/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(body.get("status"), "ok")

    def test_satellite_summary(self):
        status, body = get_json("/api/v1/satellite/summary?area_id=bc")
        self.assertEqual(status, 200)
        self.assertIn("risk_label", body)
        self.assertIn("recommended_actions", body)

    def test_goes_latest_json(self):
        status, body = get_json("/api/v1/satellite/goes/latest.json?sector=pnw")
        self.assertEqual(status, 200)
        self.assertIn("sector", body)
        self.assertIn("status", body)
        self.assertIn("image_url", body)

if __name__ == "__main__":
    unittest.main()
