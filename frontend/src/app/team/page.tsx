"use client";

import { useEffect, useState } from "react";

import TopNav from "../../components/TopNav";
import { useAuth } from "../../contexts/AuthContext";
import { useRequireAuth } from "../../hooks/useRequireAuth";
import api from "../../services/api";
import type {
  TeamMember,
  TeamMemberInvite,
  TeamMemberUpdate,
  UserRole,
} from "../../types/metadata";

const ROLE_OPTIONS: UserRole[] = ["admin", "steward", "data_owner", "viewer"];

const EMPTY_INVITE: TeamMemberInvite = {
  email: "",
  password: "",
  role: "viewer",
};

export default function TeamPage() {
  const { user, loading: authLoading } = useRequireAuth();
  const { user: currentUser } = useAuth();

  const [members, setMembers] = useState<TeamMember[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [showInviteForm, setShowInviteForm] = useState(false);
  const [invite, setInvite] = useState<TeamMemberInvite>(EMPTY_INVITE);
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<TeamMemberUpdate>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  const isAdmin = user?.role === "admin";

  useEffect(() => {
    if (!user) return;

    async function fetchMembers() {
      try {
        setErrorMessage(null);
        const response = await api.get<TeamMember[]>("/api/users");
        setMembers(response.data);
      } catch (error) {
        console.error(error);
        setErrorMessage(
          "Unable to load your team. Please make sure the backend is running."
        );
      }
    }

    fetchMembers();
  }, [user]);

  async function handleInvite() {
    if (!invite.email.trim() || invite.password.length < 8) {
      setInviteError("Email is required and password must be at least 8 characters.");
      return;
    }

    setInviting(true);
    setInviteError(null);

    try {
      const response = await api.post<TeamMember>("/api/users", invite);
      setMembers((prev) => [...prev, response.data]);
      setInvite(EMPTY_INVITE);
      setShowInviteForm(false);
    } catch (error) {
      console.error(error);
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Unable to invite this member.";
      setInviteError(message);
    } finally {
      setInviting(false);
    }
  }

  function startEditing(member: TeamMember) {
    setEditingId(member.id);
    setEditForm({ role: member.role, is_active: member.is_active });
    setRowError(null);
  }

  async function handleSaveMember(memberId: string) {
    setSavingId(memberId);
    setRowError(null);

    try {
      const response = await api.patch<TeamMember>(`/api/users/${memberId}`, editForm);
      setMembers((prev) =>
        prev.map((member) => (member.id === memberId ? response.data : member))
      );
      setEditingId(null);
    } catch (error) {
      console.error(error);
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Unable to save changes.";
      setRowError(message);
    } finally {
      setSavingId(null);
    }
  }

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

      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold">Team</h1>
          <div className="mt-2 text-gray-600">
            Everyone with access to this organization&apos;s catalog.
          </div>
        </div>

        {isAdmin && (
          <button
            onClick={() => setShowInviteForm((prev) => !prev)}
            className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800"
          >
            {showInviteForm ? "Cancel" : "Invite Member"}
          </button>
        )}
      </div>

      {errorMessage && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 p-4 text-red-700">
          {errorMessage}
        </div>
      )}

      {showInviteForm && isAdmin && (
        <div className="mb-6 rounded-xl bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold">Invite a team member</h2>
          <div className="text-sm text-gray-500 mb-4">
            There&apos;s no email delivery yet - set an initial password here and
            share it with them directly.
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div>
              <label className="text-sm text-gray-500 block mb-1">Email</label>
              <input
                type="email"
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={invite.email}
                onChange={(event) =>
                  setInvite((prev) => ({ ...prev, email: event.target.value }))
                }
              />
            </div>

            <div>
              <label className="text-sm text-gray-500 block mb-1">Initial Password</label>
              <input
                type="text"
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={invite.password}
                onChange={(event) =>
                  setInvite((prev) => ({ ...prev, password: event.target.value }))
                }
              />
            </div>

            <div>
              <label className="text-sm text-gray-500 block mb-1">Role</label>
              <select
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={invite.role}
                onChange={(event) =>
                  setInvite((prev) => ({ ...prev, role: event.target.value as UserRole }))
                }
              >
                {ROLE_OPTIONS.map((role) => (
                  <option key={role} value={role}>
                    {role.replace("_", " ")}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {inviteError && (
            <div className="mt-4 text-sm text-red-600">{inviteError}</div>
          )}

          <button
            onClick={handleInvite}
            disabled={inviting}
            className="mt-4 rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
          >
            {inviting ? "Inviting..." : "Add to Team"}
          </button>
        </div>
      )}

      <section className="rounded-xl bg-white p-6 shadow">
        {rowError && (
          <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {rowError}
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-gray-500">
                <th className="py-3">Email</th>
                <th className="py-3">Role</th>
                <th className="py-3">Status</th>
                <th className="py-3">Joined</th>
                {isAdmin && <th className="py-3 text-right">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {members.map((member) => (
                <tr key={member.id} className="border-b hover:bg-gray-50">
                  <td className="py-3">
                    {member.email}
                    {member.id === currentUser?.id && (
                      <span className="ml-2 text-xs text-gray-400">(you)</span>
                    )}
                  </td>

                  {editingId === member.id ? (
                    <>
                      <td className="py-3">
                        <select
                          className="rounded-lg border px-2 py-1 text-sm"
                          value={editForm.role ?? member.role}
                          onChange={(event) =>
                            setEditForm((prev) => ({
                              ...prev,
                              role: event.target.value as UserRole,
                            }))
                          }
                        >
                          {ROLE_OPTIONS.map((role) => (
                            <option key={role} value={role}>
                              {role}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="py-3">
                        <select
                          className="rounded-lg border px-2 py-1 text-sm"
                          value={String(editForm.is_active ?? member.is_active)}
                          onChange={(event) =>
                            setEditForm((prev) => ({
                              ...prev,
                              is_active: event.target.value === "true",
                            }))
                          }
                        >
                          <option value="true">Active</option>
                          <option value="false">Deactivated</option>
                        </select>
                      </td>
                      <td className="py-3 text-gray-500">
                        {member.created_at
                          ? new Date(member.created_at).toLocaleDateString()
                          : "-"}
                      </td>
                      <td className="py-3 text-right">
                        <button
                          onClick={() => handleSaveMember(member.id)}
                          disabled={savingId === member.id}
                          className="mr-2 rounded-lg bg-black px-3 py-1.5 text-xs text-white hover:bg-gray-800 disabled:opacity-50"
                        >
                          {savingId === member.id ? "Saving..." : "Save"}
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          className="rounded-lg border px-3 py-1.5 text-xs hover:bg-gray-100"
                        >
                          Cancel
                        </button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="py-3">
                        <span className="rounded-full bg-gray-100 px-2 py-1 text-xs uppercase">
                          {member.role.replace("_", " ")}
                        </span>
                      </td>
                      <td className="py-3">
                        <span
                          className={`rounded-full px-2 py-1 text-xs ${
                            member.is_active
                              ? "bg-green-100 text-green-700"
                              : "bg-gray-200 text-gray-600"
                          }`}
                        >
                          {member.is_active ? "Active" : "Deactivated"}
                        </span>
                      </td>
                      <td className="py-3 text-gray-500">
                        {member.created_at
                          ? new Date(member.created_at).toLocaleDateString()
                          : "-"}
                      </td>
                      {isAdmin && (
                        <td className="py-3 text-right">
                          <button
                            onClick={() => startEditing(member)}
                            className="text-xs text-gray-500 hover:text-black"
                          >
                            Edit
                          </button>
                        </td>
                      )}
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {members.length === 0 && (
          <div className="py-8 text-gray-500">Loading team members...</div>
        )}
      </section>
    </main>
  );
}
