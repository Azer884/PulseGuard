"use client";

import { useState, type FormEvent } from "react";
import type { TaskInput, TaskView } from "@/lib/types";
import Modal from "./Modal";

interface Props {
  task?: TaskView;
  tasks: TaskView[];
  taskTypes: string[];
  onSubmit: (input: TaskInput) => Promise<void>;
  onClose: () => void;
}

const inputClass =
  "w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500";

/** Tasks that (transitively) depend on `taskId`; choosing them as dependencies would create a cycle. */
function dependents(taskId: string, tasks: TaskView[]): Set<string> {
  const result = new Set<string>();
  let frontier = [taskId];
  while (frontier.length) {
    const next = tasks.filter((t) => !result.has(t.task_id) && t.dependencies.some((d) => frontier.includes(d))).map((t) => t.task_id);
    next.forEach((id) => result.add(id));
    frontier = next;
  }
  return result;
}

export default function TaskFormModal({ task, tasks, taskTypes, onSubmit, onClose }: Props) {
  const [title, setTitle] = useState(task?.title ?? "");
  const [taskType, setTaskType] = useState(task?.task_type ?? taskTypes[0]);
  const [effort, setEffort] = useState(task?.effort_estimate_hours != null ? String(task.effort_estimate_hours) : "");
  const [deps, setDeps] = useState<string[]>(task?.dependencies ?? []);
  const [deadline, setDeadline] = useState(task?.deadline ?? "");
  const [errors, setErrors] = useState<{ title?: string; effort?: string }>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const blocked = task ? dependents(task.task_id, tasks) : new Set<string>();
  const options = tasks.filter((t) => t.task_id !== task?.task_id);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const effortValue = Number(effort);
    const next = {
      title: title.trim() ? undefined : "Title is required",
      effort: effort.trim() === "" || !Number.isFinite(effortValue) || effortValue <= 0 || effortValue > 1000 ? "Enter hours between 0 and 1000" : undefined,
    };
    setErrors(next);
    if (next.title || next.effort) return;
    setPending(true);
    setServerError(null);
    try {
      await onSubmit({ title: title.trim(), task_type: taskType, effort_estimate_hours: effortValue, dependencies: deps, deadline: deadline || null });
    } catch (err) {
      setServerError((err as Error).message);
      setPending(false);
    }
  };

  return (
    <Modal
      title={task ? `Edit ${task.task_id}` : "Add Task"}
      subtitle="Effort is the estimated hours for someone working at normal speed. The simulation scales it by each twin's speed for the task type."
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} className="text-xs font-semibold px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
            Cancel
          </button>
          <button type="submit" form="task-form" disabled={pending} className="bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold px-4 py-2.5 rounded-xl disabled:opacity-50">
            {pending ? "Saving…" : task ? "Save Task" : "Add Task"}
          </button>
        </>
      }
    >
      <form id="task-form" onSubmit={submit} noValidate className="space-y-4">
        {serverError && (
          <p className="text-xs bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 rounded-xl px-3 py-2">{serverError}</p>
        )}
        <div className="space-y-1">
          <label htmlFor="task-title" className="text-xs font-semibold text-slate-600 dark:text-slate-300">Title</label>
          <input id="task-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder="Payments API" className={inputClass} autoFocus />
          {errors.title && <p className="text-[11px] text-rose-600 dark:text-rose-400">{errors.title}</p>}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="space-y-1">
            <label htmlFor="task-type" className="text-xs font-semibold text-slate-600 dark:text-slate-300">Task type</label>
            <select id="task-type" value={taskType} onChange={(e) => setTaskType(e.target.value)} className={inputClass}>
              {taskTypes.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label htmlFor="task-effort" className="text-xs font-semibold text-slate-600 dark:text-slate-300">Effort (h)</label>
            <input id="task-effort" type="number" min={0.5} max={1000} step="0.5" value={effort} onChange={(e) => setEffort(e.target.value)} placeholder="8" className={inputClass} />
            {errors.effort && <p className="text-[11px] text-rose-600 dark:text-rose-400">{errors.effort}</p>}
          </div>
          <div className="space-y-1">
            <label htmlFor="task-deadline" className="text-xs font-semibold text-slate-600 dark:text-slate-300">Deadline</label>
            <input id="task-deadline" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} className={inputClass} />
          </div>
        </div>
        <div className="space-y-1">
          <span className="text-xs font-semibold text-slate-600 dark:text-slate-300">Depends on</span>
          {options.length === 0 ? (
            <p className="text-[11px] text-slate-400">No other tasks yet.</p>
          ) : (
            <div className="max-h-44 overflow-y-auto border border-slate-200 dark:border-slate-800 rounded-xl divide-y divide-slate-100 dark:divide-slate-800">
              {options.map((t) => {
                const disabled = blocked.has(t.task_id);
                return (
                  <label key={t.task_id} className={`flex items-center gap-2 px-3 py-1.5 text-xs ${disabled ? "opacity-40" : "cursor-pointer"}`} title={disabled ? "Would create a dependency cycle" : undefined}>
                    <input
                      type="checkbox"
                      disabled={disabled}
                      checked={deps.includes(t.task_id)}
                      onChange={() => setDeps((d) => (d.includes(t.task_id) ? d.filter((x) => x !== t.task_id) : [...d, t.task_id]))}
                      className="accent-brand-600"
                    />
                    <span className="font-mono text-slate-400">{t.task_id}</span>
                    <span className="truncate">{t.title}</span>
                    <span className="ml-auto text-slate-400">{t.effective_task_type ?? "Unknown"}</span>
                  </label>
                );
              })}
            </div>
          )}
        </div>
      </form>
    </Modal>
  );
}
