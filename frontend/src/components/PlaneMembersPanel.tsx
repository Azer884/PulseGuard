"use client";

import { useCallback, useEffect, useState } from "react";
import { Link2, UserPlus, UserX } from "lucide-react";
import { api } from "@/lib/api";
import type { EmployeeInput, EmployeeSummary, PlaneMember } from "@/lib/types";
import EmployeeFormModal from "./EmployeeFormModal";
import { Card, SectionHeading } from "./ui";

interface Props {
  team: EmployeeSummary[];
  onEmployeeCreated: (employee: EmployeeSummary) => void;
  onMappingChanged: () => void;
  notify: (message: string, kind?: "success" | "error") => void;
}

const STATUS_STYLE: Record<PlaneMember["status"], string> = {
  matched: "text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950 border-emerald-200 dark:border-emerald-800",
  left_unassigned: "text-slate-500 bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-slate-700",
  unmatched: "text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950 border-amber-200 dark:border-amber-800",
};
const STATUS_LABEL: Record<PlaneMember["status"], string> = { matched: "Matched", left_unassigned: "Left unassigned", unmatched: "Unmatched" };

export default function PlaneMembersPanel({ team, onEmployeeCreated, onMappingChanged, notify }: Props) {
  const [members, setMembers] = useState<PlaneMember[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [creatingFor, setCreatingFor] = useState<PlaneMember | null>(null);
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(async (refresh: boolean) => {
    try {
      setMembers(await api.planeMembers(refresh));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .planeMembers(true)
      .then((m) => !cancelled && setMembers(m))
      .catch((err) => !cancelled && setError((err as Error).message));
    return () => {
      cancelled = true;
    };
  }, []);

  const nameOf = (id: string | null) => team.find((e) => e.employee_id === id)?.name ?? id ?? "";

  const map = async (member: PlaneMember, action: "match" | "leave_unassigned" | "clear", employeeId: string | null = null) => {
    setBusy(member.plane_user_id);
    try {
      setMembers(await api.planeMapMember(member.plane_user_id, action, employeeId));
      onMappingChanged();
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setBusy(null);
    }
  };

  const createEmployee = async (input: EmployeeInput) => {
    if (!creatingFor) return;
    const created = await api.createEmployee(input);
    onEmployeeCreated(created);
    await map(creatingFor, "match", created.employee_id);
    notify(`${created.name} created and matched. Generate their AI Twin in Team to include them in simulations.`);
    setCreatingFor(null);
    await load(false);
  };

  const visible = (members ?? []).filter((m) => showAll || m.assigned_task_count > 0 || m.status !== "unmatched");
  const hidden = (members?.length ?? 0) - visible.length;

  return (
    <Card className="p-6 space-y-4">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
        <SectionHeading
          title="Plane Team Members"
          subtitle="Match each Plane user to a PulseGuard employee. Plane assignees only count for simulation once matched — nothing is matched automatically."
        />
        {hidden > 0 && (
          <button onClick={() => setShowAll(true)} className="text-xs font-semibold text-brand-600 dark:text-brand-400 whitespace-nowrap">
            Show {hidden} member{hidden === 1 ? "" : "s"} without tasks
          </button>
        )}
      </div>
      {error && <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p>}
      {!members && !error && <p className="text-sm text-slate-400">Loading Plane members…</p>}
      {members && visible.length === 0 && <p className="text-sm text-slate-500">No Plane users are assigned to imported work items.</p>}
      <div className="divide-y divide-slate-100 dark:divide-slate-800">
        {visible.map((m) => {
          const suggestion = m.suggested_employee_id ? team.find((e) => e.employee_id === m.suggested_employee_id) : undefined;
          const disabled = busy === m.plane_user_id;
          return (
            <div key={m.plane_user_id} className="py-3 flex flex-col lg:flex-row lg:items-center gap-3">
              <div className="min-w-0 lg:w-64">
                <p className="text-sm font-semibold truncate">{m.display_name}</p>
                <p className="text-[11px] text-slate-400 truncate">
                  Plane: {m.email ?? m.plane_user_id} · {m.assigned_task_count} task{m.assigned_task_count === 1 ? "" : "s"}
                </p>
              </div>
              <span className={`self-start lg:self-center text-[11px] font-semibold px-2 py-0.5 rounded-full border ${STATUS_STYLE[m.status]}`}>{STATUS_LABEL[m.status]}</span>
              <div className="flex flex-wrap items-center gap-2 lg:ml-auto">
                {suggestion && m.status === "unmatched" && (
                  <button onClick={() => map(m, "match", suggestion.employee_id)} disabled={disabled} className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 text-white flex items-center gap-1.5 disabled:opacity-50">
                    <Link2 className="w-3.5 h-3.5" /> Match suggested: {suggestion.name}
                  </button>
                )}
                <select
                  value={m.status === "matched" ? (m.employee_id ?? "") : ""}
                  disabled={disabled || team.length === 0}
                  onChange={(e) => (e.target.value ? map(m, "match", e.target.value) : map(m, "clear"))}
                  aria-label={`Match ${m.display_name}`}
                  className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-brand-500 max-w-60"
                >
                  <option value="">{team.length ? "Match to…" : "No employees yet"}</option>
                  {team.map((e) => (
                    <option key={e.employee_id} value={e.employee_id}>
                      {e.name} — {e.current_role}
                    </option>
                  ))}
                </select>
                {m.status !== "matched" && (
                  <button onClick={() => setCreatingFor(m)} disabled={disabled} className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center gap-1.5 disabled:opacity-50">
                    <UserPlus className="w-3.5 h-3.5" /> Create Employee
                  </button>
                )}
                {m.status === "unmatched" ? (
                  <button onClick={() => map(m, "leave_unassigned")} disabled={disabled} className="text-xs font-semibold px-3 py-1.5 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center gap-1.5 disabled:opacity-50">
                    <UserX className="w-3.5 h-3.5" /> Leave Unassigned
                  </button>
                ) : (
                  <button onClick={() => map(m, "clear")} disabled={disabled} className="text-xs font-semibold px-3 py-1.5 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50">
                    Reset
                  </button>
                )}
              </div>
              {m.status === "matched" && <p className="text-[11px] text-slate-400 lg:hidden">Matched to {nameOf(m.employee_id)}</p>}
            </div>
          );
        })}
      </div>
      {creatingFor && (
        <EmployeeFormModal defaults={{ name: creatingFor.display_name }} onSubmit={createEmployee} onClose={() => setCreatingFor(null)} />
      )}
    </Card>
  );
}
