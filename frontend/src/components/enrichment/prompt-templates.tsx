"use client";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

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
    label: "Summarize what company does",
    template: "Summarize what /Company/ does in 2-3 sentences. Focus on their main product or service.",
  },
  {
    label: "Find recent news about company",
    template: "Find recent news about /Company/ from the last 3 months. Summarize the most important developments.",
  },
  {
    label: "Find LinkedIn URL for person",
    template: "Find the LinkedIn profile URL for /Person/ at /Company/. Return only the URL.",
  },
];

interface PromptTemplatesProps {
  onSelect: (template: string) => void;
}

export function PromptTemplates({ onSelect }: PromptTemplatesProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-mono text-[#52525b] hover:text-[#a1a1aa] hover:bg-[#27272a] border border-transparent hover:border-[#3f3f46] transition-all" />
        }
      >
        Templates ▾
      </DropdownMenuTrigger>
      <DropdownMenuContent
        className="w-72 bg-[#18181b] border-[#3f3f46]"
        side="bottom"
        align="start"
      >
        <DropdownMenuLabel className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] px-2">
          Prompt Templates
        </DropdownMenuLabel>
        <DropdownMenuSeparator className="bg-[#27272a]" />
        {PROMPT_TEMPLATES.map((t) => (
          <DropdownMenuItem
            key={t.label}
            className="flex flex-col items-start gap-0.5 cursor-pointer text-[#e4e4e7] focus:bg-[#27272a] focus:text-[#fafafa] py-2"
            onClick={() => onSelect(t.template)}
          >
            <span className="text-sm font-medium">{t.label}</span>
            <span className="text-[11px] font-mono text-[#52525b] truncate w-full">{t.template}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
