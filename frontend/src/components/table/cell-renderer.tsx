"use client";
import type { ICellRendererParams } from "ag-grid-community";
import type { CellStatus } from "@/types";

const STATUS_DISPLAY: Record<CellStatus, { icon: string; className: string }> = {
  empty: { icon: "", className: "text-zinc-600" },
  pending: { icon: "⏳", className: "text-zinc-400" },
  running: { icon: "⏳", className: "text-blue-400 animate-pulse" },
  found: { icon: "✓", className: "text-emerald-400" },
  not_found: { icon: "✗", className: "text-zinc-500" },
  error: { icon: "!", className: "text-red-400" },
  review: { icon: "⚠", className: "text-amber-400" },
};

export function CellRenderer(params: ICellRendererParams) {
  const cell = params.data?._cells?.[params.colDef?.field ?? ""];
  if (!cell) return <span className="text-zinc-600">{params.value ?? ""}</span>;
  const status = STATUS_DISPLAY[cell.status as CellStatus] ?? STATUS_DISPLAY.empty;
  if (cell.status === "running" || cell.status === "pending") {
    return <span className={status.className}>{status.icon} ...</span>;
  }
  if (cell.value) return <span>{cell.value}</span>;
  return <span className={status.className}>{status.icon || "—"}</span>;
}
