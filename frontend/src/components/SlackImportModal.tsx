"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Check, Search } from "lucide-react";
import { ApiError, api, describeRowIssues } from "@/lib/api";
import type { ImportResult, SlackMember, SlackStatus } from "@/lib/types";
import Modal from "./Modal";
import { initials } from "./ui";

interface Props {
  onImported: (result: ImportResult) => void;
  onClose: () => void;
}

type Details = { role: string; skills: string; experience: string; workload: string; weekly: string };

const cell =
  "w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-brand-500";

function numberInvalid(raw: string, min: number, max: number, inclusiveMin: boolean): boolean {
  if (raw.trim() === "") return true;
  const n = Number(raw);
  return !Number.isFinite(n) || (inclusiveMin ? n < min : n <= min) || n > max;
}

function detailsProblem(d: Details): string | null {
  if (!d.role.trim()) return "role";
  if (numberInvalid(d.experience, 0, 60, true)) return "experience (0–60)";
  if (numberInvalid(d.workload, 0, 168, true)) return "workload (0–168)";
  if (numberInvalid(d.weekly, 0, 168, false)) return "weekly hours (1–168)";
  return null;
}

function SetupInstructions({ status }: { status: SlackStatus }) {
  return (
    <div className="space-y-4 text-sm">
      {status.configured && status.error ? (
        <p className="text-xs bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 rounded-xl px-3 py-2">
          Slack rejected the configured token: <code>{status.error}</code>. Check the token and its scopes.
        </p>
      ) : (
        <p className="text-slate-600 dark:text-slate-300">Slack is not connected yet. Connect a Slack app with read-only access to member names:</p>
      )}
      <ol className="list-decimal pl-5 space-y-1.5 text-slate-600 dark:text-slate-300 text-xs">
        <li>
          Create an app at <span className="font-mono">api.slack.com/apps</span> → <em>From scratch</em> → pick your workspace.
        </li>
        <li>
          <em>OAuth &amp; Permissions</em> → <em>Bot Token Scopes</em> → add <code>users:read</code>.
        </li>
        <li>
          <em>Install to Workspace</em>, then copy the <em>Bot User OAuth Token</em> (starts with <code>xoxb-</code>).
        </li>
        <li>
          Put it in <code>backend/.env</code> as <code>SLACK_BOT_TOKEN=xoxb-…</code> and restart the backend.
        </li>
      </ol>
      <p className="text-[11px] text-slate-400">
        The token stays on the server. PulseGuard reads only member names and profile titles — no messages, channels or activity.
      </p>
    </div>
  );
}

export default function SlackImportModal({ onImported, onClose }: Props) {
  const [status, setStatus] = useState<SlackStatus | null>(null);
  const [members, setMembers] = useState<SlackMember[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [step, setStep] = useState<"pick" | "details">("pick");
  const [details, setDetails] = useState<Record<string, Details>>({});
  const [generateTwins, setGenerateTwins] = useState(true);
  const [pending, setPending] = useState(false);
  const [issues, setIssues] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await api.slackStatus();
        if (cancelled) return;
        setStatus(s);
        if (s.connected) {
          const list = await api.slackMembers();
          if (!cancelled) setMembers(list);
        }
      } catch (err) {
        if (!cancelled) setLoadError((err as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const byId = useMemo(() => new Map((members ?? []).map((m) => [m.slack_user_id, m])), [members]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (members ?? []).filter((m) => !q || m.name.toLowerCase().includes(q) || (m.title ?? "").toLowerCase().includes(q));
  }, [members, query]);

  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const goToDetails = () => {
    setDetails((prev) => {
      const next: Record<string, Details> = {};
      for (const id of selected) {
        next[id] = prev[id] ?? { role: byId.get(id)?.title ?? "", skills: "", experience: "", workload: "", weekly: "40" };
      }
      return next;
    });
    setIssues([]);
    setStep("details");
  };

  const setField = (id: string, field: keyof Details, value: string) =>
    setDetails((d) => ({ ...d, [id]: { ...d[id], [field]: value } }));

  const fillDown = (field: keyof Details) => {
    const first = details[selected[0]]?.[field] ?? "";
    setDetails((d) => Object.fromEntries(selected.map((id) => [id, { ...d[id], [field]: first }])));
  };

  const problems = selected
    .map((id, i) => {
      const problem = details[id] ? detailsProblem(details[id]) : "details";
      return problem ? `Row ${i + 1} (${byId.get(id)?.name}): ${problem}` : null;
    })
    .filter(Boolean) as string[];

  const submit = async () => {
    if (problems.length) {
      setIssues(problems);
      return;
    }
    setPending(true);
    setIssues([]);
    try {
      const payload = selected.map((id) => {
        const d = details[id];
        return {
          slack_user_id: id,
          current_role: d.role.trim(),
          skills: d.skills.split(",").map((s) => s.trim()).filter(Boolean),
          experience_years: Number(d.experience),
          available_roles: [],
          current_workload_hours: Number(d.workload),
          weekly_available_hours: Number(d.weekly),
        };
      });
      onImported(await api.slackImport(payload, generateTwins));
    } catch (err) {
      setIssues(
        err instanceof ApiError && err.issues.length
          ? describeRowIssues(err.issues, "members", (i) => byId.get(selected[i])?.name)
          : [(err as Error).message],
      );
      setPending(false);
    }
  };

  const connected = status?.connected && members;

  const footer = !connected ? (
    <button onClick={onClose} className="text-xs font-semibold px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
      Close
    </button>
  ) : step === "pick" ? (
    <>
      <span className="mr-auto text-xs text-slate-500 dark:text-slate-400">{selected.length} selected</span>
      <button onClick={onClose} className="text-xs font-semibold px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
        Cancel
      </button>
      <button onClick={goToDetails} disabled={!selected.length} className="bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold px-4 py-2.5 rounded-xl disabled:opacity-50">
        Next: add details
      </button>
    </>
  ) : (
    <>
      <label className="mr-auto flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
        <input type="checkbox" checked={generateTwins} onChange={(e) => setGenerateTwins(e.target.checked)} className="accent-brand-600" />
        Generate AI Twins after import
      </label>
      <button onClick={() => setStep("pick")} className="text-xs font-semibold px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center gap-1.5">
        <ArrowLeft className="w-3.5 h-3.5" /> Back
      </button>
      <button onClick={submit} disabled={pending} className="bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold px-4 py-2.5 rounded-xl disabled:opacity-50">
        {pending ? "Importing…" : `Import ${selected.length}`}
      </button>
    </>
  );

  return (
    <Modal
      wide
      title="Add Employees from Slack"
      subtitle={status?.workspace ? `Workspace: ${status.workspace}` : "Pick workspace members to add to your team."}
      onClose={onClose}
      footer={footer}
    >
      {loadError ? (
        <p className="text-xs text-rose-600 dark:text-rose-400">{loadError}</p>
      ) : !status || (status.connected && !members) ? (
        <p className="text-sm text-slate-400">Connecting to Slack…</p>
      ) : !status.connected ? (
        <SetupInstructions status={status} />
      ) : step === "pick" ? (
        <div className="space-y-3">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by name or title"
              className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div className="divide-y divide-slate-100 dark:divide-slate-800 border border-slate-200 dark:border-slate-800 rounded-xl max-h-80 overflow-y-auto">
            {filtered.length === 0 && <p className="text-xs text-slate-400 p-4">No members match.</p>}
            {filtered.map((m) => {
              const onTeam = Boolean(m.existing_employee_id);
              const checked = selected.includes(m.slack_user_id);
              return (
                <label key={m.slack_user_id} className={`flex items-center gap-3 px-3 py-2.5 ${onTeam ? "opacity-60" : "cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50"}`}>
                  <input type="checkbox" disabled={onTeam} checked={checked} onChange={() => toggle(m.slack_user_id)} className="accent-brand-600" />
                  <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-800 text-xs font-bold flex items-center justify-center shrink-0">{initials(m.name)}</div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium truncate">{m.name}</p>
                    <p className="text-[11px] text-slate-400 truncate">{m.title ?? "No title in Slack profile"}</p>
                  </div>
                  {onTeam && (
                    <span className="text-[11px] flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                      <Check className="w-3 h-3" /> On team
                    </span>
                  )}
                </label>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Slack provides names and titles only. Fill in what the twin needs — nothing is guessed. Role defaults to the Slack title.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] uppercase text-slate-400">
                  <th className="pb-2 pr-2">Member</th>
                  <th className="pb-2 pr-2 min-w-32">Role</th>
                  <th className="pb-2 pr-2 min-w-36">Skills (comma-separated)</th>
                  {(["experience", "workload", "weekly"] as const).map((f) => (
                    <th key={f} className="pb-2 pr-2 w-20">
                      {f === "experience" ? "Exp (yrs)" : f === "workload" ? "Workload h" : "Weekly h"}
                      {selected.length > 1 && (
                        <button onClick={() => fillDown(f)} className="block normal-case text-brand-600 dark:text-brand-400 hover:underline" title="Copy the first row's value to all rows">
                          fill down
                        </button>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {selected.map((id) => {
                  const d = details[id];
                  if (!d) return null;
                  return (
                    <tr key={id}>
                      <td className="py-1 pr-2 font-medium whitespace-nowrap">{byId.get(id)?.name}</td>
                      <td className="py-1 pr-2">
                        <input value={d.role} onChange={(e) => setField(id, "role", e.target.value)} placeholder="Required" className={cell} />
                      </td>
                      <td className="py-1 pr-2">
                        <input value={d.skills} onChange={(e) => setField(id, "skills", e.target.value)} placeholder="Python, SQL" className={cell} />
                      </td>
                      <td className="py-1 pr-2">
                        <input type="number" min={0} max={60} value={d.experience} onChange={(e) => setField(id, "experience", e.target.value)} className={cell} />
                      </td>
                      <td className="py-1 pr-2">
                        <input type="number" min={0} max={168} value={d.workload} onChange={(e) => setField(id, "workload", e.target.value)} className={cell} />
                      </td>
                      <td className="py-1 pr-2">
                        <input type="number" min={1} max={168} value={d.weekly} onChange={(e) => setField(id, "weekly", e.target.value)} className={cell} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {issues.length > 0 && (
            <div className="bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-800 rounded-xl px-3 py-2 text-xs text-rose-700 dark:text-rose-300 space-y-0.5">
              <p className="font-semibold">Nothing was imported yet. Fix:</p>
              {issues.map((issue, i) => (
                <p key={i}>{issue}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
