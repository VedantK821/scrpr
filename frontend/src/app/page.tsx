"use client";
import { useState } from "react";
import Link from "next/link";
import { useTables, useCreateTable } from "@/hooks/use-api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function HomePage() {
  const { data, isLoading } = useTables();
  const createTable = useCreateTable();
  const [name, setName] = useState("");
  const [open, setOpen] = useState(false);

  const handleCreate = async () => {
    if (!name.trim()) return;
    await createTable.mutateAsync(name.trim());
    setName("");
    setOpen(false);
  };

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold tracking-tight">Scrpr</h1>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger render={<Button />}>
              + New Table
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Create Table</DialogTitle></DialogHeader>
              <div className="space-y-4 pt-4">
                <div>
                  <Label htmlFor="table-name">Table name</Label>
                  <Input id="table-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Top 25 MNCs" onKeyDown={(e) => e.key === "Enter" && handleCreate()} />
                </div>
                <Button onClick={handleCreate} disabled={createTable.isPending} className="w-full">
                  {createTable.isPending ? "Creating..." : "Create"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
        {isLoading ? (
          <p className="text-zinc-500">Loading...</p>
        ) : data?.tables.length === 0 ? (
          <p className="text-zinc-500">No tables yet. Create one to get started.</p>
        ) : (
          <div className="grid gap-3">
            {data?.tables.map((table) => (
              <Link key={table.id} href={`/table/${table.id}`} className="block p-4 rounded-lg bg-zinc-900 border border-zinc-800 hover:border-zinc-600 transition-colors">
                <h2 className="font-semibold">{table.name}</h2>
                <p className="text-sm text-zinc-500">Created {new Date(table.created_at).toLocaleDateString()}</p>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
