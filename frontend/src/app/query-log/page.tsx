"use client";

import { useEffect, useState } from "react";

import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type { QueryLogReport } from "../../types/metadata";

const WINDOW_OPTIONS = [7, 30, 90];

function sourceLabel(sources: string[]) {
  if (sources.length === 2) return "Ask + Search";
  if (sources[0] === "ask") return "Ask";
  if (sources[0] === "search") return "Search";
  return sources.join(", ");
}

export default function QueryLogPage() {
  const { user, loading: authLoading } = useRequireAuth();

  const [days, setDays] = useState(30);
  const [report, setReport] = useState<QueryLogReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  useEffect(() => {
    if (!user) return;

    async function fetchReport() {
      try {
        setLoading(true);
        setErrorMessage(null);
        setForbidden(false);
        const response = await api.get<QueryLogReport>("/api/query-log/report", {
          params: { days },
        });
        setReport(response.data);
      } catch (error) {
        const status = (error as { response?: { status?: number } })?.response?.status;
        if (status === 403) {
          setForbidden(true);
        } else {
          console.error(error);
          setErrorMessage("Unable to load search insights right now.");
        }
      } finally {
        setLoading(false);
      }
    }

    fetchReport();
  }, [user, days]);

  if (authLoading || !user) {
    return (
      <main className="min-h-screen bg-gray-100 p-10">
        <div className="rounded-lg bg-white p-6 shadow">Loading...</div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-100 p-10">
      <TopNav />

      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold">Search Insights</h1>
          <p className="mt-2 text-gray-600">
            What people are asking on the Ask page and typing into search - and,
            more usefully, what isn&apos;t landing. Recurring gaps here are good
            candidates for a new built-in intent, glossary term, or FAQ entry.
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2 rounded-lg border bg-white p-1">
          {WINDOW_OPTIONS.map((option) => (
            <button
              key={option}
              onClick={() => setDays(option)}
              className={`rounded-md px-3 py-1.5 text-sm ${
                days === option ? "bg-black text-white" : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              {option}d
            </button>
          ))}
        </div>
      </div>

      {forbidden && (
        <div className="rounded-xl bg-white p-6 shadow">
          <p className="text-gray-600">
            Search Insights is only available to admins. Ask an admin on your
            team if you need access.
          </p>
        </div>
      )}

      {!forbidden && errorMessage && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {errorMessage}
        </div>
      )}

      {!forbidden && !loading && report && (
        <>
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-xl bg-white p-6 shadow">
              <div className="text-sm text-gray-500">Total queries</div>
              <div className="mt-1 text-3xl font-bold">{report.total_queries}</div>
              <div className="mt-1 text-xs text-gray-400">last {report.window_days} days</div>
            </div>
            <div className="rounded-xl bg-white p-6 shadow">
              <div className="text-sm text-gray-500">Unanswered</div>
              <div className="mt-1 text-3xl font-bold">{report.unanswered_count}</div>
              <div className="mt-1 text-xs text-gray-400">
                no result or a fixed give-up reply
              </div>
            </div>
            <div className="rounded-xl bg-white p-6 shadow">
              <div className="text-sm text-gray-500">Unanswered rate</div>
              <div className="mt-1 text-3xl font-bold">{report.unanswered_rate}%</div>
              <div className="mt-1 text-xs text-gray-400">of all logged queries</div>
            </div>
          </div>

          <section className="mb-6 rounded-xl bg-white p-6 shadow">
            <h2 className="text-lg font-semibold">Top unanswered questions</h2>
            <p className="mt-1 text-sm text-gray-500">
              Ranked by how often they were asked, most recent first as a
              tiebreaker.
            </p>

            {report.top_unanswered.length === 0 ? (
              <div className="mt-4 text-gray-500">
                Nothing unanswered in this window - good sign.
              </div>
            ) : (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-500">
                      <th className="py-2">Query</th>
                      <th className="py-2">Asked</th>
                      <th className="py-2">Where</th>
                      <th className="py-2">Last asked</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.top_unanswered.map((group) => (
                      <tr key={group.query_text} className="border-b hover:bg-gray-50">
                        <td className="py-2 pr-4">{group.query_text}</td>
                        <td className="py-2 pr-4">{group.count}x</td>
                        <td className="py-2 pr-4 text-gray-600">
                          {sourceLabel(group.sources)}
                        </td>
                        <td className="py-2 whitespace-nowrap text-gray-500">
                          {new Date(group.last_asked_at).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="rounded-xl bg-white p-6 shadow">
            <h2 className="text-lg font-semibold">Most asked overall</h2>
            <p className="mt-1 text-sm text-gray-500">
              Includes answered queries too - a recurring question that IS
              being answered is still a signal something deserves a more
              prominent home in the catalog.
            </p>

            {report.top_overall.length === 0 ? (
              <div className="mt-4 text-gray-500">No queries logged in this window yet.</div>
            ) : (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-500">
                      <th className="py-2">Query</th>
                      <th className="py-2">Asked</th>
                      <th className="py-2">Where</th>
                      <th className="py-2">Last asked</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.top_overall.map((group) => (
                      <tr key={group.query_text} className="border-b hover:bg-gray-50">
                        <td className="py-2 pr-4">{group.query_text}</td>
                        <td className="py-2 pr-4">{group.count}x</td>
                        <td className="py-2 pr-4 text-gray-600">
                          {sourceLabel(group.sources)}
                        </td>
                        <td className="py-2 whitespace-nowrap text-gray-500">
                          {new Date(group.last_asked_at).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </main>
  );
}
