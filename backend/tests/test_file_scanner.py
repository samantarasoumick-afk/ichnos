"""
Unit tests for app/connectors/file_scanner.py: type inference,
nullable detection, sampling, and the error cases a bad upload should
surface as a clear ValueError (which the API layer turns into a 400).
"""

import unittest

from app.connectors.file_scanner import parse_csv_upload


def _csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


class ParseCsvUploadTests(unittest.TestCase):

    def test_infers_integer_column(self):
        csv_text = "id,name\n1,Alice\n2,Bob\n3,Carol\n"
        result = parse_csv_upload(_csv_bytes(csv_text), table_name="people")

        dataset = result["datasets"][0]
        columns_by_name = {name: (data_type, nullable) for name, data_type, nullable in dataset["columns"]}

        self.assertEqual(columns_by_name["id"], ("integer", "NO"))
        self.assertEqual(columns_by_name["name"], ("varchar", "NO"))
        self.assertEqual(dataset["row_count"], 3)

    def test_infers_numeric_column(self):
        csv_text = "price\n19.99\n5.50\n100\n"
        result = parse_csv_upload(_csv_bytes(csv_text), table_name="prices")
        columns_by_name = {name: data_type for name, data_type, _n in result["datasets"][0]["columns"]}
        self.assertEqual(columns_by_name["price"], "numeric")

    def test_mixed_types_fall_back_to_varchar(self):
        csv_text = "value\n1\nabc\n3\n"
        result = parse_csv_upload(_csv_bytes(csv_text), table_name="mixed")
        columns_by_name = {name: data_type for name, data_type, _n in result["datasets"][0]["columns"]}
        self.assertEqual(columns_by_name["value"], "varchar")

    def test_detects_nullable_column(self):
        csv_text = "email\na@b.com\n\nc@d.com\n"
        result = parse_csv_upload(_csv_bytes(csv_text), table_name="contacts")
        columns_by_name = {name: nullable for name, _dt, nullable in result["datasets"][0]["columns"]}
        self.assertEqual(columns_by_name["email"], "YES")

    def test_column_samples_exclude_empty_values(self):
        csv_text = "email\na@b.com\n\nc@d.com\n"
        result = parse_csv_upload(_csv_bytes(csv_text), table_name="contacts")
        samples = result["datasets"][0]["column_samples"]["email"]
        self.assertEqual(samples, ["a@b.com", "c@d.com"])

    def test_column_stats_count_non_null_and_distinct(self):
        csv_text = "status\nactive\nactive\ninactive\n\n"
        result = parse_csv_upload(_csv_bytes(csv_text), table_name="statuses")
        stats = result["datasets"][0]["column_stats"]["status"]
        self.assertEqual(stats["non_null"], 3)
        self.assertEqual(stats["distinct"], 2)

    def test_schema_and_table_name_are_used_as_given(self):
        csv_text = "id\n1\n"
        result = parse_csv_upload(_csv_bytes(csv_text), table_name="widgets", schema_name="my_uploads")
        dataset = result["datasets"][0]
        self.assertEqual(dataset["schema_name"], "my_uploads")
        self.assertEqual(dataset["table_name"], "widgets")

    def test_no_foreign_keys_from_a_csv(self):
        csv_text = "id\n1\n"
        result = parse_csv_upload(_csv_bytes(csv_text), table_name="widgets")
        self.assertEqual(result["foreign_keys"], [])

    def test_empty_file_raises(self):
        with self.assertRaises(ValueError):
            parse_csv_upload(b"", table_name="empty")

    def test_header_only_no_data_rows_raises(self):
        with self.assertRaises(ValueError):
            parse_csv_upload(_csv_bytes("id,name\n"), table_name="empty")

    def test_duplicate_header_raises(self):
        with self.assertRaises(ValueError):
            parse_csv_upload(_csv_bytes("id,id\n1,2\n"), table_name="dupes")

    def test_undecodable_bytes_raise(self):
        with self.assertRaises(ValueError):
            parse_csv_upload(b"\xff\xfe\x00\x01not-utf8", table_name="bad")


if __name__ == "__main__":
    unittest.main()
