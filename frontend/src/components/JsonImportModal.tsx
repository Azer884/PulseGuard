"use client";

import { useMemo, useState, type ChangeEvent } from "react";
import { FileUp } from "lucide-react";
import { ApiError, api, describeRowIssues } from "@/lib/api";
import type { ImportResult } from "@/lib/types";
import Modal from "./Modal";

const MAX_ROWS = 500;

const EXAMPLE = JSON.stringify(
  [
    {
      name: "Alex Johnson",
      current_role: "Backend Developer",
      skills: ["Python", "FastAPI", "PostgreSQL"],
      experience_years: 3,
      available_roles: ["API Integration"],
      current_workload_hours: 24,
      weekly_available_hours: 40,
    },
    {
      name: "Priya Shah",
      current_role: "Frontend Developer",
      skills: ["React", "TypeScript"],
      experience_years: 5,
      available_roles: [],
      current_workload_hours: 32,
      weekly_available_hours: 40,
    },
  ],
  null,
  2,
);

type Parsed = { rows: Record<string, unknown>[]; error: null } | { rows: null; error: string };

function parse(text: string): Parsed {
  if (!text.trim()) return { rows: null, error: "Paste JSON or choose a file." };
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch (err) {
    return { rows: null, error: `Invalid JSON: ${(err as Error).message}` };
  }
  const list = Array.isArray(data) ? data : (data as { employees?: unknown })?.employees;
  if (!Array.isArray(list)) return { rows: null, error: 'Expected an array of employees, or an object with an "employees" array.' };
  if (list.length === 0) return { rows: null, error: "The list is empty." };
  if (list.length > MAX_ROWS) return { rows: null, error: `At most ${MAX_ROWS} employees per import (got ${list.length}).` };
  if (!list.every((r) => r && typeof r === "object" && !Array.isArray(r))) return { rows: null, error: "Every entry must be an object." };
  return { rows: list as Record<string, unknown>[], error: null };
}

interface Props {
  onImported: (result: ImportResult) => void;
  onClose: () => void;
}

export default function JsonImportModal({ onImported, onClose }: Props) {
  const [text, setText] = useState("");
  const [generateTwins, setGenerateTwins] = useState(true);
  const [pending, setPending] = useState(false);
  const [issues, setIssues] = useState<string[]>([]);
  const parsed = useMemo(() => parse(text), [text]);

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setIssues([]);
    setText(await file.text());
  };

  const submit = async () => {
    if (!parsed.rows) return;
    setPending(true);
    setIssues([]);
    try {
      onImported(await api.importEmployees(parsed.rows, generateTwins));
    } catch (err) {
      const rows = parsed.rows;
      setIssues(
        err instanceof ApiError && err.issues.length
          ? describeRowIssues(err.issues, "employees", (i) => (typeof rows[i]?.name === "string" ? (rows[i].name as string) : undefined))
          : [(err as Error).message],
      );
      setPending(false);
    }
  };

  return (
    <Modal
      wide
      title="Import Employees from JSON"
      subtitle="All rows are validated first. If any row is invalid, nothing is imported."
      onClose={onClose}
      footer={
        <>
          <label className="mr-auto flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
            <input type="checkbox" checked={generateTwins} onChange={(e) => setGenerateTwins(e.target.checked)} className="accent-brand-600" />
            Generate AI Twins after import
          </label>
          <button onClick={onClose} className="text-xs font-semibold px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
            Cancel
          </button>
          <button onClick={submit} disabled={!parsed.rows || pending} className="bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold px-4 py-2.5 rounded-xl disabled:opacity-50">
            {pending ? "Importing…" : parsed.rows ? `Import ${parsed.rows.length} employee${parsed.rows.length === 1 ? "" : "s"}` : "Import"}
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <label className="cursor-pointer text-xs font-semibold px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center gap-1.5">
            <FileUp className="w-3.5 h-3.5" /> Choose .json file
            <input type="file" accept=".json,application/json" onChange={onFile} className="hidden" />
          </label>
          <button onClick={() => setText(EXAMPLE)} className="text-xs font-semibold px-3 py-2 rounded-xl text-brand-600 dark:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-950">
            Insert example
          </button>
          <span className="text-[11px] text-slate-400">or paste below</span>
        </div>

        <textarea
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setIssues([]);
          }}
          spellCheck={false}
          placeholder={EXAMPLE}
          className="w-full h-64 font-mono text-xs bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl p-3 focus:outline-none focus:ring-2 focus:ring-brand-500 placeholder:text-slate-300 dark:placeholder:text-slate-700"
        />

        {text.trim() && parsed.error && <p className="text-xs text-rose-600 dark:text-rose-400">{parsed.error}</p>}
        {parsed.rows && issues.length === 0 && (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {parsed.rows.length} employee{parsed.rows.length === 1 ? "" : "s"} detected:{" "}
            {parsed.rows
              .slice(0, 6)
              .map((r) => (typeof r.name === "string" && r.name.trim() ? r.name : "(no name)"))
              .join(", ")}
            {parsed.rows.length > 6 && `, +${parsed.rows.length - 6} more`}
          </p>
        )}
        {issues.length > 0 && (
          <div className="bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-800 rounded-xl px-3 py-2 text-xs text-rose-700 dark:text-rose-300 space-y-0.5 max-h-40 overflow-y-auto">
            <p className="font-semibold">Nothing was imported. Fix these rows and try again:</p>
            {issues.map((issue, i) => (
              <p key={i}>{issue}</p>
            ))}
          </div>
        )}

        <details className="text-xs text-slate-500 dark:text-slate-400">
          <summary className="cursor-pointer font-semibold">Field reference</summary>
          <ul className="mt-2 space-y-1 list-disc pl-5">
            <li><code>name</code>, <code>current_role</code> — required, non-empty</li>
            <li><code>experience_years</code> (0–60), <code>current_workload_hours</code> (0–168), <code>weekly_available_hours</code> (&gt;0–168) — required</li>
            <li><code>skills</code>, <code>available_roles</code> — optional lists of strings</li>
            <li>IDs are assigned by PulseGuard; any <code>employee_id</code> in the file is ignored.</li>
          </ul>
        </details>
      </div>
    </Modal>
  );
}
