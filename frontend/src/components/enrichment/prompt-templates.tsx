"use client";
import { useState } from "react";

const PROMPT_TEMPLATES = [
  {
    label: "Find role at company",
    template: "Find the /Role/ at /Company/. Return their full name and title.",
  },
  {
    label: "Get email for person",
    template: "Find the professional email address for /Person/ at /Company/. Return only the email.",
  },
  {
    label: "Summarize company",
    template: "Summarize what /Company/ does in 2-3 sentences. Focus on their main product or service.",
  },
  {
    label: "Find recent news",
    template: "Find recent news about /Company/ from the last 3 months. Summarize the most important developments.",
  },
  {
    label: "Find LinkedIn URL",
    template: "Find the LinkedIn profile URL for /Person/ at /Company/. Return only the URL.",
  },
];

interface PromptTemplatesProps {
  onSelect: (template: string) => void;
}

export function PromptTemplates({ onSelect }: PromptTemplatesProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-mono text-[#52525b] hover:text-[#a1a1aa] hover:bg-[#27272a] border border-transparent hover:border-[#3f3f46] transition-all"
      >
        Templates {open ? "▴" : "▾"}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-full mt-1 z-50 w-72 rounded-lg border border-[#3f3f46] bg-[#18181b] shadow-xl py-1">
            <div className="px-3 py-1.5 text-[10px] font-mono uppercase tracking-widest text-[#52525b]">
              Prompt Templates
            </div>
            <div className="h-px bg-[#27272a] mx-1 my-1" />
            {PROMPT_TEMPLATES.map((t) => (
              <button
                key={t.label}
                onClick={() => { onSelect(t.template); setOpen(false); }}
                className="w-full text-left px-3 py-2 hover:bg-[#27272a] transition-colors"
              >
                <span className="block text-sm text-[#e4e4e7]">{t.label}</span>
                <span className="block text-[11px] font-mono text-[#52525b] truncate">{t.template}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
