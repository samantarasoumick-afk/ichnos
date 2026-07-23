"""
Unit tests for app/connectors/tableau_connector.py against a mocked
`requests` module - there's no live Tableau server in this
environment. Covers the sign-in -> GraphQL query -> sign-out sequence,
error surfacing for a rejected sign-in, an unreachable server, and a
GraphQL-level error payload (which Tableau returns with a 200 status,
so it needs its own check separate from the HTTP status code).
"""

import unittest
from unittest.mock import MagicMock, patch

import requests

from app.connectors.tableau_connector import (
    TableauConnectionError,
    fetch_workbooks_with_upstream_tables,
)


def _response(status_code=200, json_body=None, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body or {}
    response.text = text
    return response


SIGNIN_OK = _response(
    status_code=200,
    json_body={"credentials": {"token": "tok-123", "site": {"id": "site-1"}}},
)


class FetchWorkbooksTests(unittest.TestCase):

    @patch("app.connectors.tableau_connector.requests.post")
    def test_happy_path_returns_workbooks_with_upstream_tables(self, mock_post):
        graphql_ok = _response(
            status_code=200,
            json_body={
                "data": {
                    "workbooks": [
                        {
                            "luid": "wb-1",
                            "name": "Sales Overview",
                            "projectName": "Finance",
                            "upstreamTables": [
                                {"name": "orders", "schema": "public"},
                                {"name": "customers", "schema": "public"},
                            ],
                        },
                        {
                            "luid": "wb-2",
                            "name": "No Lineage Report",
                            "projectName": None,
                            "upstreamTables": [],
                        },
                    ]
                }
            },
        )
        signout_ok = _response(status_code=200)

        mock_post.side_effect = [SIGNIN_OK, graphql_ok, signout_ok]

        workbooks = fetch_workbooks_with_upstream_tables(
            server_url="https://tableau.example.com",
            site_content_url="acme",
            token_name="my-pat",
            token_value="secret-value",
        )

        self.assertEqual(len(workbooks), 2)
        self.assertEqual(workbooks[0]["name"], "Sales Overview")
        self.assertEqual(workbooks[0]["project_name"], "Finance")
        self.assertEqual(
            workbooks[0]["upstream_tables"],
            [
                {"name": "orders", "schema": "public"},
                {"name": "customers", "schema": "public"},
            ],
        )
        self.assertEqual(workbooks[1]["upstream_tables"], [])

        # Sign-in, GraphQL query, sign-out - in that order.
        self.assertEqual(mock_post.call_count, 3)
        signin_call, graphql_call, signout_call = mock_post.call_args_list
        self.assertIn("/auth/signin", signin_call.args[0])
        self.assertIn("/api/metadata/graphql", graphql_call.args[0])
        self.assertIn("/auth/signout", signout_call.args[0])

    @patch("app.connectors.tableau_connector.requests.post")
    def test_trailing_slash_on_server_url_is_stripped(self, mock_post):
        graphql_ok = _response(status_code=200, json_body={"data": {"workbooks": []}})
        mock_post.side_effect = [SIGNIN_OK, graphql_ok, _response(200)]

        fetch_workbooks_with_upstream_tables(
            server_url="https://tableau.example.com/",
            site_content_url="",
            token_name="my-pat",
            token_value="secret-value",
        )

        signin_call = mock_post.call_args_list[0]
        self.assertEqual(
            signin_call.args[0],
            "https://tableau.example.com/api/3.21/auth/signin",
        )

    @patch("app.connectors.tableau_connector.requests.post")
    def test_rejected_signin_raises_clear_error(self, mock_post):
        mock_post.return_value = _response(
            status_code=401, text="Invalid personal access token"
        )

        with self.assertRaises(TableauConnectionError) as ctx:
            fetch_workbooks_with_upstream_tables(
                server_url="https://tableau.example.com",
                site_content_url="",
                token_name="bad-name",
                token_value="bad-secret",
            )

        self.assertIn("sign-in failed", str(ctx.exception))

    @patch("app.connectors.tableau_connector.requests.post")
    def test_unreachable_server_raises_clear_error(self, mock_post):
        mock_post.side_effect = requests.ConnectionError("name resolution failed")

        with self.assertRaises(TableauConnectionError) as ctx:
            fetch_workbooks_with_upstream_tables(
                server_url="https://unreachable.example.com",
                site_content_url="",
                token_name="my-pat",
                token_value="secret-value",
            )

        self.assertIn("Unable to reach", str(ctx.exception))

    @patch("app.connectors.tableau_connector.requests.post")
    def test_graphql_error_payload_raises_even_with_200_status(self, mock_post):
        # Tableau's Metadata API returns HTTP 200 with an "errors" key
        # for a bad query, rather than a non-200 status.
        graphql_error = _response(
            status_code=200,
            json_body={"errors": [{"message": "Cannot query field upstreamTables"}]},
        )
        mock_post.side_effect = [SIGNIN_OK, graphql_error, _response(200)]

        with self.assertRaises(TableauConnectionError) as ctx:
            fetch_workbooks_with_upstream_tables(
                server_url="https://tableau.example.com",
                site_content_url="",
                token_name="my-pat",
                token_value="secret-value",
            )

        self.assertIn("errors", str(ctx.exception))

    @patch("app.connectors.tableau_connector.requests.post")
    def test_blank_server_url_rejected_before_any_request(self, mock_post):
        with self.assertRaises(TableauConnectionError):
            fetch_workbooks_with_upstream_tables(
                server_url="",
                site_content_url="",
                token_name="my-pat",
                token_value="secret-value",
            )

        mock_post.assert_not_called()

    @patch("app.connectors.tableau_connector.requests.post")
    def test_signout_is_attempted_even_if_graphql_call_fails(self, mock_post):
        graphql_failure = _response(status_code=500, text="internal error")
        mock_post.side_effect = [SIGNIN_OK, graphql_failure, _response(200)]

        with self.assertRaises(TableauConnectionError):
            fetch_workbooks_with_upstream_tables(
                server_url="https://tableau.example.com",
                site_content_url="",
                token_name="my-pat",
                token_value="secret-value",
            )

        # signin + graphql + signout, even though graphql raised.
        self.assertEqual(mock_post.call_count, 3)
        self.assertIn("/auth/signout", mock_post.call_args_list[2].args[0])


if __name__ == "__main__":
    unittest.main()
