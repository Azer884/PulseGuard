"use client";

import { useState, type KeyboardEvent } from "react";
import { X } from "lucide-react";

interface Props {
  id: string;
  values: string[];
  onChange: (values: string[]) => void;
  placeholder: string;
}

export default function TagInput({ id, values, onChange, placeholder }: Props) {
  const [draft, setDraft] = useState("");

  const commit = () => {
    const item = draft.trim().replace(/,$/, "").trim();
    setDraft("");
    if (item && !values.some((v) => v.toLowerCase() === item.toLowerCase())) onChange([...values, item]);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && !draft && values.length) {
      onChange(values.slice(0, -1));
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-2 py-1.5 focus-within:ring-2 focus-within:ring-brand-500">
      {values.map((value) => (
        <span key={value} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-brand-50 dark:bg-brand-950 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-800 text-xs">
          {value}
          <button type="button" onClick={() => onChange(values.filter((v) => v !== value))} aria-label={`Remove ${value}`}>
            <X className="w-3 h-3" />
          </button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={commit}
        placeholder={values.length ? "" : placeholder}
        className="flex-1 min-w-[8rem] bg-transparent text-sm py-1 px-1 focus:outline-none"
      />
    </div>
  );
}
