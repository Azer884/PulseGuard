"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { Trash2 } from "lucide-react";
import type { EmployeeInput, EmployeeSummary } from "@/lib/types";
import Modal from "./Modal";
import TagInput from "./TagInput";

interface Props {
  employee?: EmployeeSummary;
  /** Prefilled values when creating (e.g. a name from an external tool). */
  defaults?: Partial<EmployeeInput>;
  onSubmit: (input: EmployeeInput) => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
}

type Errors = Partial<Record<"name" | "current_role" | "experience_years" | "current_workload_hours" | "weekly_available_hours", string>>;

function numberError(raw: string, min: number, max: number, allowMin: boolean): string | undefined {
  if (raw.trim() === "") return "Required";
  const value = Number(raw);
  if (!Number.isFinite(value)) return "Must be a number";
  if (allowMin ? value < min : value <= min) return allowMin ? `Must be ${min} or more` : `Must be more than ${min}`;
  if (value > max) return `Must be ${max} or less`;
  return undefined;
}

const inputClass =
  "w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500";

function Field({ id, label, hint, error, children }: { id: string; label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-xs font-semibold text-slate-600 dark:text-slate-300">
        {label}
      </label>
      {children}
      {error ? <p className="text-[11px] text-rose-600 dark:text-rose-400">{error}</p> : hint && <p className="text-[11px] text-slate-400">{hint}</p>}
    </div>
  );
}

export default function EmployeeFormModal({ employee, defaults, onSubmit, onDelete, onClose }: Props) {
  const [name, setName] = useState(employee?.name ?? defaults?.name ?? "");
  const [role, setRole] = useState(employee?.current_role ?? defaults?.current_role ?? "");
  const [skills, setSkills] = useState<string[]>(employee?.skills ?? []);
  const [experience, setExperience] = useState(employee ? String(employee.experience_years) : "");
  const [availableRoles, setAvailableRoles] = useState<string[]>(
    employee ? employee.available_roles.filter((r) => r.toLowerCase() !== employee.current_role.toLowerCase()) : [],
  );
  const [workload, setWorkload] = useState(employee ? String(employee.current_workload_hours) : "");
  const [weekly, setWeekly] = useState(employee ? String(employee.weekly_available_hours) : "40");
  const [errors, setErrors] = useState<Errors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const next: Errors = {
      name: name.trim() ? undefined : "Name is required",
      current_role: role.trim() ? undefined : "Current role is required",
      experience_years: numberError(experience, 0, 60, true),
      current_workload_hours: numberError(workload, 0, 168, true),
      weekly_available_hours: numberError(weekly, 0, 168, false),
    };
    setErrors(next);
    if (Object.values(next).some(Boolean)) return;

    setPending(true);
    setServerError(null);
    try {
      await onSubmit({
        name: name.trim(),
        current_role: role.trim(),
        skills,
        experience_years: Number(experience),
        available_roles: [role.trim(), ...availableRoles],
        current_workload_hours: Number(workload),
        weekly_available_hours: Number(weekly),
      });
    } catch (err) {
      setServerError((err as Error).message);
      setPending(false);
    }
  };

  const remove = async () => {
    if (!onDelete || !window.confirm(`Delete ${employee?.name} and their AI Twin? This cannot be undone.`)) return;
    setPending(true);
    try {
      await onDelete();
    } catch (err) {
      setServerError((err as Error).message);
      setPending(false);
    }
  };

  return (
    <Modal
      title={employee ? `Edit ${employee.name}` : "Add Employee"}
      subtitle={employee ? `${employee.employee_id} · editing marks an existing AI Twin as outdated` : "Create a team member profile. You can generate their AI Twin next."}
      onClose={onClose}
      footer={
        <>
          {employee && onDelete && (
            <button
              type="button"
              onClick={remove}
              disabled={pending}
              className="mr-auto text-xs font-semibold px-3 py-2.5 rounded-xl text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/50 flex items-center gap-1.5 disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" /> Delete
            </button>
          )}
          <button type="button" onClick={onClose} className="text-xs font-semibold px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
            Cancel
          </button>
          <button type="submit" form="employee-form" disabled={pending} className="bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold px-4 py-2.5 rounded-xl disabled:opacity-50">
            {pending ? "Saving…" : employee ? "Save Changes" : "Add Employee"}
          </button>
        </>
      }
    >
      <form id="employee-form" onSubmit={submit} noValidate className="space-y-4">
        {serverError && (
          <p className="text-xs bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 rounded-xl px-3 py-2">{serverError}</p>
        )}
        <Field id="emp-name" label="Name" error={errors.name}>
          <input id="emp-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Alex Johnson" maxLength={120} className={inputClass} autoFocus />
        </Field>
        <Field id="emp-role" label="Current Role" error={errors.current_role}>
          <input id="emp-role" value={role} onChange={(e) => setRole(e.target.value)} placeholder="Backend Developer" maxLength={120} className={inputClass} />
        </Field>
        <Field id="emp-skills" label="Skills" hint="Press Enter or comma to add each skill.">
          <TagInput id="emp-skills" values={skills} onChange={setSkills} placeholder="Python, FastAPI, PostgreSQL" />
        </Field>
        <Field id="emp-available-roles" label="Other Available Roles" hint="Roles this person could also take. The current role is always included.">
          <TagInput id="emp-available-roles" values={availableRoles} onChange={setAvailableRoles} placeholder="API Integration" />
        </Field>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Field id="emp-exp" label="Experience (years)" error={errors.experience_years}>
            <input id="emp-exp" type="number" min={0} max={60} step="0.5" value={experience} onChange={(e) => setExperience(e.target.value)} placeholder="3" className={inputClass} />
          </Field>
          <Field id="emp-workload" label="Current Workload (h)" hint="Weekly hours outside this backlog" error={errors.current_workload_hours}>
            <input id="emp-workload" type="number" min={0} max={168} value={workload} onChange={(e) => setWorkload(e.target.value)} placeholder="24" className={inputClass} />
          </Field>
          <Field id="emp-weekly" label="Weekly Availability (h)" error={errors.weekly_available_hours}>
            <input id="emp-weekly" type="number" min={1} max={168} value={weekly} onChange={(e) => setWeekly(e.target.value)} placeholder="40" className={inputClass} />
          </Field>
        </div>
      </form>
    </Modal>
  );
}
