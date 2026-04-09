"use client";
import { useMemo } from "react";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, type ColDef } from "ag-grid-community";
import type { Column, Row } from "@/types";
import { CellRenderer } from "./cell-renderer";

ModuleRegistry.registerModules([AllCommunityModule]);

interface DataTableProps {
  columns: Column[];
  rows: Row[];
  onCellEdit?: (cellId: string, value: string) => void;
}

export function DataTable({ columns, rows, onCellEdit }: DataTableProps) {
  const colDefs: ColDef[] = useMemo(
    () => [
      { headerName: "#", valueGetter: "node.rowIndex + 1", width: 60, pinned: "left", sortable: false },
      ...columns.map((col) => ({
        headerName: col.name,
        field: col.id,
        cellRenderer: CellRenderer,
        editable: col.type === "text" || col.type === "url" || col.type === "email" || col.type === "number",
        minWidth: 150,
        flex: 1,
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
    <div className="ag-theme-alpine-dark w-full h-full">
      <AgGridReact
        columnDefs={colDefs}
        rowData={rowData}
        defaultColDef={{ resizable: true, sortable: true, filter: true }}
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
