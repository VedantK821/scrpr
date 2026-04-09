"use client";
import { useState, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PromptTemplates } from "@/components/enrichment/prompt-templates";
import { cn } from "@/lib/utils";

interface EnrichmentPanelProps {
  open: boolean;
  onClose: () => void;
  onSave: (config: { name: string; type: "agent" | "waterfall"; config: Record<string, unknown> }) => void;
  initialType?: "agent" | "waterfall";
}

const ENRICHMENT_SOURCES = [
  {
    id: "ai_agent",
    name: "AI Agent Research",
    icon: "🤖",
    description: "AI browses the web to find any data point",
    status: "available" as const,
    note: "Powered by GPT-4o",
  },
  {
    id: "hunter",
    name: "Hunter.io",
    icon: "📧",
    description: "Find emails by domain",
    status: "available" as const,
    note: "25 free/mo",
  },
  {
    id: "apollo",
    name: "Apollo.io",
    icon: "🚀",
    description: "People search with titles",
    status: "no_key" as const,
    note: "API key required",
  },
  {
    id: "email_pattern",
    name: "Email Pattern",
    icon: "📝",
    description: "Generate from name + domain",
    status: "available" as const,
    note: "No API key needed",
  },
];

type SourceStatus = "available" | "no_key" | "rate_limited";

function StatusBadge({ status }: { status: SourceStatus }) {
  if (status === "available")
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-emerald-900/30 border border-emerald-700/40 text-[10px] font-mono text-emerald-400">
        <span className="w-1 h-1 rounded-full bg-emerald-400" />
        Active
      </span>
    );
  if (status === "no_key")
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-[#27272a] border border-[#3f3f46] text-[10px] font-mono text-[#71717a]">
        <span className="w-1 h-1 rounded-full bg-[#52525b]" />
        Configure
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-amber-900/30 border border-amber-700/40 text-[10px] font-mono text-amber-400">
      <span className="w-1 h-1 rounded-full bg-amber-400" />
      Low Quota
    </span>
  );
}

function StepDots({ step }: { step: "choose" | "configure" }) {
  const steps = [
    { id: "choose", label: "Choose" },
    { id: "configure", label: "Configure" },
  ];
  const activeIdx = step === "choose" ? 0 : 1;

  return (
    <div className="flex items-center gap-2">
      {steps.map((s, i) => (
        <div key={s.id} className="flex items-center gap-2">
          <div className="flex items-center gap-1.5">
            <div
              className={cn(
                "w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-mono font-bold transition-all duration-200",
                i === activeIdx
                  ? "bg-[#06b6d4] text-[#09090b]"
                  : i < activeIdx
                  ? "bg-emerald-500/20 text-emerald-500 border border-emerald-500/30"
                  : "bg-[#27272a] text-[#52525b]"
              )}
              style={i === activeIdx ? { boxShadow: "0 0 10px rgba(6,182,212,0.5)" } : undefined}
            >
              {i < activeIdx ? "✓" : i + 1}
            </div>
            <span
              className={cn(
                "text-xs transition-colors",
                i === activeIdx ? "text-[#fafafa] font-medium" : "text-[#52525b]"
              )}
            >
              {s.label}
            </span>
          </div>
          {i < steps.length - 1 && (
            <div
              className="w-8 h-px transition-all duration-300"
              style={{
                background: i < activeIdx
                  ? "linear-gradient(90deg, rgba(16,185,129,0.4), rgba(16,185,129,0.2))"
                  : "#27272a"
              }}
            />
          )}
        </div>
      ))}
    </div>
  );
}

// Highlight /Variable/ references in a string
function PromptDisplay({ value }: { value: string }) {
  const parts = value.split(/(\/[^/\n]+\/)/g);
  return (
    <>
      {parts.map((part, i) =>
        /^\/[^/\n]+\/$/.test(part) ? (
          <span key={i} className="text-[#06b6d4] font-medium" style={{ textShadow: "0 0 8px rgba(6,182,212,0.3)" }}>
            {part}
          </span>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  );
}

export function EnrichmentPanel({ open, onClose, onSave, initialType }: EnrichmentPanelProps) {
  const [step, setStep] = useState<"choose" | "configure">("choose");
  const [selectedType, setSelectedType] = useState<"agent" | "waterfall">(initialType ?? "agent");

  // Sync initialType when it changes (e.g. guide triggers with a specific type)
  useEffect(() => {
    if (open && initialType) setSelectedType(initialType);
  }, [open, initialType]);
  const [selectedSources, setSelectedSources] = useState<string[]>(["ai_agent"]);
  const [columnName, setColumnName] = useState("");
  const [prompt, setPrompt] = useState("");

  if (!open) return null;

  const handleSave = () => {
    if (!columnName.trim() || !prompt.trim()) return;
    onSave({
      name: columnName,
      type: selectedType,
      config: {
        prompt,
        sources: selectedType === "waterfall" ? selectedSources : undefined,
      },
    });
    setStep("choose");
    setColumnName("");
    setPrompt("");
    setSelectedSources(["ai_agent"]);
    onClose();
  };

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 z-40"
        style={{ background: "rgba(0,0,0,0.55)", backdropFilter: "blur(3px)" }}
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed inset-y-0 right-0 w-[400px] z-50 flex flex-col panel-slide-in">
        {/* Glass background */}
        <div className="absolute inset-0 glass-panel border-l border-[#3f3f46]/60" style={{ borderRadius: 0 }} />

        {/* Top accent line */}
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#06b6d4]/60 to-transparent" />

        <div className="relative flex flex-col h-full">
          {/* Header */}
          <div className="flex items-start justify-between px-5 py-4 border-b border-[#27272a]">
            <div>
              <h2 className="font-semibold text-[#fafafa] font-mono text-sm">
                {step === "choose" ? "Add Enrichment Column" : "Configure Column"}
              </h2>
              <div className="mt-2.5">
                <StepDots step={step} />
              </div>
            </div>
            <button
              onClick={onClose}
              className="w-7 h-7 rounded-md flex items-center justify-center text-[#52525b] hover:text-[#a1a1aa] hover:bg-[#27272a] transition-all text-sm mt-0.5"
            >
              ✕
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-5 space-y-5">
            {step === "choose" ? (
              <>
                {/* Column type */}
                <div className="space-y-2">
                  <Label className="text-[#52525b] text-[10px] font-mono uppercase tracking-widest">
                    Column Type
                  </Label>
                  <div className="grid grid-cols-2 gap-2">
                    {(["agent", "waterfall"] as const).map((type) => {
                      const isSelected = selectedType === type;
                      return (
                        <button
                          key={type}
                          onClick={() => setSelectedType(type)}
                          className={cn(
                            "p-3 rounded-xl border text-left transition-all duration-200",
                            isSelected
                              ? "border-[#06b6d4]/50 bg-[#06b6d4]/8 text-[#fafafa]"
                              : "border-[#27272a] bg-[#27272a]/30 hover:border-[#3f3f46] hover:bg-[#27272a]/50 text-[#a1a1aa] hover:text-[#fafafa]"
                          )}
                          style={isSelected ? { boxShadow: "0 0 14px rgba(6,182,212,0.15), inset 0 0 20px rgba(6,182,212,0.03)" } : undefined}
                        >
                          <div className="font-medium text-sm mb-1">
                            {type === "agent" ? "🤖 AI Agent" : "⛓ Waterfall"}
                          </div>
                          <div className="text-[11px] text-[#52525b]">
                            {type === "agent" ? "Single AI research source" : "Chain multiple sources"}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Waterfall source selection */}
                {selectedType === "waterfall" && (
                  <div className="space-y-2">
                    <Label className="text-[#52525b] text-[10px] font-mono uppercase tracking-widest">
                      Sources (in order)
                    </Label>
                    <div className="space-y-2">
                      {ENRICHMENT_SOURCES.map((source) => {
                        const isChecked = selectedSources.includes(source.id);
                        return (
                          <label
                            key={source.id}
                            className={cn(
                              "flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all duration-200",
                              isChecked
                                ? "border-[#3f3f46] bg-[#27272a]/60"
                                : "border-[#27272a] bg-transparent hover:border-[#3f3f46] hover:bg-[#27272a]/30"
                            )}
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setSelectedSources([...selectedSources, source.id]);
                                } else {
                                  setSelectedSources(selectedSources.filter((s) => s !== source.id));
                                }
                              }}
                              className="mt-0.5 accent-[#06b6d4]"
                            />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between gap-2 mb-0.5">
                                <span className="text-sm text-[#fafafa] font-medium">
                                  {source.icon} {source.name}
                                </span>
                                <StatusBadge status={source.status} />
                              </div>
                              <div className="text-[11px] text-[#52525b]">{source.description}</div>
                              <div className="text-[10px] font-mono text-[#3f3f46] mt-0.5">{source.note}</div>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Agent: show available sources info */}
                {selectedType === "agent" && (
                  <div className="rounded-xl border border-[#27272a] bg-[#09090b]/50 p-3 space-y-2.5">
                    <p className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] mb-2">
                      Available Sources
                    </p>
                    {ENRICHMENT_SOURCES.map((source) => (
                      <div key={source.id} className="flex items-center gap-2.5">
                        <span className="text-sm">{source.icon}</span>
                        <span className="text-xs text-[#a1a1aa] flex-1">{source.name}</span>
                        <StatusBadge status={source.status} />
                      </div>
                    ))}
                  </div>
                )}

                <button
                  onClick={() => setStep("configure")}
                  className="w-full py-2.5 rounded-lg btn-cyan-gradient text-sm font-semibold"
                >
                  Next: Configure →
                </button>
              </>
            ) : (
              <>
                {/* Column name */}
                <div>
                  <Label className="text-[#52525b] text-[10px] font-mono uppercase tracking-widest mb-1.5 block">
                    Column Name
                  </Label>
                  <Input
                    value={columnName}
                    onChange={(e) => setColumnName(e.target.value)}
                    placeholder="e.g. Recruiter Email"
                    className="bg-[#09090b] border-[#3f3f46] text-[#fafafa] placeholder:text-[#52525b] focus-visible:border-[#06b6d4] focus-visible:ring-[#06b6d4]/20"
                  />
                </div>

                {/* Prompt */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <Label className="text-[#52525b] text-[10px] font-mono uppercase tracking-widest">
                      Prompt
                    </Label>
                    <PromptTemplates onSelect={(tpl) => setPrompt(tpl)} />
                  </div>

                  {/* Code-editor style textarea */}
                  <div className="relative rounded-xl overflow-hidden border border-[#3f3f46] bg-[#09090b]">
                    <div className="absolute left-0 top-0 bottom-0 w-8 bg-[#18181b] border-r border-[#27272a] flex flex-col pt-2.5 gap-[1.625rem] pointer-events-none">
                      {Array.from({ length: 6 }).map((_, i) => (
                        <span key={i} className="text-[10px] text-[#3f3f46] font-mono text-right pr-2 leading-none">{i + 1}</span>
                      ))}
                    </div>
                    <textarea
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      placeholder="Find the head of campus recruitment at /Company/. Return their name, title, and email."
                      rows={6}
                      className={cn(
                        "w-full pl-10 pr-3 py-2.5",
                        "text-sm text-[#fafafa] placeholder:text-[#3f3f46]",
                        "focus:outline-none",
                        "resize-none leading-relaxed font-mono bg-transparent",
                        "transition-all"
                      )}
                    />
                  </div>

                  <div className="mt-2 flex items-start gap-1.5">
                    <span className="text-[#06b6d4] text-xs mt-px">ℹ</span>
                    <p className="text-[11px] text-[#52525b] leading-relaxed">
                      Use{" "}
                      <code className="text-[#06b6d4] bg-[#06b6d4]/10 px-1 rounded font-mono">/ColumnName/</code>{" "}
                      to reference other columns. Variables are highlighted in{" "}
                      <span className="text-[#06b6d4]">cyan</span>.
                    </p>
                  </div>

                  {/* Live variable preview */}
                  {prompt && prompt.includes("/") && (
                    <div className="mt-2 p-2.5 rounded-lg bg-[#09090b] border border-[#27272a] text-[11px] font-mono leading-relaxed text-[#71717a]">
                      <PromptDisplay value={prompt} />
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex gap-2 pt-2">
                  <button
                    onClick={() => setStep("choose")}
                    className="flex-1 py-2 rounded-lg border border-[#3f3f46] text-[#a1a1aa] hover:text-[#fafafa] hover:bg-[#27272a] text-sm transition-all"
                  >
                    ← Back
                  </button>
                  <button
                    onClick={handleSave}
                    disabled={!columnName.trim() || !prompt.trim()}
                    className={cn(
                      "flex-1 py-2 rounded-lg text-sm font-semibold transition-all",
                      columnName.trim() && prompt.trim()
                        ? "btn-cyan-gradient"
                        : "bg-[#27272a] text-[#52525b] cursor-not-allowed"
                    )}
                  >
                    Add Column
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
