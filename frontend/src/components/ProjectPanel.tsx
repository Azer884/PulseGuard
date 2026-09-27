"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, ClipboardList, Pencil, Plus, RefreshCw, Trash2, Wand2 } from "lucide-react";
import { api } from "@/lib/api";
import type { EmployeeSummary, ProjectDetail, ProjectSettings, TaskInput, TaskView } from "@/lib/types";
import PlaneMembersPanel from "./PlaneMembersPanel";
import TaskFormModal from "./TaskFormModal";
import { Card } from "./ui";

interface Props {
  project: ProjectDetail;
  team: EmployeeSummary[];
  onProjectChange: (project: ProjectDetail) => void;
  onEmployeeCreated: (employee: EmployeeSummary) => void;
  onGoToTeam: () => void;
  notify: (message: string, kind?: "success" | "error") => void;
}

type Filter = "all" | "attention" | "simulated";

const secondaryBtn =
  "text-xs font-semibold px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center gap-2 disabled:opacity-50";
const primaryBtn = "bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs px-4 py-2.5 rounded-xl flex items-center gap-2 disabled:opacity-50";
const cellInput =
  "bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-brand-500";

const STATUS_STYLE: Record<string, string> = {
  started: "bg-brand-50 dark:bg-brand-950 text-brand-700 dark:text-brand-300",
  completed: "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300",
  cancelled: "bg-slate-100 dark:bg-slate-800 text-slate-500 line-through",
};

function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
  return new Date(iso).toLocaleDateString();
}

function estimateLabel(t: TaskView): string {
  if (!t.estimate_raw) return "—";
  if (t.estimate_kind === "points") return `${t.estimate_raw} pts`;
  return t.estimate_raw;
}

const EFFORT_SOURCE: Record<string, string> = { manual: "entered", plane_time: "Plane time", points: "from points", override: "your hours" };

export default function ProjectPanel({ project, team, onProjectChange, onEmployeeCreated, onGoToTeam, notify }: Props) {
  const [modal, setModal] = useState<{ task?: TaskView } | null>(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [hoursPerPoint, setHoursPerPoint] = useState(project.settings.hours_per_point?.toString() ?? "");
  const [editingHours, setEditingHours] = useState<Record<string, string>>({});

  const pid = project.project_id;
  const imported = project.source !== "local";
  const memberById = useMemo(() => new Map(team.map((m) => [m.employee_id, m])), [team]);
  const cycleName = useMemo(() => new Map(project.cycles.map((c) => [c.cycle_id, c.name])), [project.cycles]);

  const guarded = async (action: () => Promise<ProjectDetail | void>, success?: string) => {
    setBusy(true);
    try {
      const detail = await action();
      if (detail) onProjectChange(detail);
      if (success) notify(success);
    } catch (err) {
      notify((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const saveSettings = (patch: Partial<ProjectSettings>) => guarded(() => api.updateSettings(pid, { ...project.settings, ...patch }));

  const saveTask = async (input: TaskInput) => {
    const detail = modal?.task ? await api.updateTask(pid, modal.task.task_id, input) : await api.createTask(pid, input);
    onProjectChange(detail);
    setModal(null);
  };

  const setOverride = (t: TaskView, patch: { task_type?: string | null; effort_hours?: number | null }) =>
    guarded(() =>
      api.setTaskOverrides(pid, t.task_id, {
        task_type: patch.task_type !== undefined ? patch.task_type : t.task_type_override,
        effort_hours: patch.effort_hours !== undefined ? patch.effort_hours : t.effort_hours_override,
      }),
    );

  const commitHours = (t: TaskView) => {
    const raw = editingHours[t.task_id];
    setEditingHours((drafts) => {
      const next = { ...drafts };
      delete next[t.task_id];
      return next;
    });
    if (raw === undefined) return;
    const value = raw.trim() === "" ? null : Number(raw);
    if (value !== null && (!Number.isFinite(value) || value <= 0 || value > 1000)) {
      notify("Hours must be between 0 and 1000.", "error");
      return;
    }
    if (value !== t.effort_hours_override) void setOverride(t, { effort_hours: value });
  };

  const changeAssignee = (t: TaskView, value: string) => {
    const change =
      value === "__follow" ? { task_id: t.task_id, assigned_employee_id: null, follow_source: true } : { task_id: t.task_id, assigned_employee_id: value || null };
    void guarded(() => api.setAssignment(pid, [change]));
  };

  const sync = () =>
    guarded(async () => {
      const { report, project: detail } = await api.syncProject(pid);
      notify(`Synced from Plane: ${report.created} new, ${report.updated} updated, ${report.removed} removed.`);
      return detail;
    });

  const removeTask = (t: TaskView) => {
    if (!window.confirm(`Delete ${t.task_id} "${t.title}"? Tasks depending on it lose that dependency.`)) return;
    void guarded(() => api.deleteTask(pid, t.task_id), `${t.task_id} deleted.`);
  };

  const visibleTasks = project.tasks.filter((t) => (filter === "attention" ? t.issues.length > 0 : filter === "simulated" ? t.in_simulation : true));
  const unassignedSimulated = project.tasks.filter((t) => t.in_simulation && !t.assigned_employee_id).length;
  const twinsReady = team.filter((m) => m.twin_status !== "not_generated").length;
  const unitHours = Number(hoursPerPoint);
  const hoursPerPointDirty = hoursPerPoint !== (project.settings.hours_per_point?.toString() ?? "");
  const hasPoints = project.tasks.some((t) => t.estimate_kind === "points");

  const load = new Map<string, { tasks: number; hours: number }>();
  for (const t of project.tasks) {
    if (!t.in_simulation || !t.assigned_employee_id || t.effort_estimate_hours == null) continue;
    const entry = load.get(t.assigned_employee_id) ?? { tasks: 0, hours: 0 };
    load.set(t.assigned_employee_id, { tasks: entry.tasks + 1, hours: entry.hours + t.effort_estimate_hours });
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
            {project.name}
            {project.identifier && <span className="font-mono text-sm text-slate-400">{project.identifier}</span>}
            <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full border border-slate-200 dark:border-slate-700 text-slate-500">{imported ? "Plane" : "Local"}</span>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {imported ? `Source of truth: Plane · last synced ${relativeTime(project.last_synced_at)}` : "Tasks you manage directly in PulseGuard."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {imported ? (
            <button onClick={sync} disabled={busy} className={secondaryBtn}>
              <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} /> Sync Plane
            </button>
          ) : project.tasks.length === 0 ? (
            <button onClick={() => guarded(() => api.loadSampleBacklog(pid), "Sample backlog loaded.")} disabled={busy} className={secondaryBtn}>
              <ClipboardList className="w-3.5 h-3.5" /> Load sample backlog
            </button>
          ) : (
            <button
              onClick={() => window.confirm("Delete every task in this backlog and all assignments? This cannot be undone.") && guarded(() => api.clearTasks(pid), "Backlog cleared.")}
              disabled={busy}
              className={secondaryBtn}
            >
              <Trash2 className="w-3.5 h-3.5" /> Clear
            </button>
          )}
          <button
            onClick={() => guarded(() => api.autoAssign(pid), "Unassigned tasks assigned to the best-fitting twins.")}
            disabled={busy || unassignedSimulated === 0 || twinsReady === 0}
            title={twinsReady === 0 ? "Generate AI Twins first" : unassignedSimulated === 0 ? "Every simulated task is assigned" : undefined}
            className={secondaryBtn}
          >
            <Wand2 className="w-3.5 h-3.5 text-amber-500" /> Auto-assign {unassignedSimulated > 0 ? `(${unassignedSimulated})` : ""}
          </button>
          {!imported && (
            <button onClick={() => setModal({})} className={primaryBtn}>
              <Plus className="w-3.5 h-3.5" /> Add Task
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          ["Tasks (open)", `${project.task_count} (${project.open_task_count})`],
          ["In simulation", project.simulated_task_count],
          ["Need attention", project.attention_count],
          ["Team twins ready", `${twinsReady} / ${team.length}`],
        ].map(([label, value]) => (
          <Card key={label as string} className="p-4">
            <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
            <p className={`text-2xl font-bold mt-0.5 ${label === "Need attention" && Number(value) > 0 ? "text-amber-600 dark:text-amber-400" : ""}`}>{value}</p>
          </Card>
        ))}
      </div>

      {imported && (
        <Card className="p-4 flex flex-col lg:flex-row lg:items-center gap-4 text-xs">
          <div className="flex items-center gap-2">
            <label htmlFor="hpp" className="font-semibold whitespace-nowrap">1 point =</label>
            <input
              id="hpp"
              type="number"
              min={0.25}
              step="0.25"
              value={hoursPerPoint}
              onChange={(e) => setHoursPerPoint(e.target.value)}
              placeholder="—"
              className={`${cellInput} w-20`}
            />
            <span>hours</span>
            {hoursPerPointDirty && (
              <button
                disabled={busy || (hoursPerPoint !== "" && !(unitHours > 0 && unitHours <= 100))}
                onClick={() => saveSettings({ hours_per_point: hoursPerPoint === "" ? null : unitHours })}
                className="font-semibold text-brand-600 dark:text-brand-400 disabled:opacity-50"
              >
                Save
              </button>
            )}
            {hasPoints && !project.settings.hours_per_point && <span className="text-amber-600 dark:text-amber-400">Point estimates need a conversion to simulate.</span>}
          </div>
          <div className="flex items-center gap-2">
            <label htmlFor="cycle" className="font-semibold">Simulate</label>
            <select id="cycle" value={project.settings.cycle_id ?? ""} disabled={busy} onChange={(e) => saveSettings({ cycle_id: e.target.value || null })} className={cellInput}>
              <option value="">All cycles</option>
              {project.cycles.map((c) => (
                <option key={c.cycle_id} value={c.cycle_id}>
                  {c.name}
                  {project.current_cycle?.cycle_id === c.cycle_id ? " (current)" : ""}
                </option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={project.settings.include_completed} disabled={busy} onChange={(e) => saveSettings({ include_completed: e.target.checked })} className="accent-brand-600" />
            Include completed/cancelled
          </label>
        </Card>
      )}

      {imported && project.sync_notes.length > 0 && (
        <Card className="p-4 text-xs space-y-1 text-slate-600 dark:text-slate-300">
          <p className="font-semibold flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-500" /> Notes from the last sync
          </p>
          {project.sync_notes.map((n, i) => (
            <p key={i}>• {n}</p>
          ))}
        </Card>
      )}

      {team.length === 0 && (
        <Card className="p-4 flex items-center justify-between gap-4 text-sm">
          <span className="text-slate-500 dark:text-slate-400">Add team members before assigning tasks.</span>
          <button onClick={onGoToTeam} className={secondaryBtn}>Go to Team</button>
        </Card>
      )}

      {imported && <PlaneMembersPanel team={team} onEmployeeCreated={onEmployeeCreated} onMappingChanged={() => guarded(() => api.getProject(pid))} notify={notify} />}

      {project.tasks.length === 0 ? (
        <Card className="p-12 text-center space-y-2">
          <ClipboardList className="w-8 h-8 mx-auto text-brand-500" />
          <h3 className="font-bold text-lg">No tasks yet.</h3>
          <p className="text-sm text-slate-500 dark:text-slate-400">{imported ? "This Plane project has no work items." : "Add tasks or load the sample backlog to start simulating."}</p>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="flex items-center gap-1 p-3 border-b border-slate-200 dark:border-slate-800 text-xs">
            {(
              [
                ["all", `All (${project.tasks.length})`],
                ["attention", `Needs attention (${project.attention_count})`],
                ["simulated", `In simulation (${project.simulated_task_count})`],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setFilter(key)}
                className={`px-3 py-1.5 rounded-lg font-semibold ${filter === key ? "bg-brand-600 text-white" : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"}`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="bg-slate-100 dark:bg-slate-950 text-slate-500 dark:text-slate-400 text-xs font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4">Task</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">Estimate → hours</th>
                  <th className="py-3 px-4">Depends on</th>
                  <th className="py-3 px-4">Deadline</th>
                  <th className="py-3 px-4 min-w-48">Assignee</th>
                  {!imported && <th className="py-3 px-4" />}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {visibleTasks.map((t) => {
                  const hoursDraft = editingHours[t.task_id];
                  const followValue = t.assignment_source === "manual" ? (t.assigned_employee_id ?? "") : imported ? "__follow" : (t.assigned_employee_id ?? "");
                  const planeAssignee = t.assignment_source === "plane" && t.assigned_employee_id ? memberById.get(t.assigned_employee_id)?.name : null;
                  return (
                    <tr key={t.task_id} className={t.in_simulation ? "" : "opacity-60"}>
                      <td className="py-2.5 px-4 align-top">
                        <div className="flex items-baseline gap-2">
                          <span className="font-mono text-xs text-slate-400 whitespace-nowrap">{t.task_id}</span>
                          <span className="font-medium" title={t.description ?? undefined}>{t.title}</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5 mt-1 text-[10px]">
                          {t.status && <span className={`px-1.5 py-0.5 rounded ${STATUS_STYLE[t.status_group ?? ""] ?? "bg-slate-100 dark:bg-slate-800 text-slate-500"}`}>{t.status}</span>}
                          {t.priority && <span className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500 capitalize">{t.priority}</span>}
                          {t.cycle_id && <span className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500">{cycleName.get(t.cycle_id) ?? "cycle"}</span>}
                          {!t.in_simulation && <span className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500">not simulated</span>}
                        </div>
                        {t.issues.length > 0 && (
                          <ul className="mt-1 text-[11px] text-amber-700 dark:text-amber-400 space-y-0.5">
                            {t.issues.map((issue) => (
                              <li key={issue}>• {issue}</li>
                            ))}
                          </ul>
                        )}
                      </td>
                      <td className="py-2.5 px-4 align-top text-xs">
                        {imported ? (
                          <select
                            value={t.task_type_override ?? ""}
                            disabled={busy}
                            aria-label={`Task type for ${t.task_id}`}
                            onChange={(e) => setOverride(t, { task_type: e.target.value || null })}
                            className={`${cellInput} ${t.effective_task_type ? "" : "border-amber-300 dark:border-amber-700"}`}
                          >
                            <option value="">{t.task_type ? `${t.task_type} (from label)` : "Unknown"}</option>
                            {project.task_types.map((type) => (
                              <option key={type} value={type}>{type}</option>
                            ))}
                          </select>
                        ) : (
                          t.effective_task_type
                        )}
                      </td>
                      <td className="py-2.5 px-4 align-top text-xs whitespace-nowrap">
                        {imported ? (
                          <div className="space-y-1">
                            <span className="text-slate-500">{estimateLabel(t)}</span>
                            <div className="flex items-center gap-1">
                              <input
                                type="number"
                                min={0.5}
                                step="0.5"
                                aria-label={`Hours for ${t.task_id}`}
                                value={hoursDraft ?? t.effort_hours_override?.toString() ?? ""}
                                placeholder={t.effort_estimate_hours != null ? String(t.effort_estimate_hours) : "hours"}
                                onChange={(e) => setEditingHours((h) => ({ ...h, [t.task_id]: e.target.value }))}
                                onBlur={() => commitHours(t)}
                                onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                                className={`${cellInput} w-20 ${t.effort_estimate_hours == null ? "border-amber-300 dark:border-amber-700" : ""}`}
                              />
                              <span className="text-slate-400">h</span>
                            </div>
                            {t.effort_estimate_hours != null && <span className="text-[10px] text-slate-400">{t.effort_estimate_hours} h · {EFFORT_SOURCE[t.effort_source ?? ""]}</span>}
                          </div>
                        ) : (
                          <span className="tabular-nums">{t.effort_estimate_hours} h</span>
                        )}
                      </td>
                      <td className="py-2.5 px-4 align-top text-xs font-mono text-slate-500">
                        {t.dependencies.join(", ") || "—"}
                        {t.external_dependency_ids.length > 0 && <span className="block text-[10px] text-amber-600">+{t.external_dependency_ids.length} external</span>}
                      </td>
                      <td className="py-2.5 px-4 align-top text-xs whitespace-nowrap">{t.deadline ?? "—"}</td>
                      <td className="py-2.5 px-4 align-top">
                        <select
                          value={followValue}
                          disabled={busy}
                          aria-label={`Assignee for ${t.task_id}`}
                          onChange={(e) => changeAssignee(t, e.target.value)}
                          className={`w-full ${cellInput} ${t.assigned_employee_id || !t.in_simulation ? "" : "border-amber-300 dark:border-amber-700"}`}
                        >
                          {imported && (
                            <option value="__follow">
                              Plane assignee{planeAssignee ? `: ${planeAssignee}` : t.source_assignee_ids.length ? " (unmatched)" : " (none)"}
                            </option>
                          )}
                          <option value="">Unassigned</option>
                          {t.assigned_employee_id && !memberById.has(t.assigned_employee_id) && <option value={t.assigned_employee_id}>{t.assigned_employee_id} (removed)</option>}
                          {team.map((m) => (
                            <option key={m.employee_id} value={m.employee_id}>
                              {m.name} · {m.current_role}
                              {m.twin_status === "not_generated" ? " (no twin)" : ""}
                            </option>
                          ))}
                        </select>
                        {t.assignment_source === "manual" && imported && <span className="text-[10px] text-slate-400">overrides Plane</span>}
                      </td>
                      {!imported && (
                        <td className="py-2.5 px-4 align-top whitespace-nowrap text-right">
                          <button onClick={() => setModal({ task: t })} aria-label={`Edit ${t.task_id}`} className="p-1.5 rounded-lg text-slate-400 hover:text-brand-600 hover:bg-slate-100 dark:hover:bg-slate-800">
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button onClick={() => removeTask(t)} aria-label={`Delete ${t.task_id}`} className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/50">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {team.length > 0 && project.simulated_task_count > 0 && (
        <Card className="p-6 space-y-3">
          <div>
            <h3 className="font-bold text-lg">Planned Load</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Existing workload plus assigned hours of simulated tasks, against weekly availability. The simulation also adjusts hours by each twin&apos;s speed.
            </p>
          </div>
          <div className="space-y-2">
            {team.map((m) => {
              const entry = load.get(m.employee_id) ?? { tasks: 0, hours: 0 };
              const total = m.current_workload_hours + entry.hours;
              const pct = Math.round((total / m.weekly_available_hours) * 100);
              const over = total > m.weekly_available_hours;
              return (
                <div key={m.employee_id} className="grid grid-cols-[minmax(0,10rem)_1fr_auto] items-center gap-3 text-xs">
                  <span className="truncate font-medium">{m.name}</span>
                  <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                    <div className={`h-full ${over ? "bg-rose-500" : "bg-brand-500"}`} style={{ width: `${Math.min(100, pct)}%` }} />
                  </div>
                  <span className={`tabular-nums ${over ? "text-rose-600 dark:text-rose-400 font-semibold" : "text-slate-500"}`}>
                    {m.current_workload_hours} + {Math.round(entry.hours * 10) / 10} h / {m.weekly_available_hours} h · {entry.tasks} task{entry.tasks === 1 ? "" : "s"}
                  </span>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {modal && <TaskFormModal task={modal.task} tasks={project.tasks} taskTypes={project.task_types} onSubmit={saveTask} onClose={() => setModal(null)} />}
    </div>
  );
}
