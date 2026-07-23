"use client";

import { useState } from "react";

import api from "../services/api";

export default function TableauConnectForm() {

  const [name, setName] = useState("");

  const [serverUrl, setServerUrl] = useState("");

  const [siteContentUrl, setSiteContentUrl] = useState("");

  const [tokenName, setTokenName] = useState("");

  const [tokenValue, setTokenValue] = useState("");

  const [loading, setLoading] = useState(false);

  async function connectTableau() {

    try {

      setLoading(true);

      const response = await api.post("/api/sources/connect/tableau", {
        name,
        server_url: serverUrl,
        site_content_url: siteContentUrl,
        token_name: tokenName,
        token_value: tokenValue,
      });

      alert(
        `Tableau site connected: ${response.data.workbooks_discovered} workbook(s), ` +
          `${response.data.lineage_edges_created} lineage edge(s)`
      );

      window.location.reload();

    } catch (error: unknown) {

      console.error(error);

      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;

      alert(detail || "Failed to connect Tableau site");

    } finally {

      setLoading(false);
    }
  }

  return (

    <div>

      <p className="text-sm text-gray-500 mb-4">
        Connects to a Tableau Server or Cloud site using a Personal
        Access Token and discovers every workbook&apos;s upstream
        tables via Tableau&apos;s Metadata API. Each workbook becomes
        a lineage node linked to any tables already cataloged from
        another source - no table inventory of its own, just where the
        data behind each workbook comes from.
      </p>

      <div className="grid grid-cols-2 gap-4">

        <input
          placeholder="Source Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="border p-3 rounded"
        />

        <input
          placeholder="Server URL (e.g. https://10ax.online.tableau.com)"
          value={serverUrl}
          onChange={(e) => setServerUrl(e.target.value)}
          className="border p-3 rounded"
        />

        <input
          placeholder="Site Content URL (optional - blank for Default site)"
          value={siteContentUrl}
          onChange={(e) => setSiteContentUrl(e.target.value)}
          className="border p-3 rounded"
        />

        <div />

        <input
          placeholder="Personal Access Token Name"
          value={tokenName}
          onChange={(e) => setTokenName(e.target.value)}
          className="border p-3 rounded"
        />

        <input
          type="password"
          placeholder="Personal Access Token Secret"
          value={tokenValue}
          onChange={(e) => setTokenValue(e.target.value)}
          className="border p-3 rounded"
        />

      </div>

      <button
        onClick={connectTableau}
        disabled={loading}
        className="
          mt-6
          bg-black
          text-white
          px-6
          py-3
          rounded-xl
        "
      >
        {loading
          ? "Connecting..."
          : "Connect Tableau Site"}
      </button>

    </div>
  );
}
