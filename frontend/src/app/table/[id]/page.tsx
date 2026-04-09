"use client";
import { use, useState } from "react";
import Link from "next/link";
import { useTable, useColumns, useRows, useCreateColumn, useCreateRow } from "@/hooks/use-api";
import { api } from "@/lib/api-client";
import { DataTable } from "@/components/table/data-table";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function TablePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: table } = useTable(id);
  const { data: columns = [] } = useColumns(id);
  const { data: rows = [] } = useRows(id);
  const createColumn = useCreateColumn(id);
  const createRow = useCreateRow(id);
  const [colName, setColName] = useState("");
  const [colDialogOpen, setColDialogOpen] = useState(false);

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

  return (
    <main className="h-screen flex flex-col bg-zinc-950 text-zinc-100">
      <div className="flex items-center gap-4 px-4 py-3 border-b border-zinc-800">
        <Link href="/" className="text-zinc-400 hover:text-zinc-200">← Back</Link>
        <h1 className="text-lg font-semibold">{table?.name ?? "Loading..."}</h1>
        <div className="ml-auto flex gap-2">
          <Dialog open={colDialogOpen} onOpenChange={setColDialogOpen}>
            <DialogTrigger render={<Button variant="outline" size="sm" />}>+ Column</DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Add Column</DialogTitle></DialogHeader>
              <div className="space-y-4 pt-4">
                <div><Label>Column name</Label><Input value={colName} onChange={(e) => setColName(e.target.value)} placeholder="e.g. Company" onKeyDown={(e) => e.key === "Enter" && handleAddColumn()} /></div>
                <Button onClick={handleAddColumn} className="w-full">Add</Button>
              </div>
            </DialogContent>
          </Dialog>
          <Button variant="outline" size="sm" onClick={handleAddRow}>+ Row</Button>
        </div>
      </div>
      <div className="flex-1"><DataTable columns={columns} rows={rows} onCellEdit={handleCellEdit} /></div>
      <div className="flex items-center gap-4 px-4 py-2 border-t border-zinc-800 text-sm text-zinc-500">
        <span>Rows: {rows.length}</span>
        <span>Columns: {columns.length}</span>
      </div>
    </main>
  );
}
