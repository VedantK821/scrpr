"use client";
import { use, useState, useCallback } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useTable, useColumns, useRows, useCreateColumn, useCreateRow } from "@/hooks/use-api";
import { useWebSocket } from "@/hooks/use-websocket";
import { api } from "@/lib/api-client";
import { DataTable } from "@/components/table/data-table";
import { EnrichmentPanel } from "@/components/enrichment/enrichment-panel";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Column } from "@/types";

// Enrichment column types
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
    select: (data) => data,
  });

  // Auto-stop polling when enrichment finishes
  const running = status?.running ?? 0;
  const completed = status?.completed ?? 0;
  const total = status?.total ?? 0;
  const isFinished = isRunning && total > 0 && running === 0 && completed >= total;

  const handleRun = async () => {
    try {
      setIsRunning(true);
      await api.enrichments.trigger(tableId, column.id);
    } catch (e) {
      setIsRunning(false);
    }
  };

  return (
    <div className="flex items-center gap-1 w-full">
      <span className="truncate flex-1 text-xs font-medium">{column.name}</span>
      {isRunning && total > 0 && !isFinished ? (
        <span className="text-xs text-blue-400 whitespace-nowrap">
          {completed}/{total}
        </span>
      ) : null}
      <button
        onClick={handleRun}
        disabled={isRunning && !isFinished}
        title="Run enrichment"
        className="ml-1 px-1.5 py-0.5 rounded text-xs font-medium bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
      >
        {isRunning && !isFinished ? "..." : "▶ Run"}
      </button>
    </div>
  );
}

function QuotaDisplay() {
  const { data: quota } = useQuery({
    queryKey: ["quota"],
    queryFn: api.enrichments.quota,
    staleTime: 60_000,
  });

  if (!quota) return null;

  const entries = Object.entries(quota);
  if (entries.length === 0) return null;

  return (
    <div className="flex items-center gap-3">
      {entries.map(([source, info]) => (
        <span key={source} className="text-xs text-zinc-500">
          {source}:{" "}
          <span className={info.remaining < 5 ? "text-amber-400" : "text-zinc-400"}>
            {info.remaining}/{info.limit}
          </span>
        </span>
      ))}
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
  const [colName, setColName] = useState("");
  const [colDialogOpen, setColDialogOpen] = useState(false);
  const [enrichPanelOpen, setEnrichPanelOpen] = useState(false);

  // Connect WebSocket for real-time cell updates
  useWebSocket(id);

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

  const enrichmentColumns = columns.filter((c) => ENRICHMENT_TYPES.has(c.type));

  return (
    <main className="h-screen flex flex-col bg-zinc-950 text-zinc-100">
      <div className="flex items-center gap-4 px-4 py-3 border-b border-zinc-800">
        <Link href="/" className="text-zinc-400 hover:text-zinc-200 text-sm">
          ← Back
        </Link>
        <h1 className="text-lg font-semibold">{table?.name ?? "Loading..."}</h1>

        <div className="ml-auto flex gap-2 items-center">
          {/* Enrichment column run buttons */}
          {enrichmentColumns.map((col) => (
            <EnrichmentColumnHeader key={col.id} column={col} tableId={id} />
          ))}

          {/* Export CSV */}
          <Button variant="outline" size="sm" onClick={handleExportCSV}>
            Export CSV
          </Button>

          {/* Enrich Data panel trigger */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setEnrichPanelOpen(true)}
          >
            + Enrich Data
          </Button>

          {/* Add plain text column */}
          <Dialog open={colDialogOpen} onOpenChange={setColDialogOpen}>
            <DialogTrigger render={<Button variant="outline" size="sm" />}>+ Column</DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Add Column</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-4">
                <div>
                  <Label>Column name</Label>
                  <Input
                    value={colName}
                    onChange={(e) => setColName(e.target.value)}
                    placeholder="e.g. Company"
                    onKeyDown={(e) => e.key === "Enter" && handleAddColumn()}
                  />
                </div>
                <Button onClick={handleAddColumn} className="w-full">
                  Add
                </Button>
              </div>
            </DialogContent>
          </Dialog>

          <Button variant="outline" size="sm" onClick={handleAddRow}>
            + Row
          </Button>
        </div>
      </div>

      <div className="flex-1 min-h-0">
        <DataTable columns={columns} rows={rows} onCellEdit={handleCellEdit} />
      </div>

      <div className="flex items-center gap-4 px-4 py-2 border-t border-zinc-800 text-sm text-zinc-500">
        <span>Rows: {rows.length}</span>
        <span>Columns: {columns.length}</span>
        <div className="ml-auto">
          <QuotaDisplay />
        </div>
      </div>

      {/* Slide-out enrichment panel */}
      <EnrichmentPanel
        open={enrichPanelOpen}
        onClose={() => setEnrichPanelOpen(false)}
        onSave={handleEnrichmentSave}
      />
    </main>
  );
}
