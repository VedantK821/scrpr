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
      <DialogContent className="max-w-sm bg-[#18181b] border-[#3f3f46] text-[#fafafa]">
        <DialogHeader>
          <DialogTitle className="text-[#fafafa] font-mono text-sm tracking-wide">
            Keyboard Shortcuts
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-1 pt-2">
          {SHORTCUTS.map((shortcut) => (
            <div
              key={shortcut.description}
              className="flex items-center justify-between py-2 border-b border-[#27272a] last:border-0"
            >
              <span className="text-sm text-[#a1a1aa]">{shortcut.description}</span>
              <div className="flex items-center gap-1">
                {shortcut.keys.map((key, i) => (
                  <span key={i} className="flex items-center gap-1">
                    <kbd className="inline-flex items-center justify-center rounded-md border border-[#3f3f46] bg-[#27272a] px-1.5 py-0.5 text-xs font-mono text-[#a1a1aa] min-w-[1.5rem]">
                      {key}
                    </kbd>
                    {i < shortcut.keys.length - 1 && (
                      <span className="text-[#3f3f46] text-xs">+</span>
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
