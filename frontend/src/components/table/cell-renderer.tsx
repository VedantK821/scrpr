"use client";
import type { ICellRendererParams } from "ag-grid-community";
import type { CellStatus } from "@/types";

interface StatusConfig {
  dot?: string;
  dotClass?: string;
  textClass: string;
  label?: string;
}

const STATUS_CONFIG: Record<CellStatus, StatusConfig> = {
  empty: {
    textClass: "text-[#3f3f46]",
    label: "",
  },
  pending: {
    textClass: "text-[#52525b]",
    label: "Waiting...",
  },
  running: {
    textClass: "text-[#06b6d4]",
    label: "Running",
  },
  found: {
    dot: "bg-emerald-500",
    dotClass: "shrink-0",
    textClass: "text-[#e4e4e7]",
  },
  not_found: {
    textClass: "text-[#3f3f46]",
    label: "—",
  },
  error: {
    dot: "bg-red-500",
    dotClass: "shrink-0",
    textClass: "text-[#ef4444]",
    label: "Error",
  },
  review: {
    dot: "bg-amber-500",
    dotClass: "shrink-0",
    textClass: "text-[#f59e0b]",
  },
};

export function CellRenderer(params: ICellRendererParams) {
  const cell = params.data?._cells?.[params.colDef?.field ?? ""];

  // Plain text column (no cell metadata)
  if (!cell) {
    return (
      <span className="text-[#e4e4e7] truncate">{params.value ?? ""}</span>
    );
  }

  const status = cell.status as CellStatus;
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.empty;

  // Running state — cyan pulse
  if (status === "running") {
    return (
      <span className="flex items-center gap-1.5 text-[#06b6d4]">
        <span
          className="w-1.5 h-1.5 rounded-full bg-[#06b6d4] shrink-0 animate-pulse"
          style={{ animationDuration: "0.9s" }}
        />
        <span className="text-xs font-mono animate-pulse" style={{ animationDuration: "0.9s" }}>
          Running
        </span>
      </span>
    );
  }

  // Pending state
  if (status === "pending") {
    return (
      <span className="text-[#3f3f46] text-xs font-mono">Waiting...</span>
    );
  }

  // Not found
  if (status === "not_found") {
    return <span className="text-[#3f3f46]">—</span>;
  }

  // Error
  if (status === "error") {
    return (
      <span className="flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
        <span className="text-red-400 text-xs">Error</span>
      </span>
    );
  }

  // Review (amber dot + value)
  if (status === "review" && cell.value) {
    return (
      <span className="flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" />
        <span className="text-[#e4e4e7] truncate">{cell.value}</span>
      </span>
    );
  }

  // Found — green dot + value
  if (status === "found" && cell.value) {
    return (
      <span className="flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0 opacity-70" />
        <span className="text-[#e4e4e7] truncate">{cell.value}</span>
      </span>
    );
  }

  // Has value (plain text cells)
  if (cell.value) {
    return <span className="text-[#e4e4e7] truncate">{cell.value}</span>;
  }

  // Empty fallback
  return <span className="text-[#3f3f46]">—</span>;
}
