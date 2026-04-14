import unittest

from app.services.analytics_service import AnalyticsService


class AnalyticsServiceTests(unittest.TestCase):
    def test_get_overview_has_expected_shape(self) -> None:
        result = AnalyticsService().get_overview()
        self.assertIn(result.get("status"), {"ok", "degraded"})
        self.assertIn("metrics", result)
        metrics = result.get("metrics") or {}
        self.assertIn("contacts", metrics)
        self.assertIn("conversations", metrics)
        self.assertIn("messages", metrics)
        self.assertIn("posts", metrics)
        self.assertIn("pending_jobs", metrics)


if __name__ == "__main__":
    unittest.main()
