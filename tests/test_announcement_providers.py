from datetime import datetime
import unittest

from paper_trading_simulator.announcements import (
    AnnouncementFetchResult,
    CorporateAnnouncement,
    FallbackAnnouncementProvider,
    ManualUploadAnnouncementProvider,
    MockAnnouncementProvider,
    ProviderStatus,
    build_announcement_provider,
    parse_announcement_csv,
)


class FailingProvider:
    name = "Failing Provider"

    def fetch(self, days=3, limit=25):
        fetched_at = datetime(2026, 6, 8, 9, 15)
        status = ProviderStatus(self.name, False, "403 Forbidden", fetched_at, 0, "blocked")
        return AnnouncementFetchResult([], False, "403 Forbidden", fetched_at, "blocked", self.name, None, [status])


class WorkingProvider:
    name = "Working Provider"

    def fetch(self, days=3, limit=25):
        fetched_at = datetime(2026, 6, 8, 9, 16)
        announcements = [
            CorporateAnnouncement("ABC", "ABC Limited", "ABC wins order", "Large order", fetched_at, self.name)
        ]
        status = ProviderStatus(self.name, True, "OK", fetched_at, 1, "working")
        return AnnouncementFetchResult(announcements, True, "OK", fetched_at, "working", self.name, fetched_at, [status])


class AnnouncementProviderTests(unittest.TestCase):
    def test_manual_csv_parses_common_columns(self):
        csv_text = "symbol,company,headline,details,date\nABC,ABC Limited,ABC wins large order,Large order win,2026-06-08 09:20:00\n"

        announcements = parse_announcement_csv(csv_text)

        self.assertEqual(len(announcements), 1)
        self.assertEqual(announcements[0].symbol, "ABC")
        self.assertIn("large order", announcements[0].headline)

    def test_manual_provider_merges_multiple_csv_files(self):
        csv_one = "SYMBOL,COMPANY NAME,SUBJECT,DETAILS,BROADCAST DATE/TIME\nABC,ABC Limited,ABC wins order,Large order,08-Jun-2026 09:20:00\n"
        csv_two = "SYMBOL,COMPANY NAME,SUBJECT,DETAILS,BROADCAST DATE/TIME\nXYZ,XYZ Limited,XYZ receives approval,Approval received,08-Jun-2026 09:25:00\n"
        provider = ManualUploadAnnouncementProvider((csv_one, csv_two))

        result = provider.fetch(days=2, limit=10)

        self.assertTrue(result.ok)
        self.assertEqual(len(result.announcements), 2)
        self.assertEqual({item.symbol for item in result.announcements}, {"ABC", "XYZ"})

    def test_fallback_uses_next_provider_after_failure(self):
        provider = FallbackAnnouncementProvider([FailingProvider(), WorkingProvider()])

        result = provider.fetch(days=1, limit=10)

        self.assertTrue(result.ok)
        self.assertEqual(result.source_used, "Working Provider")
        self.assertEqual(len(result.provider_statuses), 2)
        self.assertEqual(result.provider_statuses[0].provider, "Failing Provider")

    def test_mock_mode_is_available(self):
        provider = build_announcement_provider(mode="mock")

        result = provider.fetch(days=1, limit=10)

        self.assertTrue(result.ok)
        self.assertEqual(result.source_used, MockAnnouncementProvider.name)
        self.assertGreaterEqual(len(result.announcements), 1)


if __name__ == "__main__":
    unittest.main()
