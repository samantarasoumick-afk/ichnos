"""
Tableau doesn't fit the SCANNERS contract at all: there's no
schema/table structure to introspect, and the useful signal isn't
"what tables exist" but "which workbooks read from which already-
cataloged tables" - i.e. lineage, not a new dataset inventory in the
usual sense. So this connector is deliberately *not* registered in
app/connectors/registry.py; it's reached through its own dedicated
endpoint (POST /api/sources/connect/tableau), the same "dedicated
endpoint" pattern used for dbt artifact uploads.

Two Tableau APIs are involved:

1. REST API `auth/signin` - exchanges a Personal Access Token (the
   modern, non-expiring-until-revoked credential Tableau recommends
   over username/password) for a short-lived session token scoped to
   one site.
2. Metadata API (GraphQL, at /api/metadata/graphql) - the only Tableau
   API that exposes a workbook's *upstream tables* directly, which is
   exactly the lineage signal we want. The REST API alone has no
   equivalent query.
"""

import requests


# Tableau REST API version - not tied to a specific server version;
# Tableau Server/Cloud are backward compatible with older REST API
# versions, and this one is recent enough to support PAT-based sign-in
# on any currently-supported release.
API_VERSION = "3.21"

REQUEST_TIMEOUT_SECONDS = 30


class TableauConnectionError(Exception):
    """
    Raised for anything that keeps us from getting a usable list of
    workbooks back: an unreachable server, a rejected credential, or a
    GraphQL-level error. Callers (the API endpoint) turn this into a
    400 with the message intact, rather than a raw 500 - a wrong PAT
    or a typo'd server URL is a user mistake, not a server bug.
    """


def _sign_in(server_url: str, site_content_url: str, token_name: str, token_value: str):
    """
    Returns (auth_token, site_id). site_content_url is the short name
    in a site's URL (e.g. the "acme" in .../site/acme/...) - an empty
    string means the server's Default site.
    """

    url = f"{server_url}/api/{API_VERSION}/auth/signin"

    body = {
        "credentials": {
            "personalAccessTokenName": token_name,
            "personalAccessTokenSecret": token_value,
            "site": {"contentUrl": site_content_url or ""},
        }
    }

    try:
        response = requests.post(
            url,
            json=body,
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise TableauConnectionError(
            f"Unable to reach Tableau server at {server_url}: {exc}"
        )

    if response.status_code != 200:
        raise TableauConnectionError(
            f"Tableau sign-in failed ({response.status_code}): "
            f"{response.text[:300]}"
        )

    try:
        credentials = response.json()["credentials"]
        return credentials["token"], credentials["site"]["id"]
    except (KeyError, ValueError) as exc:
        raise TableauConnectionError(
            f"Unexpected response from Tableau sign-in: {exc}"
        )


def _sign_out(server_url: str, auth_token: str):
    """
    Best-effort - releases the session token server-side. A failure
    here shouldn't fail the whole connect/scan, since we already have
    what we came for by the time this runs.
    """

    try:
        requests.post(
            f"{server_url}/api/{API_VERSION}/auth/signout",
            headers={"X-Tableau-Auth": auth_token},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        pass


_WORKBOOKS_QUERY = """
query MetadataPlatformWorkbookLineage {
  workbooks {
    luid
    name
    projectName
    upstreamTables {
      name
      schema
    }
  }
}
"""


def fetch_workbooks_with_upstream_tables(
    server_url: str,
    site_content_url: str,
    token_name: str,
    token_value: str,
) -> list[dict]:
    """
    Signs in, runs the Metadata API query, signs out, and returns a
    plain list of {"luid", "name", "project_name", "upstream_tables":
    [{"name", "schema"}, ...]} - already unwrapped from GraphQL's
    response envelope so callers (tableau_ingestion_service) don't
    need to know anything about GraphQL.
    """

    server_url = (server_url or "").rstrip("/")

    if not server_url:
        raise TableauConnectionError("A Tableau server URL is required.")

    auth_token, _site_id = _sign_in(
        server_url, site_content_url, token_name, token_value
    )

    try:

        try:
            response = requests.post(
                f"{server_url}/api/metadata/graphql",
                json={"query": _WORKBOOKS_QUERY},
                headers={
                    "X-Tableau-Auth": auth_token,
                    "Accept": "application/json",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise TableauConnectionError(
                f"Unable to reach Tableau Metadata API: {exc}"
            )

        if response.status_code != 200:
            raise TableauConnectionError(
                f"Tableau Metadata API request failed ({response.status_code}): "
                f"{response.text[:300]}"
            )

        payload = response.json()

        if payload.get("errors"):
            raise TableauConnectionError(
                f"Tableau Metadata API returned errors: {payload['errors']}"
            )

        raw_workbooks = ((payload.get("data") or {}).get("workbooks")) or []

        workbooks = []

        for wb in raw_workbooks:

            upstream_tables = [
                {"name": t.get("name"), "schema": t.get("schema")}
                for t in (wb.get("upstreamTables") or [])
                if t.get("name")
            ]

            workbooks.append({
                "luid": wb.get("luid"),
                "name": wb.get("name"),
                "project_name": wb.get("projectName"),
                "upstream_tables": upstream_tables,
            })

        return workbooks

    finally:
        _sign_out(server_url, auth_token)
