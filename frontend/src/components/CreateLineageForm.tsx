"use client";

import { useState } from "react";

import api from "../services/api";
import type { Dataset } from "../types/metadata";

type Props = {
  datasets: Dataset[];
  // When set, this form is embedded on that dataset's own page: its
  // side of the relationship is fixed (via a toggle, not a dropdown)
  // so the user only has to pick the *other* dataset, rather than
  // re-finding the dataset they're already looking at in a long list.
  currentDataset?: Dataset;
  onCreated?: () => void;
};

function datasetLabel(dataset: Dataset) {
  return `${dataset.schema_name}.${dataset.name}`;
}

export default function CreateLineageForm({ datasets, currentDataset, onCreated }: Props) {
  const [currentRole, setCurrentRole] = useState<"upstream" | "downstream">("upstream");
  const [otherId, setOtherId] = useState("");
  const [upstreamId, setUpstreamId] = useState("");
  const [downstreamId, setDownstreamId] = useState("");
  const [transformationType, setTransformationType] = useState("");
  const [transformationDescription, setTransformationDescription] = useState("");
  const [filterLogic, setFilterLogic] = useState("");
  const [saving, setSaving] = useState(false);

  const sortedDatasets = [...datasets]
    .filter((dataset) => !currentDataset || dataset.id !== currentDataset.id)
    .sort((a, b) => datasetLabel(a).localeCompare(datasetLabel(b)));

  const resolvedUpstreamId = currentDataset
    ? currentRole === "upstream"
      ? currentDataset.id
      : otherId
    : upstreamId;

  const resolvedDownstreamId = currentDataset
    ? currentRole === "downstream"
      ? currentDataset.id
      : otherId
    : downstreamId;

  async function createLineage() {
    if (!resolvedUpstreamId || !resolvedDownstreamId) {
      alert("Choose both an upstream and a downstream dataset");
      return;
    }

    if (resolvedUpstreamId === resolvedDownstreamId) {
      alert("Upstream and downstream must be different datasets");
      return;
    }

    try {
      setSaving(true);
      await api.post("/api/lineage", {
        upstream_dataset_id: resolvedUpstreamId,
        downstream_dataset_id: resolvedDownstreamId,
        transformation_type: transformationType || undefined,
        transformation_description: transformationDescription || undefined,
        filter_logic: filterLogic || undefined,
      });
      if (onCreated) {
        onCreated();
      } else {
        window.location.reload();
      }
    } catch (error) {
      console.error(error);
      alert("Failed to create lineage edge");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-xl bg-white p-6 shadow mb-8">
      <h2 className="mb-2 text-xl font-semibold">Document Lineage</h2>
      <p className="mb-4 text-sm text-gray-500">
        For relationships automated discovery can&apos;t see - a CSV source with
        no foreign keys, or a transform that happens outside the database
        entirely. Describe what the transformation and any filtering actually
        do, so a consumer doesn&apos;t have to guess.
      </p>

      {currentDataset ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <label className="text-sm text-gray-500 block mb-1">This dataset is the...</label>
            <select
              className="w-full rounded-lg border px-3 py-2 text-sm"
              value={currentRole}
              onChange={(event) => setCurrentRole(event.target.value as "upstream" | "downstream")}
            >
              <option value="upstream">Upstream (source)</option>
              <option value="downstream">Downstream (derived)</option>
            </select>
          </div>

          <div>
            <label className="text-sm text-gray-500 block mb-1">
              {currentRole === "upstream" ? "Downstream (derived)" : "Upstream (source)"}
            </label>
            <select
              className="w-full rounded-lg border px-3 py-2 text-sm"
              value={otherId}
              onChange={(event) => setOtherId(event.target.value)}
            >
              <option value="">Choose a dataset...</option>
              {sortedDatasets.map((dataset) => (
                <option key={dataset.id} value={dataset.id}>
                  {datasetLabel(dataset)}
                </option>
              ))}
            </select>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <label className="text-sm text-gray-500 block mb-1">Upstream (source)</label>
            <select
              className="w-full rounded-lg border px-3 py-2 text-sm"
              value={upstreamId}
              onChange={(event) => setUpstreamId(event.target.value)}
            >
              <option value="">Choose a dataset...</option>
              {sortedDatasets.map((dataset) => (
                <option key={dataset.id} value={dataset.id}>
                  {datasetLabel(dataset)}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-sm text-gray-500 block mb-1">Downstream (derived)</label>
            <select
              className="w-full rounded-lg border px-3 py-2 text-sm"
              value={downstreamId}
              onChange={(event) => setDownstreamId(event.target.value)}
            >
              <option value="">Choose a dataset...</option>
              {sortedDatasets.map((dataset) => (
                <option key={dataset.id} value={dataset.id}>
                  {datasetLabel(dataset)}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 mt-4">

        <div>
          <label className="text-sm text-gray-500 block mb-1">Transformation Type</label>
          <input
            type="text"
            placeholder="e.g. dbt_model, ETL job, manual join"
            className="w-full rounded-lg border px-3 py-2 text-sm"
            value={transformationType}
            onChange={(event) => setTransformationType(event.target.value)}
          />
        </div>

        <div className="md:col-span-2">
          <label className="text-sm text-gray-500 block mb-1">
            Transformation Description
          </label>
          <textarea
            placeholder="What does this transformation actually do?"
            rows={2}
            className="w-full rounded-lg border px-3 py-2 text-sm"
            value={transformationDescription}
            onChange={(event) => setTransformationDescription(event.target.value)}
          />
        </div>

        <div className="md:col-span-2">
          <label className="text-sm text-gray-500 block mb-1">Filter Logic</label>
          <textarea
            placeholder="e.g. WHERE status = 'active', excludes soft-deleted rows"
            rows={2}
            className="w-full rounded-lg border px-3 py-2 text-sm"
            value={filterLogic}
            onChange={(event) => setFilterLogic(event.target.value)}
          />
        </div>
      </div>

      <button
        onClick={createLineage}
        disabled={saving}
        className="mt-4 rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
      >
        {saving ? "Saving..." : "Add Lineage Edge"}
      </button>
    </div>
  );
}
