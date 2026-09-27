import { ArrowRight, Check } from "lucide-react";
import type { Assignment, AnalyzeResponse, Rotation } from "@/lib/types";
import { Card, SectionHeading } from "./ui";

interface Props {
  result: AnalyzeResponse;
  baseline: Assignment[];
  nameOf: (employeeId: string) => string;
  taskLabel: (taskId: string) => string;
  busy: boolean;
  onApply: (rotation: Rotation) => void;
}

export default function RotationsTable({ result, baseline, nameOf, taskLabel, busy, onApply }: Props) {
  const baselineMap = new Map(baseline.map((a) => [a.task_id, a.assigned_employee_id]));

  return (
    <Card className="p-6 space-y-4">
      <SectionHeading
        title="Top Optimized Rotations"
        subtitle={`Top ${result.rotations_ranked.length} of ${result.rotations_evaluated} evaluated rotations, ranked by simulated project completion time. Applying one updates the project assignment.`}
      />
      <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="bg-slate-100 dark:bg-slate-950 text-slate-500 dark:text-slate-400 text-xs font-semibold uppercase tracking-wider">
              <th className="py-3 px-4">Rank</th>
              <th className="py-3 px-4">Completion time</th>
              <th className="py-3 px-4">Changes vs. current assignment</th>
              <th className="py-3 px-4" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
            {result.rotations_ranked.map((rot, i) => {
              const changes = rot.assignments.filter((a) => baselineMap.get(a.task_id) !== a.assigned_employee_id);
              return (
                <tr key={rot.rotation_id} className={i === 0 ? "bg-brand-50/60 dark:bg-brand-950/30" : ""}>
                  <td className="py-3 px-4">
                    <span className="font-bold">#{i + 1}</span>
                    <span className="block font-mono text-[10px] text-slate-400">{rot.rotation_id}</span>
                  </td>
                  <td className="py-3 px-4 font-semibold whitespace-nowrap">{rot.total_completion_time_hours} h</td>
                  <td className="py-3 px-4 space-y-0.5">
                    {changes.length ? (
                      changes.map((a) => {
                        const before = baselineMap.get(a.task_id);
                        return (
                          <div key={a.task_id} className="text-xs flex flex-wrap items-center gap-1">
                            <span className="font-semibold">{taskLabel(a.task_id)}:</span>
                            <span className={before ? "" : "italic text-amber-600 dark:text-amber-400"}>{before ? nameOf(before) : "unassigned"}</span>
                            <ArrowRight className="w-3 h-3 text-slate-400" />
                            <span>{nameOf(a.assigned_employee_id)}</span>
                          </div>
                        );
                      })
                    ) : (
                      <span className="text-xs text-slate-400">Same as current assignment</span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-right">
                    {changes.length > 0 && (
                      <button
                        onClick={() => onApply(rot)}
                        disabled={busy}
                        className="bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold px-3 py-2 rounded-lg flex items-center gap-1.5 disabled:opacity-50 ml-auto"
                      >
                        <Check className="w-3.5 h-3.5" /> Apply
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
