"use client";

import { useEffect, useState } from "react";
import { Download, FolderKanban, Link2, RefreshCw, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import type { EmployeeSummary, ImportReport, PlaneStatus, ProjectDetail, ProjectSummary } from "@/lib/types";
import PlaneConnectModal from "./PlaneConnectModal";
import PlaneImportModal from "./PlaneImportModal";
import ProjectPanel from "./ProjectPanel";
import { Card } from "./ui";

interface Props {
  projects: ProjectSummary[];
  activeProject: ProjectDetail | null;
  team: EmployeeSummary[];
  onSelect: (projectId: string) => void;
  onProjectChange: (project: ProjectDetail) => void;
  onProjectsChanged: (selectProjectId?: string) => Promise<void>;
  onEmployeeCreated: (employee: EmployeeSummary) => void;
  onGoToTeam: () => void;
  notify: (message: string, kind?: "success" | "error") => void;
}

const secondaryBtn =
  "text-xs font-semibold px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center gap-2 disabled:opacity-50";

function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
  return new Date(iso).toLocaleDateString();
}

export default function ProjectsPanel({ projects, activeProject, team, onSelect, onProjectChange, onProjectsChanged, onEmployeeCreated, onGoToTeam, notify }: Props) {
  const [plane, setPlane] = useState<PlaneStatus | null>(null);
  const [modal, setModal] = useState<"connect" | "import" | null>(null);
  const [syncing, setSyncing] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .planeStatus()
      .then((s) => !cancelled && setPlane(s))
      .catch(() => !cancelled && setPlane(null));
    return () => {
      cancelled = true;
    };
  }, []);

  const imported = async (report: ImportReport) => {
    setModal(null);
    await onProjectsChanged(report.project_id);
    notify(`Plane import: ${report.created} new, ${report.updated} updated, ${report.removed} removed task(s).${report.notes.length ? " See sync notes." : ""}`);
  };

  const sync = async (p: ProjectSummary) => {
    setSyncing(p.project_id);
    try {
      const { report, project } = await api.syncProject(p.project_id);
      await onProjectsChanged();
      if (activeProject?.project_id === p.project_id) onProjectChange(project);
      notify(`${p.name} synced: ${report.created} new, ${report.updated} updated, ${report.removed} removed.`);
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setSyncing(null);
    }
  };

  const remove = async (p: ProjectSummary) => {
    if (!window.confirm(`Remove "${p.name}" from PulseGuard? Nothing is deleted in Plane; you can import it again later.`)) return;
    try {
      await api.deleteProject(p.project_id);
      await onProjectsChanged(activeProject?.project_id === p.project_id ? "local" : undefined);
      notify(`${p.name} removed from PulseGuard.`);
    } catch (err) {
      notify((err as Error).message, "error");
    }
  };

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Projects</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {plane?.connected
                ? `Plane connected: ${plane.workspace_slug} (${plane.base_url})`
                : plane?.configured
                  ? `Plane connection failed: ${plane.error}`
                  : "Manage a local backlog, or import projects from Plane as the source of truth."}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => setModal("connect")} className={secondaryBtn}>
              <Link2 className="w-3.5 h-3.5" /> {plane?.configured ? "Plane Connection" : "Connect Plane"}
            </button>
            <button
              onClick={() => setModal("import")}
              disabled={!plane?.connected}
              title={plane?.connected ? undefined : "Connect Plane first"}
              className="bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs px-4 py-2.5 rounded-xl flex items-center gap-2 disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5" /> Import from Plane
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {projects.map((p) => {
            const active = activeProject?.project_id === p.project_id;
            return (
              <Card key={p.project_id} className={`p-5 flex flex-col justify-between gap-4 ${active ? "ring-2 ring-brand-500" : ""}`}>
                <div className="space-y-1">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-bold text-slate-900 dark:text-white flex items-center gap-2">
                      <FolderKanban className="w-4 h-4 text-brand-500" /> {p.name}
                    </h3>
                    <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full border border-slate-200 dark:border-slate-700 text-slate-500">
                      {p.source === "plane" ? "Plane" : "Local"}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 dark:text-slate-300">
                    {p.task_count} task{p.task_count === 1 ? "" : "s"}
                    {p.current_cycle ? ` • ${p.current_cycle.name}` : ""}
                    {p.attention_count > 0 && <span className="text-amber-600 dark:text-amber-400"> • {p.attention_count} need attention</span>}
                  </p>
                  {p.source === "plane" && <p className="text-[11px] text-slate-400">Last synced: {relativeTime(p.last_synced_at)}</p>}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => onSelect(p.project_id)}
                    disabled={active}
                    className="flex-1 bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold px-3 py-2 rounded-lg disabled:opacity-60"
                  >
                    {active ? "Open" : "Open"}
                  </button>
                  {p.source === "plane" && (
                    <>
                      <button onClick={() => sync(p)} disabled={syncing !== null || !plane?.connected} className="text-xs font-semibold px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center gap-1.5 disabled:opacity-50">
                        <RefreshCw className={`w-3.5 h-3.5 ${syncing === p.project_id ? "animate-spin" : ""}`} /> Sync
                      </button>
                      <button onClick={() => remove(p)} aria-label={`Remove ${p.name}`} className="p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/50">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      </div>

      {activeProject ? (
        <ProjectPanel
          key={activeProject.project_id}
          project={activeProject}
          team={team}
          onProjectChange={onProjectChange}
          onEmployeeCreated={onEmployeeCreated}
          onGoToTeam={onGoToTeam}
          notify={notify}
        />
      ) : (
        <Card className="p-10 text-center text-sm text-slate-500 dark:text-slate-400">The project could not be loaded. Is the FastAPI backend running?</Card>
      )}

      {modal === "connect" && (
        <PlaneConnectModal
          onConnected={(s) => {
            setPlane(s);
            setModal(null);
            notify(`Connected to Plane workspace ${s.workspace_slug}.`);
          }}
          onDisconnected={() => {
            setPlane({ configured: false, connected: false, config_source: null, base_url: null, workspace_slug: null, api_key_hint: null, user: null, error: null });
            setModal(null);
            notify("Plane disconnected.");
          }}
          onClose={() => setModal(null)}
        />
      )}
      {modal === "import" && <PlaneImportModal onImported={imported} onClose={() => setModal(null)} />}
    </div>
  );
}
