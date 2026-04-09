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
    <div className="rounded-xl border border-[#27272a] glass-panel p-5 space-y-3">
      <div className="skeleton h-5 w-2/3" />
      <div className="skeleton h-3 w-1/3 mt-1" />
      <div className="flex gap-2 mt-3">
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
        "group block rounded-xl border border-[#27272a]",
        "glass-panel card-hover card-animate",
        "hover:border-[#06b6d4]/40",
        "relative overflow-hidden p-5"
      )}
      style={{
        animationDelay: `${index * 80}ms`,
      }}
    >
      {/* Subtle top accent line on hover */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#06b6d4]/0 to-transparent group-hover:via-[#06b6d4]/60 transition-all duration-500" />

      {/* Bottom glow on hover */}
      <div
        className="absolute inset-x-0 bottom-0 h-20 opacity-0 group-hover:opacity-100 transition-all duration-300 pointer-events-none"
        style={{ background: "radial-gradient(ellipse at 50% 100%, rgba(6,182,212,0.06) 0%, transparent 70%)" }}
      />

      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-[#09090b] border border-[#3f3f46] flex items-center justify-center shrink-0 group-hover:border-[#06b6d4]/40 transition-colors duration-200">
            <span className="text-sm">◫</span>
          </div>
          <h2 className="font-semibold text-[#fafafa] text-[15px] truncate">{table.name}</h2>
        </div>
        {isNew && (
          <span className="shrink-0 inline-flex items-center rounded-full bg-[#06b6d4]/10 border border-[#06b6d4]/20 px-2 py-0.5 text-[10px] font-mono text-[#06b6d4]"
            style={{ boxShadow: "0 0 8px rgba(6,182,212,0.15)" }}>
            NEW
          </span>
        )}
      </div>

      {/* Meta */}
      <p className="text-[12px] text-[#52525b] font-mono">
        Updated {relTime}
      </p>

      {/* Arrow indicator */}
      <div className="absolute right-4 top-1/2 -translate-y-1/2 text-[#3f3f46] group-hover:text-[#06b6d4] group-hover:translate-x-1 transition-all duration-200">
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
        <div className="w-24 h-24 rounded-2xl border-2 border-dashed border-[#3f3f46] flex items-center justify-center glass-panel">
          <span className="text-4xl opacity-60">◫</span>
        </div>
        <div className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-[#06b6d4]/10 border border-[#06b6d4]/30 flex items-center justify-center"
          style={{ boxShadow: "0 0 10px rgba(6,182,212,0.2)" }}>
          <span className="text-[#06b6d4] text-sm leading-none">+</span>
        </div>
      </div>
      <h3 className="text-xl font-semibold text-[#fafafa] mb-2">No tables yet</h3>
      <p className="text-[#71717a] text-sm max-w-xs mb-8 leading-relaxed">
        Create your first table to start enriching data. Import a CSV or build from scratch.
      </p>
      <button
        onClick={onNew}
        className="btn-cyan-gradient inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold"
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
            <h1 className="text-3xl font-bold tracking-tight font-mono mb-1 gradient-text">
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
                  className="btn-cyan-gradient inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold shrink-0"
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
                  className="w-full btn-cyan-gradient font-semibold border-0"
                >
                  {createTable.isPending ? "Creating..." : "Create Table"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Gradient divider */}
      <div className="gradient-divider mb-8" />

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
