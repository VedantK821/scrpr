"use client";
import { use, useState, useCallback } from "react";
import Link from "next/link";
import { useTable, useColumns, useRows } from "@/hooks/use-api";
import { api } from "@/lib/api-client";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import type { EmailDraft } from "@/types";
import { cn } from "@/lib/utils";

type Step = "compose" | "preview" | "send";
type PersonalizationLevel = "light" | "medium" | "max";

// ─── Step Progress Bar ─────────────────────────────────────────────────
const STEPS: { id: Step; label: string; desc: string }[] = [
  { id: "compose", label: "Compose", desc: "Write template" },
  { id: "preview", label: "Preview", desc: "Review drafts" },
  { id: "send", label: "Send", desc: "Launch campaign" },
];

function StepProgressBar({
  step,
  drafts,
  onNavigate,
}: {
  step: Step;
  drafts: EmailDraft[];
  onNavigate: (s: Step) => void;
}) {
  const activeIdx = STEPS.findIndex((s) => s.id === step);

  return (
    <div className="flex items-center gap-0 mb-10">
      {STEPS.map((s, i) => {
        const isActive = s.id === step;
        const isDone = i < activeIdx;
        const isClickable = s.id === "compose" || (drafts.length > 0 && (s.id === "preview" || s.id === "send"));

        return (
          <div key={s.id} className="flex items-center">
            <button
              onClick={() => isClickable && onNavigate(s.id)}
              disabled={!isClickable}
              className={cn(
                "flex items-center gap-2.5 group transition-all",
                isClickable ? "cursor-pointer" : "cursor-not-allowed opacity-40"
              )}
            >
              {/* Step dot */}
              <div
                className={cn(
                  "w-7 h-7 rounded-full flex items-center justify-center text-xs font-mono font-bold transition-all",
                  isActive
                    ? "bg-[#06b6d4] text-[#09090b]"
                    : isDone
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    : "bg-[#27272a] text-[#52525b] border border-[#3f3f46]"
                )}
                style={isActive ? { boxShadow: "0 0 16px rgba(6,182,212,0.4)" } : undefined}
              >
                {isDone ? "✓" : i + 1}
              </div>

              {/* Step label */}
              <div className="text-left">
                <div
                  className={cn(
                    "text-sm font-medium transition-colors",
                    isActive ? "text-[#fafafa]" : isDone ? "text-[#71717a]" : "text-[#3f3f46]"
                  )}
                >
                  {s.label}
                </div>
                <div className="text-[10px] text-[#52525b] font-mono">{s.desc}</div>
              </div>
            </button>

            {/* Connector */}
            {i < STEPS.length - 1 && (
              <div className="w-16 h-px mx-4 transition-all">
                <div
                  className={cn(
                    "h-full transition-all duration-300",
                    isDone ? "bg-emerald-500/30" : "bg-[#27272a]"
                  )}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Confidence Badge ─────────────────────────────────────────────────
function ConfidenceBadge({ confidence }: { confidence: number | null }) {
  if (confidence === null) return null;
  const pct = Math.round(confidence * 100);
  const cls =
    pct >= 80
      ? "bg-emerald-900/30 text-emerald-400 border-emerald-700/50"
      : pct >= 50
      ? "bg-amber-900/30 text-amber-400 border-amber-700/50"
      : "bg-red-900/30 text-red-400 border-red-700/50";
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono ${cls}`}>
      {pct}%
    </span>
  );
}

// ─── Draft Card ───────────────────────────────────────────────────────
function DraftCard({
  draft,
  selected,
  onToggleSelect,
  onSkip,
  onUpdate,
  index,
}: {
  draft: EmailDraft;
  selected: boolean;
  onToggleSelect: () => void;
  onSkip: () => void;
  onUpdate: (subject: string, body: string) => Promise<void>;
  index: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editSubject, setEditSubject] = useState(draft.subject);
  const [editBody, setEditBody] = useState(draft.body);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    await onUpdate(editSubject, editBody);
    setSaving(false);
    setEditing(false);
  };

  const skipped = draft.status === "skipped";
  const sent = draft.status === "sent";

  return (
    <div
      className={cn(
        "rounded-xl border transition-all card-animate",
        skipped
          ? "border-[#27272a] bg-[#18181b]/30 opacity-40"
          : sent
          ? "border-emerald-800/30 bg-emerald-950/10"
          : selected
          ? "border-[#06b6d4]/30 bg-[#06b6d4]/5"
          : "border-[#27272a] bg-[#18181b] hover:border-[#3f3f46]"
      )}
      style={{ animationDelay: `${index * 40}ms` }}
    >
      {/* Card header */}
      <div className="flex items-center gap-3 px-4 py-3">
        {!skipped && !sent && (
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggleSelect}
            className="h-4 w-4 rounded border-[#3f3f46] accent-[#06b6d4] shrink-0"
          />
        )}
        {sent && (
          <span className="w-4 h-4 rounded-full bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 text-[9px] shrink-0">
            ✓
          </span>
        )}

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-[#e4e4e7] truncate font-medium">{draft.to_email}</span>
            <ConfidenceBadge confidence={draft.confidence} />
            {skipped && (
              <span className="text-[10px] font-mono text-[#52525b] border border-[#27272a] rounded-full px-2 py-0.5">
                Skipped
              </span>
            )}
            {sent && (
              <span className="text-[10px] font-mono text-emerald-400 border border-emerald-800/50 rounded-full px-2 py-0.5">
                Sent
              </span>
            )}
          </div>
          <div className="text-[12px] text-[#52525b] truncate mt-0.5 font-mono">{draft.subject}</div>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {!skipped && !sent && (
            <button
              onClick={onSkip}
              className="text-[11px] text-[#52525b] hover:text-[#a1a1aa] px-2 py-1 rounded-md hover:bg-[#27272a] transition-all"
            >
              Skip
            </button>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[11px] text-[#52525b] hover:text-[#a1a1aa] px-2 py-1 rounded-md hover:bg-[#27272a] transition-all font-mono"
          >
            {expanded ? "▴" : "▾"}
          </button>
        </div>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-[#27272a] px-4 py-4 space-y-4">
          {editing ? (
            <>
              <div>
                <Label className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] mb-1.5 block">Subject</Label>
                <Input
                  value={editSubject}
                  onChange={(e) => setEditSubject(e.target.value)}
                  className="bg-[#09090b] border-[#3f3f46] text-[#fafafa] focus-visible:border-[#06b6d4] focus-visible:ring-[#06b6d4]/20"
                />
              </div>
              <div>
                <Label className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] mb-1.5 block">Body</Label>
                <textarea
                  value={editBody}
                  onChange={(e) => setEditBody(e.target.value)}
                  rows={8}
                  className="w-full rounded-lg border border-[#3f3f46] bg-[#09090b] px-3 py-2.5 text-sm text-[#fafafa] placeholder:text-[#52525b] focus:outline-none focus:ring-1 focus:ring-[#06b6d4]/40 focus:border-[#06b6d4]/40 resize-y font-mono leading-relaxed"
                />
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={handleSave}
                  disabled={saving}
                  className="bg-[#06b6d4] hover:bg-[#22d3ee] text-[#09090b] font-semibold border-0"
                >
                  {saving ? "Saving..." : "Save"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setEditing(false);
                    setEditSubject(draft.subject);
                    setEditBody(draft.body);
                  }}
                  className="border-[#3f3f46] text-[#a1a1aa] hover:text-[#fafafa] hover:bg-[#27272a]"
                >
                  Cancel
                </Button>
              </div>
            </>
          ) : (
            <>
              <div>
                <div className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] mb-1.5">Subject</div>
                <div className="text-sm text-[#e4e4e7] font-medium">{draft.subject}</div>
              </div>
              <div>
                <div className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] mb-1.5">Body</div>
                <pre className="text-[13px] text-[#a1a1aa] whitespace-pre-wrap font-sans leading-relaxed">{draft.body}</pre>
              </div>
              {!skipped && !sent && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setEditing(true)}
                  className="border-[#3f3f46] text-[#a1a1aa] hover:text-[#fafafa] hover:bg-[#27272a]"
                >
                  Edit
                </Button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Personalization Level Selector ──────────────────────────────────
const PERSONALIZATION_OPTIONS = [
  {
    id: "light" as PersonalizationLevel,
    label: "Light",
    emoji: "⚡",
    desc: "Fill variables only",
    detail: "Fast, consistent, no AI rewriting",
  },
  {
    id: "medium" as PersonalizationLevel,
    label: "Medium",
    emoji: "✨",
    desc: "Rewrite + research",
    detail: "AI adds context per row",
  },
  {
    id: "max" as PersonalizationLevel,
    label: "Max",
    emoji: "🎯",
    desc: "Fully custom",
    detail: "Unique email for every row",
  },
];

function PersonalizationSelector({
  value,
  onChange,
}: {
  value: PersonalizationLevel;
  onChange: (v: PersonalizationLevel) => void;
}) {
  return (
    <div className="grid grid-cols-3 gap-3">
      {PERSONALIZATION_OPTIONS.map((opt) => {
        const isSelected = value === opt.id;
        return (
          <button
            key={opt.id}
            onClick={() => onChange(opt.id)}
            className={cn(
              "p-3.5 rounded-xl border text-left transition-all",
              isSelected
                ? "border-[#06b6d4]/50 bg-[#06b6d4]/8"
                : "border-[#27272a] bg-[#18181b] hover:border-[#3f3f46]"
            )}
            style={isSelected ? { boxShadow: "0 0 16px rgba(6,182,212,0.12)" } : undefined}
          >
            <div className="text-lg mb-1.5">{opt.emoji}</div>
            <div className={cn("font-semibold text-sm", isSelected ? "text-[#fafafa]" : "text-[#a1a1aa]")}>
              {opt.label}
            </div>
            <div className={cn("text-[11px] mt-0.5", isSelected ? "text-[#71717a]" : "text-[#52525b]")}>
              {opt.desc}
            </div>
            <div className="text-[10px] font-mono text-[#3f3f46] mt-1">{opt.detail}</div>
          </button>
        );
      })}
    </div>
  );
}

// ─── Variable Highlighter ─────────────────────────────────────────────
function VariableHints({ columnNames }: { columnNames: string[] }) {
  if (columnNames.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {columnNames.map((name) => (
        <span
          key={name}
          className="inline-flex items-center rounded-md bg-[#06b6d4]/10 border border-[#06b6d4]/20 px-1.5 py-0.5 text-[11px] font-mono text-[#06b6d4] cursor-pointer hover:bg-[#06b6d4]/20 transition-colors"
        >
          /{name}/
        </span>
      ))}
    </div>
  );
}

// ─── Send Progress ────────────────────────────────────────────────────
function SendProgress({ sent, total }: { sent: number; total: number }) {
  const pct = total > 0 ? (sent / total) * 100 : 0;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="text-[#a1a1aa]">
          Sent <span className="text-[#fafafa] font-semibold">{sent}</span> of{" "}
          <span className="text-[#fafafa] font-semibold">{total}</span>
        </span>
        <span className="font-mono text-xs text-[#71717a]">{Math.round(pct)}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-[#27272a] overflow-hidden">
        <div
          className="h-full rounded-full bg-[#06b6d4] transition-all duration-500 progress-fill"
          style={{ width: `${pct}%`, boxShadow: "0 0 8px rgba(6,182,212,0.5)" }}
        />
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────
export default function EmailsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: table } = useTable(id);
  const { data: columns = [] } = useColumns(id);
  const { data: rows = [] } = useRows(id);

  const [step, setStep] = useState<Step>("compose");

  // Compose state
  const [subjectTemplate, setSubjectTemplate] = useState("Hi /FirstName/, quick question about /Company/");
  const [bodyTemplate, setBodyTemplate] = useState(
    "Hi /FirstName/,\n\nI came across /Company/ and was really impressed by what you're building.\n\n[Your pitch here]\n\nWould love to connect — are you open to a quick chat?\n\nBest,\n[Your name]"
  );
  const [personalizationLevel, setPersonalizationLevel] = useState<PersonalizationLevel>("light");
  const [aiInstructions, setAiInstructions] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  // Preview state
  const [drafts, setDrafts] = useState<EmailDraft[]>([]);
  const [selectedDraftIds, setSelectedDraftIds] = useState<Set<string>>(new Set());

  // Send state
  const [delaySeconds, setDelaySeconds] = useState(30);
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<{ sent: number; failed: number } | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);

  // Test send state
  const [testEmail, setTestEmail] = useState("");
  const [testSending, setTestSending] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const handleGenerateDrafts = async () => {
    setGenerating(true);
    setGenerateError(null);
    try {
      const generated = await api.emails.compose({
        table_id: id,
        subject_template: subjectTemplate,
        body_template: bodyTemplate,
        personalization_level: personalizationLevel,
      });
      setDrafts(generated);
      setSelectedDraftIds(new Set(generated.filter((d) => d.status !== "skipped").map((d) => d.id)));
      setStep("preview");
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : "Failed to generate drafts");
    } finally {
      setGenerating(false);
    }
  };

  const handleToggleSelect = useCallback((draftId: string) => {
    setSelectedDraftIds((prev) => {
      const next = new Set(prev);
      if (next.has(draftId)) next.delete(draftId);
      else next.add(draftId);
      return next;
    });
  }, []);

  const handleSkip = useCallback(async (draftId: string) => {
    await api.emails.updateDraft(draftId, { status: "skipped" });
    setDrafts((prev) => prev.map((d) => (d.id === draftId ? { ...d, status: "skipped" } : d)));
    setSelectedDraftIds((prev) => {
      const next = new Set(prev);
      next.delete(draftId);
      return next;
    });
  }, []);

  const handleUpdateDraft = useCallback(async (draftId: string, subject: string, body: string) => {
    const updated = await api.emails.updateDraft(draftId, { subject, body });
    setDrafts((prev) => prev.map((d) => (d.id === draftId ? { ...d, ...updated } : d)));
  }, []);

  const handleSend = async () => {
    setSending(true);
    setSendError(null);
    setSendResult(null);
    try {
      const result = await api.emails.send(Array.from(selectedDraftIds), delaySeconds);
      setSendResult({ sent: result.sent, failed: result.failed });
      setDrafts((prev) =>
        prev.map((d) => (selectedDraftIds.has(d.id) ? { ...d, status: "sent" } : d))
      );
    } catch (err) {
      setSendError(err instanceof Error ? err.message : "Failed to send emails");
    } finally {
      setSending(false);
    }
  };

  const handleTestSend = async () => {
    if (!testEmail.trim()) return;
    setTestSending(true);
    setTestResult(null);
    try {
      const previewDraft = drafts.find((d) => selectedDraftIds.has(d.id)) ?? drafts[0];
      if (!previewDraft) {
        setTestResult("No draft available for test send.");
        return;
      }
      const result = await api.emails.testSend(testEmail, previewDraft.subject, previewDraft.body);
      setTestResult(result.success ? "Test email sent!" : `Error: ${result.error}`);
    } catch (err) {
      setTestResult(err instanceof Error ? err.message : "Failed to send test email");
    } finally {
      setTestSending(false);
    }
  };

  const columnNames = columns.map((c) => c.name);
  const activeDrafts = drafts.filter((d) => d.status !== "skipped");

  const handleNavigate = (s: Step) => {
    if (s === "compose") setStep("compose");
    if (s === "preview" && drafts.length > 0) setStep("preview");
    if (s === "send" && drafts.length > 0) setStep("send");
  };

  return (
    <div className="min-h-full">
      {/* Sticky sub-header with back link */}
      <div className="sticky top-0 z-10 flex items-center gap-3 px-6 py-3 border-b border-[#27272a] bg-[#09090b]/90 backdrop-blur-sm">
        <Link
          href={`/table/${id}`}
          className="flex items-center gap-1.5 text-xs text-[#52525b] hover:text-[#a1a1aa] transition-colors font-mono"
        >
          ← {table?.name ?? "Table"}
        </Link>
        <div className="h-3 w-px bg-[#27272a]" />
        <span className="text-xs text-[#71717a] font-mono">Email Composer</span>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-10">
        {/* Step progress bar */}
        <StepProgressBar step={step} drafts={drafts} onNavigate={handleNavigate} />

        {/* ── STEP 1: COMPOSE ── */}
        {step === "compose" && (
          <div className="space-y-7 page-fade-in">
            <div>
              <h2 className="text-xl font-bold text-[#fafafa] font-mono mb-1">Compose Template</h2>
              <p className="text-sm text-[#71717a]">
                Use{" "}
                <code className="bg-[#27272a] border border-[#3f3f46] px-1.5 rounded text-[#06b6d4] text-xs font-mono">
                  /ColumnName/
                </code>{" "}
                to reference table data
              </p>
              {columnNames.length > 0 && <VariableHints columnNames={columnNames} />}
            </div>

            {/* Subject */}
            <div>
              <Label className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] mb-1.5 block">
                Subject Line
              </Label>
              <Input
                value={subjectTemplate}
                onChange={(e) => setSubjectTemplate(e.target.value)}
                placeholder="Hi /FirstName/, quick question about /Company/"
                className="bg-[#18181b] border-[#3f3f46] text-[#fafafa] placeholder:text-[#52525b] focus-visible:border-[#06b6d4] focus-visible:ring-[#06b6d4]/20 font-mono"
              />
            </div>

            {/* Body */}
            <div>
              <Label className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] mb-1.5 block">
                Email Body
              </Label>
              <textarea
                value={bodyTemplate}
                onChange={(e) => setBodyTemplate(e.target.value)}
                rows={11}
                placeholder={"Hi /FirstName/,\n\n..."}
                className="w-full rounded-xl border border-[#3f3f46] bg-[#18181b] px-4 py-3 text-sm text-[#fafafa] placeholder:text-[#3f3f46] focus:outline-none focus:ring-1 focus:ring-[#06b6d4]/40 focus:border-[#06b6d4]/40 resize-y font-mono leading-relaxed transition-all"
              />
            </div>

            {/* Personalization */}
            <div>
              <Label className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] mb-3 block">
                AI Personalization Level
              </Label>
              <PersonalizationSelector value={personalizationLevel} onChange={setPersonalizationLevel} />
            </div>

            {/* AI Instructions */}
            {(personalizationLevel === "medium" || personalizationLevel === "max") && (
              <div className="page-fade-in">
                <Label className="text-[10px] font-mono uppercase tracking-widest text-[#52525b] mb-1.5 block">
                  AI Instructions{" "}
                  <span className="text-[#3f3f46] normal-case tracking-normal font-normal">(optional)</span>
                </Label>
                <textarea
                  value={aiInstructions}
                  onChange={(e) => setAiInstructions(e.target.value)}
                  rows={3}
                  placeholder="e.g. Mention their recent funding round. Be casual and brief. Avoid buzzwords."
                  className="w-full rounded-xl border border-[#3f3f46] bg-[#18181b] px-4 py-3 text-sm text-[#fafafa] placeholder:text-[#52525b] focus:outline-none focus:ring-1 focus:ring-[#06b6d4]/40 focus:border-[#06b6d4]/40 resize-y transition-all"
                />
              </div>
            )}

            {/* Error */}
            {generateError && (
              <div className="rounded-xl border border-red-800/50 bg-red-950/20 px-4 py-3 text-sm text-red-400">
                {generateError}
              </div>
            )}

            {/* Generate CTA */}
            <div className="flex items-center gap-4 pt-2">
              <button
                onClick={handleGenerateDrafts}
                disabled={generating || !subjectTemplate.trim() || !bodyTemplate.trim()}
                className={cn(
                  "inline-flex items-center gap-2 px-5 py-2.5 rounded-lg font-semibold text-sm transition-all",
                  generating || !subjectTemplate.trim() || !bodyTemplate.trim()
                    ? "bg-[#27272a] text-[#52525b] cursor-not-allowed"
                    : "bg-[#06b6d4] hover:bg-[#22d3ee] text-[#09090b]"
                )}
                style={
                  !generating && subjectTemplate.trim() && bodyTemplate.trim()
                    ? { boxShadow: "0 0 16px rgba(6,182,212,0.2)" }
                    : undefined
                }
              >
                {generating ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-[#06b6d4]/30 border-t-[#06b6d4] rounded-full animate-spin" />
                    Generating...
                  </>
                ) : (
                  <>✦ Generate {rows.length} Draft{rows.length === 1 ? "" : "s"}</>
                )}
              </button>
              <span className="text-xs text-[#52525b] font-mono">
                {rows.length === 0 ? "No rows yet" : `${rows.length} row${rows.length === 1 ? "" : "s"} → ${rows.length} email${rows.length === 1 ? "" : "s"}`}
              </span>
            </div>
          </div>
        )}

        {/* ── STEP 2: PREVIEW ── */}
        {step === "preview" && (
          <div className="space-y-5 page-fade-in">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-[#fafafa] font-mono mb-0.5">Review Drafts</h2>
                <p className="text-sm text-[#71717a]">
                  {drafts.length} draft{drafts.length === 1 ? "" : "s"} —{" "}
                  <span className="text-[#a1a1aa]">{selectedDraftIds.size} selected</span>
                </p>
              </div>
              <div className="flex items-center gap-3 text-xs font-mono">
                <button
                  onClick={() =>
                    setSelectedDraftIds(
                      new Set(drafts.filter((d) => d.status !== "skipped").map((d) => d.id))
                    )
                  }
                  className="text-[#06b6d4] hover:text-[#22d3ee] transition-colors"
                >
                  Select all
                </button>
                <span className="text-[#27272a]">·</span>
                <button
                  onClick={() => setSelectedDraftIds(new Set())}
                  className="text-[#52525b] hover:text-[#a1a1aa] transition-colors"
                >
                  Deselect all
                </button>
              </div>
            </div>

            <div className="space-y-3">
              {drafts.map((draft, i) => (
                <DraftCard
                  key={draft.id}
                  draft={draft}
                  index={i}
                  selected={selectedDraftIds.has(draft.id)}
                  onToggleSelect={() => handleToggleSelect(draft.id)}
                  onSkip={() => handleSkip(draft.id)}
                  onUpdate={(subject, body) => handleUpdateDraft(draft.id, subject, body)}
                />
              ))}
            </div>

            <div className="flex gap-3 pt-4">
              <button
                onClick={() => setStep("compose")}
                className="px-4 py-2 rounded-lg border border-[#3f3f46] text-[#a1a1aa] hover:text-[#fafafa] hover:bg-[#27272a] text-sm transition-all"
              >
                ← Back
              </button>
              <button
                onClick={() => setStep("send")}
                disabled={selectedDraftIds.size === 0}
                className={cn(
                  "flex-1 py-2 rounded-lg font-semibold text-sm transition-all",
                  selectedDraftIds.size === 0
                    ? "bg-[#27272a] text-[#52525b] cursor-not-allowed"
                    : "bg-[#06b6d4] hover:bg-[#22d3ee] text-[#09090b]"
                )}
                style={selectedDraftIds.size > 0 ? { boxShadow: "0 0 12px rgba(6,182,212,0.2)" } : undefined}
              >
                Continue to Send → ({selectedDraftIds.size} selected)
              </button>
            </div>
          </div>
        )}

        {/* ── STEP 3: SEND ── */}
        {step === "send" && (
          <div className="space-y-6 page-fade-in">
            <div>
              <h2 className="text-xl font-bold text-[#fafafa] font-mono mb-0.5">Send Campaign</h2>
              <p className="text-sm text-[#71717a]">
                {selectedDraftIds.size} email{selectedDraftIds.size === 1 ? "" : "s"} ready to send
              </p>
            </div>

            {/* Send settings */}
            <div className="rounded-xl border border-[#27272a] bg-[#18181b] p-5 space-y-4">
              <h3 className="text-sm font-semibold text-[#fafafa] font-mono">Send Settings</h3>
              <div className="flex items-center gap-3">
                <Label className="text-sm text-[#71717a] whitespace-nowrap">Delay between emails</Label>
                <Input
                  type="number"
                  value={delaySeconds}
                  onChange={(e) => setDelaySeconds(Number(e.target.value))}
                  min={0}
                  max={300}
                  className="w-20 bg-[#09090b] border-[#3f3f46] text-[#fafafa] focus-visible:border-[#06b6d4] focus-visible:ring-[#06b6d4]/20 font-mono text-center"
                />
                <span className="text-sm text-[#52525b]">seconds</span>
              </div>
              <p className="text-[11px] font-mono text-[#3f3f46]">
                Est. time: ~{Math.round(Math.max(0, (selectedDraftIds.size - 1) * delaySeconds) / 60)} min
              </p>
            </div>

            {/* Selected emails summary */}
            <div className="rounded-xl border border-[#27272a] bg-[#18181b] p-5">
              <h3 className="text-sm font-semibold text-[#fafafa] font-mono mb-3">Recipients</h3>
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {activeDrafts
                  .filter((d) => selectedDraftIds.has(d.id))
                  .map((d) => (
                    <div key={d.id} className="flex items-center justify-between text-sm py-0.5">
                      <span className="text-[#a1a1aa] truncate font-mono text-xs">{d.to_email}</span>
                      <ConfidenceBadge confidence={d.confidence} />
                    </div>
                  ))}
              </div>
            </div>

            {/* Send result */}
            {sendResult && (
              <div className="space-y-3">
                <div className="rounded-xl border border-emerald-800/50 bg-emerald-950/20 px-4 py-3 text-sm text-emerald-400">
                  ✓ Sent {sendResult.sent} email{sendResult.sent === 1 ? "" : "s"} successfully
                  {sendResult.failed > 0 && (
                    <span className="text-amber-400"> · {sendResult.failed} failed</span>
                  )}
                </div>
                <SendProgress sent={sendResult.sent} total={sendResult.sent + sendResult.failed} />
              </div>
            )}

            {sendError && (
              <div className="rounded-xl border border-red-800/50 bg-red-950/20 px-4 py-3 text-sm text-red-400">
                {sendError}
              </div>
            )}

            {/* Test send */}
            <div className="rounded-xl border border-[#27272a] bg-[#18181b] p-5 space-y-3">
              <div>
                <h3 className="text-sm font-semibold text-[#fafafa] font-mono mb-0.5">Test Send</h3>
                <p className="text-[11px] text-[#52525b]">Send the first selected draft to yourself to verify formatting.</p>
              </div>
              <div className="flex gap-2">
                <Input
                  type="email"
                  value={testEmail}
                  onChange={(e) => setTestEmail(e.target.value)}
                  placeholder="your@email.com"
                  className="flex-1 bg-[#09090b] border-[#3f3f46] text-[#fafafa] placeholder:text-[#52525b] focus-visible:border-[#06b6d4] focus-visible:ring-[#06b6d4]/20 font-mono"
                />
                <Button
                  variant="outline"
                  onClick={handleTestSend}
                  disabled={testSending || !testEmail.trim()}
                  size="sm"
                  className="border-[#3f3f46] text-[#a1a1aa] hover:text-[#fafafa] hover:bg-[#27272a]"
                >
                  {testSending ? "Sending..." : "Send Test"}
                </Button>
              </div>
              {testResult && (
                <p
                  className={cn(
                    "text-xs font-mono",
                    testResult.startsWith("Error") ? "text-red-400" : "text-emerald-400"
                  )}
                >
                  {testResult}
                </p>
              )}
            </div>

            {/* Send actions */}
            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setStep("preview")}
                className="px-4 py-2.5 rounded-lg border border-[#3f3f46] text-[#a1a1aa] hover:text-[#fafafa] hover:bg-[#27272a] text-sm transition-all"
              >
                ← Back
              </button>
              <button
                onClick={handleSend}
                disabled={sending || selectedDraftIds.size === 0 || !!sendResult}
                className={cn(
                  "flex-1 py-2.5 rounded-lg font-semibold text-sm transition-all",
                  sending || selectedDraftIds.size === 0 || !!sendResult
                    ? "bg-[#27272a] text-[#52525b] cursor-not-allowed"
                    : "bg-[#06b6d4] hover:bg-[#22d3ee] text-[#09090b]"
                )}
                style={
                  !sending && selectedDraftIds.size > 0 && !sendResult
                    ? { boxShadow: "0 0 16px rgba(6,182,212,0.2)" }
                    : undefined
                }
              >
                {sending ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-3.5 h-3.5 border-2 border-[#06b6d4]/30 border-t-[#06b6d4] rounded-full animate-spin" />
                    Sending...
                  </span>
                ) : (
                  `Send ${selectedDraftIds.size} Email${selectedDraftIds.size === 1 ? "" : "s"} →`
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
