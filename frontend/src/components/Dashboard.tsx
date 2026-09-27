"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Camera,
  ClipboardList,
  Download,
  FileCode,
  Gauge,
  Moon,
  Network,
  Search,
  Sun,
  TriangleAlert,
  Undo2,
  UserRound,
  Users,
  Wand2,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { MODE_LABELS } from "@/lib/types";
import type { ActionableSwap, AssignmentChange, EmployeeResult, EmployeeSummary, Mode, ProjectDetail, ProjectSummary, Rotation, SimulateResponse } from "@/lib/types";
import DeltaMetricsPanel from "./DeltaMetricsPanel";
import ProjectsPanel from "./ProjectsPanel";
import RotationsTable from "./RotationsTable";
import SimulationLoader, { SIMULATION_DURATION_MS } from "./SimulationLoader";
import SwapsList from "./SwapsList";
import TeamPanel from "./TeamPanel";
import TwinCard from "./TwinCard";
import { Card } from "./ui";

type Tab = "team" | "projects" | "simulation" | "payload";
type TwinSort = "risk" | "stamina" | "compatibility" | "name";
type Toast = { message: string; kind: "success" | "error" } | null;
type RunLogEntry = { id: number; text: string; time: string };
type UndoState = { projectId: string; label: string; changes: AssignmentChange[]; mode: Mode; target: string | null } | null;

const RISK_RANK: Record<string, number> = { Critical: 3, Warning: 2, Normal: 1 };

function compareNullable(a: number | null | undefined, b: number | null | undefined): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  return b - a;
}

interface Props {
  initialTeam: EmployeeSummary[] | null;
  initialProjects: ProjectSummary[];
  initialProject: ProjectDetail | null;
  initialSimulation: SimulateResponse | null;
  initialError: string | null;
}

export default function Dashboard({ initialTeam, initialProjects, initialProject, initialSimulation, initialError }: Props) {
  const [tab, setTab] = useState<Tab>("team");
  const [dark, setDark] = useState(true);
  const [team, setTeamState] = useState<EmployeeSummary[] | null>(initialTeam);
  const [projects, setProjects] = useState<ProjectSummary[]>(initialProjects);
  const [activeProjectId, setActiveProjectId] = useState(initialProject?.project_id ?? "local");
  const [project, setProjectState] = useState<ProjectDetail | null>(initialProject);
  const [sim, setSim] = useState<SimulateResponse | null>(initialSimulation);
  const [stale, setStale] = useState(false);
  const [busyMode, setBusyMode] = useState<Mode | null>(null);
  const [applying, setApplying] = useState(false);
  const [undo, setUndo] = useState<UndoState>(null);
  const [toast, setToast] = useState<Toast>(
    initialError ? { message: `Backend request failed: ${initialError}. Is the FastAPI backend running?`, kind: "error" } : null,
  );
  const [runLog, setRunLog] = useState<RunLogEntry[]>([]);
  const [twinSort, setTwinSort] = useState<TwinSort>("risk");
  const [twinQuery, setTwinQuery] = useState("");
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const logId = useRef(0);

  const notify = useCallback((message: string, kind: "success" | "error" = "success") => {
    setToast({ message, kind });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), kind === "error" ? 8000 : 4000);
  }, []);

  const log = useCallback((text: string) => {
    const id = ++logId.current;
    setRunLog((entries) => [{ id, text, time: new Date().toLocaleTimeString() }, ...entries].slice(0, 12));
  }, []);

  // Any change to the team or project invalidates the last simulation.
  const setTeam: typeof setTeamState = useCallback((value) => {
    setTeamState(value);
    setStale(true);
  }, []);
  const setProject = useCallback((detail: ProjectDetail) => {
    setProjectState(detail);
    setProjects((list) => list.map((p) => (p.project_id === detail.project_id ? detail : p)));
    setStale(true);
  }, []);

  const reloadProjects = useCallback(
    async (selectProjectId?: string) => {
      try {
        const [list, detail] = await Promise.all([api.listProjects(), api.getProject(selectProjectId ?? activeProjectId)]);
        setProjects(list);
        if (selectProjectId) setActiveProjectId(selectProjectId);
        setProject(detail);
      } catch (err) {
        notify(`Could not load projects: ${(err as Error).message}`, "error");
      }
    },
    [activeProjectId, notify, setProject],
  );

  const selectProject = async (projectId: string) => {
    setActiveProjectId(projectId);
    setSim(null);
    setUndo(null);
    try {
      setProject(await api.getProject(projectId));
    } catch (err) {
      notify(`Could not load project: ${(err as Error).message}`, "error");
    }
  };

  const run = useCallback(
    async (mode: Mode, target?: string | null, projectId: string = activeProjectId) => {
      setBusyMode(mode);
      try {
        // Hold the loader for a minimum time so the run reads as a simulation; results are the engine's.
        const [response] = await Promise.all([
          api.simulate(projectId, mode, target),
          new Promise((resolve) => setTimeout(resolve, SIMULATION_DURATION_MS[mode])),
        ]);
        setSim(response);
        setStale(false);
        const name = target ? response.context.employees.find((e) => e.employee_id === target)?.name : undefined;
        const label = `${MODE_LABELS[mode]}${name ? ` for ${name}` : ""}`;
        log(`${label}: ${response.analysis.warnings.length} warning(s).`);
        if (mode !== "status_snapshot") notify(`${label} complete.`);
        return response;
      } catch (err) {
        notify(`Simulation failed: ${(err as Error).message}`, "error");
        return null;
      } finally {
        setBusyMode(null);
      }
    },
    [activeProjectId, log, notify],
  );

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  const openTab = (next: Tab) => {
    setTab(next);
    if (next === "projects") void reloadProjects();
    if (next === "simulation" && (stale || !sim) && !busyMode) void run("status_snapshot");
  };

  /** Apply assignment changes, remember how to undo them, then re-run the simulation. */
  const applyChanges = async (changes: AssignmentChange[], label: string, rerun: Mode, target: string | null = null) => {
    setApplying(true);
    try {
      const current = await api.getProject(activeProjectId);
      const before = new Map(current.tasks.map((t) => [t.task_id, t]));
      // Restore exactly: a manual choice, or following the source tool's assignee again.
      const inverse: AssignmentChange[] = changes.map((c) => {
        const task = before.get(c.task_id);
        if (task?.assignment_source === "manual") return { task_id: c.task_id, assigned_employee_id: task.assigned_employee_id };
        if (task?.source === "plane") return { task_id: c.task_id, assigned_employee_id: null, follow_source: true };
        return { task_id: c.task_id, assigned_employee_id: null };
      });
      setProject(await api.setAssignment(activeProjectId, changes));
      setUndo({ projectId: activeProjectId, label, changes: inverse, mode: rerun, target });
      log(`Applied: ${label}.`);
      await run(rerun, target);
    } catch (err) {
      notify(`Could not apply change: ${(err as Error).message}`, "error");
    } finally {
      setApplying(false);
    }
  };

  const undoLast = async () => {
    if (!undo) return;
    setApplying(true);
    try {
      setProject(await api.setAssignment(undo.projectId, undo.changes));
      log(`Undid: ${undo.label}.`);
      const { mode, target } = undo;
      setUndo(null);
      await run(mode, target);
    } catch (err) {
      notify(`Undo failed: ${(err as Error).message}`, "error");
    } finally {
      setApplying(false);
    }
  };

  const nameOf = useCallback(
    (id: string) => sim?.context.employees.find((e) => e.employee_id === id)?.name ?? team?.find((e) => e.employee_id === id)?.name ?? id,
    [sim, team],
  );
  const taskById = useMemo(() => new Map((sim?.context.tasks ?? []).map((t) => [t.task_id, t])), [sim]);
  const taskLabel = useCallback((id: string) => {
    const task = taskById.get(id);
    return task ? `${id} ${task.title}` : id;
  }, [taskById]);

  const applyRotation = (rotation: Rotation) => {
    const current = new Map((sim?.payload.current_assignment ?? []).map((a) => [a.task_id, a.assigned_employee_id]));
    const changes = rotation.assignments
      .filter((a) => current.get(a.task_id) !== a.assigned_employee_id)
      .map((a) => ({ task_id: a.task_id, assigned_employee_id: a.assigned_employee_id }));
    void applyChanges(changes, `rotation #${(sim?.analysis.rotations_ranked.indexOf(rotation) ?? 0) + 1} (${changes.length} task change${changes.length === 1 ? "" : "s"})`, "optimize_fastest");
  };

  const applySwap = (swap: ActionableSwap) => {
    const [from, to] = swap.swap_between;
    const changes: AssignmentChange[] = [{ task_id: swap.tasks_affected[0], assigned_employee_id: to }];
    if (swap.tasks_affected[1]) changes.push({ task_id: swap.tasks_affected[1], assigned_employee_id: from });
    const mode = sim?.analysis.mode ?? "resolve_burnout_all";
    const target = mode === "resolve_burnout_single" ? (sim?.payload.target_employee_id ?? null) : null;
    void applyChanges(changes, `swap ${nameOf(from)} → ${nameOf(to)}`, mode, target);
  };

  const exportReport = () => {
    if (!sim) return;
    const blob = new Blob([JSON.stringify({ generated_at: new Date().toISOString(), payload: sim.payload, analysis: sim.analysis, context: sim.context }, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `pulseguard-${sim.analysis.mode}-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const result = sim?.analysis ?? null;
  const busy = busyMode !== null || applying;
  const scores = useMemo(() => new Map<string, EmployeeResult>((result?.employees ?? []).map((e) => [e.employee_id, e])), [result]);
  const usesTopRotation = result?.mode === "optimize_fastest" && result.rotations_ranked.length > 0;
  const twins = useMemo(() => sim?.payload.employees ?? [], [sim]);

  const tasksByEmployee = useMemo(() => {
    const assignment = usesTopRotation ? result!.rotations_ranked[0].assignments : (sim?.payload.current_assignment ?? []);
    const map = new Map<string, { task_id: string; task_type: string; title?: string }[]>();
    for (const a of assignment) {
      const task = taskById.get(a.task_id);
      if (task) map.set(a.assigned_employee_id, [...(map.get(a.assigned_employee_id) ?? []), { task_id: task.task_id, task_type: task.effective_task_type ?? "Unknown", title: task.title }]);
    }
    return map;
  }, [sim, result, usesTopRotation, taskById]);

  const sortedTwins = useMemo(() => {
    const q = twinQuery.trim().toLowerCase();
    return twins
      .filter((t) => !q || t.name.toLowerCase().includes(q) || t.current_role.toLowerCase().includes(q))
      .sort((a, b) => {
        const sa = scores.get(a.employee_id);
        const sb = scores.get(b.employee_id);
        let cmp = 0;
        if (twinSort === "stamina") cmp = compareNullable(sa?.stamina, sb?.stamina);
        else if (twinSort === "compatibility") cmp = compareNullable(sa?.compatibility_pct, sb?.compatibility_pct);
        else if (twinSort === "risk") cmp = (RISK_RANK[sb?.risk_level ?? ""] ?? 0) - (RISK_RANK[sa?.risk_level ?? ""] ?? 0);
        return cmp || a.name.localeCompare(b.name);
      });
  }, [twins, scores, twinSort, twinQuery]);

  const atRiskCount = result?.employees.filter((e) => e.risk_level !== "Normal").length;
  const isBurnoutMode = result?.mode === "resolve_burnout_all" || result?.mode === "resolve_burnout_single";
  const canSimulate = twins.length > 0 && (sim?.context.tasks.length ?? 0) > 0;

  const navButton = (id: Tab, label: string, Icon: typeof Network) => (
    <button
      key={id}
      onClick={() => openTab(id)}
      className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all ${
        tab === id
          ? "bg-brand-50 dark:bg-brand-950/80 text-brand-700 dark:text-brand-300 font-semibold border border-brand-200 dark:border-brand-800/50"
          : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
      }`}
    >
      <Icon className="w-4 h-4" />
      <span>{label}</span>
    </button>
  );
  const navItems: [Tab, string, typeof Network][] = [
    ["team", "Team", UserRound],
    ["projects", "Projects", ClipboardList],
    ["simulation", "Twins & Simulation", Network],
    ["payload", "Engine Payload", FileCode],
  ];

  const secondaryBtn =
    "bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold text-xs px-4 py-2.5 rounded-xl flex items-center gap-2 disabled:opacity-50";
  const primaryBtn = "bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs px-4 py-2.5 rounded-xl flex items-center gap-2 disabled:opacity-50";

  return (
    <>
      <header className="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 sticky top-0 z-30 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 to-indigo-400 flex items-center justify-center text-white shadow-md shadow-brand-500/20">
            <Users className="w-5 h-5" />
          </div>
          <div>
            <h1 className="font-bold text-slate-900 dark:text-white tracking-tight text-lg">
              PulseGuard{" "}
              <span className="text-brand-600 dark:text-brand-400 font-semibold text-xs px-2 py-0.5 bg-brand-50 dark:bg-brand-950 rounded-full border border-brand-200 dark:border-brand-800 ml-1">
                AI Twins
              </span>
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">AI Scrum Master · Team Twin Simulation</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-2 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 px-3 py-1.5 rounded-full text-xs font-medium border border-slate-200 dark:border-slate-700">
            <span className={`w-2 h-2 rounded-full ${busy ? "bg-brand-500 animate-pulse" : stale ? "bg-amber-500" : result ? "bg-emerald-500" : "bg-slate-400"}`} />
            <span>{busyMode ? `Running: ${MODE_LABELS[busyMode]}` : applying ? "Applying change…" : stale ? "Simulation out of date" : result ? "Engine ready" : "Engine idle"}</span>
          </div>
          <button
            onClick={() => setDark((d) => !d)}
            className="p-2 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700"
            title="Toggle light/dark mode"
          >
            {dark ? <Sun className="w-5 h-5 text-amber-400" /> : <Moon className="w-5 h-5 text-slate-700" />}
          </button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <aside className="w-64 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 flex-col justify-between p-4 hidden md:flex">
          <nav className="space-y-1">
            <div className="px-3 pb-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">Modules</div>
            {navItems.map(([id, label, Icon]) => navButton(id, label, Icon))}
          </nav>
          <div className="bg-slate-50 dark:bg-slate-950 p-4 rounded-xl border border-slate-200 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400 space-y-2">
            <div className="font-semibold text-slate-700 dark:text-slate-300">Activity</div>
            <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1 text-[11px]">
              {runLog.length === 0 ? (
                <p className="text-slate-400 italic">No runs yet.</p>
              ) : (
                runLog.map((entry) => (
                  <div key={entry.id} className="border-l-2 border-brand-500 pl-2 py-0.5">
                    <p className="text-slate-700 dark:text-slate-300 leading-tight">{entry.text}</p>
                    <span className="text-[9px] text-slate-400">{entry.time}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6">
          <div className="grid grid-cols-2 md:hidden gap-2">{navItems.map(([id, label, Icon]) => navButton(id, label, Icon))}</div>

          {toast && (
            <div
              className={`px-4 py-3 rounded-xl flex items-center justify-between border text-sm ${
                toast.kind === "error"
                  ? "bg-rose-50 dark:bg-rose-950 border-rose-200 dark:border-rose-800 text-rose-800 dark:text-rose-200"
                  : "bg-brand-50 dark:bg-brand-950 border-brand-200 dark:border-brand-800 text-brand-800 dark:text-brand-200"
              }`}
            >
              <p>{toast.message}</p>
              <button onClick={() => setToast(null)} className="px-2" aria-label="Dismiss">
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          <div className={tab === "team" ? "" : "hidden"}>
            <TeamPanel team={team} setTeam={setTeam} notify={notify} />
          </div>

          {tab === "projects" && (
            <ProjectsPanel
              projects={projects}
              activeProject={project}
              team={team ?? []}
              onSelect={selectProject}
              onProjectChange={setProject}
              onProjectsChanged={reloadProjects}
              onEmployeeCreated={(employee) => setTeam((t) => [...(t ?? []), employee])}
              onGoToTeam={() => openTab("team")}
              notify={notify}
            />
          )}

          {tab === "simulation" && (
            <div className="space-y-6">
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                <div>
                  <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Twins &amp; Simulation</h2>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Runs on your team&apos;s AI Twins and the selected project. All numbers come from the deterministic engine.
                  </p>
                  <div className="mt-2 flex items-center gap-2 text-xs">
                    <label htmlFor="sim-project" className="font-semibold text-slate-500">Project</label>
                    <select
                      id="sim-project"
                      value={activeProjectId}
                      disabled={busy}
                      onChange={async (e) => {
                        const next = e.target.value;
                        await selectProject(next);
                        await run("status_snapshot", null, next);
                      }}
                      className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-brand-500"
                    >
                      {projects.map((p) => (
                        <option key={p.project_id} value={p.project_id}>
                          {p.name} ({p.source === "plane" ? "Plane" : "Local"})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button disabled={busy} onClick={() => run("status_snapshot")} className={secondaryBtn}>
                    <Camera className="w-3.5 h-3.5 text-slate-400" /> Status Snapshot
                  </button>
                  <button disabled={busy || !canSimulate} onClick={() => run("optimize_fastest")} className={primaryBtn}>
                    <Gauge className="w-3.5 h-3.5" /> Optimize for Fastest Delivery
                  </button>
                  <button disabled={busy || !canSimulate} onClick={() => run("resolve_burnout_all")} className={secondaryBtn}>
                    <Wand2 className="w-3.5 h-3.5 text-amber-500" /> Resolve All Burnout Risks
                  </button>
                  <button disabled={!sim} onClick={exportReport} className={secondaryBtn} title="Download the payload and results as JSON">
                    <Download className="w-3.5 h-3.5" /> Export
                  </button>
                </div>
              </div>

              {stale && (
                <Card className="p-4 flex items-center justify-between gap-4 text-sm border-amber-300 dark:border-amber-800">
                  <span className="text-amber-700 dark:text-amber-300">The team or backlog changed since this simulation ran.</span>
                  <button disabled={busy} onClick={() => run("status_snapshot")} className={secondaryBtn}>Refresh</button>
                </Card>
              )}

              {undo && (
                <Card className="p-4 flex items-center justify-between gap-4 text-sm">
                  <span>
                    Applied <span className="font-semibold">{undo.label}</span> to the project assignment.
                  </span>
                  <button disabled={busy} onClick={undoLast} className={secondaryBtn}>
                    <Undo2 className="w-3.5 h-3.5" /> Undo
                  </button>
                </Card>
              )}

              {!sim ? (
                <Card className="p-10 text-center text-sm text-slate-500 dark:text-slate-400">No simulation yet. Is the FastAPI backend running?</Card>
              ) : twins.length === 0 ? (
                <Card className="p-12 text-center space-y-3">
                  <h3 className="font-bold text-lg">No AI Twins to simulate yet.</h3>
                  <p className="text-sm text-slate-500 dark:text-slate-400">Add team members and generate their AI Twins first.</p>
                  <button onClick={() => openTab("team")} className={`${primaryBtn} mx-auto`}>Go to Team</button>
                </Card>
              ) : sim.context.tasks.length === 0 ? (
                <Card className="p-12 text-center space-y-3">
                  <h3 className="font-bold text-lg">No simulatable tasks in {sim.context.project_name}.</h3>
                  <p className="text-sm text-slate-500 dark:text-slate-400">
                    {sim.context.excluded_tasks.length > 0
                      ? `${sim.context.excluded_tasks.length} task(s) need an hour estimate before they can be simulated.`
                      : "Add tasks, load the sample backlog, or import a Plane project."}
                  </p>
                  <button onClick={() => openTab("projects")} className={`${primaryBtn} mx-auto`}>Go to Projects</button>
                </Card>
              ) : (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {[
                      { label: "Twins simulated", value: `${twins.length} / ${twins.length + sim.context.excluded_employees.length}` },
                      { label: "At risk (Warning + Critical)", value: atRiskCount ?? "—", accent: true },
                      { label: "Backlog tasks", value: `${sim.context.tasks.length} (${sim.context.unassigned_task_ids.length} unassigned)` },
                      { label: "Rotations evaluated", value: result?.mode === "optimize_fastest" ? result.rotations_evaluated : "—" },
                    ].map((s) => (
                      <Card key={s.label} className="p-4">
                        <p className="text-xs text-slate-500 dark:text-slate-400">{s.label}</p>
                        <p className={`text-2xl font-bold mt-0.5 ${s.accent ? "text-amber-600 dark:text-amber-400" : ""}`}>{s.value}</p>
                      </Card>
                    ))}
                  </div>

                  {(sim.context.excluded_employees.length > 0 || sim.context.unassigned_task_ids.length > 0 || sim.context.excluded_tasks.length > 0) && (
                    <Card className="p-4 space-y-2 text-xs text-slate-600 dark:text-slate-300">
                      {sim.context.excluded_employees.length > 0 && (
                        <div className="flex items-center justify-between gap-4">
                          <span>
                            Not simulated (no AI Twin): <span className="font-semibold">{sim.context.excluded_employees.map((e) => e.name).join(", ")}</span>
                          </span>
                          <button onClick={() => openTab("team")} className="text-brand-600 dark:text-brand-400 font-semibold whitespace-nowrap">Generate twins</button>
                        </div>
                      )}
                      {sim.context.unassigned_task_ids.length > 0 && (
                        <div className="flex items-center justify-between gap-4">
                          <span>
                            Unassigned tasks: <span className="font-semibold">{sim.context.unassigned_task_ids.map(taskLabel).join(", ")}</span>. Optimize still proposes full assignments; delta metrics need a complete baseline.
                          </span>
                          <button onClick={() => openTab("projects")} className="text-brand-600 dark:text-brand-400 font-semibold whitespace-nowrap">Assign</button>
                        </div>
                      )}
                      {sim.context.excluded_tasks.length > 0 && (
                        <div className="flex items-center justify-between gap-4">
                          <span>
                            Not simulated (no hour estimate): <span className="font-semibold">{sim.context.excluded_tasks.map((t) => t.task_id).join(", ")}</span>
                          </span>
                          <button onClick={() => openTab("projects")} className="text-brand-600 dark:text-brand-400 font-semibold whitespace-nowrap">Add hours</button>
                        </div>
                      )}
                    </Card>
                  )}

                  <DeltaMetricsPanel result={result} />

                  {result && result.warnings.length > 0 && (
                    <details className="bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-2xl p-5" open={result.warnings.length <= 4}>
                      <summary className="font-bold text-amber-800 dark:text-amber-300 text-sm flex items-center gap-2 cursor-pointer">
                        <TriangleAlert className="w-4 h-4" /> Engine warnings ({result.warnings.length})
                      </summary>
                      <ul className="mt-2 space-y-1 text-xs text-amber-900 dark:text-amber-200 list-disc pl-5">
                        {result.warnings.map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                      </ul>
                    </details>
                  )}

                  {result && isBurnoutMode && (
                    <SwapsList swaps={result.recommendations.actionable_swaps} nameOf={nameOf} taskLabel={taskLabel} busy={busy} onApply={applySwap} />
                  )}
                  {result && result.mode === "optimize_fastest" && (
                    <RotationsTable result={result} baseline={sim.payload.current_assignment} nameOf={nameOf} taskLabel={taskLabel} busy={busy} onApply={applyRotation} />
                  )}

                  <div className="space-y-4">
                    <Card className="p-4 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                      <div className="flex items-center gap-3 flex-wrap">
                        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Sort twins:</span>
                        <div className="inline-flex rounded-xl bg-slate-100 dark:bg-slate-950 p-1 border border-slate-200 dark:border-slate-800 gap-1">
                          {(["risk", "stamina", "compatibility", "name"] as const).map((key) => (
                            <button
                              key={key}
                              onClick={() => setTwinSort(key)}
                              className={`px-3 py-1.5 rounded-lg text-xs font-semibold capitalize transition-all ${
                                twinSort === key ? "bg-brand-600 text-white" : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                              }`}
                            >
                              {key}
                            </button>
                          ))}
                        </div>
                        <div className="relative">
                          <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
                          <input
                            value={twinQuery}
                            onChange={(e) => setTwinQuery(e.target.value)}
                            placeholder="Filter twins"
                            className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl pl-8 pr-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-brand-500 w-44"
                          />
                        </div>
                      </div>
                      {result && (
                        <div className="text-xs text-slate-500 dark:text-slate-400">
                          Last run: <span className="font-semibold text-slate-800 dark:text-white">{MODE_LABELS[result.mode]}</span>
                          {usesTopRotation && " · cards show the top rotation"}
                        </div>
                      )}
                    </Card>

                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                      {sortedTwins.map((twin) => (
                        <TwinCard
                          key={twin.employee_id}
                          employee={twin}
                          score={scores.get(twin.employee_id)}
                          tasks={tasksByEmployee.get(twin.employee_id) ?? []}
                          scoredAgainst={usesTopRotation ? "top rotation" : "current assignment"}
                          busy={busy}
                          onFindSwap={(id) => run("resolve_burnout_single", id)}
                        />
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {busyMode && tab === "simulation" && (
            <SimulationLoader mode={busyMode} projectName={projects.find((p) => p.project_id === activeProjectId)?.name} />
          )}

          {tab === "payload" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Engine Payload</h2>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  The exact request built from your team&apos;s twins and the backlog for <code>POST /api/ai-twins/analyze</code>, and the engine&apos;s response.
                </p>
              </div>
              {sim ? (
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                  {(
                    [
                      ["Request", sim.payload],
                      ["Response", sim.analysis],
                    ] as const
                  ).map(([label, value]) => (
                    <Card key={label} className="p-4 min-w-0">
                      <h3 className="text-sm font-semibold mb-2">{label}</h3>
                      <pre className="text-xs overflow-auto max-h-[70vh] text-slate-600 dark:text-slate-300">{JSON.stringify(value, null, 2)}</pre>
                    </Card>
                  ))}
                </div>
              ) : (
                <Card className="p-10 text-center text-sm text-slate-500 dark:text-slate-400">No simulation has run yet.</Card>
              )}
            </div>
          )}
        </main>
      </div>
    </>
  );
}
