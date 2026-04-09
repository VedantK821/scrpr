"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTables, useCreateTable } from "@/hooks/use-api";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function QuotaMini() {
  const { data: quota } = useQuery({
    queryKey: ["quota"],
    queryFn: api.enrichments.quota,
    staleTime: 60_000,
  });

  if (!quota) return null;
  const entries = Object.entries(quota);
  if (entries.length === 0) return null;

  return (
    <div className="px-3 py-3 border-t border-[#27272a] space-y-2">
      <p className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] mb-2">Quota</p>
      {entries.map(([source, info]) => {
        const pct = info.limit > 0 ? (info.used / info.limit) * 100 : 0;
        const isLow = info.remaining < info.limit * 0.2;
        return (
          <div key={source} className="space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-[#71717a] font-mono truncate">{source}</span>
              <span className={cn("text-[11px] font-mono", isLow ? "text-amber-400" : "text-[#a1a1aa]")}>
                {info.remaining}/{info.limit}
              </span>
            </div>
            <div className="h-1 rounded-full bg-[#27272a] overflow-hidden">
              <div
                className={cn("h-full rounded-full transition-all", isLow ? "bg-amber-500" : "bg-[#06b6d4]")}
                style={{ width: `${Math.max(2, 100 - pct)}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

interface SidebarProps {
  collapsed: boolean;
  onCollapse: (v: boolean) => void;
}

export function Sidebar({ collapsed, onCollapse }: SidebarProps) {
  const pathname = usePathname();
  const { data } = useTables();
  const createTable = useCreateTable();
  const [name, setName] = useState("");
  const [open, setOpen] = useState(false);

  // Extract active table id from URL
  const activeTableId = pathname?.match(/\/table\/([^/]+)/)?.[1] ?? null;

  const handleCreate = async () => {
    if (!name.trim()) return;
    await createTable.mutateAsync(name.trim());
    setName("");
    setOpen(false);
  };

  return (
    <aside
      className={cn(
        "relative flex flex-col bg-[#18181b] border-r border-[#27272a] transition-all duration-200 shrink-0",
        collapsed ? "w-0 overflow-hidden" : "w-[240px]"
      )}
    >
      {/* Brand */}
      <div className="flex items-center gap-2 px-4 py-4 border-b border-[#27272a]">
        <div className="relative flex items-center justify-center w-7 h-7 rounded-md bg-[#09090b] border border-[#3f3f46]">
          <span className="font-mono text-sm font-bold text-[#fafafa] leading-none">S</span>
          <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-[#06b6d4]" style={{ boxShadow: "0 0 6px rgba(6,182,212,0.6)" }} />
        </div>
        <span className="font-mono text-sm font-bold tracking-tight text-[#fafafa]">SCRPR</span>
      </div>

      {/* Navigation content */}
      <div className="flex-1 overflow-y-auto py-3 space-y-1">
        {/* Tables section */}
        <div className="px-3 mb-1">
          <p className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] mb-2 px-1">Tables</p>
          <div className="space-y-0.5">
            {data?.items.map((table, i) => {
              const isActive = table.id === activeTableId;
              return (
                <Link
                  key={table.id}
                  href={`/table/${table.id}`}
                  className={cn(
                    "flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-all group",
                    "sidebar-item-animate",
                    isActive
                      ? "bg-[#06b6d4]/10 text-[#06b6d4] border border-[#06b6d4]/20"
                      : "text-[#a1a1aa] hover:text-[#fafafa] hover:bg-[#27272a] border border-transparent"
                  )}
                  style={{ animationDelay: `${i * 30}ms` }}
                >
                  <span
                    className={cn(
                      "w-1.5 h-1.5 rounded-full shrink-0 transition-all",
                      isActive ? "bg-[#06b6d4]" : "bg-[#3f3f46] group-hover:bg-[#71717a]"
                    )}
                  />
                  <span className="truncate font-medium text-[13px]">{table.name}</span>
                </Link>
              );
            })}
          </div>

          {/* New Table button */}
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger
              render={
                <button className="flex items-center gap-2 px-2 py-1.5 mt-1 w-full rounded-md text-[13px] text-[#52525b] hover:text-[#a1a1aa] hover:bg-[#27272a] transition-all border border-transparent hover:border-[#27272a]" />
              }
            >
              <span className="text-base leading-none">+</span>
              <span>New Table</span>
            </DialogTrigger>
            <DialogContent className="bg-[#18181b] border-[#3f3f46] text-[#fafafa]">
              <DialogHeader>
                <DialogTitle className="text-[#fafafa] font-mono">Create Table</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-2">
                <div>
                  <Label htmlFor="sb-table-name" className="text-[#a1a1aa] text-xs">Table name</Label>
                  <Input
                    id="sb-table-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Top 25 MNCs"
                    onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                    className="mt-1.5 bg-[#09090b] border-[#3f3f46] text-[#fafafa] placeholder:text-[#52525b] focus-visible:border-[#06b6d4] focus-visible:ring-[#06b6d4]/20"
                  />
                </div>
                <Button
                  onClick={handleCreate}
                  disabled={createTable.isPending}
                  className="w-full bg-[#06b6d4] hover:bg-[#22d3ee] text-[#09090b] font-semibold border-0"
                >
                  {createTable.isPending ? "Creating..." : "Create Table"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>

        {/* Divider */}
        <div className="mx-3 my-2 border-t border-[#27272a]" />

        {/* Quick Actions */}
        <div className="px-3">
          <p className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] mb-2 px-1">Quick Actions</p>
          <div className="space-y-0.5">
            <button className="flex items-center gap-2 px-2 py-1.5 w-full rounded-md text-[13px] text-[#71717a] hover:text-[#a1a1aa] hover:bg-[#27272a] transition-all text-left">
              <span className="text-sm">⬆</span>
              <span>Import CSV</span>
            </button>
            <button className="flex items-center gap-2 px-2 py-1.5 w-full rounded-md text-[13px] text-[#71717a] hover:text-[#a1a1aa] hover:bg-[#27272a] transition-all text-left">
              <span className="text-sm">◧</span>
              <span>Templates</span>
            </button>
          </div>
        </div>
      </div>

      {/* Quota */}
      <QuotaMini />
    </aside>
  );
}
