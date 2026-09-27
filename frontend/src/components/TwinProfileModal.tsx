"use client";

import { Info, Pencil, RefreshCw, TriangleAlert } from "lucide-react";
import type { AITwin, TwinStatus } from "@/lib/types";
import Modal from "./Modal";

interface Props {
  twin: AITwin;
  status: TwinStatus;
  busy: boolean;
  onEdit: () => void;
  onRegenerate: () => void;
  onClose: () => void;
}

function Bar({ label, pct, detail }: { label: string; pct: number | null; detail?: string }) {
  return (
    <div className="grid grid-cols-[minmax(0,9rem)_1fr_3rem] items-center gap-3 text-sm" title={detail}>
      <span className="truncate text-slate-700 dark:text-slate-300">{label}</span>
      <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
        {pct !== null && <div className="h-full bg-brand-500" style={{ width: `${pct}%` }} />}
      </div>
      <span className="text-right font-semibold tabular-nums">{pct === null ? "—" : `${pct}%`}</span>
    </div>
  );
}

function SectionLabel({ children }: { children: string }) {
  return <h4 className="text-[11px] font-semibold uppercase tracking-wider text-brand-600 dark:text-brand-400 mb-2">{children}</h4>;
}

export default function TwinProfileModal({ twin, status, busy, onEdit, onRegenerate, onClose }: Props) {
  const profile = twin.simulation_profile;
  const unmappedRoles = twin.role_compatibility.filter((r) => r.compatibility_pct === null);
  const fit = [...twin.task_type_fit].sort((a, b) => b.compatibility_pct - a.compatibility_pct || a.task_type.localeCompare(b.task_type));

  const rows = [
    ["Workload", `${profile.current_workload_hours} / ${profile.weekly_available_hours} h`],
    ["Capacity used", `${profile.capacity_used_pct}%`],
    ["Autonomy", `${profile.autonomy_pct}%`],
    ["Cognitive load", `${profile.cognitive_load_pct}%`],
    ["Scheduled overtime", `${twin.overtime_hours_last_7d} h`],
    ["Velocity baseline", `${twin.historical_velocity} tasks/day`],
  ];

  return (
    <Modal
      wide
      title={twin.name}
      subtitle={
        <>
          AI Twin · {twin.current_role} · {twin.employee_id}
        </>
      }
      onClose={onClose}
      footer={
        <>
          <button onClick={onEdit} className="text-xs font-semibold px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center gap-1.5">
            <Pencil className="w-3.5 h-3.5" /> Edit Employee
          </button>
          <button onClick={onRegenerate} disabled={busy} className="bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold px-4 py-2.5 rounded-xl flex items-center gap-1.5 disabled:opacity-50">
            <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} /> Regenerate Twin
          </button>
        </>
      }
    >
      <div className="space-y-6">
        {status === "outdated" && (
          <p className="text-xs flex items-start gap-2 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 rounded-xl px-3 py-2">
            <TriangleAlert className="w-4 h-4 shrink-0" />
            The employee profile changed after this twin was generated. Regenerate to update it.
          </p>
        )}
        <p className="text-xs flex items-start gap-2 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 rounded-xl px-3 py-2">
          <Info className="w-4 h-4 shrink-0 text-brand-500" />
          Values below are simulation parameters estimated from the profile with fixed rules — not measurements of a real person.
        </p>

        <div>
          <SectionLabel>Skills</SectionLabel>
          <div className="flex flex-wrap gap-1.5">
            {twin.skills.length ? (
              twin.skills.map((s) => (
                <span key={s} className="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs">
                  {s}
                </span>
              ))
            ) : (
              <span className="text-xs text-slate-400">No skills listed</span>
            )}
          </div>
        </div>

        <div>
          <SectionLabel>Role Compatibility</SectionLabel>
          <div className="space-y-2">
            {twin.role_compatibility.map((r) => (
              <Bar
                key={r.role}
                label={r.role}
                pct={r.compatibility_pct}
                detail={r.matched_task_types.length ? `Maps to: ${r.matched_task_types.join(", ")}` : "Role not mapped to a known task type"}
              />
            ))}
          </div>
          {unmappedRoles.length > 0 && (
            <p className="text-[11px] text-slate-400 mt-2">
              {unmappedRoles.map((r) => r.role).join(", ")}: no score — role name does not map to a known task type.
            </p>
          )}
        </div>

        <div>
          <SectionLabel>Task-Type Fit</SectionLabel>
          <div className="space-y-2">
            {fit.map((f) => (
              <Bar
                key={f.task_type}
                label={f.task_type}
                pct={f.compatibility_pct}
                detail={`Speed ×${f.estimated_speed}${f.matched_signals.length ? ` · from ${f.matched_signals.join(", ")}` : " · no matching skills"}`}
              />
            ))}
          </div>
        </div>

        <div>
          <SectionLabel>Simulation Profile</SectionLabel>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            {rows.map(([label, value]) => (
              <div key={label} className="flex justify-between gap-2 border-b border-slate-100 dark:border-slate-800 pb-1">
                <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
                <dd className="font-semibold tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
        </div>

        <details className="text-xs">
          <summary className="cursor-pointer font-semibold text-slate-600 dark:text-slate-300">How these parameters were estimated</summary>
          <dl className="mt-2 space-y-2">
            {Object.entries(twin.parameter_notes).map(([key, note]) => (
              <div key={key}>
                <dt className="font-mono text-[11px] text-slate-500">{key}</dt>
                <dd className="text-slate-600 dark:text-slate-300">{note}</dd>
              </div>
            ))}
          </dl>
        </details>
      </div>
    </Modal>
  );
}
