"use client";

import { useEffect, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import type { ImportReport, PlaneProjectSummary } from "@/lib/types";
import Modal from "./Modal";

interface Props {
  onImported: (report: ImportReport) => void;
  onClose: () => void;
}

export default function PlaneImportModal({ onImported, onClose }: Props) {
  const [projects, setProjects] = useState<PlaneProjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .planeProjects()
      .then((p) => !cancelled && setProjects(p))
      .catch((err) => !cancelled && setError((err as Error).message));
    return () => {
      cancelled = true;
    };
  }, []);

  const run = async (project: PlaneProjectSummary) => {
    setBusyId(project.plane_project_id);
    setError(null);
    try {
      onImported(await api.planeImport(project.plane_project_id));
    } catch (err) {
      setError((err as Error).message);
      setBusyId(null);
    }
  };

  return (
    <Modal
      wide
      title="Import from Plane"
      subtitle="Importing an already imported project syncs it instead of creating a copy."
      onClose={onClose}
      footer={
        <button onClick={onClose} className="text-xs font-semibold px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
          Close
        </button>
      }
    >
      {error && (
        <p className="mb-3 text-xs bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 rounded-xl px-3 py-2">{error}</p>
      )}
      {!projects && !error && <p className="text-sm text-slate-400">Loading Plane projects…</p>}
      {projects && projects.length === 0 && <p className="text-sm text-slate-500">This workspace has no projects your API key can see.</p>}
      {projects && projects.length > 0 && (
        <div className="divide-y divide-slate-100 dark:divide-slate-800 border border-slate-200 dark:border-slate-800 rounded-xl">
          {projects.map((p) => (
            <div key={p.plane_project_id} className="flex items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold truncate">
                  {p.name} {p.identifier && <span className="font-mono text-xs text-slate-400">{p.identifier}</span>}
                </p>
                {p.description && <p className="text-[11px] text-slate-400 truncate">{p.description}</p>}
              </div>
              <button
                onClick={() => run(p)}
                disabled={busyId !== null}
                className={`text-xs font-semibold px-3 py-2 rounded-lg flex items-center gap-1.5 disabled:opacity-50 ${
                  p.imported_project_id ? "border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800" : "bg-brand-600 hover:bg-brand-500 text-white"
                }`}
              >
                {p.imported_project_id ? <RefreshCw className={`w-3.5 h-3.5 ${busyId === p.plane_project_id ? "animate-spin" : ""}`} /> : <Download className="w-3.5 h-3.5" />}
                {busyId === p.plane_project_id ? "Working…" : p.imported_project_id ? "Sync" : "Import"}
              </button>
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
