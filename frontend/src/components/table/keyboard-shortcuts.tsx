"use client";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const SHORTCUTS = [
  { keys: ["?"], description: "Show keyboard shortcuts" },
  { keys: ["Ctrl", "E"], description: "Open enrichment panel" },
  { keys: ["Ctrl", "F"], description: "Find in table" },
  { keys: ["Space"], description: "Select row" },
  { keys: ["Ctrl", "Z"], description: "Undo" },
];

interface KeyboardShortcutsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function KeyboardShortcutsDialog({ open, onOpenChange }: KeyboardShortcutsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm bg-zinc-900 border-zinc-800 text-zinc-100">
        <DialogHeader>
          <DialogTitle className="text-zinc-100">Keyboard Shortcuts</DialogTitle>
        </DialogHeader>
        <div className="space-y-2 pt-2">
          {SHORTCUTS.map((shortcut) => (
            <div key={shortcut.description} className="flex items-center justify-between py-1.5 border-b border-zinc-800 last:border-0">
              <span className="text-sm text-zinc-300">{shortcut.description}</span>
              <div className="flex items-center gap-1">
                {shortcut.keys.map((key, i) => (
                  <span key={i}>
                    <kbd className="inline-flex items-center justify-center rounded border border-zinc-600 bg-zinc-800 px-1.5 py-0.5 text-xs font-mono text-zinc-200 min-w-[1.5rem]">
                      {key}
                    </kbd>
                    {i < shortcut.keys.length - 1 && (
                      <span className="text-zinc-600 mx-0.5 text-xs">+</span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
