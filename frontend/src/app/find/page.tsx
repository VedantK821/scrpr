"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type { FindResponse } from "@/types";

const EXAMPLE_CRITERIA = [
  { label: "Top IT companies in India", criteria: "Top 50 IT companies in India by revenue and employee count", entity: "companies" },
  { label: "Fortune 500 companies", criteria: "Fortune 500 companies with highest revenue in 2024", entity: "companies" },
  { label: "Startups in Bangalore", criteria: "Series A and B funded startups headquartered in Bangalore, India", entity: "companies" },
  { label: "IIT campus recruiters", criteria: "Top 100 MNCs in India that hire from IITs through campus recruitment programs", entity: "companies" },
  { label: "SaaS unicorns India", criteria: "Indian SaaS companies valued at over $1 billion (unicorns)", entity: "companies" },
  { label: "AI/ML researchers", criteria: "Top AI and machine learning researchers in India at leading universities", entity: "people" },
] as const;

const TARGET_COUNTS = [10, 25, 50, 100] as const;

interface RecentFind {
  id: string;
  tableId: string;
  tableName: string;
  entitiesFound: number;
  entityType: string;
  criteria: string;
  timestamp: Date;
}

function RecentFindItem({
  find,
  onOpen,
}: {
  find: RecentFind;
  onOpen: (tableId: string) => void;
}) {
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const diffMs = find.timestamp.getTime() - Date.now();
  const diffMin = Math.round(diffMs / 60000);
  const diffHr = Math.round(diffMs / 3600000);
  let relTime = "";
  if (Math.abs(diffMin) < 60) relTime = rtf.format(diffMin, "minute");
  else relTime = rtf.format(diffHr, "hour");

  return (
    <div className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg bg-[#09090b] border border-[#27272a] hover:border-[#3f3f46] transition-colors">
      <div className="flex items-center gap-2.5 min-w-0">
        <span className="text-[#06b6d4] text-sm shrink-0">◫</span>
        <div className="min-w-0">
          <p className="text-[13px] text-[#a1a1aa] font-medium truncate">{find.tableName}</p>
          <p className="text-[11px] text-[#52525b] font-mono truncate">
            {find.entitiesFound} {find.entityType} · {relTime}
          </p>
        </div>
      </div>
      <button
        onClick={() => onOpen(find.tableId)}
        className="text-[11px] font-mono text-[#06b6d4] hover:text-[#22d3ee] transition-colors shrink-0"
      >
        Open →
      </button>
    </div>
  );
}

export default function FindPage() {
  const router = useRouter();
  const qc = useQueryClient();

  const [criteria, setCriteria] = useState("");
  const [entityType, setEntityType] = useState<"companies" | "people">("companies");
  const [targetCount, setTargetCount] = useState<number>(25);
  const [tableName, setTableName] = useState("");
  const [result, setResult] = useState<FindResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recentFinds, setRecentFinds] = useState<RecentFind[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [stages, setStages] = useState<{stage: string; message: string}[]>([]);
  const [currentStage, setCurrentStage] = useState<string>("");

  const STAGE_ICONS: Record<string, string> = {
    thinking: "🧠",
    initial_list: "📋",
    searching: "🔍",
    scraping: "🌐",
    expanding: "📊",
    deduplicating: "🧹",
    saving: "💾",
    done: "✅",
  };

  const findMutation = useMutation({
    mutationFn: () =>
      api.find.buildList({
        criteria: criteria.trim(),
        target_count: targetCount,
        entity_type: entityType,
        table_name: tableName.trim() || undefined,
      }),
    onSuccess: (data) => {
      setResult(data);
      setError(null);
      setIsSearching(false);
      setCurrentStage("done");
      setStages(prev => [...prev, {stage: "done", message: `Found ${data.entities_found} ${entityType}. Table created.`}]);
      qc.invalidateQueries({ queryKey: ["tables"] });
      setRecentFinds((prev) => [
        {
          id: crypto.randomUUID(),
          tableId: data.table_id,
          tableName: data.table_name,
          entitiesFound: data.entities_found,
          entityType,
          criteria: criteria.trim(),
          timestamp: new Date(),
        },
        ...prev.slice(0, 9),
      ]);
    },
    onError: (e: Error) => {
      setError(e.message);
      setResult(null);
      setIsSearching(false);
    },
  });

  const handleFind = () => {
    if (!criteria.trim()) return;
    setResult(null);
    setError(null);
    setStages([]);
    setIsSearching(true);

    // Simulate stage progression while the actual request runs
    const stageSequence = [
      { stage: "thinking", message: "Analyzing your criteria...", delay: 0 },
      { stage: "initial_list", message: `Generating initial list of ${targetCount} ${entityType} from AI knowledge...`, delay: 3000 },
      { stage: "searching", message: "Generating search queries for web verification...", delay: 15000 },
      { stage: "scraping", message: "Scraping top search results for additional data...", delay: 25000 },
      { stage: "expanding", message: "Cross-referencing web data to expand and verify list...", delay: 60000 },
      { stage: "deduplicating", message: "Deduplicating and cleaning results...", delay: 90000 },
      { stage: "saving", message: "Creating table and saving results...", delay: 120000 },
    ];

    const timers: ReturnType<typeof setTimeout>[] = [];
    for (const s of stageSequence) {
      const t = setTimeout(() => {
        setCurrentStage(s.stage);
        setStages(prev => [...prev, { stage: s.stage, message: s.message }]);
      }, s.delay);
      timers.push(t);
    }

    findMutation.mutate(undefined, {
      onSettled: () => {
        timers.forEach(clearTimeout);
      },
    });
  };

  const handleExampleClick = (example: (typeof EXAMPLE_CRITERIA)[number]) => {
    setCriteria(example.criteria);
    setEntityType(example.entity as "companies" | "people");
    setResult(null);
    setError(null);
  };

  return (
    <div className="max-w-3xl mx-auto px-8 py-10">
      {/* Header */}
      <div className="mb-8 card-animate">
        <div className="flex items-center gap-3 mb-2">
          <div
            className="w-9 h-9 rounded-lg bg-[#06b6d4]/10 border border-[#06b6d4]/20 flex items-center justify-center"
            style={{ boxShadow: "0 0 16px rgba(6,182,212,0.1)" }}
          >
            <span className="text-[#06b6d4] text-lg">⌕</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight font-mono gradient-text">Find</h1>
        </div>
        <p className="text-[#71717a] text-sm leading-relaxed">
          Describe what you&apos;re looking for in plain English — Scrpr researches the web and builds a ready-to-enrich table.
        </p>
      </div>

      <div className="gradient-divider mb-8" />

      {/* Main input card */}
      <div className="rounded-xl border border-[#27272a] bg-[#18181b] p-6 space-y-6 card-animate">
        {/* Criteria textarea */}
        <div className="space-y-2">
          <Label className="text-[#a1a1aa] text-xs font-mono uppercase tracking-wider">
            Describe what you&apos;re looking for
          </Label>
          <textarea
            value={criteria}
            onChange={(e) => setCriteria(e.target.value)}
            placeholder="e.g. Top 100 MNCs in India that hire from IITs through campus recruitment programs"
            rows={4}
            className={cn(
              "w-full resize-none rounded-lg border bg-[#09090b] px-3 py-2.5 text-sm text-[#fafafa]",
              "placeholder:text-[#52525b] placeholder:text-sm",
              "border-[#3f3f46] focus:outline-none focus:border-[#06b6d4] focus:ring-2 focus:ring-[#06b6d4]/20",
              "transition-colors font-sans leading-relaxed"
            )}
          />
          {/* Example buttons */}
          <div className="flex flex-wrap gap-1.5 pt-1">
            {EXAMPLE_CRITERIA.map((ex) => (
              <button
                key={ex.label}
                onClick={() => handleExampleClick(ex)}
                className="text-[11px] font-mono px-2 py-1 rounded-md border border-[#3f3f46] text-[#71717a] hover:text-[#a1a1aa] hover:border-[#06b6d4]/40 hover:bg-[#06b6d4]/5 transition-all"
              >
                {ex.label}
              </button>
            ))}
          </div>
        </div>

        {/* Entity type + Target count */}
        <div className="grid grid-cols-2 gap-4">
          {/* Entity type toggle */}
          <div className="space-y-2">
            <Label className="text-[#a1a1aa] text-xs font-mono uppercase tracking-wider">Entity Type</Label>
            <div className="flex rounded-lg border border-[#3f3f46] overflow-hidden bg-[#09090b]">
              {(["companies", "people"] as const).map((type) => (
                <button
                  key={type}
                  onClick={() => setEntityType(type)}
                  className={cn(
                    "flex-1 py-1.5 text-[13px] font-mono transition-all",
                    entityType === type
                      ? "bg-[#06b6d4]/15 text-[#06b6d4] border-r border-[#06b6d4]/30 last:border-r-0"
                      : "text-[#71717a] hover:text-[#a1a1aa] hover:bg-[#27272a]/50 border-r border-[#27272a] last:border-r-0"
                  )}
                >
                  {type === "companies" ? "◫ Companies" : "◎ People"}
                </button>
              ))}
            </div>
          </div>

          {/* Target count */}
          <div className="space-y-2">
            <Label className="text-[#a1a1aa] text-xs font-mono uppercase tracking-wider">Target Count</Label>
            <div className="flex rounded-lg border border-[#3f3f46] overflow-hidden bg-[#09090b]">
              {TARGET_COUNTS.map((count) => (
                <button
                  key={count}
                  onClick={() => setTargetCount(count)}
                  className={cn(
                    "flex-1 py-1.5 text-[13px] font-mono transition-all border-r border-[#27272a] last:border-r-0",
                    targetCount === count
                      ? "bg-[#06b6d4]/15 text-[#06b6d4]"
                      : "text-[#71717a] hover:text-[#a1a1aa] hover:bg-[#27272a]/50"
                  )}
                >
                  {count}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Optional table name */}
        <div className="space-y-2">
          <Label htmlFor="find-table-name" className="text-[#a1a1aa] text-xs font-mono uppercase tracking-wider">
            Table name{" "}
            <span className="text-[#52525b] normal-case tracking-normal">(optional — auto-generated if blank)</span>
          </Label>
          <Input
            id="find-table-name"
            value={tableName}
            onChange={(e) => setTableName(e.target.value)}
            placeholder="e.g. Campus Hiring MNCs India"
            className="bg-[#09090b] border-[#3f3f46] text-[#fafafa] placeholder:text-[#52525b] focus-visible:border-[#06b6d4] focus-visible:ring-[#06b6d4]/20"
          />
        </div>

        {/* CTA */}
        <Button
          onClick={handleFind}
          disabled={findMutation.isPending || !criteria.trim()}
          className={cn(
            "w-full h-10 font-semibold text-sm transition-all",
            findMutation.isPending
              ? "bg-[#06b6d4]/20 text-[#06b6d4] border border-[#06b6d4]/30 cursor-not-allowed"
              : "btn-cyan-gradient"
          )}
        >
          {findMutation.isPending ? (
            <span className="flex items-center gap-2.5">
              <span className="inline-block w-3.5 h-3.5 rounded-full border-2 border-[#06b6d4]/30 border-t-[#06b6d4] animate-spin" />
              {currentStage ? (STAGE_ICONS[currentStage] || "⏳") + " " : ""}
              {stages.length > 0 ? stages[stages.length - 1].message : "Starting research..."}
            </span>
          ) : (
            <span className="flex items-center gap-2">
              <span>⌕</span>
              Find &amp; Build Table
            </span>
          )}
        </Button>

        {/* Stage progress log */}
        {isSearching && stages.length > 0 && (
          <div className="mt-4 rounded-lg border border-[#27272a] bg-[#09090b] p-3 space-y-1.5 font-mono text-xs">
            {stages.map((s, i) => (
              <div key={i} className={cn(
                "flex items-center gap-2",
                i === stages.length - 1 ? "text-[#06b6d4]" : "text-[#52525b]"
              )}>
                <span>{STAGE_ICONS[s.stage] || "•"}</span>
                <span>{s.message}</span>
                {i === stages.length - 1 && currentStage !== "done" && (
                  <span className="inline-block w-2 h-2 rounded-full bg-[#06b6d4] animate-pulse ml-1" />
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Result card */}
      {(result || error) && (
        <div
          className={cn(
            "mt-5 rounded-xl border p-5 card-animate",
            result
              ? "bg-emerald-500/5 border-emerald-500/20"
              : "bg-red-500/5 border-red-500/20"
          )}
        >
          {result && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-emerald-400 text-lg">✓</span>
                <p className="text-[#fafafa] font-semibold text-sm">
                  Found {result.entities_found} {entityType}
                </p>
              </div>
              <p className="text-[#71717a] text-xs font-mono">
                Table &quot;{result.table_name}&quot; created with {result.fields.length} columns:{" "}
                <span className="text-[#52525b]">{result.fields.slice(0, 5).join(", ")}{result.fields.length > 5 ? "…" : ""}</span>
              </p>
              <Button
                onClick={() => router.push(`/table/${result.table_id}`)}
                size="sm"
                className="btn-cyan-gradient font-semibold"
              >
                Open Table →
              </Button>
            </div>
          )}
          {error && (
            <div className="flex items-start gap-2">
              <span className="text-red-400 text-sm mt-0.5">✕</span>
              <div>
                <p className="text-red-400 text-sm font-semibold">Find failed</p>
                <p className="text-red-400/70 text-xs font-mono mt-0.5">{error}</p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Recent finds */}
      {recentFinds.length > 0 && (
        <div className="mt-8 space-y-3 card-animate">
          <h2 className="text-[10px] font-mono uppercase tracking-widest text-[#52525b]">Recent Finds</h2>
          <div className="space-y-2">
            {recentFinds.map((find) => (
              <RecentFindItem
                key={find.id}
                find={find}
                onOpen={(tableId) => router.push(`/table/${tableId}`)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Empty tip */}
      {recentFinds.length === 0 && !findMutation.isPending && !result && (
        <div className="mt-8 text-center py-6">
          <p className="text-[#3f3f46] text-xs font-mono">
            Your recent find results will appear here after your first search.
          </p>
        </div>
      )}
    </div>
  );
}
