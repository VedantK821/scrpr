"use client";
import { use, useState, useCallback, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useTable, useColumns, useRows,
  useCreateColumn, useCreateRow,
  useDeleteColumn, useUpdateColumn,
  useDeleteRow, useUpdateTable,
} from "@/hooks/use-api";
import { useWebSocket } from "@/hooks/use-websocket";
import { api } from "@/lib/api-client";
import { DataTable } from "@/components/table/data-table";
import { EnrichmentPanel } from "@/components/enrichment/enrichment-panel";
import { KeyboardShortcutsDialog } from "@/components/table/keyboard-shortcuts";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
  DialogTrigger, DialogFooter, DialogClose,
} from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import type { Column, ColumnType } from "@/types";
import { cn } from "@/lib/utils";

const ENRICHMENT_TYPES = new Set(["agent", "waterfall"]);

const COLUMN_TYPES: { value: string; label: string; icon: string }[] = [
  { value: "text", label: "Text", icon: "Aa" },
  { value: "url", label: "URL", icon: "🔗" },
  { value: "email", label: "Email", icon: "✉" },
  { value: "number", label: "Number", icon: "#" },
  { value: "date", label: "Date", icon: "📅" },
  { value: "checkbox", label: "Checkbox", icon: "☑" },
  { value: "select", label: "Select", icon: "▾" },
];

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
          ? "bg-[#06b6d4]/10 text-[#06b6d4] cursor-not-allowed run-pulse"
          : "btn-cyan-gradient"
      )}
    >
      <span className="text-xs">{running ? "⏳" : "▶"}</span>
      {running ? "Running..." : "Run All"}
    </button>
  );
}

function TableStats({ rows, columns }: { rows: unknown[]; columns: unknown[] }) {
  return (
    <div className="flex items-center gap-2 text-xs text-[#52525b] font-mono mt-1">
      <span className="text-[#71717a]">{rows.length}</span>
      <span>{rows.length === 1 ? "row" : "rows"}</span>
      <span className="text-[#3f3f46]">·</span>
      <span className="text-[#71717a]">{columns.length}</span>
      <span>{columns.length === 1 ? "col" : "cols"}</span>
    </div>
  );
}

// Inline-editable table name
function EditableTableName({ tableId, initialName }: { tableId: string; initialName: string }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(initialName);
  const inputRef = useRef<HTMLInputElement>(null);
  const updateTable = useUpdateTable();
  const { success, error } = useToast();

  // Sync if table name changes from external source
  useEffect(() => {
    if (!editing) setValue(initialName);
  }, [initialName, editing]);

  const startEdit = () => {
    setEditing(true);
    setTimeout(() => inputRef.current?.select(), 0);
  };

  const commitEdit = async () => {
    const trimmed = value.trim();
    if (!trimmed || trimmed === initialName) {
      setValue(initialName);
      setEditing(false);
      return;
    }
    try {
      await updateTable.mutateAsync({ id: tableId, name: trimmed });
      success("Table renamed");
    } catch (err) {
      error(err instanceof Error ? err.message : "Failed to rename table");
      setValue(initialName);
    } finally {
      setEditing(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") commitEdit();
    if (e.key === "Escape") {
      setValue(initialName);
      setEditing(false);
    }
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={commitEdit}
        onKeyDown={handleKeyDown}
        autoFocus
        className="text-2xl font-bold text-[#fafafa] font-mono tracking-tight bg-transparent border-b border-[#06b6d4] outline-none w-full max-w-sm"
        disabled={updateTable.isPending}
      />
    );
  }

  return (
    <button
      onClick={startEdit}
      title="Click to rename"
      className="text-2xl font-bold text-[#fafafa] font-mono tracking-tight truncate hover:text-[#06b6d4] transition-colors group/rename"
    >
      {initialName}
      <span className="ml-2 text-sm text-[#3f3f46] group-hover/rename:text-[#52525b] transition-colors">✎</span>
    </button>
  );
}

// Toolbar button variant styles
const toolbarBtnBase = "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150";
const toolbarBtnDefault = `${toolbarBtnBase} text-[#a1a1aa] bg-[#27272a] hover:bg-[#3f3f46] border border-[#3f3f46] hover:border-[#52525b] hover:text-[#fafafa]`;
const toolbarBtnEnrich = `${toolbarBtnBase} text-[#06b6d4] bg-[#06b6d4]/10 hover:bg-[#06b6d4]/20 border border-[#06b6d4]/20 hover:border-[#06b6d4]/50 font-semibold`;

// Toolbar divider
function ToolbarDivider() {
  return <div className="h-5 w-px bg-[#3f3f46] mx-1" />;
}

// Column header with dropdown (for non-enrichment columns)
function ColumnHeaderMenu({
  column,
  tableId,
}: {
  column: Column;
  tableId: string;
}) {
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [newName, setNewName] = useState(column.name);
  const deleteColumn = useDeleteColumn(tableId);
  const updateColumn = useUpdateColumn(tableId);
  const { success, error } = useToast();

  const handleRename = async () => {
    const trimmed = newName.trim();
    if (!trimmed) return;
    try {
      await updateColumn.mutateAsync({ colId: column.id, data: { name: trimmed } });
      success("Column renamed");
      setRenameOpen(false);
    } catch (err) {
      error(err instanceof Error ? err.message : "Failed to rename column");
    }
  };

  const handleDelete = async () => {
    try {
      await deleteColumn.mutateAsync(column.id);
      success(`Column "${column.name}" deleted`);
      setDeleteOpen(false);
    } catch (err) {
      error(err instanceof Error ? err.message : "Failed to delete column");
    }
  };

  return (
    <>
      <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
        <DropdownMenuTrigger
          render={
            <button className="flex items-center gap-1.5 w-full hover:text-[#06b6d4] transition-colors" />
          }
        >
          <span className="truncate">{column.name}</span>
          <span className="text-[10px] text-[#52525b] shrink-0">▾</span>
        </DropdownMenuTrigger>
        <DropdownMenuContent side="bottom" align="start" className="min-w-[130px] bg-[#18181b] border-[#3f3f46]">
          <DropdownMenuItem
            onClick={() => { setMenuOpen(false); setNewName(column.name); setRenameOpen(true); }}
            className="text-[#a1a1aa] focus:text-[#fafafa] focus:bg-[#27272a]"
          >
            Rename
          </DropdownMenuItem>
          <DropdownMenuSeparator className="bg-[#27272a]" />
          <DropdownMenuItem
            variant="destructive"
            onClick={() => { setMenuOpen(false); setDeleteOpen(true); }}
            className="text-red-400 focus:text-red-300 focus:bg-red-950/30"
          >
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Rename dialog */}
      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent className="bg-[#18181b] border-[#3f3f46] text-[#fafafa]">
          <DialogHeader>
            <DialogTitle className="text-[#fafafa] font-mono">Rename Column</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleRename()}
              autoFocus
              className="bg-[#09090b] border-[#3f3f46] text-[#fafafa] focus-visible:border-[#06b6d4] focus-visible:ring-[#06b6d4]/20"
            />
            <div className="flex gap-2 justify-end">
              <DialogClose render={<Button variant="outline" className="border-[#3f3f46] text-[#a1a1aa] hover:bg-[#27272a]" />}>
                Cancel
              </DialogClose>
              <Button
                onClick={handleRename}
                disabled={updateColumn.isPending || !newName.trim()}
                className="btn-cyan-gradient border-0 font-semibold"
              >
                {updateColumn.isPending ? "Saving..." : "Rename"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="bg-[#18181b] border-[#3f3f46] text-[#fafafa]">
          <DialogHeader>
            <DialogTitle className="text-[#fafafa] font-mono">Delete Column</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-[#a1a1aa] leading-relaxed">
            Delete <span className="text-[#fafafa] font-semibold">"{column.name}"</span>? All cell data in this column will be permanently removed.
          </p>
          <div className="flex gap-2 justify-end mt-2">
            <DialogClose render={<Button variant="outline" className="border-[#3f3f46] text-[#a1a1aa] hover:bg-[#27272a]" />}>
              Cancel
            </DialogClose>
            <Button
              onClick={handleDelete}
              disabled={deleteColumn.isPending}
              className="bg-red-900/30 border border-red-700/40 text-red-400 hover:bg-red-900/50"
            >
              {deleteColumn.isPending ? "Deleting..." : "Delete Column"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function TablePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { data: table } = useTable(id);
  const { data: columns = [] } = useColumns(id);
  const { data: rows = [] } = useRows(id);
  const createColumn = useCreateColumn(id);
  const createRow = useCreateRow(id);
  const deleteRow = useDeleteRow(id);
  const queryClient = useQueryClient();
  const { success, error } = useToast();

  const [colName, setColName] = useState("");
  const [colType, setColType] = useState("text");
  const [colDialogOpen, setColDialogOpen] = useState(false);
  const [enrichPanelOpen, setEnrichPanelOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set());
  const [deletingRows, setDeletingRows] = useState(false);
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
    try {
      await createColumn.mutateAsync({ name: colName.trim(), type: colType });
      success("Column added");
      setColName("");
      setColType("text");
      setColDialogOpen(false);
    } catch (err) {
      error(err instanceof Error ? err.message : "Failed to add column");
    }
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
    api.csv.exportServer(id);
  };

  const handleImportCSV = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsImporting(true);
    try {
      const result = await api.csv.import(id, file);
      await queryClient.invalidateQueries({ queryKey: ["columns", id] });
      await queryClient.invalidateQueries({ queryKey: ["rows", id] });
      success(`Imported ${result.rows_imported} rows`);
    } catch (err) {
      error(err instanceof Error ? err.message : "CSV import failed");
    } finally {
      setIsImporting(false);
      if (csvInputRef.current) csvInputRef.current.value = "";
    }
  };

  const handleDeleteSelectedRows = async () => {
    if (selectedRowIds.size === 0) return;
    setDeletingRows(true);
    try {
      await Promise.all(Array.from(selectedRowIds).map((rowId) => deleteRow.mutateAsync(rowId)));
      success(`Deleted ${selectedRowIds.size} row${selectedRowIds.size === 1 ? "" : "s"}`);
      setSelectedRowIds(new Set());
    } catch (err) {
      error(err instanceof Error ? err.message : "Failed to delete rows");
    } finally {
      setDeletingRows(false);
    }
  };

  const enrichmentColumns = columns.filter((c) => ENRICHMENT_TYPES.has(c.type));
  const regularColumns = columns.filter((c) => !ENRICHMENT_TYPES.has(c.type));

  return (
    <div className="h-full flex flex-col">
      {/* ── Header ── */}
      <div className="border-b border-[#27272a] bg-[#09090b]/70 backdrop-blur-sm shrink-0">
        {/* Cyan top accent line */}
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#06b6d4]/30 to-transparent pointer-events-none" />

        {/* Title row */}
        <div className="flex items-center justify-between gap-4 px-6 pt-5 pb-3">
          <div className="min-w-0 flex-1">
            {table?.name ? (
              <EditableTableName tableId={id} initialName={table.name} />
            ) : (
              <div className="skeleton h-7 w-44 rounded-md" />
            )}
            <TableStats rows={rows} columns={columns} />
          </div>
          <RunAllButton tableId={id} enrichmentColumns={enrichmentColumns} />
        </div>

        {/* Action toolbar */}
        <div className="flex items-center gap-1.5 px-6 pb-3 flex-wrap">
          {/* Column button */}
          <Dialog open={colDialogOpen} onOpenChange={setColDialogOpen}>
            <DialogTrigger
              render={
                <button className={toolbarBtnDefault} />
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
                <div>
                  <Label className="text-[#a1a1aa] text-xs mb-1.5 block">Column type</Label>
                  <div className="grid grid-cols-3 gap-1.5">
                    {COLUMN_TYPES.map((ct) => (
                      <button
                        key={ct.value}
                        onClick={() => setColType(ct.value)}
                        className={cn(
                          "flex items-center gap-1.5 px-2.5 py-2 rounded-lg border text-xs font-medium transition-all",
                          colType === ct.value
                            ? "border-[#06b6d4]/50 bg-[#06b6d4]/10 text-[#06b6d4]"
                            : "border-[#27272a] bg-[#09090b] text-[#71717a] hover:border-[#3f3f46] hover:text-[#a1a1aa]"
                        )}
                      >
                        <span className="text-sm">{ct.icon}</span>
                        {ct.label}
                      </button>
                    ))}
                  </div>
                </div>
                <Button
                  onClick={handleAddColumn}
                  disabled={createColumn.isPending || !colName.trim()}
                  className="w-full btn-cyan-gradient font-semibold border-0"
                >
                  {createColumn.isPending ? "Adding..." : "Add Column"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>

          {/* Row */}
          <button onClick={handleAddRow} className={toolbarBtnDefault}>
            + Row
          </button>

          {/* Delete selected rows */}
          {selectedRowIds.size > 0 && (
            <button
              onClick={handleDeleteSelectedRows}
              disabled={deletingRows}
              className={cn(
                toolbarBtnBase,
                "text-red-400 bg-red-950/20 hover:bg-red-950/40 border border-red-800/30 hover:border-red-700/50 disabled:opacity-50"
              )}
            >
              {deletingRows ? "Deleting..." : `Delete ${selectedRowIds.size} Row${selectedRowIds.size === 1 ? "" : "s"}`}
            </button>
          )}

          <ToolbarDivider />

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
            className={cn(toolbarBtnDefault, "disabled:opacity-50")}
          >
            <span>⬆</span>
            {isImporting ? "Importing..." : "Import"}
          </button>

          {/* Export */}
          <button onClick={handleExportCSV} className={toolbarBtnDefault}>
            <span>⬇</span>
            Export
          </button>

          <ToolbarDivider />

          {/* Enrich Data */}
          <button
            onClick={() => setEnrichPanelOpen(true)}
            className={toolbarBtnEnrich}
          >
            + Enrich Data
          </button>

          <ToolbarDivider />

          {/* Email */}
          <Link
            href={`/table/${id}/emails`}
            className={toolbarBtnDefault}
          >
            <span>📧</span>
            Email
          </Link>

          {/* Spacer */}
          <div className="flex-1" />

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
      <div className="flex-1 min-h-0 relative">
        {/* Subtle inset top border */}
        <div className="absolute inset-x-0 top-0 h-px bg-[#06b6d4]/20 z-10 pointer-events-none" />

        {columns.length === 0 && rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-8 card-animate">
            <div className="w-16 h-16 rounded-xl border-2 border-dashed border-[#3f3f46] flex items-center justify-center mb-4 glass-panel">
              <span className="text-2xl opacity-50">◫</span>
            </div>
            <h3 className="text-base font-semibold text-[#a1a1aa] mb-1">Empty table</h3>
            <p className="text-[#52525b] text-sm">Add columns and rows to get started, or import a CSV</p>
          </div>
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            onCellEdit={handleCellEdit}
            selectedRowIds={selectedRowIds}
            onRowSelectionChange={setSelectedRowIds}
            columnMenuRenderer={(col) =>
              !ENRICHMENT_TYPES.has(col.type) ? (
                <ColumnHeaderMenu column={col} tableId={id} />
              ) : null
            }
          />
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
