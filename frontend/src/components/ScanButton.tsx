"use client";

import { useState } from "react";

import api from "../services/api";

type Props = {
  sourceId: string;
};

export default function ScanButton({
  sourceId,
}: Props) {

  const [loading, setLoading] =
    useState(false);

  async function handleScan() {

    try {

      setLoading(true);

      await api.post(
        `/api/scanner/${sourceId}`
      );

      alert("Scan completed");

      window.location.reload();

    } catch (error) {

      console.error(error);

      alert("Scan failed");

    } finally {

      setLoading(false);

    }
  }

  return (

    <button
      onClick={handleScan}
      disabled={loading}
      className="
        mt-3
        bg-blue-600
        hover:bg-blue-700
        text-white
        px-4
        py-2
        rounded-lg
        text-sm
      "
    >
      {loading
        ? "Scanning..."
        : "Run Scan"}
    </button>
  );
}