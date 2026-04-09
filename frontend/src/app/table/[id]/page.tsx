"use client";
import { use, useState, useCallback, useEffect, useRef } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTable, useColumns, useRows, useCreateColumn, useCreateRow } from "@/hooks/use-api";
import { useWebSocket } from "@/hooks/use-websocket";
import { api } from "@/lib/api-client";
import { DataTable } from "@/components/table/data-table";
import { EnrichmentPanel } from "@/components/enrichment/enrichment-panel";
import { KeyboardShortcutsDialog } from "@/components/table/keyboard-shortcuts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Column } from "@/types";
import { cn } from "@/lib/utils";

const ENRICHMENT_TYPES = new Set(["agent", "waterfall"]);

function EnrichmentColumnHeader({
  column,
  tableId,
}: {
  column: Column;
  tableId: string;
}) {
  const [isRunning, setIsRunning] = useState(false);

  const { data: status } = useQuery({
    queryKey: ["enrich-status", tableId, column.id],
    queryFn: () => api.enrichments.status(tableId, column.id),
    enabled: isRunning,
    refetchInterval: isRunning ? 2000 : false,
  });

  const running = status?.running ?? 0;
  const completed = status?.completed ?? 0;
  const total = status?.total ?? 0;
  const isFinished = isRunning && total > 0 && running === 0 && completed >= total;

  const handleRun = async () => {
    try {
      setIsRunning(true);
      await api.enrichments.trigger(tableId, column.id);
    } catch {
      setIsRunning(false);
    }
  };

  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  const typeLabel = column.type === "agent" ? "AI" : "⛓";

  return (
    <div className="flex items-center gap-2 w-full group">
      <div className="flex items-center gap-1.5 flex-1 min-w-0">
        <span className="text-[10px] font-mono text-[#52525b]">{typeLabel}</span>
        <span className="truncate text-xs font-medium text-[#a1a1aa]">{column.name}</span>
        {isRunning && !isFinished && total > 0 && (
          <span className="text-[10px] font-mono text-[#06b6d4] whitespace-nowrap">
            {completed}/{total}
          </span>
        )}
      </div>
      <button
        onClick={handleRun}
        disabled={isRunning && !isFinished}
        title="Run enrichment"
        className={cn(
          "shrink-0 px-1.5 py-0.5 rounded text-[10px] font-mono transition-all",
          isRunning && !isFinished
            ? "text-[#06b6d4] bg-[#06b6d4]/10 cursor-not-allowed opacity-70"
            : "text-[#06b6d4] bg-[#06b6d4]/10 hover:bg-[#06b6d4]/20 hover:shadow-[0_0_8px_rgba(6,182,212,0.2)]"
        )}
      >
        {isRunning && !isFinished ? "..." : "▶"}
      </button>

      {/* Progress bar on header */}
      {isRunning && !isFinished && total > 0 && (
        <div className="absolute inset-x-0 bottom-0 h-0.5 bg-[#27272a]">
          <div
            className="h-full bg-[#06b6d4] transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

function RunAllButton({ tableId, enrichmentColumns }: { tableId: string; enrichmentColumns: Column[] }) {
  const [running, setRunning] = useState(false);

  const handleRunAll = async () => {
    if (enrichmentColumns.length === 0) return;
    setRunning(true);
    try {
      await Promise.all(
        enrichmentColumns.map((col) => api.enrichments.trigger(tableId, col.id))
      );
    } finally {
      setTimeout(() => setRunning(false), 3000);
    }
  };

  if (enrichmentColumns.length === 0) return null;

  return (
    <button
      onClick={handleRunAll}
      disabled={running}
      className={cn(
        "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-all",
        running
          ? "bg-[#06b6d4]/10 text-[#06b6d4] cursor-not-allowed"
          : "bg-[#06b6d4] text-[#09090b] hover:bg-[#22d3ee]"
      )}
      style={running ? undefined : { boxShadow: "0 0 12px rgba(6,182,212,0.25)" }}
    >
      <span className="text-xs">{running ? "⏳" : "▶"}</span>
      {running ? "Running..." : "Run All"}
    </button>
  );
}

function TableStats({ rows, columns }: { rows: unknown[]; columns: unknown[] }) {
  return (
    <div className="flex items-center gap-4 text-xs text-[#52525b] font-mono">
      <span>
        <span className="text-[#71717a]">{rows.length}</span>{" "}
        {rows.length === 1 ? "row" : "rows"}
      </span>
      <span className="text-[#3f3f46]">·</span>
      <span>
        <span className="text-[#71717a]">{columns.length}</span>{" "}
        {columns.length === 1 ? "col" : "cols"}
      </span>
    </div>
  );
}

export default function TablePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: table } = useTable(id);
  const { data: columns = [] } = useColumns(id);
  const { data: rows = [] } = useRows(id);
  const createColumn = useCreateColumn(id);
  const createRow = useCreateRow(id);
  const queryClient = useQueryClient();
  const [colName, setColName] = useState("");
  const [colDialogOpen, setColDialogOpen] = useState(false);
  const [enrichPanelOpen, setEnrichPanelOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const csvInputRef = useRef<HTMLInputElement>(null);

  useWebSocket(id);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "?") {
        e.preventDefault();
        setShortcutsOpen(true);
      }
      if (e.key === "e" && e.ctrlKey) {
        e.preventDefault();
        setEnrichPanelOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const handleAddColumn = async () => {
    if (!colName.trim()) return;
    await createColumn.mutateAsync({ name: colName.trim(), type: "text" });
    setColName("");
    setColDialogOpen(false);
  };

  const handleAddRow = () => createRow.mutateAsync(undefined);

  const handleCellEdit = async (cellId: string, value: string) => {
    await api.cells.update(cellId, { value });
  };

  const handleEnrichmentSave = useCallback(
    async (config: { name: string; type: "agent" | "waterfall"; config: Record<string, unknown> }) => {
      await createColumn.mutateAsync({
        name: config.name,
        type: config.type,
        config: config.config,
      });
    },
    [createColumn],
  );

  const handleExportCSV = () => {
    api.csv.export(id, columns, rows);
  };

  const handleImportCSV = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsImporting(true);
    try {
      await api.csv.import(id, file);
      await queryClient.invalidateQueries({ queryKey: ["columns", id] });
      await queryClient.invalidateQueries({ queryKey: ["rows", id] });
    } catch (err) {
      console.error("CSV import failed:", err);
    } finally {
      setIsImporting(false);
      if (csvInputRef.current) csvInputRef.current.value = "";
    }
  };

  const enrichmentColumns = columns.filter((c) => ENRICHMENT_TYPES.has(c.type));

  return (
    <div className="h-full flex flex-col">
      {/* ── Header ── */}
      <div className="border-b border-[#27272a] bg-[#09090b]/60 backdrop-blur-sm shrink-0">
        {/* Title row */}
        <div className="flex items-center justify-between gap-4 px-6 pt-5 pb-3">
          <div className="min-w-0">
            <h1 className="text-xl font-bold text-[#fafafa] font-mono truncate">
              {table?.name ?? (
                <span className="skeleton h-6 w-40 inline-block rounded" />
              )}
            </h1>
            <TableStats rows={rows} columns={columns} />
          </div>
          <RunAllButton tableId={id} enrichmentColumns={enrichmentColumns} />
        </div>

        {/* Action toolbar */}
        <div className="flex items-center gap-2 px-6 pb-3 flex-wrap">
          {/* Column button */}
          <Dialog open={colDialogOpen} onOpenChange={setColDialogOpen}>
            <DialogTrigger
              render={
                <button className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-[#a1a1aa] bg-[#27272a] hover:bg-[#3f3f46] border border-[#3f3f46] hover:border-[#52525b] transition-all" />
              }
            >
              + Column
            </DialogTrigger>
            <DialogContent className="bg-[#18181b] border-[#3f3f46] text-[#fafafa]">
              <DialogHeader>
                <DialogTitle className="text-[#fafafa] font-mono">Add Column</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-2">
                <div>
                  <Label className="text-[#a1a1aa] text-xs">Column name</Label>
                  <Input
                    value={colName}
                    onChange={(e) => setColName(e.target.value)}
                    placeholder="e.g. Company"
                    onKeyDown={(e) => e.key === "Enter" && handleAddColumn()}
                    className="mt-1.5 bg-[#09090b] border-[#3f3f46] text-[#fafafa] placeholder:text-[#52525b] focus-visible:border-[#06b6d4] focus-visible:ring-[#06b6d4]/20"
                  />
                </div>
                <Button
                  onClick={handleAddColumn}
                  className="w-full bg-[#06b6d4] hover:bg-[#22d3ee] text-[#09090b] font-semibold border-0"
                >
                  Add Column
                </Button>
              </div>
            </DialogContent>
          </Dialog>

          {/* Row */}
          <button
            onClick={handleAddRow}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-[#a1a1aa] bg-[#27272a] hover:bg-[#3f3f46] border border-[#3f3f46] hover:border-[#52525b] transition-all"
          >
            + Row
          </button>

          {/* Import */}
          <input
            ref={csvInputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={handleImportCSV}
          />
          <button
            onClick={() => csvInputRef.current?.click()}
            disabled={isImporting}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-[#a1a1aa] bg-[#27272a] hover:bg-[#3f3f46] border border-[#3f3f46] hover:border-[#52525b] transition-all disabled:opacity-50"
          >
            <span>⬆</span>
            {isImporting ? "Importing..." : "Import"}
          </button>

          {/* Export */}
          <button
            onClick={handleExportCSV}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-[#a1a1aa] bg-[#27272a] hover:bg-[#3f3f46] border border-[#3f3f46] hover:border-[#52525b] transition-all"
          >
            <span>⬇</span>
            Export
          </button>

          {/* Spacer */}
          <div className="flex-1" />

          {/* Enrich Data */}
          <button
            onClick={() => setEnrichPanelOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold text-[#06b6d4] bg-[#06b6d4]/10 hover:bg-[#06b6d4]/20 border border-[#06b6d4]/20 hover:border-[#06b6d4]/40 transition-all"
          >
            + Enrich Data
          </button>

          {/* Email */}
          <Link
            href={`/table/${id}/emails`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-[#a1a1aa] bg-[#27272a] hover:bg-[#3f3f46] border border-[#3f3f46] hover:border-[#52525b] transition-all"
          >
            <span>📧</span>
            Email
          </Link>

          {/* Shortcuts help */}
          <button
            onClick={() => setShortcutsOpen(true)}
            className="inline-flex items-center justify-center w-7 h-7 rounded-md text-xs font-mono text-[#52525b] hover:text-[#a1a1aa] hover:bg-[#27272a] border border-transparent hover:border-[#3f3f46] transition-all"
            title="Keyboard shortcuts (?)"
          >
            ?
          </button>
        </div>
      </div>

      {/* ── Data table ── */}
      <div className="flex-1 min-h-0">
        {columns.length === 0 && rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-8 card-animate">
            <div className="w-16 h-16 rounded-xl border-2 border-dashed border-[#3f3f46] flex items-center justify-center mb-4 bg-[#18181b]">
              <span className="text-2xl opacity-50">◫</span>
            </div>
            <h3 className="text-base font-semibold text-[#a1a1aa] mb-1">Empty table</h3>
            <p className="text-[#52525b] text-sm">Add columns and rows to get started, or import a CSV</p>
          </div>
        ) : (
          <DataTable columns={columns} rows={rows} onCellEdit={handleCellEdit} />
        )}
      </div>

      {/* Enrichment panel */}
      <EnrichmentPanel
        open={enrichPanelOpen}
        onClose={() => setEnrichPanelOpen(false)}
        onSave={handleEnrichmentSave}
      />

      {/* Keyboard shortcuts dialog */}
      <KeyboardShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </div>
  );
}
