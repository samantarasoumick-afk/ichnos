"use client";

import { useState } from "react";

import api from "../services/api";

export default function DbtUploadForm() {

  const [name, setName] = useState("");

  const [manifestFile, setManifestFile] = useState<File | null>(null);

  const [catalogFile, setCatalogFile] = useState<File | null>(null);

  const [loading, setLoading] = useState(false);

  async function uploadDbtProject() {

    if (!manifestFile) {
      alert("Please choose a manifest.json file");
      return;
    }

    try {

      setLoading(true);

      const formData = new FormData();
      formData.append("name", name);
      formData.append("manifest_file", manifestFile);
      if (catalogFile) {
        formData.append("catalog_file", catalogFile);
      }

      const response = await api.post("/api/sources/upload/dbt", formData);

      alert(
        `dbt project processed: ${response.data.datasets_discovered} model(s), ` +
          `${response.data.lineage_edges_created} lineage edge(s)`
      );

      window.location.reload();

    } catch (error: unknown) {

      console.error(error);

      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;

      alert(detail || "Failed to process dbt project");

    } finally {

      setLoading(false);
    }
  }

  return (

    <div>

      <p className="text-sm text-gray-500 mb-4">
        Onboard an entire dbt project at once from its compiled artifacts -
        no live connection needed. manifest.json (in your project&apos;s
        target/ directory after a `dbt run` or `dbt compile`) captures every
        model&apos;s columns and its real dependency graph, which becomes
        lineage automatically, with the compiled SQL attached as
        documentation. catalog.json (from `dbt docs generate`) is optional
        but adds real column types instead of &quot;unknown&quot;.
      </p>

      <div className="grid grid-cols-2 gap-4">

        <input
          placeholder="Source Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="border p-3 rounded"
        />

        <div />

        <div>
          <label className="text-xs text-gray-500 block mb-1">
            manifest.json (required)
          </label>
          <input
            type="file"
            accept=".json"
            onChange={(e) => setManifestFile(e.target.files?.[0] ?? null)}
            className="border p-3 rounded bg-white w-full"
          />
        </div>

        <div>
          <label className="text-xs text-gray-500 block mb-1">
            catalog.json (optional)
          </label>
          <input
            type="file"
            accept=".json"
            onChange={(e) => setCatalogFile(e.target.files?.[0] ?? null)}
            className="border p-3 rounded bg-white w-full"
          />
        </div>

      </div>

      <button
        onClick={uploadDbtProject}
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
          ? "Processing..."
          : "Upload dbt Project"}
      </button>

    </div>
  );
}
