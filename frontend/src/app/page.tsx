"use client";
import { useState } from "react";
import Link from "next/link";
import { useTables, useCreateTable } from "@/hooks/use-api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Table } from "@/types";
import { cn } from "@/lib/utils";

function SkeletonCard() {
  return (
    <div className="rounded-xl border border-[#27272a] bg-[#18181b] p-5 space-y-3">
      <div className="skeleton h-4 w-2/3" />
      <div className="skeleton h-3 w-1/3" />
      <div className="flex gap-2 mt-2">
        <div className="skeleton h-5 w-14 rounded-full" />
        <div className="skeleton h-5 w-16 rounded-full" />
      </div>
    </div>
  );
}

function TableCard({ table, index }: { table: Table; index: number }) {
  const created = new Date(table.created_at);
  const updated = new Date(table.updated_at);
  const isNew = Date.now() - created.getTime() < 60_000 * 5;

  // Format relative time
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const diffMs = updated.getTime() - Date.now();
  const diffMin = Math.round(diffMs / 60000);
  const diffHr = Math.round(diffMs / 3600000);
  const diffDay = Math.round(diffMs / 86400000);
  let relTime = "";
  if (Math.abs(diffMin) < 60) relTime = rtf.format(diffMin, "minute");
  else if (Math.abs(diffHr) < 24) relTime = rtf.format(diffHr, "hour");
  else relTime = rtf.format(diffDay, "day");

  return (
    <Link
      href={`/table/${table.id}`}
      className={cn(
        "group block rounded-xl border border-[#27272a] bg-[#18181b] p-5",
        "hover:border-[#06b6d4]/40 hover:bg-[#1c1c1f]",
        "transition-all duration-200 card-animate",
        "relative overflow-hidden"
      )}
      style={{ animationDelay: `${index * 50}ms` }}
    >
      {/* Subtle top accent on hover */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#06b6d4]/0 to-transparent group-hover:via-[#06b6d4]/50 transition-all duration-300" />

      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-7 h-7 rounded-md bg-[#09090b] border border-[#3f3f46] flex items-center justify-center shrink-0 group-hover:border-[#06b6d4]/30 transition-colors">
            <span className="text-sm">◫</span>
          </div>
          <h2 className="font-semibold text-[#fafafa] text-[15px] truncate">{table.name}</h2>
        </div>
        {isNew && (
          <span className="shrink-0 inline-flex items-center rounded-full bg-[#06b6d4]/10 border border-[#06b6d4]/20 px-2 py-0.5 text-[10px] font-mono text-[#06b6d4]">
            NEW
          </span>
        )}
      </div>

      {/* Meta */}
      <p className="text-[12px] text-[#52525b] font-mono">
        Updated {relTime}
      </p>

      {/* Arrow indicator */}
      <div className="absolute right-4 top-1/2 -translate-y-1/2 text-[#3f3f46] group-hover:text-[#06b6d4] group-hover:translate-x-0.5 transition-all duration-200">
        →
      </div>
    </Link>
  );
}

function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 px-8 text-center card-animate">
      {/* Grid illustration */}
      <div className="relative mb-8">
        <div className="w-24 h-24 rounded-2xl border-2 border-dashed border-[#3f3f46] flex items-center justify-center bg-[#18181b]">
          <span className="text-4xl opacity-60">◫</span>
        </div>
        <div className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-[#06b6d4]/10 border border-[#06b6d4]/30 flex items-center justify-center">
          <span className="text-[#06b6d4] text-sm leading-none">+</span>
        </div>
      </div>
      <h3 className="text-xl font-semibold text-[#fafafa] mb-2">No tables yet</h3>
      <p className="text-[#71717a] text-sm max-w-xs mb-8 leading-relaxed">
        Create your first table to start enriching data. Import a CSV or build from scratch.
      </p>
      <button
        onClick={onNew}
        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[#06b6d4] hover:bg-[#22d3ee] text-[#09090b] font-semibold text-sm transition-colors"
        style={{ boxShadow: "0 0 20px rgba(6,182,212,0.25)" }}
      >
        <span className="text-lg leading-none">+</span>
        Create your first table
      </button>
    </div>
  );
}

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

  const tables = data?.items ?? [];

  return (
    <div className="max-w-4xl mx-auto px-8 py-10">
      {/* Hero section */}
      <div className="mb-10 card-animate">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-[#fafafa] tracking-tight font-mono mb-1">
              Your Tables
            </h1>
            <p className="text-[#71717a] text-sm">
              {isLoading
                ? "Loading..."
                : tables.length === 0
                ? "Create your first enrichment table to get started"
                : `${tables.length} table${tables.length === 1 ? "" : "s"} — click to open`}
            </p>
          </div>

          {/* New Table CTA */}
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger
              render={
                <button
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#06b6d4] hover:bg-[#22d3ee] text-[#09090b] font-semibold text-sm transition-all shrink-0"
                  style={{ boxShadow: "0 0 16px rgba(6,182,212,0.2)" }}
                />
              }
            >
              <span className="text-base leading-none">+</span>
              New Table
            </DialogTrigger>
            <DialogContent className="bg-[#18181b] border-[#3f3f46] text-[#fafafa]">
              <DialogHeader>
                <DialogTitle className="text-[#fafafa] font-mono text-base">Create Table</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-2">
                <div>
                  <Label htmlFor="home-table-name" className="text-[#a1a1aa] text-xs mb-1.5 block">
                    Table name
                  </Label>
                  <Input
                    id="home-table-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Top 25 MNCs"
                    onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                    className="bg-[#09090b] border-[#3f3f46] text-[#fafafa] placeholder:text-[#52525b] focus-visible:border-[#06b6d4] focus-visible:ring-[#06b6d4]/20"
                  />
                </div>
                <Button
                  onClick={handleCreate}
                  disabled={createTable.isPending || !name.trim()}
                  className="w-full bg-[#06b6d4] hover:bg-[#22d3ee] text-[#09090b] font-semibold border-0"
                >
                  {createTable.isPending ? "Creating..." : "Create Table"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Divider */}
      <div className="border-t border-[#27272a] mb-8" />

      {/* Content */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : tables.length === 0 ? (
        <EmptyState onNew={() => setOpen(true)} />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {tables.map((table, i) => (
            <TableCard key={table.id} table={table} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}
