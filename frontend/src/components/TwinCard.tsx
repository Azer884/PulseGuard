import { RefreshCw } from "lucide-react";
import type { Employee, EmployeeResult } from "@/lib/types";
import { RiskBadge, initials, show } from "./ui";

interface Props {
  employee: Employee;
  score?: EmployeeResult;
  tasks: { task_id: string; task_type: string; title?: string }[];
  scoredAgainst: string;
  busy: boolean;
  onFindSwap: (employeeId: string) => void;
}

export default function TwinCard({ employee, score, tasks, scoredAgainst, busy, onFindSwap }: Props) {
  const atRisk = score && score.risk_level !== "Normal";
  const barColor = !score
    ? "bg-slate-300"
    : score.risk_level === "Critical"
      ? "bg-rose-500"
      : score.risk_level === "Warning"
        ? "bg-amber-500"
        : "bg-emerald-500";

  return (
    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 flex flex-col justify-between gap-4">
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-slate-100 dark:bg-slate-800 font-bold flex items-center justify-center text-sm border border-slate-200 dark:border-slate-700">
              {initials(employee.name)}
            </div>
            <div>
              <h4 className="font-bold text-slate-900 dark:text-white text-sm">{employee.name}</h4>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {employee.current_role} · {employee.employee_id}
              </p>
            </div>
          </div>
          <RiskBadge risk={score?.risk_level} />
        </div>

        <div>
          <div className="flex justify-between text-[10px] font-semibold uppercase text-slate-400 mb-1">
            <span>Stamina</span>
            <span>Stress score {show(score?.stress_score)}</span>
          </div>
          <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
            <div className={`h-full ${barColor}`} style={{ width: `${score ? Math.max(0, Math.min(100, score.stamina)) : 0}%` }} />
          </div>
          <p className="text-lg font-bold mt-1">{show(score?.stamina, "%")}</p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="bg-slate-50 dark:bg-slate-950 p-2.5 rounded-xl border border-slate-200 dark:border-slate-800">
            <span className="text-[10px] text-slate-400 uppercase font-semibold">Compatibility</span>
            <p className="text-lg font-bold text-brand-600 dark:text-brand-400">{show(score?.compatibility_pct, "%")}</p>
          </div>
          <div className="bg-slate-50 dark:bg-slate-950 p-2.5 rounded-xl border border-slate-200 dark:border-slate-800">
            <span className="text-[10px] text-slate-400 uppercase font-semibold">Velocity</span>
            <p className="text-lg font-bold">
              {show(score?.velocity_tasks_per_day)} <span className="text-xs font-medium text-slate-400">tasks/day</span>
            </p>
          </div>
        </div>

        <div className="space-y-1.5">
          <span className="text-[10px] text-slate-400 uppercase font-semibold">Tasks ({scoredAgainst})</span>
          <div className="flex flex-wrap gap-1.5">
            {tasks.length ? (
              tasks.map((t) => (
                <span key={t.task_id} title={t.title} className="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-[11px]">
                  {t.task_id} · {t.task_type}
                </span>
              ))
            ) : (
              <span className="text-[11px] text-slate-400">No tasks assigned</span>
            )}
          </div>
        </div>

        <div className="space-y-1.5">
          <span className="text-[10px] text-slate-400 uppercase font-semibold">Contributing factors</span>
          <div className="flex flex-wrap gap-1.5">
            {score?.primary_contributing_factors.length ? (
              score.primary_contributing_factors.map((f) => (
                <span key={f} className="px-2 py-0.5 rounded-full bg-rose-50 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-900 text-[11px]">
                  {f}
                </span>
              ))
            ) : (
              <span className="text-[11px] text-slate-400">{score ? "None flagged by the data" : "Not scored — see warnings"}</span>
            )}
          </div>
        </div>
      </div>

      {atRisk && (
        <div className="pt-4 border-t border-slate-200 dark:border-slate-800">
          <button
            onClick={() => onFindSwap(employee.employee_id)}
            disabled={busy}
            className="w-full py-2 px-3 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white font-semibold text-xs rounded-xl flex items-center justify-center gap-1.5"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Find swap for this twin</span>
          </button>
        </div>
      )}
    </div>
  );
}
