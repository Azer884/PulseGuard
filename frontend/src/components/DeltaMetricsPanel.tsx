import type { AnalyzeResponse } from "@/lib/types";
import { signed } from "./ui";

export default function DeltaMetricsPanel({ result }: { result: AnalyzeResponse | null }) {
  const d = result?.delta_metrics ?? null;
  const isOptimize = result?.mode === "optimize_fastest";

  const metrics = [
    { label: "Projected Velocity Boost", value: signed(d?.velocity_boost_pct, "%"), hint: "Completion-time gain of the top rotation vs. current assignment." },
    { label: "Burnout Mitigation", value: signed(d?.burnout_mitigation_pct, "%"), hint: "Change in average stress score vs. current assignment." },
    { label: "Milestone Time Saved", value: signed(d?.milestone_time_saved_hours, " h"), hint: "Simulated project makespan reduction." },
  ];

  const note = !isOptimize
    ? "Run “Optimize for Fastest Delivery” to compute delta metrics."
    : d
      ? "Top-ranked rotation compared with the current assignment."
      : "Delta metrics could not be calculated — see warnings.";

  return (
    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-md relative overflow-hidden">
      <div className="absolute right-0 top-0 w-96 h-96 bg-brand-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 relative">
        {metrics.map((m) => (
          <div key={m.label} className="space-y-1">
            <span className="text-xs uppercase font-semibold text-brand-600 dark:text-brand-400 tracking-wider">{m.label}</span>
            <h3 className="text-3xl font-extrabold text-slate-900 dark:text-white">{m.value}</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">{m.hint}</p>
          </div>
        ))}
      </div>
      <p className="relative text-xs text-slate-400 mt-4">{note}</p>
    </div>
  );
}
