"use client";
import { use, useState, useCallback } from "react";
import Link from "next/link";
import { useTable, useColumns, useRows } from "@/hooks/use-api";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { EmailDraft } from "@/types";

type Step = "compose" | "preview" | "send";
type PersonalizationLevel = "light" | "medium" | "max";

function ConfidenceBadge({ confidence }: { confidence: number | null }) {
  if (confidence === null) return null;
  const pct = Math.round(confidence * 100);
  const color =
    pct >= 80 ? "bg-emerald-900/40 text-emerald-300 border-emerald-700" :
    pct >= 50 ? "bg-amber-900/40 text-amber-300 border-amber-700" :
                "bg-red-900/40 text-red-300 border-red-700";
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium ${color}`}>
      {pct}% confident
    </span>
  );
}

function DraftCard({
  draft,
  selected,
  onToggleSelect,
  onSkip,
  onUpdate,
}: {
  draft: EmailDraft;
  selected: boolean;
  onToggleSelect: () => void;
  onSkip: () => void;
  onUpdate: (subject: string, body: string) => Promise<void>;
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

  return (
    <div className={`rounded-lg border ${skipped ? "border-zinc-800 opacity-50" : selected ? "border-blue-600 bg-blue-950/20" : "border-zinc-800 bg-zinc-900/50"} transition-colors`}>
      {/* Card header row */}
      <div className="flex items-center gap-3 px-4 py-3">
        {!skipped && (
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggleSelect}
            className="h-4 w-4 rounded border-zinc-600 accent-blue-500"
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-zinc-300 truncate">{draft.to_email}</span>
            <ConfidenceBadge confidence={draft.confidence} />
            {skipped && (
              <span className="text-xs text-zinc-500 border border-zinc-700 rounded px-1.5 py-0.5">Skipped</span>
            )}
          </div>
          <div className="text-xs text-zinc-500 truncate mt-0.5">{draft.subject}</div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {!skipped && (
            <button
              onClick={onSkip}
              className="text-xs text-zinc-500 hover:text-zinc-300 px-2 py-1 rounded hover:bg-zinc-800 transition-colors"
            >
              Skip
            </button>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-zinc-400 hover:text-zinc-200 px-2 py-1 rounded hover:bg-zinc-800 transition-colors"
          >
            {expanded ? "Collapse" : "Expand"}
          </button>
        </div>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-zinc-800 px-4 py-3 space-y-3">
          {editing ? (
            <>
              <div>
                <Label className="text-xs text-zinc-400">Subject</Label>
                <Input
                  value={editSubject}
                  onChange={(e) => setEditSubject(e.target.value)}
                  className="mt-1 bg-zinc-800 border-zinc-700 text-zinc-100"
                />
              </div>
              <div>
                <Label className="text-xs text-zinc-400">Body</Label>
                <textarea
                  value={editBody}
                  onChange={(e) => setEditBody(e.target.value)}
                  rows={8}
                  className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
                />
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={handleSave} disabled={saving}>
                  {saving ? "Saving..." : "Save"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => { setEditing(false); setEditSubject(draft.subject); setEditBody(draft.body); }}>
                  Cancel
                </Button>
              </div>
            </>
          ) : (
            <>
              <div>
                <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">Subject</div>
                <div className="text-sm text-zinc-200">{draft.subject}</div>
              </div>
              <div>
                <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">Body</div>
                <pre className="text-sm text-zinc-300 whitespace-pre-wrap font-sans leading-relaxed">{draft.body}</pre>
              </div>
              {!skipped && (
                <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
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

export default function EmailsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: table } = useTable(id);
  const { data: columns = [] } = useColumns(id);
  const { data: rows = [] } = useRows(id);

  const [step, setStep] = useState<Step>("compose");

  // Compose step state
  const [subjectTemplate, setSubjectTemplate] = useState("Hi /FirstName/, quick question about /Company/");
  const [bodyTemplate, setBodyTemplate] = useState(
    "Hi /FirstName/,\n\nI came across /Company/ and was really impressed by what you're building.\n\n[Your pitch here]\n\nWould love to connect — are you open to a quick chat?\n\nBest,\n[Your name]"
  );
  const [personalizationLevel, setPersonalizationLevel] = useState<PersonalizationLevel>("light");
  const [aiInstructions, setAiInstructions] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  // Preview step state
  const [drafts, setDrafts] = useState<EmailDraft[]>([]);
  const [selectedDraftIds, setSelectedDraftIds] = useState<Set<string>>(new Set());

  // Send step state
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
      // Select all non-skipped by default
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
      if (next.has(draftId)) {
        next.delete(draftId);
      } else {
        next.add(draftId);
      }
      return next;
    });
  }, []);

  const handleSkip = useCallback(async (draftId: string) => {
    await api.emails.updateDraft(draftId, { status: "skipped" });
    setDrafts((prev) =>
      prev.map((d) => (d.id === draftId ? { ...d, status: "skipped" } : d))
    );
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

  const handleSelectAll = () => {
    setSelectedDraftIds(new Set(drafts.filter((d) => d.status !== "skipped").map((d) => d.id)));
  };

  const handleDeselectAll = () => setSelectedDraftIds(new Set());

  const handleSend = async () => {
    setSending(true);
    setSendError(null);
    setSendResult(null);
    try {
      const result = await api.emails.send(Array.from(selectedDraftIds), delaySeconds);
      setSendResult({ sent: result.sent, failed: result.failed });
      // Update draft statuses
      setDrafts((prev) =>
        prev.map((d) => selectedDraftIds.has(d.id) ? { ...d, status: "sent" } : d)
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
      // Use the first selected draft or first draft as preview
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

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* Header */}
      <div className="flex items-center gap-4 px-4 py-3 border-b border-zinc-800 bg-zinc-950 sticky top-0 z-10">
        <Link href={`/table/${id}`} className="text-zinc-400 hover:text-zinc-200 text-sm">
          Back to {table?.name ?? "Table"}
        </Link>
        <div className="h-4 w-px bg-zinc-700" />
        <h1 className="text-base font-semibold text-zinc-100">Email Composer</h1>

        {/* Step indicators */}
        <div className="ml-auto flex items-center gap-1">
          {(["compose", "preview", "send"] as Step[]).map((s, i) => (
            <button
              key={s}
              onClick={() => {
                if (s === "compose") setStep("compose");
                if (s === "preview" && drafts.length > 0) setStep("preview");
                if (s === "send" && drafts.length > 0) setStep("send");
              }}
              disabled={s !== "compose" && drafts.length === 0}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                step === s
                  ? "bg-blue-600 text-white"
                  : "text-zinc-500 hover:text-zinc-300 disabled:opacity-40 disabled:cursor-not-allowed"
              }`}
            >
              <span className={`h-4 w-4 rounded-full flex items-center justify-center text-[10px] font-bold ${step === s ? "bg-white/20" : "bg-zinc-800"}`}>
                {i + 1}
              </span>
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 py-8">
        {/* ── STEP 1: COMPOSE ── */}
        {step === "compose" && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold mb-1">Compose Email Template</h2>
              <p className="text-sm text-zinc-500">
                Use <code className="bg-zinc-800 px-1 rounded text-zinc-300">/ColumnName/</code> to reference data from your table.
                Available columns: {columnNames.length > 0 ? columnNames.map((n) => <code key={n} className="bg-zinc-800 px-1 rounded text-blue-300 text-xs ml-1">/{ n }/</code>) : <span className="text-zinc-600">none yet</span>}
              </p>
            </div>

            <div>
              <Label className="text-sm text-zinc-300">Subject Line</Label>
              <Input
                value={subjectTemplate}
                onChange={(e) => setSubjectTemplate(e.target.value)}
                placeholder="Hi /FirstName/, quick question about /Company/"
                className="mt-1.5 bg-zinc-900 border-zinc-700 text-zinc-100"
              />
            </div>

            <div>
              <Label className="text-sm text-zinc-300">Email Body</Label>
              <textarea
                value={bodyTemplate}
                onChange={(e) => setBodyTemplate(e.target.value)}
                rows={12}
                placeholder="Hi /FirstName/,&#10;&#10;..."
                className="mt-1.5 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y font-mono leading-relaxed"
              />
            </div>

            {/* Personalization level */}
            <div>
              <Label className="text-sm text-zinc-300">AI Personalization</Label>
              <div className="mt-1.5 flex gap-2">
                {(["light", "medium", "max"] as PersonalizationLevel[]).map((level) => (
                  <button
                    key={level}
                    onClick={() => setPersonalizationLevel(level)}
                    className={`flex-1 py-2.5 px-3 rounded-lg border text-sm font-medium transition-colors ${
                      personalizationLevel === level
                        ? "border-blue-500 bg-blue-600/20 text-blue-300"
                        : "border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300"
                    }`}
                  >
                    {level === "light" && "Light"}
                    {level === "medium" && "Medium"}
                    {level === "max" && "Max"}
                    <div className="text-[10px] font-normal mt-0.5 opacity-70">
                      {level === "light" && "Fill variables only"}
                      {level === "medium" && "Rewrite + research"}
                      {level === "max" && "Fully custom per row"}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* AI instructions for medium/max */}
            {(personalizationLevel === "medium" || personalizationLevel === "max") && (
              <div>
                <Label className="text-sm text-zinc-300">AI Instructions <span className="text-zinc-500 font-normal">(optional)</span></Label>
                <textarea
                  value={aiInstructions}
                  onChange={(e) => setAiInstructions(e.target.value)}
                  rows={3}
                  placeholder="e.g. Mention their recent funding round. Be casual and brief. Avoid buzzwords."
                  className="mt-1.5 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
                />
              </div>
            )}

            {generateError && (
              <div className="rounded-lg border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-300">
                {generateError}
              </div>
            )}

            <div className="flex items-center gap-3">
              <Button
                onClick={handleGenerateDrafts}
                disabled={generating || !subjectTemplate.trim() || !bodyTemplate.trim()}
                className="px-6"
              >
                {generating ? "Generating..." : `Generate Drafts (${rows.length} rows)`}
              </Button>
              <span className="text-xs text-zinc-600">
                {rows.length === 0 ? "No rows in table yet" : `Will create ${rows.length} email draft${rows.length === 1 ? "" : "s"}`}
              </span>
            </div>
          </div>
        )}

        {/* ── STEP 2: PREVIEW ── */}
        {step === "preview" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold">Review Drafts</h2>
                <p className="text-sm text-zinc-500 mt-0.5">
                  {drafts.length} draft{drafts.length === 1 ? "" : "s"} generated &mdash; {selectedDraftIds.size} selected to send
                </p>
              </div>
              <div className="flex gap-2">
                <button onClick={handleSelectAll} className="text-xs text-blue-400 hover:text-blue-300">Select all</button>
                <span className="text-zinc-700">·</span>
                <button onClick={handleDeselectAll} className="text-xs text-zinc-500 hover:text-zinc-300">Deselect all</button>
              </div>
            </div>

            <div className="space-y-3">
              {drafts.map((draft) => (
                <DraftCard
                  key={draft.id}
                  draft={draft}
                  selected={selectedDraftIds.has(draft.id)}
                  onToggleSelect={() => handleToggleSelect(draft.id)}
                  onSkip={() => handleSkip(draft.id)}
                  onUpdate={(subject, body) => handleUpdateDraft(draft.id, subject, body)}
                />
              ))}
            </div>

            <div className="flex gap-3 pt-2">
              <Button variant="outline" onClick={() => setStep("compose")}>
                Back
              </Button>
              <Button
                onClick={() => setStep("send")}
                disabled={selectedDraftIds.size === 0}
              >
                Continue to Send ({selectedDraftIds.size} selected)
              </Button>
            </div>
          </div>
        )}

        {/* ── STEP 3: SEND ── */}
        {step === "send" && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold">Send Emails</h2>
              <p className="text-sm text-zinc-500 mt-0.5">
                Sending {selectedDraftIds.size} email{selectedDraftIds.size === 1 ? "" : "s"}
              </p>
            </div>

            {/* Delay config */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
              <h3 className="text-sm font-medium text-zinc-300">Send Settings</h3>
              <div className="flex items-center gap-3">
                <Label className="text-sm text-zinc-400 whitespace-nowrap">Delay between emails</Label>
                <Input
                  type="number"
                  value={delaySeconds}
                  onChange={(e) => setDelaySeconds(Number(e.target.value))}
                  min={0}
                  max={300}
                  className="w-24 bg-zinc-800 border-zinc-700 text-zinc-100"
                />
                <span className="text-sm text-zinc-500">seconds</span>
              </div>
              <p className="text-xs text-zinc-600">
                Total estimated send time: ~{Math.round((selectedDraftIds.size - 1) * delaySeconds / 60)} minutes
              </p>
            </div>

            {/* Selected drafts summary */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <h3 className="text-sm font-medium text-zinc-300 mb-2">Selected Emails</h3>
              <div className="space-y-1 max-h-48 overflow-y-auto">
                {activeDrafts
                  .filter((d) => selectedDraftIds.has(d.id))
                  .map((d) => (
                    <div key={d.id} className="flex items-center justify-between text-sm py-0.5">
                      <span className="text-zinc-400 truncate">{d.to_email}</span>
                      <ConfidenceBadge confidence={d.confidence} />
                    </div>
                  ))}
              </div>
            </div>

            {/* Send result */}
            {sendResult && (
              <div className="rounded-lg border border-emerald-800 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-300">
                Sent {sendResult.sent} email{sendResult.sent === 1 ? "" : "s"} successfully
                {sendResult.failed > 0 && `, ${sendResult.failed} failed`}.
              </div>
            )}
            {sendError && (
              <div className="rounded-lg border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-300">
                {sendError}
              </div>
            )}

            {/* Test send */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
              <h3 className="text-sm font-medium text-zinc-300">Test Send</h3>
              <p className="text-xs text-zinc-500">Send the first selected draft to yourself to verify formatting.</p>
              <div className="flex gap-2">
                <Input
                  type="email"
                  value={testEmail}
                  onChange={(e) => setTestEmail(e.target.value)}
                  placeholder="your@email.com"
                  className="flex-1 bg-zinc-800 border-zinc-700 text-zinc-100"
                />
                <Button
                  variant="outline"
                  onClick={handleTestSend}
                  disabled={testSending || !testEmail.trim()}
                  size="sm"
                >
                  {testSending ? "Sending..." : "Send Test"}
                </Button>
              </div>
              {testResult && (
                <p className={`text-xs ${testResult.startsWith("Error") ? "text-red-400" : "text-emerald-400"}`}>
                  {testResult}
                </p>
              )}
            </div>

            <div className="flex gap-3">
              <Button variant="outline" onClick={() => setStep("preview")}>
                Back
              </Button>
              <Button
                onClick={handleSend}
                disabled={sending || selectedDraftIds.size === 0 || !!sendResult}
                className="px-6"
              >
                {sending ? "Sending..." : `Send ${selectedDraftIds.size} Email${selectedDraftIds.size === 1 ? "" : "s"}`}
              </Button>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
