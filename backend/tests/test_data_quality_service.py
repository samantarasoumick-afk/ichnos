import unittest

from app.services.data_quality_service import DataQualityService


class DataQualityServiceTests(unittest.TestCase):

    def test_empty_table_reports_zero_not_random(self):

        result = DataQualityService.profile({
            "columns": [("id", "integer", "NO")],
            "row_count": 0,
            "column_stats": {},
            "column_samples": {},
        })

        self.assertEqual(result["completeness"], 0.0)
        self.assertEqual(result["uniqueness"], 0.0)
        self.assertEqual(result["overall_score"], 0.0)

    def test_completeness_and_uniqueness_from_real_counts(self):

        # 10 rows, "id" column fully populated and fully unique,
        # "nickname" column half-null and low cardinality among the
        # non-null values.
        dataset_info = {
            "columns": [
                ("id", "integer", "NO"),
                ("nickname", "text", "YES"),
            ],
            "row_count": 10,
            "column_stats": {
                "id": {"non_null": 10, "distinct": 10},
                "nickname": {"non_null": 5, "distinct": 2},
            },
            "column_samples": {
                "id": [str(i) for i in range(10)],
                "nickname": ["Al", "Al", "Bo", "Bo", "Bo"],
            },
        }

        result = DataQualityService.profile(dataset_info)

        # completeness = avg(10/10, 5/10) = avg(1.0, 0.5) = 0.75 -> 75.0
        self.assertEqual(result["completeness"], 75.0)

        # uniqueness = avg(10/10, 2/5) = avg(1.0, 0.4) = 0.70 -> 70.0
        self.assertEqual(result["uniqueness"], 70.0)

    def test_validity_checks_email_column_against_pattern(self):

        dataset_info = {
            "columns": [("email", "text", "YES")],
            "row_count": 4,
            "column_stats": {"email": {"non_null": 4, "distinct": 4}},
            "column_samples": {
                "email": ["a@b.com", "c@d.com", "not-an-email", "e@f.com"],
            },
        }

        result = DataQualityService.profile(dataset_info)

        # 3 of 4 sampled values match the email pattern -> 75.0
        self.assertEqual(result["validity"], 75.0)

    def test_consistency_checks_numeric_type_columns(self):

        dataset_info = {
            "columns": [("age", "integer", "YES")],
            "row_count": 4,
            "column_stats": {"age": {"non_null": 4, "distinct": 3}},
            "column_samples": {
                "age": ["25", "30", "not-a-number", "40"],
            },
        }

        result = DataQualityService.profile(dataset_info)

        # 3 of 4 sampled values parse as numbers -> 75.0
        self.assertEqual(result["consistency"], 75.0)

    def test_columns_with_no_checkable_pattern_dont_hurt_validity(self):

        dataset_info = {
            "columns": [("notes", "text", "YES")],
            "row_count": 2,
            "column_stats": {"notes": {"non_null": 2, "distinct": 2}},
            "column_samples": {"notes": ["hello", "world"]},
        }

        result = DataQualityService.profile(dataset_info)

        self.assertEqual(result["validity"], 100.0)
        self.assertEqual(result["consistency"], 100.0)

    def test_is_deterministic_not_random(self):

        dataset_info = {
            "columns": [("id", "integer", "NO")],
            "row_count": 5,
            "column_stats": {"id": {"non_null": 5, "distinct": 5}},
            "column_samples": {"id": ["1", "2", "3", "4", "5"]},
        }

        first = DataQualityService.profile(dataset_info)
        second = DataQualityService.profile(dataset_info)

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
