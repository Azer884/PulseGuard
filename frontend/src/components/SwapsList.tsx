import { ArrowLeftRight, ArrowRight, Check } from "lucide-react";
import type { ActionableSwap } from "@/lib/types";
import { Card, SectionHeading } from "./ui";

interface Props {
  swaps: ActionableSwap[];
  nameOf: (employeeId: string) => string;
  taskLabel: (taskId: string) => string;
  busy: boolean;
  onApply: (swap: ActionableSwap) => void;
}

export default function SwapsList({ swaps, nameOf, taskLabel, busy, onApply }: Props) {
  return (
    <Card className="p-6 space-y-4">
      <SectionHeading
        title="Task Swap Recommendations"
        subtitle="Each recommendation moves real backlog tasks between people whose roles cover them. Nothing changes until you apply it, and every change can be undone."
      />
      {swaps.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">
          No valid swap found. The engine does not fabricate recommendations — check warnings for details.
        </p>
      ) : (
        <div className="space-y-3">
          {swaps.map((s) => {
            const [from, to] = s.swap_between;
            const exchange = s.tasks_affected.length === 2;
            return (
              <div
                key={`${s.swap_between.join("-")}-${s.tasks_affected.join("-")}`}
                className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 p-4 flex flex-col md:flex-row md:items-center justify-between gap-4"
              >
                <div className="space-y-2 min-w-0">
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <span>{nameOf(from)}</span>
                    {exchange ? <ArrowLeftRight className="w-3.5 h-3.5 text-brand-500" /> : <ArrowRight className="w-3.5 h-3.5 text-brand-500" />}
                    <span>{nameOf(to)}</span>
                    <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-800 text-slate-500">{exchange ? "Exchange" : "Hand-off"}</span>
                  </div>
                  <div className="text-xs text-slate-600 dark:text-slate-300 space-y-0.5">
                    <p>
                      {taskLabel(s.tasks_affected[0])}: {nameOf(from)} → {nameOf(to)}
                    </p>
                    {exchange && (
                      <p>
                        {taskLabel(s.tasks_affected[1])}: {nameOf(to)} → {nameOf(from)}
                      </p>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400">{s.rationale}</p>
                </div>
                <div className="flex md:flex-col items-center md:items-end gap-3 shrink-0">
                  <div className="text-right">
                    <p className="text-2xl font-extrabold text-emerald-600 dark:text-emerald-400">-{s.expected_stress_reduction_pct}%</p>
                    <p className="text-[10px] uppercase font-semibold text-slate-400">Stress for {nameOf(from)}</p>
                  </div>
                  <button
                    onClick={() => onApply(s)}
                    disabled={busy}
                    className="bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold px-3 py-2 rounded-lg flex items-center gap-1.5 disabled:opacity-50"
                  >
                    <Check className="w-3.5 h-3.5" /> Apply swap
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
