"use client";

import { useState } from "react";

import CreateSourceForm from "./CreateSourceForm";
import DbtUploadForm from "./DbtUploadForm";
import FileUploadForm from "./FileUploadForm";
import TableauConnectForm from "./TableauConnectForm";

type Tab = "connect" | "upload" | "dbt" | "tableau";

export default function AddSourceCard() {

  const [tab, setTab] = useState<Tab>("connect");

  return (

    <div className="bg-white rounded-xl p-6 shadow mb-8">

      <div className="flex items-center justify-between mb-6">

        <h2 className="text-2xl font-semibold">
          Add Source
        </h2>

        <div className="flex rounded-lg border overflow-hidden text-sm">

          <button
            onClick={() => setTab("connect")}
            className={`px-4 py-2 ${
              tab === "connect"
                ? "bg-black text-white"
                : "bg-white text-gray-600"
            }`}
          >
            Connect Database
          </button>

          <button
            onClick={() => setTab("upload")}
            className={`px-4 py-2 ${
              tab === "upload"
                ? "bg-black text-white"
                : "bg-white text-gray-600"
            }`}
          >
            Upload File
          </button>

          <button
            onClick={() => setTab("dbt")}
            className={`px-4 py-2 ${
              tab === "dbt"
                ? "bg-black text-white"
                : "bg-white text-gray-600"
            }`}
          >
            dbt Project
          </button>

          <button
            onClick={() => setTab("tableau")}
            className={`px-4 py-2 ${
              tab === "tableau"
                ? "bg-black text-white"
                : "bg-white text-gray-600"
            }`}
          >
            Tableau
          </button>

        </div>

      </div>

      {tab === "connect" && <CreateSourceForm />}
      {tab === "upload" && <FileUploadForm />}
      {tab === "dbt" && <DbtUploadForm />}
      {tab === "tableau" && <TableauConnectForm />}

    </div>
  );
}
