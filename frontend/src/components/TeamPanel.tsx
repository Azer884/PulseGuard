"use client";

import { useState, type Dispatch, type SetStateAction } from "react";
import { Bot, CheckSquare, Eye, FileJson, Pencil, Plus, MessageSquare, RefreshCw, Sparkles, Trash2, Users, X } from "lucide-react";
import { api } from "@/lib/api";
import type { AITwin, EmployeeInput, EmployeeSummary, ImportResult, TwinStatus } from "@/lib/types";
import EmployeeFormModal from "./EmployeeFormModal";
import JsonImportModal from "./JsonImportModal";
import SlackImportModal from "./SlackImportModal";
import TwinProfileModal from "./TwinProfileModal";
import { Card, initials } from "./ui";

type ModalState =
  | { kind: "create" }
  | { kind: "json" }
  | { kind: "slack" }
  | { kind: "edit"; employeeId: string }
  | { kind: "twin"; twin: AITwin }
  | null;

interface Props {
  team: EmployeeSummary[] | null;
  setTeam: Dispatch<SetStateAction<EmployeeSummary[] | null>>;
  notify: (message: string, kind?: "success" | "error") => void;
}

const STATUS_STYLES: Record<TwinStatus, { label: string; className: string }> = {
  generated: { label: "Generated", className: "text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950 border-emerald-200 dark:border-emerald-800" },
  outdated: { label: "Outdated", className: "text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950 border-amber-200 dark:border-amber-800" },
  not_generated: { label: "Not generated", className: "text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-slate-700" },
};

const SOURCE_LABELS: Record<EmployeeSummary["source"], string | null> = { manual: null, slack: "Slack", json_import: "JSON" };

const secondaryBtn =
  "text-xs font-semibold px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center gap-2 disabled:opacity-50";

export default function TeamPanel({ team, setTeam, notify }: Props) {
  const [modal, setModal] = useState<ModalState>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selection, setSelection] = useState<string[] | null>(null);
  const [removing, setRemoving] = useState(false);

  const reload = async () => {
    setLoading(true);
    try {
      setTeam(await api.listEmployees());
    } catch (err) {
      notify(`Could not load team: ${(err as Error).message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  const setStatus = (id: string, twin_status: TwinStatus) =>
    setTeam((t) => t?.map((e) => (e.employee_id === id ? { ...e, twin_status } : e)) ?? t);

  const nameOf = (id: string) => team?.find((e) => e.employee_id === id)?.name ?? id;

  const create = async (input: EmployeeInput) => {
    const created = await api.createEmployee(input);
    setTeam((t) => [...(t ?? []), created]);
    setModal(null);
    notify(`${created.name} added to the team. Generate their AI Twin next.`);
  };

  const imported = (result: ImportResult, via: string) => {
    setTeam((t) => [...(t ?? []), ...result.created]);
    setModal(null);
    const skipped = result.skipped.length ? ` ${result.skipped.length} skipped (already on the team).` : "";
    notify(`Imported ${result.created.length} employee${result.created.length === 1 ? "" : "s"} from ${via}.${skipped}`);
  };

  const update = async (id: string, input: EmployeeInput) => {
    const updated = await api.updateEmployee(id, input);
    setTeam((t) => t?.map((e) => (e.employee_id === id ? updated : e)) ?? t);
    setModal(null);
    notify(updated.twin_status === "outdated" ? `${updated.name} updated. Their AI Twin is now outdated — regenerate it.` : `${updated.name} updated.`);
  };

  const removeFromState = (ids: string[]) => {
    const gone = new Set(ids);
    setTeam((t) => t?.filter((e) => !gone.has(e.employee_id)) ?? t);
    setSelection((s) => s?.filter((id) => !gone.has(id)) ?? s);
  };

  // Used by the edit modal, which asks for confirmation itself.
  const removeConfirmed = async (id: string) => {
    const name = nameOf(id);
    await api.deleteEmployee(id);
    removeFromState([id]);
    setModal(null);
    notify(`${name} removed from the team.`);
  };

  const removeOne = async (id: string) => {
    if (!window.confirm(`Remove ${nameOf(id)} and their AI Twin from the team? This cannot be undone.`)) return;
    setBusyId(id);
    try {
      await removeConfirmed(id);
    } catch (err) {
      notify(`Could not remove: ${(err as Error).message}`, "error");
    } finally {
      setBusyId(null);
    }
  };

  const removeSelected = async () => {
    if (!selection?.length) return;
    if (!window.confirm(`Remove ${selection.length} employee${selection.length === 1 ? "" : "s"} and their AI Twins? This cannot be undone.`)) return;
    setRemoving(true);
    try {
      const { deleted, not_found } = await api.bulkDeleteEmployees(selection);
      removeFromState([...deleted, ...not_found]);
      setSelection(null);
      notify(`Removed ${deleted.length} employee${deleted.length === 1 ? "" : "s"}.`);
    } catch (err) {
      notify(`Could not remove: ${(err as Error).message}`, "error");
    } finally {
      setRemoving(false);
    }
  };

  const generate = async (id: string) => {
    setBusyId(id);
    try {
      const twin = await api.generateTwin(id);
      setStatus(id, "generated");
      setModal({ kind: "twin", twin });
    } catch (err) {
      notify(`Twin generation failed: ${(err as Error).message}`, "error");
    } finally {
      setBusyId(null);
    }
  };

  const view = async (id: string) => {
    setBusyId(id);
    try {
      setModal({ kind: "twin", twin: await api.getTwin(id) });
    } catch (err) {
      notify(`Could not load twin: ${(err as Error).message}`, "error");
    } finally {
      setBusyId(null);
    }
  };

  const toggleSelected = (id: string) => setSelection((s) => (s ? (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]) : [id]));

  const editing = modal?.kind === "edit" ? team?.find((e) => e.employee_id === modal.employeeId) : undefined;
  const twinEmployee = modal?.kind === "twin" ? team?.find((e) => e.employee_id === modal.twin.employee_id) : undefined;
  const readyCount = team?.filter((e) => e.twin_status === "generated").length ?? 0;
  const selecting = selection !== null;

  const addButtons = (
    <>
      <button onClick={() => setModal({ kind: "slack" })} className={secondaryBtn}>
        <MessageSquare className="w-3.5 h-3.5" /> From Slack
      </button>
      <button onClick={() => setModal({ kind: "json" })} className={secondaryBtn}>
        <FileJson className="w-3.5 h-3.5" /> Import JSON
      </button>
      <button onClick={() => setModal({ kind: "create" })} className="bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs px-4 py-2.5 rounded-xl flex items-center gap-2">
        <Plus className="w-3.5 h-3.5" /> Add Employee
      </button>
    </>
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Team</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Add team members manually, from Slack, or from a JSON file, then generate an AI Twin for each.
          </p>
        </div>
        {team && team.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            {selecting ? (
              <>
                <span className="text-xs text-slate-500 dark:text-slate-400 mr-1">{selection.length} selected</span>
                <button onClick={() => setSelection(team.map((e) => e.employee_id))} className={secondaryBtn}>
                  Select all
                </button>
                <button onClick={() => setSelection(null)} className={secondaryBtn}>
                  <X className="w-3.5 h-3.5" /> Cancel
                </button>
                <button
                  onClick={removeSelected}
                  disabled={!selection.length || removing}
                  className="bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs px-4 py-2.5 rounded-xl flex items-center gap-2 disabled:opacity-50"
                >
                  <Trash2 className="w-3.5 h-3.5" /> {removing ? "Removing…" : `Remove ${selection.length || ""}`}
                </button>
              </>
            ) : (
              <>
                <span className="text-xs text-slate-500 dark:text-slate-400 mr-1">
                  <span className="font-bold text-slate-800 dark:text-white">{readyCount}</span> of {team.length} twins ready
                </span>
                <button onClick={() => setSelection([])} className={secondaryBtn}>
                  <CheckSquare className="w-3.5 h-3.5" /> Select
                </button>
                {addButtons}
              </>
            )}
          </div>
        )}
      </div>

      {team === null ? (
        <Card className="p-10 text-center space-y-3">
          <p className="text-sm text-slate-500 dark:text-slate-400">The team could not be loaded. Is the FastAPI backend running?</p>
          <button onClick={reload} disabled={loading} className={`${secondaryBtn} mx-auto`}>
            {loading ? "Retrying…" : "Retry"}
          </button>
        </Card>
      ) : team.length === 0 ? (
        <Card className="p-12 flex flex-col items-center text-center gap-3">
          <div className="w-14 h-14 rounded-2xl bg-brand-50 dark:bg-brand-950 border border-brand-200 dark:border-brand-800 flex items-center justify-center">
            <Users className="w-7 h-7 text-brand-600 dark:text-brand-400" />
          </div>
          <h3 className="font-bold text-lg text-slate-900 dark:text-white">Your team is empty.</h3>
          <p className="text-sm text-slate-500 dark:text-slate-400">Add your first team member to create an AI Twin.</p>
          <div className="flex flex-wrap justify-center gap-2">{addButtons}</div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {team.map((emp) => {
            const status = STATUS_STYLES[emp.twin_status];
            const busy = busyId === emp.employee_id;
            const shownSkills = emp.skills.slice(0, 4);
            const sourceLabel = SOURCE_LABELS[emp.source];
            const isSelected = selection?.includes(emp.employee_id) ?? false;
            return (
              <Card
                key={emp.employee_id}
                className={`p-6 flex flex-col justify-between gap-5 transition-shadow ${isSelected ? "ring-2 ring-rose-500" : ""} ${selecting ? "cursor-pointer" : ""}`}
              >
                <div className="space-y-3" onClick={selecting ? () => toggleSelected(emp.employee_id) : undefined}>
                  <div className="flex items-center gap-3">
                    {selecting && (
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelected(emp.employee_id)}
                        onClick={(e) => e.stopPropagation()}
                        aria-label={`Select ${emp.name}`}
                        className="accent-rose-600 w-4 h-4"
                      />
                    )}
                    <div className="w-11 h-11 rounded-full bg-gradient-to-tr from-brand-600 to-indigo-400 text-white font-bold flex items-center justify-center text-sm shrink-0">
                      {initials(emp.name)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <h4 className="font-bold text-slate-900 dark:text-white text-sm truncate">{emp.name}</h4>
                      <p className="text-xs text-slate-500 dark:text-slate-400 truncate">{emp.current_role}</p>
                    </div>
                    {sourceLabel && (
                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400">
                        {sourceLabel}
                      </span>
                    )}
                    {!selecting && (
                      <button
                        onClick={() => removeOne(emp.employee_id)}
                        disabled={busy}
                        aria-label={`Remove ${emp.name}`}
                        title="Remove from team"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/50 disabled:opacity-50"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                  <p className="text-xs text-slate-600 dark:text-slate-300 min-h-4">
                    {shownSkills.length ? shownSkills.join(" • ") : <span className="text-slate-400">No skills listed</span>}
                    {emp.skills.length > shownSkills.length && <span className="text-slate-400"> +{emp.skills.length - shownSkills.length}</span>}
                  </p>
                  <div className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
                      <Bot className="w-3.5 h-3.5" /> AI Twin:
                    </span>
                    <span className={`px-2 py-0.5 rounded-full border font-semibold ${status.className}`}>{status.label}</span>
                  </div>
                  <p className="text-[11px] text-slate-400">
                    {emp.current_workload_hours} / {emp.weekly_available_hours} h · {emp.experience_years} yrs · {emp.employee_id}
                  </p>
                </div>

                {!selecting && (
                  <div className="grid grid-cols-2 gap-2 pt-4 border-t border-slate-200 dark:border-slate-800">
                    {emp.twin_status === "generated" ? (
                      <button onClick={() => view(emp.employee_id)} disabled={busy} className="py-2 px-3 bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs rounded-xl flex items-center justify-center gap-1.5 disabled:opacity-50">
                        <Eye className="w-3.5 h-3.5" /> View Twin
                      </button>
                    ) : (
                      <button onClick={() => generate(emp.employee_id)} disabled={busy} className="py-2 px-3 bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs rounded-xl flex items-center justify-center gap-1.5 disabled:opacity-50">
                        {emp.twin_status === "outdated" ? <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} /> : <Sparkles className="w-3.5 h-3.5" />}
                        {emp.twin_status === "outdated" ? "Regenerate Twin" : "Generate AI Twin"}
                      </button>
                    )}
                    <button onClick={() => setModal({ kind: "edit", employeeId: emp.employee_id })} className="py-2 px-3 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 font-semibold text-xs rounded-xl border border-slate-200 dark:border-slate-700 flex items-center justify-center gap-1.5">
                      <Pencil className="w-3.5 h-3.5" /> Edit
                    </button>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {modal?.kind === "create" && <EmployeeFormModal onSubmit={create} onClose={() => setModal(null)} />}
      {modal?.kind === "json" && <JsonImportModal onImported={(r) => imported(r, "JSON")} onClose={() => setModal(null)} />}
      {modal?.kind === "slack" && <SlackImportModal onImported={(r) => imported(r, "Slack")} onClose={() => setModal(null)} />}
      {editing && (
        <EmployeeFormModal
          key={editing.employee_id}
          employee={editing}
          onSubmit={(input) => update(editing.employee_id, input)}
          onDelete={() => removeConfirmed(editing.employee_id)}
          onClose={() => setModal(null)}
        />
      )}
      {modal?.kind === "twin" && (
        <TwinProfileModal
          twin={modal.twin}
          status={twinEmployee?.twin_status ?? "generated"}
          busy={busyId === modal.twin.employee_id}
          onEdit={() => setModal({ kind: "edit", employeeId: modal.twin.employee_id })}
          onRegenerate={() => generate(modal.twin.employee_id)}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}
