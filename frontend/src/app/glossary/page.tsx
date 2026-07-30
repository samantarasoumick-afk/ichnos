"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type {
  BusinessGlossaryTerm,
  BusinessGlossaryTermCreate,
  BusinessGlossaryTermUpdate,
  GlossaryTermLink,
} from "../../types/metadata";

const EMPTY_NEW_TERM: BusinessGlossaryTermCreate = {
  term: "",
  definition: "",
  domain: "",
  owner: "",
  status: "DRAFT",
};

export default function GlossaryPage() {
  const { user, loading: authLoading, effectiveRole } = useRequireAuth();

  const [terms, setTerms] = useState<BusinessGlossaryTerm[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const canEditGlossary = effectiveRole === "admin" || effectiveRole === "steward";

  const [showNewTermForm, setShowNewTermForm] = useState(false);
  const [newTerm, setNewTerm] = useState<BusinessGlossaryTermCreate>(EMPTY_NEW_TERM);
  const [creatingTerm, setCreatingTerm] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [editingTermId, setEditingTermId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<BusinessGlossaryTermUpdate>({});
  const [savingTerm, setSavingTerm] = useState(false);

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [linksByTerm, setLinksByTerm] = useState<Record<string, GlossaryTermLink[]>>({});
  const [linksLoading, setLinksLoading] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    async function fetchTerms() {
      try {
        setErrorMessage(null);
        const response = await api.get<BusinessGlossaryTerm[]>("/api/governance/glossary");
        setTerms([...response.data].sort((a, b) => a.term.localeCompare(b.term)));
      } catch (error) {
        console.error(error);
        setErrorMessage(
          "Unable to load the business glossary. Please make sure the backend is running."
        );
      }
    }

    fetchTerms();
  }, [user]);

  async function handleCreateTerm() {
    if (!newTerm.term.trim() || !newTerm.definition.trim()) {
      setCreateError("Term and definition are required.");
      return;
    }

    setCreatingTerm(true);
    setCreateError(null);

    try {
      const response = await api.post<BusinessGlossaryTerm>("/api/governance/glossary", {
        term: newTerm.term.trim(),
        definition: newTerm.definition.trim(),
        domain: newTerm.domain || null,
        owner: newTerm.owner || null,
        status: newTerm.status || "DRAFT",
      });
      setTerms((prev) =>
        [...prev, response.data].sort((a, b) => a.term.localeCompare(b.term))
      );
      setNewTerm(EMPTY_NEW_TERM);
      setShowNewTermForm(false);
    } catch (error) {
      console.error(error);
      setCreateError("Unable to create term. It may already exist.");
    } finally {
      setCreatingTerm(false);
    }
  }

  function startEditingTerm(term: BusinessGlossaryTerm) {
    setEditingTermId(term.id);
    setEditForm({
      term: term.term,
      definition: term.definition,
      domain: term.domain || "",
      owner: term.owner || "",
      status: term.status || "DRAFT",
    });
  }

  async function handleSaveTerm(termId: string) {
    setSavingTerm(true);

    try {
      const response = await api.patch<BusinessGlossaryTerm>(
        `/api/governance/glossary/${termId}`,
        {
          term: editForm.term,
          definition: editForm.definition,
          domain: editForm.domain || null,
          owner: editForm.owner || null,
          status: editForm.status || null,
        }
      );
      setTerms((prev) => prev.map((term) => (term.id === termId ? response.data : term)));
      setEditingTermId(null);
    } catch (error) {
      console.error(error);
    } finally {
      setSavingTerm(false);
    }
  }

  async function toggleExpanded(term: BusinessGlossaryTerm) {
    if (expandedId === term.id) {
      setExpandedId(null);
      return;
    }

    setExpandedId(term.id);

    if (!linksByTerm[term.id]) {
      setLinksLoading(term.id);
      try {
        const response = await api.get<GlossaryTermLink[]>(
          `/api/glossary-links/term/${term.id}`
        );
        setLinksByTerm((prev) => ({ ...prev, [term.id]: response.data }));
      } catch (error) {
        console.error(error);
      } finally {
        setLinksLoading(null);
      }
    }
  }

  const filteredTerms = terms.filter((term) => {
    const normalized = search.trim().toLowerCase();
    if (!normalized) return true;
    return [term.term, term.definition, term.domain, term.owner]
      .join(" ")
      .toLowerCase()
      .includes(normalized);
  });

  if (authLoading || !user) {
    return (
      <main className="min-h-screen bg-gray-100 p-10">
        <div className="rounded-xl bg-white p-6 shadow">Loading...</div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-100 p-10">
      <TopNav />

      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold">Business Glossary</h1>
          <div className="mt-2 max-w-2xl text-gray-600">
            The business definitions for the terms used across the catalog -
            connected to the technical catalog at the dataset and column
            level, so context travels with the data.
          </div>
        </div>
        {canEditGlossary && (
          <button
            onClick={() => setShowNewTermForm((prev) => !prev)}
            className="shrink-0 rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800"
          >
            {showNewTermForm ? "Cancel" : "New Term"}
          </button>
        )}
      </div>

      {errorMessage && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {errorMessage}
        </div>
      )}

      <input
        type="text"
        placeholder="Search terms, definitions, domains, owners..."
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        className="mb-6 w-full rounded-xl border p-3"
      />

      {showNewTermForm && (
        <div className="mb-6 space-y-3 rounded-xl bg-white p-6 shadow">
          <input
            type="text"
            placeholder="Term"
            className="w-full rounded-lg border px-3 py-2 text-sm"
            value={newTerm.term}
            onChange={(event) => setNewTerm((prev) => ({ ...prev, term: event.target.value }))}
          />
          <textarea
            placeholder="Definition"
            rows={2}
            className="w-full rounded-lg border px-3 py-2 text-sm"
            value={newTerm.definition}
            onChange={(event) =>
              setNewTerm((prev) => ({ ...prev, definition: event.target.value }))
            }
          />
          <div className="grid grid-cols-2 gap-3">
            <input
              type="text"
              placeholder="Domain"
              className="w-full rounded-lg border px-3 py-2 text-sm"
              value={newTerm.domain}
              onChange={(event) =>
                setNewTerm((prev) => ({ ...prev, domain: event.target.value }))
              }
            />
            <input
              type="text"
              placeholder="Owner"
              className="w-full rounded-lg border px-3 py-2 text-sm"
              value={newTerm.owner}
              onChange={(event) => setNewTerm((prev) => ({ ...prev, owner: event.target.value }))}
            />
          </div>
          <select
            className="w-full rounded-lg border px-3 py-2 text-sm"
            value={newTerm.status}
            onChange={(event) => setNewTerm((prev) => ({ ...prev, status: event.target.value }))}
          >
            <option value="DRAFT">DRAFT</option>
            <option value="APPROVED">APPROVED</option>
            <option value="DEPRECATED">DEPRECATED</option>
          </select>

          {createError && <div className="text-sm text-red-600">{createError}</div>}

          <button
            onClick={handleCreateTerm}
            disabled={creatingTerm}
            className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
          >
            {creatingTerm ? "Creating..." : "Create Term"}
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {filteredTerms.map((term) =>
          editingTermId === term.id ? (
            <div key={term.id} className="space-y-3 rounded-xl bg-white p-6 shadow md:col-span-2">
              <input
                type="text"
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={editForm.term ?? ""}
                onChange={(event) => setEditForm((prev) => ({ ...prev, term: event.target.value }))}
              />
              <textarea
                rows={2}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={editForm.definition ?? ""}
                onChange={(event) =>
                  setEditForm((prev) => ({ ...prev, definition: event.target.value }))
                }
              />
              <div className="grid grid-cols-2 gap-3">
                <input
                  type="text"
                  placeholder="Domain"
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  value={editForm.domain ?? ""}
                  onChange={(event) =>
                    setEditForm((prev) => ({ ...prev, domain: event.target.value }))
                  }
                />
                <input
                  type="text"
                  placeholder="Owner"
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  value={editForm.owner ?? ""}
                  onChange={(event) =>
                    setEditForm((prev) => ({ ...prev, owner: event.target.value }))
                  }
                />
              </div>
              <select
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={editForm.status ?? "DRAFT"}
                onChange={(event) =>
                  setEditForm((prev) => ({ ...prev, status: event.target.value }))
                }
              >
                <option value="DRAFT">DRAFT</option>
                <option value="APPROVED">APPROVED</option>
                <option value="DEPRECATED">DEPRECATED</option>
              </select>

              <div className="flex items-center gap-3">
                <button
                  onClick={() => handleSaveTerm(term.id)}
                  disabled={savingTerm}
                  className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
                >
                  {savingTerm ? "Saving..." : "Save"}
                </button>
                <button
                  onClick={() => setEditingTermId(null)}
                  className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-100"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div key={term.id} className="rounded-xl bg-white p-6 shadow">
              <div className="flex items-start justify-between">
                <div className="font-semibold">{term.term}</div>
                {canEditGlossary && (
                  <button
                    onClick={() => startEditingTerm(term)}
                    className="text-xs text-gray-500 hover:text-black"
                  >
                    Edit
                  </button>
                )}
              </div>
              <div className="mt-1 text-sm text-gray-600">{term.definition}</div>
              <div className="mt-3 text-xs text-gray-500">
                {term.domain || "No domain"} &middot; {term.owner || "No owner"} &middot;{" "}
                {term.status || "DRAFT"}
              </div>

              <button
                onClick={() => toggleExpanded(term)}
                className="mt-3 rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-50"
              >
                {expandedId === term.id ? "Hide linked data" : "Show linked data"}
              </button>

              {expandedId === term.id && (
                <div className="mt-3 border-t pt-3">
                  {linksLoading === term.id && (
                    <div className="text-sm text-gray-500">Loading...</div>
                  )}

                  {linksByTerm[term.id]?.length === 0 && (
                    <div className="text-sm text-gray-500">
                      Not linked to any dataset or column yet.
                    </div>
                  )}

                  {linksByTerm[term.id] && linksByTerm[term.id].length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {linksByTerm[term.id].map((link) => (
                        <Link
                          key={link.id}
                          href={`/datasets/${link.dataset_id}`}
                          className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700 hover:bg-gray-200"
                        >
                          {link.column_name ? `${link.column_name}` : "dataset"}
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        )}

        {filteredTerms.length === 0 && !showNewTermForm && (
          <div className="rounded-xl border border-dashed bg-white p-8 text-center text-gray-500 md:col-span-2">
            {terms.length === 0
              ? "No glossary terms yet."
              : "No terms match your search."}
            {terms.length === 0 &&
              (canEditGlossary
                ? " Click \"New Term\" to add the first one."
                : " Ask an admin or steward to add one.")}
          </div>
        )}
      </div>
    </main>
  );
}
