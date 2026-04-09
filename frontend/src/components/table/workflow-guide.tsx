"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import type { Column, Row } from "@/types";

const ENRICHMENT_TYPES = new Set(["agent", "waterfall"]);

interface WorkflowGuideProps {
  tableId: string;
  columns: Column[];
  rows: Row[];
  onImportCSV: () => void;
  onAddRow: () => void;
  onOpenEnrichment: (type?: "agent" | "waterfall") => void;
  onRunAll: () => void;
  onQuickSetup?: () => Promise<void>;
}

type Phase = "empty" | "needs-enrichment" | "ready-to-run" | "running" | "done";

function detectPhase(columns: Column[], rows: Row[]): Phase {
  if (rows.length === 0) return "empty";

  const enrichCols = columns.filter((c) => ENRICHMENT_TYPES.has(c.type));
  if (enrichCols.length === 0) return "needs-enrichment";

  // Check enrichment cell statuses
  let hasRunning = false;
  let hasPending = false;
  let hasEmpty = false;
  let hasFound = false;
  for (const row of rows) {
    for (const col of enrichCols) {
      const cell = row.cells.find((c) => c.column_id === col.id);
      if (!cell || cell.status === "empty") hasEmpty = true;
      else if (cell.status === "running") hasRunning = true;
      else if (cell.status === "pending") hasPending = true;
      else if (cell.status === "found" || cell.status === "not_found" || cell.status === "error" || cell.status === "review") hasFound = true;
    }
  }

  // Only show progress bar when a cell is actively running (not just stale pending from a restart)
  if (hasRunning) return "running";
  if (hasFound && !hasEmpty && !hasPending) return "done";
  return "ready-to-run";
}

export function WorkflowGuide({
  tableId,
  columns,
  rows,
  onImportCSV,
  onAddRow,
  onOpenEnrichment,
  onRunAll,
  onQuickSetup,
}: WorkflowGuideProps) {
  const router = useRouter();
  const [dismissed, setDismissed] = useState(false);
  const phase = detectPhase(columns, rows);

  // Don't show if dismissed or if enrichment is done
  if (dismissed) return null;
  if (phase === "done") {
    return (
      <div className="mx-6 my-2 flex items-center justify-between px-4 py-2 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
        <span className="text-xs text-emerald-400 font-mono">
          ✓ Enrichment complete — ready to send emails
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => router.push(`/table/${tableId}/emails`)}
            className="px-3 py-1 rounded text-xs font-semibold bg-[#06b6d4]/10 text-[#06b6d4] hover:bg-[#06b6d4]/20 transition-all"
          >
            📧 Compose Emails
          </button>
          <button onClick={() => setDismissed(true)} className="text-[#3f3f46] hover:text-[#71717a] text-xs">
            ✕
          </button>
        </div>
      </div>
    );
  }

  if (phase === "running") {
    // Count progress
    const enrichCols = columns.filter((c) => ENRICHMENT_TYPES.has(c.type));
    let total = 0, done = 0, errors = 0;
    for (const row of rows) {
      for (const col of enrichCols) {
        const cell = row.cells.find((c) => c.column_id === col.id);
        if (cell) {
          total++;
          if (cell.status === "found" || cell.status === "not_found") done++;
          if (cell.status === "error") { done++; errors++; }
        }
      }
    }
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;

    return (
      <div className="mx-6 my-2 px-4 py-3 rounded-lg bg-[#06b6d4]/5 border border-[#06b6d4]/20">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-[#06b6d4]">
            ⏳ Enriching... {done}/{total} cells
            {errors > 0 && <span className="text-amber-400 ml-2">({errors} error{errors > 1 ? "s" : ""})</span>}
          </span>
          <span className="text-[10px] font-mono text-[#52525b]">{pct}%</span>
        </div>
        <div className="w-full h-1.5 rounded-full bg-[#27272a] overflow-hidden">
          <div
            className="h-full bg-[#06b6d4] transition-all duration-500 rounded-full"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    );
  }

  // Phases: empty, needs-enrichment, ready-to-run
  const config = {
    empty: {
      label: "Step 1 of 3",
      title: "Add your data",
      description: "Import a CSV, use AI Find to discover companies, or add rows manually.",
      actions: (
        <>
          <button onClick={onImportCSV} className="guide-btn">📥 Import CSV</button>
          <button onClick={() => router.push("/find")} className="guide-btn guide-btn--primary">🔍 AI Find</button>
          <button onClick={onAddRow} className="guide-btn">+ Add Row</button>
        </>
      ),
    },
    "needs-enrichment": {
      label: "Step 2 of 3",
      title: "Set up enrichment",
      description: "Add columns to automatically find contacts and emails for each row.",
      actions: (
        <div className="w-full space-y-2">
          {onQuickSetup && (
            <button onClick={onQuickSetup} className="w-full py-3 rounded-lg text-sm font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20 transition-all text-center">
              ⚡ Quick Setup — auto-add &quot;Key Contact&quot; + &quot;Email&quot; columns
            </button>
          )}
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-[#52525b]">or add manually:</span>
            <button onClick={() => onOpenEnrichment("agent")} className="guide-btn">🤖 Custom Agent</button>
            <button onClick={() => onOpenEnrichment("waterfall")} className="guide-btn">⛓ Custom Waterfall</button>
          </div>
        </div>
      ),
    },
    "ready-to-run": {
      label: "Step 3 of 3",
      title: "Run enrichment",
      description: "Click Run to find contacts and emails for all rows. Takes a few minutes.",
      actions: (
        <button onClick={onRunAll} className="w-full py-3 rounded-lg text-sm font-bold btn-cyan-gradient text-center animate-pulse">
          ▶ Run All Enrichments — find contacts and emails for {rows.length} row{rows.length !== 1 ? "s" : ""}
        </button>
      ),
    },
  }[phase];

  return (
    <div className="mx-6 my-2 px-4 py-3 rounded-lg bg-[#18181b] border border-[#27272a]">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-mono text-[#06b6d4] bg-[#06b6d4]/10 px-1.5 py-0.5 rounded">{config.label}</span>
            <span className="text-sm font-semibold text-[#fafafa]">{config.title}</span>
          </div>
          <p className="text-xs text-[#71717a] mb-3">{config.description}</p>
          <div className={cn(
            phase === "ready-to-run" || phase === "needs-enrichment"
              ? "w-full"
              : "flex items-center gap-2 flex-wrap"
          )}>
            {config.actions}
          </div>
        </div>
        <button onClick={() => setDismissed(true)} className="text-[#3f3f46] hover:text-[#71717a] text-xs shrink-0 mt-1">
          ✕
        </button>
      </div>
    </div>
  );
}
