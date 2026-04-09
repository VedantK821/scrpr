"use client";
import { useMemo, useCallback } from "react";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, type ColDef, type SelectionChangedEvent } from "ag-grid-community";
import type { Column, Row } from "@/types";
import { CellRenderer } from "./cell-renderer";
import "./ag-grid-theme.css";

ModuleRegistry.registerModules([AllCommunityModule]);

interface DataTableProps {
  columns: Column[];
  rows: Row[];
  onCellEdit?: (cellId: string, value: string) => void;
  selectedRowIds?: Set<string>;
  onRowSelectionChange?: (ids: Set<string>) => void;
  columnMenuRenderer?: (col: Column) => React.ReactNode | null;
}

const ENRICHMENT_TYPES = new Set(["agent", "waterfall"]);

function getTypeIcon(type: string): string {
  switch (type) {
    case "text": return "Aa";
    case "number": return "#";
    case "email": return "✉";
    case "url": return "🔗";
    case "agent": return "🤖";
    case "waterfall": return "⛓";
    case "date": return "📅";
    case "checkbox": return "☑";
    case "select": return "▾";
    default: return "◇";
  }
}

// Custom header component that renders column menu if provided
function ColumnHeader({
  column,
  menuRenderer,
}: {
  column: Column;
  menuRenderer?: (col: Column) => React.ReactNode | null;
}) {
  const menu = menuRenderer?.(column);
  if (menu) {
    return <div className="flex items-center gap-1.5 w-full px-0.5">{menu}</div>;
  }
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] font-mono text-[#52525b]">{getTypeIcon(column.type)}</span>
      <span className="text-xs font-medium text-[#a1a1aa]">{column.name}</span>
    </div>
  );
}

export function DataTable({
  columns,
  rows,
  onCellEdit,
  selectedRowIds,
  onRowSelectionChange,
  columnMenuRenderer,
}: DataTableProps) {
  const colDefs: ColDef[] = useMemo(
    () => [
      {
        headerName: "#",
        valueGetter: "node.rowIndex + 1",
        width: 52,
        minWidth: 52,
        maxWidth: 52,
        pinned: "left",
        sortable: false,
        resizable: false,
        suppressHeaderMenuButton: true,
        checkboxSelection: true,
        headerCheckboxSelection: true,
        cellStyle: { color: "#52525b", fontFamily: "monospace", fontSize: "11px", justifyContent: "center" },
      },
      ...columns.map((col) => ({
        headerName: ENRICHMENT_TYPES.has(col.type)
          ? `${getTypeIcon(col.type)}  ${col.name}`
          : col.name,
        headerComponent: !ENRICHMENT_TYPES.has(col.type) && columnMenuRenderer
          ? () => <ColumnHeader column={col} menuRenderer={columnMenuRenderer} />
          : undefined,
        headerTooltip: `${col.type} column`,
        field: col.id,
        cellRenderer: CellRenderer,
        editable: col.type === "text" || col.type === "url" || col.type === "email" || col.type === "number",
        minWidth: 160,
        flex: 1,
        headerClass: ENRICHMENT_TYPES.has(col.type) ? "enrichment-header" : "",
      })),
    ],
    [columns, columnMenuRenderer],
  );

  const rowData = useMemo(
    () =>
      rows.map((row) => {
        const data: Record<string, unknown> = { _rowId: row.id };
        const cellMap: Record<string, { value: string | null; status: string; id: string }> = {};
        for (const cell of row.cells) {
          data[cell.column_id] = cell.value;
          cellMap[cell.column_id] = { value: cell.value, status: cell.status, id: cell.id };
        }
        data._cells = cellMap;
        return data;
      }),
    [rows],
  );

  const handleSelectionChanged = useCallback(
    (e: SelectionChangedEvent) => {
      if (!onRowSelectionChange) return;
      const selectedNodes = e.api.getSelectedNodes();
      const ids = new Set(selectedNodes.map((n) => n.data?._rowId as string).filter(Boolean));
      onRowSelectionChange(ids);
    },
    [onRowSelectionChange],
  );

  return (
    <div className="ag-theme-scrpr w-full h-full">
      <AgGridReact
        columnDefs={colDefs}
        rowData={rowData}
        defaultColDef={{
          resizable: true,
          sortable: true,
          filter: true,
          suppressHeaderMenuButton: false,
        }}
        animateRows
        rowSelection="multiple"
        suppressRowClickSelection
        onSelectionChanged={handleSelectionChanged}
        onCellValueChanged={(e) => {
          const cellId = e.data._cells?.[e.colDef.field!]?.id;
          if (cellId && onCellEdit) onCellEdit(cellId, e.newValue);
        }}
      />
    </div>
  );
}
