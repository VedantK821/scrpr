"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

function SectionCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[#27272a] bg-[#18181b] p-6 space-y-5">
      <div className="space-y-1">
        <h2 className="font-semibold text-[#fafafa] text-base font-mono">{title}</h2>
        {description && (
          <p className="text-[#71717a] text-xs">{description}</p>
        )}
      </div>
      <div className="h-px bg-gradient-to-r from-transparent via-[#3f3f46] to-transparent" />
      {children}
    </div>
  );
}

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={cn(
        "inline-block w-2 h-2 rounded-full shrink-0",
        ok ? "bg-emerald-400" : "bg-red-500"
      )}
      style={ok ? { boxShadow: "0 0 6px rgba(52,211,153,0.7)" } : { boxShadow: "0 0 6px rgba(239,68,68,0.7)" }}
    />
  );
}

function LinkedInSection() {
  const qc = useQueryClient();
  const [cookieInput, setCookieInput] = useState("");
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["linkedin-status"],
    queryFn: api.linkedin.status,
    staleTime: 30_000,
  });

  const showMsg = (text: string, ok: boolean) => {
    setMessage({ text, ok });
    setTimeout(() => setMessage(null), 5000);
  };

  const importBrowser = useMutation({
    mutationFn: () => api.linkedin.importBrowser("auto"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["linkedin-status"] });
      showMsg("LinkedIn cookie imported from browser successfully.", true);
    },
    onError: (e: Error) => showMsg(e.message, false),
  });

  const connectBrowser = useMutation({
    mutationFn: () => api.linkedin.connectBrowser(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["linkedin-status"] });
      showMsg("LinkedIn connected via browser login.", true);
    },
    onError: (e: Error) => showMsg(e.message, false),
  });

  const connectCookie = useMutation({
    mutationFn: () => api.linkedin.connectCookie(cookieInput.trim()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["linkedin-status"] });
      setCookieInput("");
      showMsg("LinkedIn connected via cookie.", true);
    },
    onError: (e: Error) => showMsg(e.message, false),
  });

  const disconnect = useMutation({
    mutationFn: () => api.linkedin.disconnect(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["linkedin-status"] });
      showMsg("LinkedIn disconnected.", true);
    },
    onError: (e: Error) => showMsg(e.message, false),
  });

  const isConnected = status?.connected ?? false;
  const anyPending =
    importBrowser.isPending ||
    connectBrowser.isPending ||
    connectCookie.isPending ||
    disconnect.isPending;

  return (
    <SectionCard
      title="LinkedIn Connection"
      description="Connect your LinkedIn account to enable profile enrichment and search."
    >
      {/* Status row */}
      <div className="flex items-center gap-3">
        {statusLoading ? (
          <div className="skeleton h-4 w-32 rounded" />
        ) : (
          <>
            <StatusDot ok={isConnected} />
            <span className={cn("text-sm font-mono", isConnected ? "text-emerald-400" : "text-red-400")}>
              {isConnected ? "Connected" : "Not Connected"}
            </span>
            {status?.has_cookie && !isConnected && (
              <span className="text-[#52525b] text-xs font-mono">(cookie stored, session inactive)</span>
            )}
          </>
        )}
      </div>

      {/* Import from browser */}
      <div className="space-y-1.5">
        <p className="text-[#a1a1aa] text-xs font-mono uppercase tracking-wider">Auto-import from Browser</p>
        <p className="text-[#52525b] text-xs">
          Imports your li_at cookie from Floorp, Firefox, or Chrome if you&apos;re already logged into LinkedIn there.
        </p>
        <Button
          onClick={() => importBrowser.mutate()}
          disabled={anyPending}
          variant="outline"
          className="border-[#3f3f46] bg-[#09090b] text-[#a1a1aa] hover:text-[#fafafa] hover:border-[#06b6d4]/50 mt-1"
          size="sm"
        >
          {importBrowser.isPending ? "Importing..." : "Auto-import from Browser"}
        </Button>
      </div>

      {/* Cookie input */}
      <div className="space-y-1.5">
        <Label className="text-[#a1a1aa] text-xs font-mono uppercase tracking-wider">Paste li_at Cookie</Label>
        <p className="text-[#52525b] text-xs">
          Get this from your browser&apos;s dev tools → Application → Cookies → linkedin.com → li_at
        </p>
        <div className="flex gap-2">
          <Input
            value={cookieInput}
            onChange={(e) => setCookieInput(e.target.value)}
            placeholder="AQEDATxxxxxx..."
            className="flex-1 bg-[#09090b] border-[#3f3f46] text-[#fafafa] placeholder:text-[#52525b] focus-visible:border-[#06b6d4] focus-visible:ring-[#06b6d4]/20 font-mono text-xs"
          />
          <Button
            onClick={() => connectCookie.mutate()}
            disabled={anyPending || !cookieInput.trim()}
            size="sm"
            className="btn-cyan-gradient shrink-0"
          >
            {connectCookie.isPending ? "Connecting..." : "Connect"}
          </Button>
        </div>
      </div>

      {/* Open browser login */}
      <div className="space-y-1.5">
        <p className="text-[#a1a1aa] text-xs font-mono uppercase tracking-wider">Open Browser Login</p>
        <p className="text-[#52525b] text-xs">
          Opens a Playwright browser window — log in manually and the session is saved automatically.
        </p>
        <Button
          onClick={() => connectBrowser.mutate()}
          disabled={anyPending}
          variant="outline"
          className="border-[#3f3f46] bg-[#09090b] text-[#a1a1aa] hover:text-[#fafafa] hover:border-[#06b6d4]/50"
          size="sm"
        >
          {connectBrowser.isPending ? "Opening Browser..." : "Open Browser Login"}
        </Button>
      </div>

      {/* Disconnect — only when connected */}
      {isConnected && (
        <div className="pt-1 border-t border-[#27272a]">
          <Button
            onClick={() => disconnect.mutate()}
            disabled={anyPending}
            variant="destructive"
            size="sm"
          >
            {disconnect.isPending ? "Disconnecting..." : "Disconnect LinkedIn"}
          </Button>
        </div>
      )}

      {/* Feedback message */}
      {message && (
        <div
          className={cn(
            "rounded-lg px-3 py-2 text-xs font-mono border",
            message.ok
              ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
              : "bg-red-500/10 border-red-500/20 text-red-400"
          )}
        >
          {message.text}
        </div>
      )}
    </SectionCard>
  );
}

function ApiKeysSection() {
  const { data: quota, isLoading } = useQuery({
    queryKey: ["quota"],
    queryFn: api.enrichments.quota,
    staleTime: 60_000,
  });

  return (
    <SectionCard
      title="API Keys"
      description="API keys are configured in your .env file. This shows which sources are active."
    >
      {isLoading ? (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="skeleton h-7 rounded" style={{ animationDelay: `${i * 60}ms` }} />
          ))}
        </div>
      ) : !quota || Object.keys(quota).length === 0 ? (
        <div className="text-[#52525b] text-sm font-mono">No quota data available.</div>
      ) : (
        <div className="space-y-2">
          {Object.entries(quota).map(([source, info]) => {
            const configured = info.limit > 0;
            return (
              <div
                key={source}
                className="flex items-center justify-between px-3 py-2.5 rounded-lg bg-[#09090b] border border-[#27272a]"
              >
                <div className="flex items-center gap-2.5">
                  <StatusDot ok={configured} />
                  <span className="text-[13px] font-mono text-[#a1a1aa] capitalize">{source}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[11px] font-mono text-[#52525b]">
                    {info.remaining}/{info.limit} remaining
                  </span>
                  <span
                    className={cn(
                      "text-[10px] font-mono px-1.5 py-0.5 rounded border",
                      configured
                        ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20"
                        : "text-red-400 bg-red-500/10 border-red-500/20"
                    )}
                  >
                    {configured ? "configured" : "missing"}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-[#09090b] border border-[#27272a]/60">
        <span className="text-[#52525b] text-sm mt-0.5">ℹ</span>
        <p className="text-[#52525b] text-xs font-mono leading-relaxed">
          Keys are set in{" "}
          <code className="text-[#71717a] bg-[#27272a] px-1 rounded text-[10px]">/c/Projects/Scrpr/backend/.env</code>
          . Restart the backend after changes.
        </p>
      </div>
    </SectionCard>
  );
}

function SmtpSection() {
  const [testEmail, setTestEmail] = useState("");
  const [testResult, setTestResult] = useState<{ text: string; ok: boolean } | null>(null);

  const testSend = useMutation({
    mutationFn: () =>
      api.emails.testSend(
        testEmail.trim() || "test@example.com",
        "Scrpr SMTP Test",
        "This is a test email from Scrpr. If you received this, your SMTP is configured correctly."
      ),
    onSuccess: (data) => {
      if (data.success) {
        setTestResult({ text: "Test email sent successfully!", ok: true });
      } else {
        setTestResult({ text: data.error || "Send failed — check SMTP settings.", ok: false });
      }
      setTimeout(() => setTestResult(null), 6000);
    },
    onError: (e: Error) => {
      setTestResult({ text: e.message, ok: false });
      setTimeout(() => setTestResult(null), 6000);
    },
  });

  return (
    <SectionCard
      title="SMTP Configuration"
      description="Email sending settings are configured via .env. Test your configuration here."
    >
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-2 text-xs font-mono">
          {[
            ["SMTP_HOST", "SMTP_PORT"],
            ["SMTP_USER", "SMTP_FROM"],
          ].flat().map((key) => (
            <div key={key} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#09090b] border border-[#27272a]">
              <span className="text-[#52525b]">{key}</span>
              <span className="text-[#3f3f46] ml-auto">•••</span>
            </div>
          ))}
        </div>

        <div className="space-y-1.5">
          <Label className="text-[#a1a1aa] text-xs">Send test email to</Label>
          <div className="flex gap-2">
            <Input
              value={testEmail}
              onChange={(e) => setTestEmail(e.target.value)}
              placeholder="you@example.com"
              type="email"
              className="flex-1 bg-[#09090b] border-[#3f3f46] text-[#fafafa] placeholder:text-[#52525b] focus-visible:border-[#06b6d4] focus-visible:ring-[#06b6d4]/20"
            />
            <Button
              onClick={() => testSend.mutate()}
              disabled={testSend.isPending}
              size="sm"
              variant="outline"
              className="border-[#3f3f46] bg-[#09090b] text-[#a1a1aa] hover:text-[#fafafa] hover:border-[#06b6d4]/50 shrink-0"
            >
              {testSend.isPending ? "Sending..." : "Test Send"}
            </Button>
          </div>
        </div>

        {testResult && (
          <div
            className={cn(
              "rounded-lg px-3 py-2 text-xs font-mono border",
              testResult.ok
                ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                : "bg-red-500/10 border-red-500/20 text-red-400"
            )}
          >
            {testResult.text}
          </div>
        )}
      </div>
    </SectionCard>
  );
}

function AboutSection() {
  return (
    <SectionCard title="About Scrpr">
      <div className="space-y-3 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-[#71717a] font-mono text-xs">Version</span>
          <span className="text-[#a1a1aa] font-mono text-xs">0.1.0</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#71717a] font-mono text-xs">Description</span>
          <span className="text-[#a1a1aa] text-xs">Open-source Clay / Claygent alternative</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#71717a] font-mono text-xs">GitHub</span>
          <a
            href="https://github.com/vedantt/scrpr"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[#06b6d4] text-xs font-mono hover:underline"
          >
            github.com/vedantt/scrpr →
          </a>
        </div>
        <div className="h-px bg-[#27272a]" />
        <div className="flex items-center justify-between">
          <span className="text-[#71717a] font-mono text-xs">Tests</span>
          <span className="text-[#a1a1aa] font-mono text-xs">255 passing</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#71717a] font-mono text-xs">Backend endpoints</span>
          <span className="text-[#a1a1aa] font-mono text-xs">36+</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#71717a] font-mono text-xs">Stack</span>
          <span className="text-[#a1a1aa] font-mono text-xs">Next.js 16 · FastAPI · PostgreSQL</span>
        </div>
      </div>
    </SectionCard>
  );
}

export default function SettingsPage() {
  return (
    <div className="max-w-2xl mx-auto px-8 py-10">
      {/* Header */}
      <div className="mb-8 card-animate">
        <h1 className="text-3xl font-bold tracking-tight font-mono mb-1 gradient-text">Settings</h1>
        <p className="text-[#71717a] text-sm">Configure connections, API keys, and email settings.</p>
      </div>

      <div className="gradient-divider mb-8" />

      <div className="space-y-6 card-animate">
        <LinkedInSection />
        <ApiKeysSection />
        <SmtpSection />
        <AboutSection />
      </div>
    </div>
  );
}
