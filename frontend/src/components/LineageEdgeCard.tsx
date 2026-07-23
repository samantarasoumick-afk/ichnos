"use client";

import Link from "next/link";
import { useState } from "react";

import api from "../services/api";
import type { Lineage } from "../types/metadata";

type Props = {
  edge: Lineage;
  href: string;
  label: string;
  canEdit: boolean;
};

export default function LineageEdgeCard({ edge, href, label, canEdit }: Props) {
  const [editing, setEditing] = useState(false);
  const [transformationType, setTransformationType] = useState(edge.transformation_type ?? "");
  const [transformationDescription, setTransformationDescription] = useState(
    edge.transformation_description ?? ""
  );
  const [filterLogic, setFilterLogic] = useState(edge.filter_logic ?? "");
  const [saving, setSaving] = useState(false);

  async function saveEdit() {
    try {
      setSaving(true);
      await api.patch(`/api/lineage/${edge.id}`, {
        transformation_type: transformationType || undefined,
        transformation_description: transformationDescription || undefined,
        filter_logic: filterLogic || undefined,
      });
      window.location.reload();
    } catch (error) {
      console.error(error);
      alert("Failed to update lineage edge");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border bg-gray-50 p-3 text-sm">
      <div className="flex items-center justify-between gap-2">
        <Link href={href} className="hover:underline">
          {label}
          {edge.transformation_type && (
            <span className="ml-2 text-xs text-gray-400">via {edge.transformation_type}</span>
          )}
        </Link>

        <div className="flex items-center gap-2 shrink-0">
          <span
            className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
              edge.documentation_source === "MANUAL"
                ? "bg-blue-100 text-blue-700"
                : "bg-gray-200 text-gray-600"
            }`}
          >
            {edge.documentation_source}
          </span>
          {canEdit && (
            <button
              onClick={() => setEditing((value) => !value)}
              className="text-xs text-gray-500 hover:text-gray-800 underline"
            >
              {editing ? "Cancel" : "Edit"}
            </button>
          )}
        </div>
      </div>

      {(edge.transformation_description || edge.filter_logic) && !editing && (
        <div className="mt-2 space-y-1 text-xs text-gray-600">
          {edge.transformation_description && <div>{edge.transformation_description}</div>}
          {edge.filter_logic && (
            <div className="font-mono text-gray-500">{edge.filter_logic}</div>
          )}
        </div>
      )}

      {editing && (
        <div className="mt-3 space-y-2">
          <input
            type="text"
            placeholder="Transformation type"
            className="w-full rounded border px-2 py-1 text-xs"
            value={transformationType}
            onChange={(event) => setTransformationType(event.target.value)}
          />
          <textarea
            placeholder="What does this transformation do?"
            rows={2}
            className="w-full rounded border px-2 py-1 text-xs"
            value={transformationDescription}
            onChange={(event) => setTransformationDescription(event.target.value)}
          />
          <textarea
            placeholder="Filter logic"
            rows={2}
            className="w-full rounded border px-2 py-1 text-xs"
            value={filterLogic}
            onChange={(event) => setFilterLogic(event.target.value)}
          />
          <button
            onClick={saveEdit}
            disabled={saving}
            className="rounded bg-black px-3 py-1 text-xs text-white hover:bg-gray-800 disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      )}
    </div>
  );
}
