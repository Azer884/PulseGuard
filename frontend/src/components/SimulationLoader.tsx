"use client";

import { useEffect, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import type { Mode } from "@/lib/types";

// Presentation only: the engine result is already computed or in flight;
// these steps pace the reveal so a run reads as a simulation.
export const SIMULATION_DURATION_MS: Record<Mode, number> = {
  status_snapshot: 900,
  resolve_burnout_single: 1800,
  resolve_burnout_all: 2200,
  optimize_fastest: 2600,
};

const STEPS: Record<Mode, string[]> = {
  status_snapshot: ["Loading team AI Twins", "Scoring stress and compatibility"],
  optimize_fastest: [
    "Loading team AI Twins",
    "Building task dependency graph",
    "Evaluating candidate rotations",
    "Scoring completion time and stress",
    "Ranking top configurations",
  ],
  resolve_burnout_all: [
    "Loading team AI Twins",
    "Projecting workload per twin",
    "Searching task hand-offs and exchanges",
    "Checking role coverage",
    "Measuring stress reduction",
  ],
  resolve_burnout_single: ["Loading AI Twin", "Projecting workload", "Searching task hand-offs and exchanges", "Measuring stress reduction"],
};

const TITLES: Record<Mode, string> = {
  status_snapshot: "Refreshing team status",
  optimize_fastest: "Simulating fastest delivery",
  resolve_burnout_all: "Simulating burnout fixes",
  resolve_burnout_single: "Simulating a swap",
};

export default function SimulationLoader({ mode, projectName }: { mode: Mode; projectName?: string }) {
  const steps = STEPS[mode];
  const duration = SIMULATION_DURATION_MS[mode];
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = performance.now();
    const timer = setInterval(() => setElapsed(performance.now() - start), 80);
    return () => clearInterval(timer);
  }, []);

  const progress = Math.min(0.97, elapsed / duration);
  const active = Math.min(steps.length - 1, Math.floor(progress * steps.length));

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4" role="status" aria-live="polite">
      <div className="absolute inset-0 bg-slate-950/50 backdrop-blur-sm" />
      <div className="relative w-full max-w-md bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl p-6 space-y-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 to-indigo-400 flex items-center justify-center">
            <Loader2 className="w-5 h-5 text-white animate-spin" />
          </div>
          <div>
            <h3 className="font-bold text-slate-900 dark:text-white">{TITLES[mode]}</h3>
            {projectName && <p className="text-xs text-slate-500 dark:text-slate-400">{projectName}</p>}
          </div>
        </div>

        <div className="h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
          <div className="h-full bg-brand-500 transition-[width] duration-100 ease-linear" style={{ width: `${Math.round(progress * 100)}%` }} />
        </div>

        <ul className="space-y-2 text-sm">
          {steps.map((step, i) => (
            <li key={step} className={`flex items-center gap-2.5 ${i > active ? "text-slate-400 dark:text-slate-600" : "text-slate-700 dark:text-slate-200"}`}>
              {i < active ? (
                <Check className="w-4 h-4 text-emerald-500" />
              ) : i === active ? (
                <Loader2 className="w-4 h-4 text-brand-500 animate-spin" />
              ) : (
                <span className="w-4 h-4 rounded-full border border-slate-300 dark:border-slate-700" />
              )}
              {step}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
