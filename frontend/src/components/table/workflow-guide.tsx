"use client";
import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import type { Column, Row } from "@/types";

const ENRICHMENT_TYPES = new Set(["agent", "waterfall"]);

type WorkflowStep = 1 | 2 | 3 | 4 | 5;

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

function detectStep(columns: Column[], rows: Row[]): WorkflowStep {
  const enrichCols = columns.filter((c) => ENRICHMENT_TYPES.has(c.type));

  // Step 1: no rows yet
  if (rows.length === 0) return 1;

  // Step 2: has rows but no enrichment columns
  if (enrichCols.length === 0) return 2;

  // Collect all enrichment cells across rows
  const enrichCellStatuses: string[] = [];
  for (const row of rows) {
    for (const col of enrichCols) {
      const cell = row.cells.find((c) => c.column_id === col.id);
      if (cell) enrichCellStatuses.push(cell.status);
    }
  }

  const total = enrichCellStatuses.length;
  if (total === 0) return 3;

  const running = enrichCellStatuses.filter((s) => s === "running" || s === "pending").length;
  const review = enrichCellStatuses.filter((s) => s === "review" || s === "error").length;
  const found = enrichCellStatuses.filter((s) => s === "found").length;
  const empty = enrichCellStatuses.filter((s) => s === "empty").length;

  // Step 3: enrichment columns exist but cells are mostly empty/pending (hasn't run yet)
  if (running > 0) return 3;
  if (empty === total) return 3;

  // Step 4: has run but some need review
  if (review > 0) return 4;

  // Step 5: most are found, ready for email
  if (found > 0) return 5;

  // Default fallback: still needs to run
  return 3;
}

interface StepInfo {
  number: WorkflowStep;
  label: string;
  title: string;
  description: string;
}

const STEPS: StepInfo[] = [
  { number: 1, label: "Add Data", title: "Add your data", description: "Import a CSV file, use AI to find companies, or add rows manually." },
  { number: 2, label: "Enrich", title: "Add enrichment columns", description: "Add enrichment columns to automatically find missing data (names, emails, titles)." },
  { number: 3, label: "Run", title: "Run enrichment", description: "Run enrichment to fill in your data. This may take a few minutes." },
  { number: 4, label: "Review", title: "Review results", description: "Check your enrichment results. Some rows may need manual review." },
  { number: 5, label: "Email", title: "Send outreach", description: "Compose personalized emails using your enriched data." },
];

function StepCircle({ num, state }: { num: number; state: "active" | "complete" | "upcoming" }) {
  return (
    <div
      className={cn(
        "w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold font-mono shrink-0 transition-all duration-300",
        state === "active" && "bg-[#06b6d4] text-[#09090b]",
        state === "complete" && "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40",
        state === "upcoming" && "bg-[#27272a] text-[#52525b] border border-[#3f3f46]"
      )}
      style={state === "active" ? { boxShadow: "0 0 12px rgba(6,182,212,0.5)" } : undefined}
    >
      {state === "complete" ? "✓" : num}
    </div>
  );
}

function ConnectorLine({ filled }: { filled: boolean }) {
  return (
    <div className="flex-1 h-px mx-1 transition-all duration-500" style={{
      background: filled
        ? "linear-gradient(90deg, rgba(16,185,129,0.5), rgba(6,182,212,0.3))"
        : "#27272a",
    }} />
  );
}

export function WorkflowGuide({
  tableId,
  columns,
  rows,
  onImportCSV,
  onAddRow,
  onOpenEnrichment,
  onQuickSetup,
  onRunAll,
}: WorkflowGuideProps) {
  const router = useRouter();
  const storageKey = `scrpr-guide-${tableId}`;

  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    try {
      const stored = localStorage.getItem(storageKey);
      return stored === "collapsed";
    } catch {
      return false;
    }
  });

  const [dismissed, setDismissed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    try {
      const stored = localStorage.getItem(storageKey);
      return stored === "dismissed";
    } catch {
      return false;
    }
  });

  // Manual step override (for skip)
  const [manualStep, setManualStep] = useState<WorkflowStep | null>(null);

  const autoStep = useMemo(() => detectStep(columns, rows), [columns, rows]);
  const currentStep: WorkflowStep = manualStep !== null ? manualStep : autoStep;

  // When auto-step advances past manual override, clear it
  useEffect(() => {
    if (manualStep !== null && autoStep > manualStep) {
      setManualStep(null);
    }
  }, [autoStep, manualStep]);

  const persist = (state: "collapsed" | "dismissed") => {
    try { localStorage.setItem(storageKey, state); } catch {}
  };

  const handleCollapse = () => {
    setCollapsed(true);
    persist("collapsed");
  };

  const handleExpand = () => {
    setCollapsed(false);
    try { localStorage.removeItem(storageKey); } catch {}
  };

  const handleDismiss = () => {
    setDismissed(true);
    persist("dismissed");
  };

  const handleSkip = () => {
    const next = Math.min(currentStep + 1, 5) as WorkflowStep;
    setManualStep(next);
  };

  // Enrich stats
  const enrichCols = useMemo(() => columns.filter((c) => ENRICHMENT_TYPES.has(c.type)), [columns]);
  const regularCols = useMemo(() => columns.filter((c) => !ENRICHMENT_TYPES.has(c.type)), [columns]);

  const enrichStats = useMemo(() => {
    let found = 0, review = 0, notFound = 0, running = 0, empty = 0;
    for (const row of rows) {
      for (const col of enrichCols) {
        const cell = row.cells.find((c) => c.column_id === col.id);
        const status = cell?.status ?? "empty";
        if (status === "found") found++;
        else if (status === "review" || status === "error") review++;
        else if (status === "not_found") notFound++;
        else if (status === "running" || status === "pending") running++;
        else empty++;
      }
    }
    return { found, review, notFound, running, empty };
  }, [rows, enrichCols]);

  // Rows with email addresses
  const rowsWithEmail = useMemo(() => {
    const emailCols = columns.filter((c) => c.type === "email");
    return rows.filter((row) =>
      emailCols.some((col) => {
        const cell = row.cells.find((c) => c.column_id === col.id);
        return cell?.value && cell.value.trim().length > 0;
      })
    ).length;
  }, [rows, columns]);

  const allComplete = currentStep === 5 && enrichStats.review === 0;

  if (dismissed) return null;

  // Collapsed state
  if (collapsed) {
    return (
      <div className="mx-4 mt-3 mb-1 flex items-center justify-between px-4 py-2 rounded-lg border border-[#27272a] bg-[#18181b]/60 text-xs text-[#71717a]">
        <span className="font-mono">
          {allComplete
            ? "✓ Workflow complete"
            : `Step ${currentStep} of 5: ${STEPS[currentStep - 1].label}`}
        </span>
        <button
          onClick={handleExpand}
          className="text-[#52525b] hover:text-[#a1a1aa] transition-colors px-2 py-0.5 rounded hover:bg-[#27272a]"
        >
          Expand
        </button>
      </div>
    );
  }

  return (
    <div className="mx-4 mt-3 mb-1 rounded-xl border border-[#27272a] bg-[#18181b]/80 backdrop-blur-sm overflow-hidden"
      style={{ boxShadow: "0 0 0 1px rgba(6,182,212,0.06), inset 0 1px 0 rgba(255,255,255,0.03)" }}
    >
      {/* Top cyan accent */}
      <div className="h-px bg-gradient-to-r from-transparent via-[#06b6d4]/40 to-transparent" />

      <div className="px-5 py-4">
        {/* Step indicators */}
        <div className="flex items-center mb-5">
          {STEPS.map((step, i) => {
            const state: "active" | "complete" | "upcoming" =
              step.number === currentStep ? "active"
              : step.number < currentStep ? "complete"
              : "upcoming";
            return (
              <div key={step.number} className="flex items-center" style={{ flex: i < STEPS.length - 1 ? "1 1 0" : undefined }}>
                <div className="flex flex-col items-center gap-1">
                  <StepCircle num={step.number} state={state} />
                  <span className={cn(
                    "text-[10px] font-mono whitespace-nowrap transition-colors",
                    state === "active" && "text-[#06b6d4] font-semibold",
                    state === "complete" && "text-emerald-400",
                    state === "upcoming" && "text-[#3f3f46]"
                  )}>
                    {step.label}
                  </span>
                </div>
                {i < STEPS.length - 1 && (
                  <ConnectorLine filled={step.number < currentStep} />
                )}
              </div>
            );
          })}
        </div>

        {/* Current step content */}
        {allComplete ? (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-emerald-400 text-base">✓</span>
              <div>
                <p className="text-sm font-semibold text-[#fafafa]">Workflow complete</p>
                <p className="text-xs text-[#52525b]">All steps done — your table is ready for outreach.</p>
              </div>
            </div>
            <button onClick={handleDismiss} className="text-xs text-[#3f3f46] hover:text-[#71717a] transition-colors">
              Hide guide
            </button>
          </div>
        ) : (
          <div>
            {/* Step title + description */}
            <div className="flex items-start justify-between gap-4 mb-3">
              <div>
                <p className="text-sm font-semibold text-[#fafafa] mb-0.5">
                  Step {currentStep}: {STEPS[currentStep - 1].title}
                </p>
                <p className="text-xs text-[#71717a] leading-relaxed">
                  {STEPS[currentStep - 1].description}
                </p>
              </div>

              {/* Controls */}
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={handleSkip}
                  className="text-xs text-[#3f3f46] hover:text-[#71717a] transition-colors whitespace-nowrap"
                >
                  Skip →
                </button>
                <button
                  onClick={handleCollapse}
                  className="text-xs text-[#3f3f46] hover:text-[#71717a] transition-colors"
                >
                  Hide
                </button>
              </div>
            </div>

            {/* Step-specific content */}
            <div className="flex items-center gap-2 flex-wrap">
              {currentStep === 1 && (
                <>
                  <button
                    onClick={onImportCSV}
                    className="guide-action-btn"
                  >
                    <span>⬆</span> Import CSV
                  </button>
                  <button
                    onClick={() => router.push("/find")}
                    className="guide-action-btn"
                  >
                    <span>🔍</span> AI Find
                  </button>
                  <button
                    onClick={onAddRow}
                    className="guide-action-btn"
                  >
                    <span>+</span> Add Row
                  </button>
                </>
              )}

              {currentStep === 2 && (
                <>
                  {onQuickSetup && (
                    <button
                      onClick={onQuickSetup}
                      className="guide-action-btn flex items-center gap-1.5 bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/20"
                    >
                      <span>⚡</span> Quick Setup (Key Contact + Email)
                    </button>
                  )}
                  <span className="text-[10px] text-[#52525b] mx-1">or manually:</span>
                  <button
                    onClick={() => onOpenEnrichment("agent")}
                    className="guide-action-btn guide-action-btn--cyan"
                  >
                    <span>🤖</span> + AI Agent
                  </button>
                  <button
                    onClick={() => onOpenEnrichment("waterfall")}
                    className="guide-action-btn guide-action-btn--cyan"
                  >
                    <span>⛓</span> + Waterfall
                  </button>
                </>
              )}

              {currentStep === 3 && (
                <>
                  <button
                    onClick={onRunAll}
                    className="guide-action-btn guide-action-btn--cyan"
                  >
                    <span>▶</span> Run All Enrichments
                  </button>
                  {enrichStats.running > 0 && (
                    <div className="flex items-center gap-2 ml-1">
                      <div className="w-28 h-1.5 rounded-full bg-[#27272a] overflow-hidden">
                        <div
                          className="h-full bg-[#06b6d4] rounded-full transition-all duration-500"
                          style={{
                            width: `${Math.round(((enrichStats.found + enrichStats.notFound + enrichStats.review) / (enrichStats.found + enrichStats.notFound + enrichStats.review + enrichStats.running + enrichStats.empty)) * 100)}%`
                          }}
                        />
                      </div>
                      <span className="text-[10px] font-mono text-[#52525b]">
                        {enrichStats.found + enrichStats.notFound + enrichStats.review}/{enrichStats.found + enrichStats.notFound + enrichStats.review + enrichStats.running + enrichStats.empty} completed
                      </span>
                    </div>
                  )}
                  {enrichStats.running === 0 && rows.length > 0 && (
                    <span className="text-[10px] font-mono text-[#3f3f46] ml-1">
                      ~{Math.max(1, Math.ceil(rows.length / 10))} min for {rows.length} row{rows.length !== 1 ? "s" : ""}
                    </span>
                  )}
                </>
              )}

              {currentStep === 4 && (
                <>
                  <div className="flex items-center gap-3 mr-2">
                    <span className="text-[10px] font-mono text-emerald-400">{enrichStats.found} found</span>
                    {enrichStats.review > 0 && (
                      <span className="text-[10px] font-mono text-amber-400">{enrichStats.review} needs review</span>
                    )}
                    {enrichStats.notFound > 0 && (
                      <span className="text-[10px] font-mono text-[#52525b]">{enrichStats.notFound} not found</span>
                    )}
                  </div>
                </>
              )}

              {currentStep === 5 && (
                <>
                  <button
                    onClick={() => router.push(`/table/${tableId}/emails`)}
                    className="guide-action-btn guide-action-btn--cyan"
                  >
                    <span>📧</span> Compose Emails
                  </button>
                  {rowsWithEmail > 0 && (
                    <span className="text-[10px] font-mono text-[#52525b] ml-1">
                      {rowsWithEmail} row{rowsWithEmail !== 1 ? "s" : ""} with email addresses ready
                    </span>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
