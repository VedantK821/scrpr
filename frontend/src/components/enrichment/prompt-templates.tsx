"use client";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";

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
          <Button variant="outline" size="sm" className="text-xs border-zinc-700 text-zinc-400 hover:text-zinc-200" />
        }
      >
        Templates
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-64 bg-zinc-900 border-zinc-700" side="bottom" align="start">
        <DropdownMenuLabel className="text-zinc-500">Prompt Templates</DropdownMenuLabel>
        <DropdownMenuSeparator className="bg-zinc-700" />
        {PROMPT_TEMPLATES.map((t) => (
          <DropdownMenuItem
            key={t.label}
            className="flex flex-col items-start gap-0.5 cursor-pointer text-zinc-200 focus:bg-zinc-800 focus:text-zinc-100"
            onClick={() => onSelect(t.template)}
          >
            <span className="text-sm font-medium">{t.label}</span>
            <span className="text-xs text-zinc-500 truncate w-full">{t.template}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
