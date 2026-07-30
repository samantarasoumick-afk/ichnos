"use client";

import { useEffect, useState } from "react";

import TopNav from "../../../components/TopNav";
import { useAuth } from "../../../contexts/AuthContext";
import { useRequireAuth } from "../../../hooks/useRequireAuth";
import api from "../../../services/api";
import type { BillingCycle, BillingStatus, PlanName, Source, TeamMember } from "../../../types/metadata";

type PlanCardInfo = {
  plan: PlanName;
  label: string;
  monthlyPrice: string;
  yearlyPrice: string;
  blurb: string;
};

// Mirrors website/index.html's pricing cards (see entitlements.py's
// docstring) - kept here rather than fetched from anywhere since the
// price copy itself isn't API-driven.
const UPGRADE_PLANS: PlanCardInfo[] = [
  {
    plan: "team",
    label: "Team",
    monthlyPrice: "$15/seat/mo",
    yearlyPrice: "billed yearly",
    blurb: "5 sources, 5 editor seats, lineage, contracts, glossary.",
  },
  {
    plan: "business",
    label: "Business",
    monthlyPrice: "$12/seat/mo",
    yearlyPrice: "billed yearly",
    blurb: "20 sources, 20 seats, Data Owner role, maturity dashboard.",
  },
];

export default function BillingPage() {
  const { user, loading: authLoading } = useRequireAuth();
  const { user: currentUser } = useAuth();

  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [sourceCount, setSourceCount] = useState<number | null>(null);
  const [seatCount, setSeatCount] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingPlan, setPendingPlan] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);

  const isAdmin = currentUser?.role === "admin";

  useEffect(() => {
    if (!user) return;

    async function fetchAll() {
      try {
        setErrorMessage(null);
        const [statusResponse, sourcesResponse, usersResponse] = await Promise.all([
          api.get<BillingStatus>("/api/billing/status"),
          api.get<Source[]>("/api/sources"),
          api.get<TeamMember[]>("/api/users"),
        ]);

        setStatus(statusResponse.data);
        setSourceCount(
          sourcesResponse.data.filter((source) => !source.is_seed_data).length
        );
        setSeatCount(
          usersResponse.data.filter((member) => member.role !== "viewer" && member.is_active)
            .length
        );
      } catch (error) {
        console.error(error);
        setErrorMessage("Unable to load billing information.");
      }
    }

    fetchAll();
  }, [user]);

  async function handleUpgrade(plan: PlanName, billingCycle: BillingCycle) {
    setPendingPlan(`${plan}-${billingCycle}`);
    setActionError(null);

    try {
      const response = await api.post<{ checkout_url: string }>("/api/billing/checkout", {
        plan,
        billing_cycle: billingCycle,
      });
      window.location.assign(response.data.checkout_url);
    } catch (error) {
      console.error(error);
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Unable to start checkout.";
      setActionError(message);
      setPendingPlan(null);
    }
  }

  async function handleManageBilling() {
    setPortalLoading(true);
    setActionError(null);

    try {
      const response = await api.post<{ portal_url: string }>("/api/billing/portal");
      window.location.assign(response.data.portal_url);
    } catch (error) {
      console.error(error);
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Unable to open the billing portal.";
      setActionError(message);
      setPortalLoading(false);
    }
  }

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

      <div className="mb-8">
        <h1 className="text-4xl font-bold">Billing</h1>
        <p className="mt-2 text-gray-600">
          Your organization&apos;s plan, usage against it, and how to change it.
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

      {status && (
        <section className="mb-8 rounded-xl bg-white p-6 shadow">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="text-xs uppercase text-gray-500">Current Plan</div>
              <div className="text-2xl font-bold capitalize">
                {status.plan}
                {status.billing_cycle ? ` (${status.billing_cycle})` : ""}
              </div>
            </div>

            <span
              className={`rounded-full px-3 py-1 text-xs ${
                status.plan_status === "active"
                  ? "bg-green-100 text-green-700"
                  : status.plan_status === "trialing"
                    ? "bg-blue-100 text-blue-700"
                    : "bg-gray-200 text-gray-600"
              }`}
            >
              {status.plan_status === "trialing" ? "Trial - full access" : status.plan_status}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="rounded-lg bg-gray-50 p-4">
              <div className="text-xs text-gray-500">Sources</div>
              <div className="text-xl font-bold">
                {sourceCount ?? "-"}
                {status.entitlements.max_sources !== null
                  ? ` / ${status.entitlements.max_sources}`
                  : " / unlimited"}
              </div>
            </div>
            <div className="rounded-lg bg-gray-50 p-4">
              <div className="text-xs text-gray-500">Editor Seats</div>
              <div className="text-xl font-bold">
                {seatCount ?? "-"}
                {status.entitlements.max_editor_seats !== null
                  ? ` / ${status.entitlements.max_editor_seats}`
                  : " / unlimited"}
              </div>
            </div>
            <div className="rounded-lg bg-gray-50 p-4">
              <div className="text-xs text-gray-500">Ask Questions / Day</div>
              <div className="text-xl font-bold">
                {status.entitlements.ask_daily_limit ?? "Unlimited"}
              </div>
            </div>
            <div className="rounded-lg bg-gray-50 p-4">
              <div className="text-xs text-gray-500">Audit Log Retention</div>
              <div className="text-xl font-bold">
                {status.entitlements.audit_log_retention_days
                  ? `${status.entitlements.audit_log_retention_days}d`
                  : "Unlimited"}
              </div>
            </div>
          </div>

          {status.plan_status === "trialing" && (
            <div className="mt-4 rounded-lg bg-blue-50 p-3 text-sm text-blue-700">
              You&apos;re on a trial - every feature is unlocked so you can fully evaluate
              DatFe. Upgrade below whenever you&apos;re ready to keep it after your trial.
            </div>
          )}

          {isAdmin && status.has_stripe_customer && (
            <div className="mt-4">
              <button
                onClick={handleManageBilling}
                disabled={portalLoading}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
              >
                {portalLoading ? "Opening..." : "Manage payment method & invoices"}
              </button>
            </div>
          )}
        </section>
      )}

      {isAdmin ? (
        <section className="rounded-xl bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold">Upgrade</h2>

          {status && !status.stripe_configured && (
            <div className="mb-4 rounded-lg bg-gray-50 p-3 text-sm text-gray-600">
              Self-serve billing isn&apos;t configured on this instance yet. Contact
              whoever runs this DatFe instance to upgrade your plan.
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {UPGRADE_PLANS.map((planInfo) => (
              <div key={planInfo.plan} className="rounded-xl border p-5">
                <div className="text-lg font-semibold">{planInfo.label}</div>
                <div className="mt-1 text-sm text-gray-500">{planInfo.blurb}</div>

                <div className="mt-4 flex gap-2">
                  <button
                    onClick={() => handleUpgrade(planInfo.plan, "monthly")}
                    disabled={pendingPlan !== null || (status ? !status.stripe_configured : true)}
                    className="flex-1 rounded-lg bg-black px-3 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
                  >
                    {pendingPlan === `${planInfo.plan}-monthly`
                      ? "Redirecting..."
                      : `Monthly - ${planInfo.monthlyPrice}`}
                  </button>
                  <button
                    onClick={() => handleUpgrade(planInfo.plan, "yearly")}
                    disabled={pendingPlan !== null || (status ? !status.stripe_configured : true)}
                    className="flex-1 rounded-lg border px-3 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
                  >
                    {pendingPlan === `${planInfo.plan}-yearly`
                      ? "Redirecting..."
                      : `Yearly - ${planInfo.yearlyPrice}`}
                  </button>
                </div>
              </div>
            ))}

            <div className="rounded-xl border border-dashed p-5">
              <div className="text-lg font-semibold">Enterprise</div>
              <div className="mt-1 text-sm text-gray-500">
                Unlimited sources and seats, SSO, dedicated support. Custom pricing.
              </div>
              <a
                href="mailto:samantara.soumick@gmail.com?subject=DatFe%20Enterprise"
                className="mt-4 inline-block rounded-lg border px-3 py-2 text-sm hover:bg-gray-50"
              >
                Talk to sales
              </a>
            </div>
          </div>
        </section>
      ) : (
        <section className="rounded-xl bg-white p-6 shadow text-sm text-gray-600">
          Only your organization&apos;s admin can change plans. Ask them if you&apos;d
          like to upgrade.
        </section>
      )}
    </main>
  );
}
