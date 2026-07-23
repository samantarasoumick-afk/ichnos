"use client";

import { useState } from "react";

import api from "../services/api";

export default function FileUploadForm() {

  const [name, setName] = useState("");

  const [tableName, setTableName] = useState("");

  const [schemaName, setSchemaName] = useState("uploads");

  const [file, setFile] = useState<File | null>(null);

  const [loading, setLoading] = useState(false);

  async function uploadFile() {

    if (!file) {
      alert("Please choose a CSV file to upload");
      return;
    }

    try {

      setLoading(true);

      const formData = new FormData();
      formData.append("name", name);
      formData.append("table_name", tableName);
      formData.append("schema_name", schemaName);
      formData.append("file", file);

      // Don't set Content-Type manually - axios/the browser needs to
      // generate the multipart boundary itself.
      await api.post("/api/sources/upload", formData);

      alert("File uploaded and processed successfully");

      window.location.reload();

    } catch (error: unknown) {

      console.error(error);

      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;

      alert(detail || "Failed to upload file");

    } finally {

      setLoading(false);
    }
  }

  return (

    <div>

      <p className="text-sm text-gray-500 mb-4">
        No live database connection? Upload a CSV export instead - it
        goes through the same classification and data quality
        pipeline as a live scan.
      </p>

      <div className="grid grid-cols-2 gap-4">

        <input
          placeholder="Source Name"
          value={name}
          onChange={(e) =>
            setName(e.target.value)
          }
          className="border p-3 rounded"
        />

        <input
          placeholder="Table Name"
          value={tableName}
          onChange={(e) =>
            setTableName(e.target.value)
          }
          className="border p-3 rounded"
        />

        <input
          placeholder="Schema Name (optional)"
          value={schemaName}
          onChange={(e) =>
            setSchemaName(e.target.value)
          }
          className="border p-3 rounded"
        />

        <input
          type="file"
          accept=".csv"
          onChange={(e) =>
            setFile(e.target.files?.[0] ?? null)
          }
          className="border p-3 rounded bg-white"
        />

      </div>

      <button
        onClick={uploadFile}
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
          ? "Uploading..."
          : "Upload File"}
      </button>

    </div>
  );
}
