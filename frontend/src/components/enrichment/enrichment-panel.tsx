"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface EnrichmentPanelProps {
  open: boolean;
  onClose: () => void;
  onSave: (config: { name: string; type: "agent" | "waterfall"; config: Record<string, unknown> }) => void;
}

const ENRICHMENT_SOURCES = [
  { id: "ai_agent", name: "AI Agent Research", icon: "🤖", description: "AI browses the web to find any data point" },
  { id: "hunter", name: "Hunter.io Email Finder", icon: "📧", description: "Find emails by domain (25 free/mo)" },
  { id: "apollo", name: "Apollo.io Contact Data", icon: "🚀", description: "People search with titles (60 free/mo)" },
  { id: "email_pattern", name: "Email Pattern Generator", icon: "📝", description: "Generate email patterns from name + domain" },
];

export function EnrichmentPanel({ open, onClose, onSave }: EnrichmentPanelProps) {
  const [step, setStep] = useState<"choose" | "configure">("choose");
  const [selectedType, setSelectedType] = useState<"agent" | "waterfall">("agent");
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
    <div className="fixed inset-y-0 right-0 w-96 bg-zinc-900 border-l border-zinc-800 shadow-xl z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <h2 className="font-semibold text-zinc-100">
          {step === "choose" ? "Add Enrichment" : "Configure Enrichment"}
        </h2>
        <button onClick={onClose} className="text-zinc-400 hover:text-zinc-200">
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {step === "choose" ? (
          <>
            {/* Choose type */}
            <div className="space-y-2">
              <Label className="text-zinc-400 text-xs uppercase tracking-wide">Column Type</Label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => setSelectedType("agent")}
                  className={`p-3 rounded-lg border text-left text-sm ${
                    selectedType === "agent"
                      ? "border-blue-500 bg-blue-500/10"
                      : "border-zinc-700 hover:border-zinc-600"
                  }`}
                >
                  <div className="font-medium text-zinc-100">🤖 AI Agent</div>
                  <div className="text-zinc-500 text-xs mt-1">Single AI research source</div>
                </button>
                <button
                  onClick={() => setSelectedType("waterfall")}
                  className={`p-3 rounded-lg border text-left text-sm ${
                    selectedType === "waterfall"
                      ? "border-blue-500 bg-blue-500/10"
                      : "border-zinc-700 hover:border-zinc-600"
                  }`}
                >
                  <div className="font-medium text-zinc-100">⛓ Waterfall</div>
                  <div className="text-zinc-500 text-xs mt-1">Chain multiple sources</div>
                </button>
              </div>
            </div>

            {/* Waterfall: select sources */}
            {selectedType === "waterfall" && (
              <div className="space-y-2">
                <Label className="text-zinc-400 text-xs uppercase tracking-wide">Sources (in order)</Label>
                {ENRICHMENT_SOURCES.map((source) => (
                  <label
                    key={source.id}
                    className="flex items-start gap-3 p-2 rounded-lg hover:bg-zinc-800 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={selectedSources.includes(source.id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedSources([...selectedSources, source.id]);
                        } else {
                          setSelectedSources(selectedSources.filter((s) => s !== source.id));
                        }
                      }}
                      className="mt-1"
                    />
                    <div>
                      <div className="text-sm text-zinc-100">
                        {source.icon} {source.name}
                      </div>
                      <div className="text-xs text-zinc-500">{source.description}</div>
                    </div>
                  </label>
                ))}
              </div>
            )}

            <Button onClick={() => setStep("configure")} className="w-full">
              Next: Configure
            </Button>
          </>
        ) : (
          <>
            {/* Configure */}
            <div>
              <Label>Column Name</Label>
              <Input
                value={columnName}
                onChange={(e) => setColumnName(e.target.value)}
                placeholder="e.g. Recruiter, Email"
                className="mt-1"
              />
            </div>

            <div>
              <Label>Prompt</Label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Find the head of campus recruitment at /Company/. Return their name, title, and email."
                className="mt-1 w-full h-32 rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-zinc-500 mt-1">Use /ColumnName/ to reference other columns</p>
            </div>

            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep("choose")} className="flex-1">
                Back
              </Button>
              <Button
                onClick={handleSave}
                className="flex-1"
                disabled={!columnName.trim() || !prompt.trim()}
              >
                Add Column
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
