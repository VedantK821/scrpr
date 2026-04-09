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
    <div className="px-3 py-3 space-y-2" style={{ borderTop: "1px solid transparent", backgroundImage: "linear-gradient(#18181b, #18181b), linear-gradient(to right, transparent, #3f3f46 30%, #3f3f46 70%, transparent)", backgroundOrigin: "border-box", backgroundClip: "padding-box, border-box" }}>
      <div className="gradient-divider mb-3" />
      <p className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] mb-2">Quota</p>
      {entries.map(([source, info]) => {
        const pct = info.limit > 0 ? (info.used / info.limit) * 100 : 0;
        const remaining = info.remaining / info.limit;
        const isLow = remaining < 0.2;
        const isMid = remaining >= 0.2 && remaining < 0.5;
        const isHigh = remaining >= 0.5;

        const barColor = isHigh
          ? "linear-gradient(90deg, #10b981, #34d399)"
          : isMid
          ? "linear-gradient(90deg, #f59e0b, #fbbf24)"
          : "linear-gradient(90deg, #ef4444, #f87171)";

        const textColor = isHigh ? "text-emerald-400" : isMid ? "text-amber-400" : "text-red-400";

        return (
          <div key={source} className="space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-[#71717a] font-mono truncate">{source}</span>
              <span className={cn("text-[11px] font-mono", textColor)}>
                {info.remaining}/{info.limit}
              </span>
            </div>
            <div className="h-1 rounded-full bg-[#27272a] overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${Math.max(2, 100 - pct)}%`, background: barColor }}
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
        "relative flex flex-col bg-[#18181b] border-r border-[#27272a] shrink-0 overflow-hidden",
        "transition-[width] duration-300 ease-in-out"
      )}
      style={{ width: collapsed ? 0 : 240 }}
    >
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-4 py-4" style={{ borderBottom: "1px solid #27272a" }}>
        <div
          className={cn(
            "relative flex items-center justify-center w-8 h-8 rounded-lg bg-[#09090b] border border-[#3f3f46] shrink-0",
            "logo-glow"
          )}
        >
          <span className="font-mono text-sm font-bold text-[#fafafa] leading-none">S</span>
          <span
            className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-[#06b6d4]"
            style={{ boxShadow: "0 0 8px rgba(6,182,212,0.8)" }}
          />
        </div>
        <span className="font-mono text-sm font-bold tracking-tight text-[#fafafa]">SCRPR</span>
      </div>

      {/* Navigation content */}
      <div className="flex-1 overflow-y-auto py-3 space-y-1">
        {/* Tables section */}
        <div className="px-3 mb-1">
          <p className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] mb-2 px-1">Tables</p>

          {/* Skeleton when no data yet */}
          {!data && (
            <div className="space-y-1.5 px-1">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="skeleton h-7 w-full rounded-md" style={{ animationDelay: `${i * 0.1}s` }} />
              ))}
            </div>
          )}

          <div className="space-y-0.5">
            {data?.items.map((table, i) => {
              const isActive = table.id === activeTableId;
              return (
                <Link
                  key={table.id}
                  href={`/table/${table.id}`}
                  className={cn(
                    "flex items-center gap-2 px-2 py-1.5 rounded-md text-sm group relative",
                    "sidebar-item-animate",
                    "transition-all duration-200",
                    isActive
                      ? "bg-[#06b6d4]/10 text-[#06b6d4] border border-[#06b6d4]/20 sidebar-active-item"
                      : "text-[#a1a1aa] hover:text-[#fafafa] hover:bg-[#27272a] border border-transparent"
                  )}
                  style={{ animationDelay: `${i * 30}ms` }}
                >
                  <span
                    className={cn(
                      "w-1.5 h-1.5 rounded-full shrink-0 transition-all duration-200",
                      isActive
                        ? "bg-[#06b6d4]"
                        : "bg-[#3f3f46] group-hover:bg-[#71717a]"
                    )}
                    style={isActive ? { boxShadow: "0 0 6px rgba(6,182,212,0.7)" } : undefined}
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
                <button className="flex items-center gap-2 px-2 py-1.5 mt-1 w-full rounded-md text-[13px] text-[#52525b] hover:text-[#a1a1aa] hover:bg-[#27272a] transition-all duration-200 border border-transparent hover:border-[#27272a]" />
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
                  className="w-full btn-cyan-gradient font-semibold"
                >
                  {createTable.isPending ? "Creating..." : "Create Table"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>

        {/* Gradient Divider */}
        <div className="mx-3 my-2 gradient-divider" />

        {/* Quick Actions */}
        <div className="px-3">
          <p className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] mb-2 px-1">Quick Actions</p>
          <div className="space-y-0.5">
            <button className="flex items-center gap-2 px-2 py-1.5 w-full rounded-md text-[13px] text-[#71717a] hover:text-[#a1a1aa] hover:bg-[#27272a] transition-all duration-200 text-left">
              <span className="text-sm">⬆</span>
              <span>Import CSV</span>
            </button>
            <button className="flex items-center gap-2 px-2 py-1.5 w-full rounded-md text-[13px] text-[#71717a] hover:text-[#a1a1aa] hover:bg-[#27272a] transition-all duration-200 text-left">
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
