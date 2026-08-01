"use client";

import { Fragment, useEffect, useState } from "react";

import TopNav from "../../components/TopNav";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type {
  BillingCycle,
  MarketingFunnel,
  OrganizationDetail,
  OrganizationSummary,
  PlanName,
  PlanStatus,
  UserLoginSummary,
} from "../../types/metadata";

const PLAN_OPTIONS: PlanName[] = ["starter", "team", "business", "enterprise"];
const CYCLE_OPTIONS: BillingCycle[] = ["monthly", "yearly"];
const STATUS_OPTIONS: PlanStatus[] = ["trialing", "active", "past_due", "canceled"];
const FUNNEL_WINDOWS = [7, 30, 90];

function formatDate(value: string | null) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

export default function PlatformAdminPage() {
  const { user, loading: authLoading } = useRequireAuth();

  const [orgs, setOrgs] = useState<OrganizationSummary[]>([]);
  const [funnel, setFunnel] = useState<MarketingFunnel | null>(null);
  const [funnelDays, setFunnelDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [logins, setLogins] = useState<UserLoginSummary[]>([]);
  const [loginsLoading, setLoginsLoading] = useState(true);

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<OrganizationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<{
    plan: PlanName;
    billing_cycle: BillingCycle;
    plan_status: PlanStatus;
  } | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    async function fetchOrgs() {
      try {
        setLoading(true);
        setForbidden(false);
        setErrorMessage(null);
        const response = await api.get<OrganizationSummary[]>("/api/platform/organizations");
        setOrgs(response.data);
      } catch (error) {
        console.error(error);
        const status = (error as { response?: { status?: number } })?.response?.status;
        if (status === 403) {
          setForbidden(true);
        } else {
          setErrorMessage("Unable to load organizations.");
        }
      } finally {
        setLoading(false);
      }
    }

    fetchOrgs();
  }, [user]);

  useEffect(() => {
    if (!user) return;

    async function fetchLogins() {
      try {
        setLoginsLoading(true);
        const response = await api.get<UserLoginSummary[]>("/api/platform/logins");
        setLogins(response.data);
      } catch (error) {
        console.error(error);
      } finally {
        setLoginsLoading(false);
      }
    }

    fetchLogins();
  }, [user]);

  useEffect(() => {
    if (!user) return;

    async function fetchFunnel() {
      try {
        const response = await api.get<MarketingFunnel>(
          `/api/platform/marketing/funnel?days=${funnelDays}`
        );
        setFunnel(response.data);
      } catch (error) {
        console.error(error);
      }
    }

    fetchFunnel();
  }, [user, funnelDays]);

  async function toggleExpanded(orgId: string) {
    if (expandedId === orgId) {
      setExpandedId(null);
      setDetail(null);
      return;
    }

    setExpandedId(orgId);
    setDetail(null);
    setDetailLoading(true);

    try {
      const response = await api.get<OrganizationDetail>(`/api/platform/organizations/${orgId}`);
      setDetail(response.data);
    } catch (error) {
      console.error(error);
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleSuspendToggle(org: OrganizationSummary) {
    setSavingId(org.id);
    setActionError(null);

    try {
      const action = org.is_suspended ? "activate" : "suspend";
      await api.post(`/api/platform/organizations/${org.id}/${action}`);
      setOrgs((prev) =>
        prev.map((item) =>
          item.id === org.id ? { ...item, is_suspended: !org.is_suspended } : item
        )
      );
    } catch (error) {
      console.error(error);
      setActionError("Unable to update this organization's access.");
    } finally {
      setSavingId(null);
    }
  }

  function startEditing(org: OrganizationSummary) {
    setEditingId(org.id);
    setEditForm({
      plan: org.plan,
      billing_cycle: org.billing_cycle ?? "monthly",
      plan_status: org.plan_status,
    });
    setActionError(null);
  }

  async function handleSavePlan(orgId: string) {
    if (!editForm) return;

    setSavingId(orgId);
    setActionError(null);

    try {
      await api.patch(`/api/platform/organizations/${orgId}/plan`, editForm);
      setOrgs((prev) =>
        prev.map((item) => (item.id === orgId ? { ...item, ...editForm } : item))
      );
      setEditingId(null);
    } catch (error) {
      console.error(error);
      setActionError("Unable to save this plan change.");
    } finally {
      setSavingId(null);
    }
  }

  if (authLoading || !user) {
    return (
      <main className="min-h-screen bg-gray-100 p-10">
        <div className="rounded-xl bg-white p-6 shadow">Loading...</div>
      </main>
    );
  }

  if (forbidden) {
    return (
      <main className="min-h-screen bg-gray-100 p-10">
        <TopNav />
        <div className="rounded-xl bg-white p-8 shadow">
          <h1 className="text-2xl font-bold mb-2">Platform Admin</h1>
          <p className="text-gray-600">
            This dashboard is restricted to DatFe&apos;s own operators. Your account
            doesn&apos;t have platform admin access.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-100 p-10">
      <TopNav />

      <div className="mb-8">
        <h1 className="text-4xl font-bold">Platform Admin</h1>
        <p className="mt-2 text-gray-600">
          Every organization on this instance - who&apos;s using it, what they&apos;re
          on, and the website visitor-to-signup funnel behind them.
        </p>
      </div>

      {errorMessage && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {errorMessage}
        </div>
      )}

      {actionError && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {actionError}
        </div>
      )}

      <section className="mb-8 rounded-xl bg-white p-6 shadow">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Visitor &rarr; Signup Funnel</h2>
          <div className="flex gap-2">
            {FUNNEL_WINDOWS.map((days) => (
              <button
                key={days}
                onClick={() => setFunnelDays(days)}
                className={`rounded-lg px-3 py-1.5 text-xs ${
                  funnelDays === days
                    ? "bg-black text-white"
                    : "border text-gray-600 hover:bg-gray-50"
                }`}
              >
                {days}d
              </button>
            ))}
          </div>
        </div>

        {funnel ? (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            <div className="rounded-lg bg-gray-50 p-4">
              <div className="text-xs text-gray-500">Pageviews</div>
              <div className="text-2xl font-bold">{funnel.pageviews}</div>
            </div>
            <div className="rounded-lg bg-gray-50 p-4">
              <div className="text-xs text-gray-500">Unique Visitors</div>
              <div className="text-2xl font-bold">{funnel.unique_visitors}</div>
            </div>
            <div className="rounded-lg bg-gray-50 p-4">
              <div className="text-xs text-gray-500">Signups Started</div>
              <div className="text-2xl font-bold">{funnel.signups_started}</div>
            </div>
            <div className="rounded-lg bg-gray-50 p-4">
              <div className="text-xs text-gray-500">Signups Completed</div>
              <div className="text-2xl font-bold">{funnel.signups_completed}</div>
            </div>
            <div className="rounded-lg bg-gray-50 p-4">
              <div className="text-xs text-gray-500">Visitor &rarr; Signup</div>
              <div className="text-2xl font-bold">{funnel.visitor_to_signup_rate}%</div>
            </div>
          </div>
        ) : (
          <div className="text-sm text-gray-500">Loading funnel...</div>
        )}

        {funnel && funnel.signups_by_source.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {funnel.signups_by_source.map((source) => (
              <span
                key={source.utm_source}
                className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700"
              >
                {source.utm_source}: {source.count}
              </span>
            ))}
          </div>
        )}
      </section>

      <section className="mb-8 rounded-xl bg-white p-6 shadow">
        <h2 className="mb-1 text-lg font-semibold">Logins ({logins.length})</h2>
        <p className="mb-4 text-sm text-gray-500">
          Everyone who has ever signed in, across every organization - password, magic
          link, or GitHub.
        </p>

        {loginsLoading ? (
          <div className="py-8 text-gray-500">Loading logins...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="py-3">User</th>
                  <th className="py-3">Organization</th>
                  <th className="py-3">Role</th>
                  <th className="py-3">Logins</th>
                  <th className="py-3">Last Method</th>
                  <th className="py-3">First Seen</th>
                  <th className="py-3">Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {logins.map((entry) => (
                  <tr key={entry.user_id} className="border-b last:border-0 hover:bg-gray-50">
                    <td className="py-3 font-medium">
                      {entry.email}
                      {entry.is_seed_data && (
                        <span className="ml-1 text-xs text-gray-400">(demo)</span>
                      )}
                    </td>
                    <td className="py-3 text-gray-600">{entry.organization_name}</td>
                    <td className="py-3 text-gray-600">{entry.role}</td>
                    <td className="py-3 text-gray-600">{entry.login_count}</td>
                    <td className="py-3 text-gray-600">{entry.last_login_method}</td>
                    <td className="py-3 text-gray-500">{formatDate(entry.first_login_at)}</td>
                    <td className="py-3 text-gray-500">{formatDate(entry.last_login_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {logins.length === 0 && (
              <div className="py-8 text-gray-500">No logins recorded yet.</div>
            )}
          </div>
        )}
      </section>

      <section className="rounded-xl bg-white p-6 shadow">
        <h2 className="mb-4 text-lg font-semibold">Organizations ({orgs.length})</h2>

        {loading ? (
          <div className="py-8 text-gray-500">Loading organizations...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="py-3">Organization</th>
                  <th className="py-3">Plan</th>
                  <th className="py-3">Status</th>
                  <th className="py-3">Sources</th>
                  <th className="py-3">Seats</th>
                  <th className="py-3">Ask&apos;Fe&apos; Usage</th>
                  <th className="py-3">Demo Data</th>
                  <th className="py-3">Last Activity</th>
                  <th className="py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {orgs.map((org) => (
                  <Fragment key={org.id}>
                    <tr className="border-b hover:bg-gray-50">
                      <td className="py-3">
                        <button
                          onClick={() => toggleExpanded(org.id)}
                          className="font-medium text-black hover:underline"
                        >
                          {org.name}
                        </button>
                        {org.is_suspended && (
                          <span className="ml-2 rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700">
                            Suspended
                          </span>
                        )}
                      </td>

                      {editingId === org.id && editForm ? (
                        <>
                          <td className="py-3">
                            <select
                              className="rounded-lg border px-2 py-1 text-xs"
                              value={editForm.plan}
                              onChange={(event) =>
                                setEditForm((prev) =>
                                  prev ? { ...prev, plan: event.target.value as PlanName } : prev
                                )
                              }
                            >
                              {PLAN_OPTIONS.map((plan) => (
                                <option key={plan} value={plan}>
                                  {plan}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="py-3">
                            <div className="flex gap-1">
                              <select
                                className="rounded-lg border px-2 py-1 text-xs"
                                value={editForm.plan_status}
                                onChange={(event) =>
                                  setEditForm((prev) =>
                                    prev
                                      ? { ...prev, plan_status: event.target.value as PlanStatus }
                                      : prev
                                  )
                                }
                              >
                                {STATUS_OPTIONS.map((status) => (
                                  <option key={status} value={status}>
                                    {status}
                                  </option>
                                ))}
                              </select>
                              <select
                                className="rounded-lg border px-2 py-1 text-xs"
                                value={editForm.billing_cycle}
                                onChange={(event) =>
                                  setEditForm((prev) =>
                                    prev
                                      ? {
                                          ...prev,
                                          billing_cycle: event.target.value as BillingCycle,
                                        }
                                      : prev
                                  )
                                }
                              >
                                {CYCLE_OPTIONS.map((cycle) => (
                                  <option key={cycle} value={cycle}>
                                    {cycle}
                                  </option>
                                ))}
                              </select>
                            </div>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="py-3">
                            <span className="rounded-full bg-gray-100 px-2 py-1 text-xs uppercase">
                              {org.plan}
                            </span>
                          </td>
                          <td className="py-3">
                            <span
                              className={`rounded-full px-2 py-1 text-xs ${
                                org.plan_status === "active"
                                  ? "bg-green-100 text-green-700"
                                  : org.plan_status === "trialing"
                                    ? "bg-blue-100 text-blue-700"
                                    : "bg-gray-200 text-gray-600"
                              }`}
                            >
                              {org.plan_status}
                            </span>
                          </td>
                        </>
                      )}

                      <td className="py-3 text-gray-600">
                        {org.real_source_count}
                        {org.max_sources !== null ? ` / ${org.max_sources}` : ""}
                      </td>
                      <td className="py-3 text-gray-600">{org.editor_seat_count}</td>
                      <td className="py-3 text-gray-600">
                        {org.ask_usage_today}
                        {org.ask_daily_limit !== null ? ` / ${org.ask_daily_limit}` : ""}
                      </td>
                      <td className="py-3 text-gray-600">{org.demo_data_loaded ? "Yes" : "No"}</td>
                      <td className="py-3 text-gray-500">{formatDate(org.last_activity_at)}</td>

                      <td className="py-3 text-right">
                        {editingId === org.id ? (
                          <>
                            <button
                              onClick={() => handleSavePlan(org.id)}
                              disabled={savingId === org.id}
                              className="mr-2 rounded-lg bg-black px-3 py-1.5 text-xs text-white hover:bg-gray-800 disabled:opacity-50"
                            >
                              {savingId === org.id ? "Saving..." : "Save"}
                            </button>
                            <button
                              onClick={() => setEditingId(null)}
                              className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-100"
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              onClick={() => startEditing(org)}
                              className="mr-2 text-xs text-gray-500 hover:text-black"
                            >
                              Edit Plan
                            </button>
                            <button
                              onClick={() => handleSuspendToggle(org)}
                              disabled={savingId === org.id}
                              className={`rounded-lg border px-3 py-1.5 text-xs disabled:opacity-50 ${
                                org.is_suspended
                                  ? "hover:bg-green-50"
                                  : "hover:bg-red-50 text-red-600"
                              }`}
                            >
                              {org.is_suspended ? "Reactivate" : "Suspend"}
                            </button>
                          </>
                        )}
                      </td>
                    </tr>

                    {expandedId === org.id && (
                      <tr className="border-b bg-gray-50">
                        <td colSpan={9} className="p-4">
                          {detailLoading && (
                            <div className="text-sm text-gray-500">Loading detail...</div>
                          )}

                          {detail && detail.id === org.id && (
                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                              <div>
                                <div className="mb-2 text-xs font-semibold uppercase text-gray-500">
                                  Members ({detail.members.length})
                                </div>
                                <div className="space-y-1 text-sm">
                                  {detail.members.map((member) => (
                                    <div key={member.id} className="flex justify-between">
                                      <span>
                                        {member.email}
                                        {member.is_seed_data && (
                                          <span className="ml-1 text-xs text-gray-400">
                                            (demo)
                                          </span>
                                        )}
                                      </span>
                                      <span className="text-gray-500">{member.role}</span>
                                    </div>
                                  ))}
                                </div>
                              </div>

                              <div>
                                <div className="mb-2 text-xs font-semibold uppercase text-gray-500">
                                  Recent Activity
                                </div>
                                <div className="space-y-1 text-sm">
                                  {detail.recent_activity.length === 0 && (
                                    <div className="text-gray-500">No activity recorded.</div>
                                  )}
                                  {detail.recent_activity.map((entry, index) => (
                                    <div key={index} className="text-gray-600">
                                      <span className="text-gray-400">
                                        {formatDate(entry.created_at)}
                                      </span>{" "}
                                      &middot; {entry.action}
                                      {entry.actor_email ? ` by ${entry.actor_email}` : ""}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>

            {orgs.length === 0 && (
              <div className="py-8 text-gray-500">No organizations yet.</div>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
