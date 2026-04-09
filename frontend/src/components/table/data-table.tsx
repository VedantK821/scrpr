"use client";
import { useMemo } from "react";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, type ColDef } from "ag-grid-community";
import type { Column, Row } from "@/types";
import { CellRenderer } from "./cell-renderer";
import "./ag-grid-theme.css";

ModuleRegistry.registerModules([AllCommunityModule]);

interface DataTableProps {
  columns: Column[];
  rows: Row[];
  onCellEdit?: (cellId: string, value: string) => void;
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
    default: return "◇";
  }
}

export function DataTable({ columns, rows, onCellEdit }: DataTableProps) {
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
        cellStyle: { color: "#52525b", fontFamily: "monospace", fontSize: "11px", justifyContent: "center" },
      },
      ...columns.map((col) => ({
        headerName: `${getTypeIcon(col.type)}  ${col.name}`,
        headerTooltip: `${col.type} column`,
        field: col.id,
        cellRenderer: CellRenderer,
        editable: col.type === "text" || col.type === "url" || col.type === "email" || col.type === "number",
        minWidth: 160,
        flex: 1,
        headerClass: ENRICHMENT_TYPES.has(col.type) ? "enrichment-header" : "",
      })),
    ],
    [columns],
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
        onCellValueChanged={(e) => {
          const cellId = e.data._cells?.[e.colDef.field!]?.id;
          if (cellId && onCellEdit) onCellEdit(cellId, e.newValue);
        }}
      />
    </div>
  );
}
