"use client";

import { useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, Unplug } from "lucide-react";
import { api } from "@/lib/api";
import type { PlaneStatus } from "@/lib/types";
import Modal from "./Modal";

interface Props {
  onConnected: (status: PlaneStatus) => void;
  onDisconnected: () => void;
  onClose: () => void;
}

const inputClass =
  "w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500";

export default function PlaneConnectModal({ onConnected, onDisconnected, onClose }: Props) {
  const [status, setStatus] = useState<PlaneStatus | null>(null);
  const [baseUrl, setBaseUrl] = useState("https://api.plane.so");
  const [slug, setSlug] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .planeStatus()
      .then((s) => {
        if (cancelled) return;
        setStatus(s);
        if (s.base_url) setBaseUrl(s.base_url);
        if (s.workspace_slug) setSlug(s.workspace_slug);
      })
      .catch((err) => !cancelled && setError((err as Error).message));
    return () => {
      cancelled = true;
    };
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!baseUrl.trim() || !slug.trim() || !apiKey.trim()) {
      setError("Base URL, workspace slug and API key are all required.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      const s = await api.planeConnect({ base_url: baseUrl.trim(), workspace_slug: slug.trim(), api_key: apiKey.trim() });
      setApiKey("");
      onConnected(s);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPending(false);
    }
  };

  const disconnect = async () => {
    if (!window.confirm("Disconnect Plane? Imported projects stay, but they cannot be synced until you reconnect.")) return;
    setPending(true);
    try {
      await api.planeDisconnect();
      onDisconnected();
    } catch (err) {
      setError((err as Error).message);
      setPending(false);
    }
  };

  const envManaged = status?.config_source === "env";

  return (
    <Modal
      title="Connect Plane"
      subtitle="Plane Cloud or a self-hosted instance. PulseGuard only reads projects, work items, cycles and members."
      onClose={onClose}
      footer={
        <>
          {status?.config_source === "saved" && (
            <button onClick={disconnect} disabled={pending} className="mr-auto text-xs font-semibold px-3 py-2.5 rounded-xl text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/50 flex items-center gap-1.5 disabled:opacity-50">
              <Unplug className="w-3.5 h-3.5" /> Disconnect
            </button>
          )}
          <button onClick={onClose} className="text-xs font-semibold px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
            Close
          </button>
          {!envManaged && (
            <button type="submit" form="plane-form" disabled={pending} className="bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold px-4 py-2.5 rounded-xl disabled:opacity-50">
              {pending ? "Testing…" : "Test & Save"}
            </button>
          )}
        </>
      }
    >
      <div className="space-y-4">
        {status?.connected && (
          <p className="text-xs flex items-center gap-2 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 rounded-xl px-3 py-2">
            <CheckCircle2 className="w-4 h-4" /> Connected to <span className="font-semibold">{status.workspace_slug}</span> at {status.base_url} as {status.user}
            {status.api_key_hint && <span className="text-emerald-600/70">(key {status.api_key_hint})</span>}
          </p>
        )}
        {status?.configured && !status.connected && status.error && (
          <p className="text-xs bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 rounded-xl px-3 py-2">
            Saved connection failed: {status.error}
          </p>
        )}
        {envManaged ? (
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Plane is configured through <code>PLANE_BASE_URL</code>, <code>PLANE_API_KEY</code> and <code>PLANE_WORKSPACE_SLUG</code> in <code>backend/.env</code>. Change it there and restart the backend.
          </p>
        ) : (
          <form id="plane-form" onSubmit={submit} className="space-y-4" noValidate>
            {error && (
              <p className="text-xs bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 rounded-xl px-3 py-2">{error}</p>
            )}
            <div className="space-y-1">
              <label htmlFor="plane-url" className="text-xs font-semibold text-slate-600 dark:text-slate-300">Plane URL</label>
              <input id="plane-url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} className={inputClass} />
              <p className="text-[11px] text-slate-400">Plane Cloud: https://api.plane.so · Self-hosted: your instance URL, e.g. https://plane.example.com</p>
            </div>
            <div className="space-y-1">
              <label htmlFor="plane-slug" className="text-xs font-semibold text-slate-600 dark:text-slate-300">Workspace slug</label>
              <input id="plane-slug" value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="my-team" className={inputClass} />
              <p className="text-[11px] text-slate-400">The part after the domain in your Plane URL: app.plane.so/<span className="font-semibold">my-team</span>/projects</p>
            </div>
            <div className="space-y-1">
              <label htmlFor="plane-key" className="text-xs font-semibold text-slate-600 dark:text-slate-300">API key</label>
              <input id="plane-key" type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="plane_api_…" className={inputClass} />
              <p className="text-[11px] text-slate-400">
                Plane → Profile settings → Personal Access Tokens. The key is tested first, then stored on the PulseGuard server (backend/data/plane.json, gitignored) and never sent back to the browser.
              </p>
            </div>
          </form>
        )}
      </div>
    </Modal>
  );
}
