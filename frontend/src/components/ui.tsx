import type { ReactNode } from "react";
import type { RiskLevel } from "@/lib/types";

export function show(value: number | string | null | undefined, suffix = ""): string {
  return value === null || value === undefined ? "—" : `${value}${suffix}`;
}

export function signed(value: number | null | undefined, suffix: string): string {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${value}${suffix}`;
}

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).map((n) => n[0]).join("").slice(0, 2).toUpperCase() || "?";
}

const RISK_STYLES: Record<RiskLevel, string> = {
  Critical: "bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800",
  Warning: "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800",
  Normal: "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800",
};

export function RiskBadge({ risk }: { risk?: RiskLevel }) {
  const style = risk ? RISK_STYLES[risk] : "bg-slate-100 dark:bg-slate-800 text-slate-500 border-slate-200 dark:border-slate-700";
  return <span className={`px-2.5 py-1 rounded-full text-xs font-semibold border whitespace-nowrap ${style}`}>{risk ?? "Not scored"}</span>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 ${className}`}>{children}</div>
  );
}

export function SectionHeading({ title, subtitle }: { title: string; subtitle?: ReactNode }) {
  return (
    <div>
      <h3 className="font-bold text-slate-900 dark:text-white text-lg">{title}</h3>
      {subtitle && <p className="text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>}
    </div>
  );
}
