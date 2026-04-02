"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Reveal from "reveal.js";

/* ─── Types ─────────────────────────────────────────────────── */

type Source = {
  id: number;
  title: string;
  url: string;
  snippet: string;
};

type DashboardMetric = {
  label: string;
  value: string;
  trend: string;
};

type Slide = {
  slide_number: number;
  title: string;
  subtitle: string;
  bullets: string[];
  key_stat: string;
  source_ids: number[];
  dashboard_metrics?: DashboardMetric[];
  slide_type?: string;
};

type ApiResponse = {
  company: string;
  generated_at: string;
  slides: Slide[];
  sources: Source[];
  pptx_url: string;
};

type AgentStatus = "idle" | "running" | "done" | "error";

type StreamEvent = {
  type: "thinking" | "search" | "source" | "progress" | "attempt" | "slides" | "done" | "error";
  data: string;
  timestamp: number;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ─── Small SVG Icons (inline to avoid deps) ────────────────── */

function IconSearch({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <circle cx="11" cy="11" r="8" />
      <path strokeLinecap="round" d="M21 21l-4.35-4.35" />
    </svg>
  );
}

function IconChart({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 3v18h18" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 16l4-8 4 4 5-10" />
    </svg>
  );
}

function IconExpand({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5" />
    </svg>
  );
}

function IconDownload({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5m0 0l5-5m-5 5V3" />
    </svg>
  );
}

function IconArrowRight({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
    </svg>
  );
}

function IconCheck({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

function IconX({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

/* ─── Status Badge Component ────────────────────────────────── */

function AgentStatusBadge({ status }: { status: AgentStatus }) {
  if (status === "idle")
    return (
      <span className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
        <span className="h-2 w-2 rounded-full bg-slate-600" />
        Waiting
      </span>
    );
  if (status === "running")
    return (
      <span className="flex items-center gap-1.5 text-xs text-amber-300">
        <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse-dot" />
        Analyzing...
      </span>
    );
  if (status === "done")
    return (
      <span className="flex items-center gap-1.5 text-xs text-emerald-400">
        <IconCheck className="w-3.5 h-3.5" />
        Complete
      </span>
    );
  return (
    <span className="flex items-center gap-1.5 text-xs text-red-400">
      <IconX className="w-3.5 h-3.5" />
      Failed
    </span>
  );
}

/* ─── Thinking Feed Component ───────────────────────────────── */

function ThinkingFeed({ events }: { events: StreamEvent[] }) {
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [events]);

  if (events.length === 0) return null;

  return (
    <div
      ref={feedRef}
      className="flex flex-col gap-1 overflow-y-auto max-h-[320px] px-1 text-xs font-mono"
    >
      {events.map((ev, i) => {
        const time = new Date(ev.timestamp).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });

        if (ev.type === "thinking") {
          return (
            <div key={i} className="flex gap-2 py-1 text-purple-300/90">
              <span className="shrink-0 text-purple-500/60">{time}</span>
              <span className="shrink-0 text-purple-400">{"\u{1F9E0}"}</span>
              <span className="leading-relaxed">{ev.data}</span>
            </div>
          );
        }
        if (ev.type === "search") {
          return (
            <div key={i} className="flex gap-2 py-1 text-sky-300/90">
              <span className="shrink-0 text-sky-500/60">{time}</span>
              <span className="shrink-0 text-sky-400">{"\u{1F50D}"}</span>
              <span>
                Searching: <span className="text-sky-200 font-semibold">{ev.data}</span>
              </span>
            </div>
          );
        }
        if (ev.type === "source") {
          let parsed: { title?: string; url?: string } = {};
          try {
            parsed = JSON.parse(ev.data);
          } catch {
            parsed = { title: ev.data, url: "" };
          }
          return (
            <div key={i} className="flex gap-2 py-1 text-emerald-300/90">
              <span className="shrink-0 text-emerald-500/60">{time}</span>
              <span className="shrink-0 text-emerald-400">{"\u{1F310}"}</span>
              <span className="truncate">
                Found: <span className="text-emerald-200">{parsed.title || parsed.url}</span>
                {parsed.url && (
                  <span className="ml-1.5 text-emerald-500/60 text-[10px]">{parsed.url}</span>
                )}
              </span>
            </div>
          );
        }
        if (ev.type === "attempt") {
          let parsed: { attempt?: number; score?: number; issues?: string[] } = {};
          try {
            parsed = JSON.parse(ev.data);
          } catch {
            /* ignore */
          }
          const scoreColor =
            (parsed.score ?? 0) >= 85
              ? "text-emerald-400"
              : (parsed.score ?? 0) >= 70
                ? "text-amber-400"
                : "text-red-400";
          return (
            <div key={i} className="flex gap-2 py-1.5 text-[var(--text-muted)]">
              <span className="shrink-0 text-[var(--text-muted)]/60">{time}</span>
              <span className="shrink-0">{"\u{1F4CA}"}</span>
              <span>
                Attempt {parsed.attempt}: score{" "}
                <span className={`font-bold ${scoreColor}`}>{parsed.score}/100</span>
                {parsed.issues && parsed.issues.length > 0 && (
                  <span className="text-amber-400/70"> ({parsed.issues.length} issues)</span>
                )}
              </span>
            </div>
          );
        }
        if (ev.type === "progress" || ev.type === "slides") {
          return (
            <div key={i} className="flex gap-2 py-1 text-[var(--gold)]/80">
              <span className="shrink-0 text-[var(--gold)]/40">{time}</span>
              <span className="shrink-0">{ev.type === "slides" ? "\u{1F4CA}" : "\u{2699}\u{FE0F}"}</span>
              <span className="font-medium">{ev.data}</span>
            </div>
          );
        }
        if (ev.type === "error") {
          return (
            <div key={i} className="flex gap-2 py-1 text-red-400">
              <span className="shrink-0 text-red-500/60">{time}</span>
              <span className="shrink-0">{"\u274C"}</span>
              <span>{ev.data}</span>
            </div>
          );
        }
        return null;
      })}
    </div>
  );
}

/* ─── Trend Arrow Helper ────────────────────────────────────── */

function trendDisplay(trend: string) {
  if (trend === "up") return { arrow: "\u2191", cls: "up" };
  if (trend === "down") return { arrow: "\u2193", cls: "down" };
  return { arrow: "\u2192", cls: "flat" };
}

/* ─── Main Page ─────────────────────────────────────────────── */

export default function Home() {
  const [company, setCompany] = useState("");
  const [loading, setLoading] = useState(false);
  const [status1, setStatus1] = useState<AgentStatus>("idle");
  const [status2, setStatus2] = useState<AgentStatus>("idle");
  const [status3, setStatus3] = useState<AgentStatus>("idle");
  const [error, setError] = useState("");
  const [result, setResult] = useState<ApiResponse | null>(null);
  const [selectedSource, setSelectedSource] = useState<number | null>(null);
  const [currentSlideIdx, setCurrentSlideIdx] = useState(0);
  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([]);

  const revealRootRef = useRef<HTMLDivElement>(null);
  const revealInstanceRef = useRef<InstanceType<typeof Reveal> | null>(null);
  const previewContainerRef = useRef<HTMLDivElement>(null);

  const sourceMap = useMemo(() => {
    const map = new Map<number, Source>();
    (result?.sources || []).forEach((s) => map.set(s.id, s));
    return map;
  }, [result?.sources]);

  /* ── Reveal.js lifecycle ──────────────────────────────────── */

  // Initialize reveal when result changes
  useEffect(() => {
    if (!result || !revealRootRef.current) return;

    // Destroy previous instance if it exists
    if (revealInstanceRef.current) {
      try {
        revealInstanceRef.current.destroy();
      } catch {
        // ignore destroy errors
      }
      revealInstanceRef.current = null;
    }

    // Small timeout to let React commit the DOM first
    const timer = setTimeout(async () => {
      if (!revealRootRef.current) return;
      const deck = new Reveal(revealRootRef.current, {
        embedded: true,
        controls: true,
        progress: true,
        center: false,
        hash: false,
        transition: "slide",
        width: "100%",
        height: 600,
        margin: 0.04,
      });

      await deck.initialize();
      revealInstanceRef.current = deck;

      // reveal.js types deck.on as HTMLElement['addEventListener'] but it
      // dispatches custom events with indexh. Cast to work around it.
      (deck as unknown as { on: (type: string, cb: (e: Record<string, unknown>) => void) => void }).on(
        "slidechanged",
        (event) => {
          setCurrentSlideIdx((event.indexh as number) ?? 0);
        }
      );

      setCurrentSlideIdx(0);
    }, 80);

    return () => clearTimeout(timer);
  }, [result]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (revealInstanceRef.current) {
        try {
          revealInstanceRef.current.destroy();
        } catch {
          // ignore
        }
      }
    };
  }, []);

  /* ── API call ─────────────────────────────────────────────── */

  const runResearch = useCallback(async () => {
    const name = company.trim();
    if (!name) return;
    setLoading(true);
    setError("");
    setResult(null);
    setSelectedSource(null);
    setCurrentSlideIdx(0);
    setStreamEvents([]);
    setStatus1("running");
    setStatus2("idle");
    setStatus3("idle");

    const addEvent = (type: StreamEvent["type"], data: string) => {
      setStreamEvents((prev) => [...prev, { type, data, timestamp: Date.now() }]);
    };

    try {
      const response = await fetch(`${API_URL}/api/research/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company: name }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "Failed to start research stream.");
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      // SSE parser that handles large multi-chunk data payloads.
      // An SSE message ends with a blank line (\n\n). We accumulate
      // data lines until we see a blank line, then process the full message.
      const processMessage = (eventType: string, dataStr: string) => {
        if (!eventType || !dataStr) return;
        try {
          const parsed = JSON.parse(dataStr);

          if (eventType === "done") {
            setResult(parsed as ApiResponse);
            setStatus1("done");
            setStatus2("done");
            setStatus3("done");
            addEvent("progress", "Report complete!");
          } else if (eventType === "agent") {
            const agentName = typeof parsed === "string" ? parsed : "";
            if (agentName === "analyst") {
              setStatus1("done");
              setStatus2("running");
              addEvent("progress", "Starting data analyst agent...");
            } else if (agentName === "ppt") {
              setStatus2("done");
              setStatus3("running");
              addEvent("progress", "Starting presentation agent...");
            }
          } else if (eventType === "slides") {
            setStatus2("done");
            setStatus3("running");
            addEvent("slides", typeof parsed === "string" ? parsed : "Building slides...");
          } else if (eventType === "error") {
            addEvent("error", typeof parsed === "string" ? parsed : "Unknown error");
          } else if (eventType === "source") {
            addEvent("source", typeof parsed === "string" ? parsed : JSON.stringify(parsed));
          } else if (eventType === "attempt") {
            addEvent("attempt", typeof parsed === "string" ? parsed : JSON.stringify(parsed));
          } else {
            addEvent(
              eventType as StreamEvent["type"],
              typeof parsed === "string" ? parsed : JSON.stringify(parsed)
            );
          }
        } catch {
          // Ignore unparseable data
        }
      };

      // Accumulate SSE messages across chunks. An SSE message is:
      //   event: <type>\n
      //   data: <json>\n
      //   \n  (blank line = end of message)
      let pendingEvent = "";
      let pendingData = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Process complete lines from the buffer
        let nlIdx: number;
        while ((nlIdx = buffer.indexOf("\n")) !== -1) {
          const line = buffer.slice(0, nlIdx).trim();
          buffer = buffer.slice(nlIdx + 1);

          if (line === "") {
            // Blank line = end of SSE message → process it
            if (pendingEvent && pendingData) {
              processMessage(pendingEvent, pendingData);
            }
            pendingEvent = "";
            pendingData = "";
          } else if (line.startsWith("event:")) {
            // New event type — if we had a pending message, flush it first
            if (pendingEvent && pendingData) {
              processMessage(pendingEvent, pendingData);
              pendingData = "";
            }
            pendingEvent = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            // Accumulate data (handles multi-line data fields)
            const chunk = line.slice(5).trimStart();
            pendingData = pendingData ? pendingData + chunk : chunk;
          }
        }
      }

      // Flush any remaining message after stream ends
      if (pendingEvent && pendingData) {
        processMessage(pendingEvent, pendingData);
      }
    } catch (err) {
      setStatus1((prev) => (prev === "done" ? "done" : "error"));
      setStatus2("error");
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(msg);
      addEvent("error", msg);
    } finally {
      setLoading(false);
    }
  }, [company]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !loading) runResearch();
    },
    [loading, runResearch]
  );

  /* ── Fullscreen ───────────────────────────────────────────── */

  const toggleFullscreen = useCallback(async () => {
    const node = previewContainerRef.current;
    if (!node) return;
    if (!document.fullscreenElement) {
      await node.requestFullscreen();
    } else {
      await document.exitFullscreen();
    }
  }, []);

  /* ── Derived ──────────────────────────────────────────────── */

  const totalSlides = result?.slides?.length || 0;
  const currentSlide = result?.slides?.[currentSlideIdx];

  /* ── Render ───────────────────────────────────────────────── */

  return (
    <main className="flex min-h-screen flex-col">
      {/* ════════ HEADER ════════ */}
      <header className="flex items-center justify-between border-b border-[var(--slate-border)] bg-[var(--navy)] px-6 py-4">
        <div className="flex items-center gap-3">
          {/* Logo mark */}
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-[var(--gold)] to-[var(--gold-dim)]">
            <svg className="h-5 w-5 text-[var(--navy)]" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10 2L2 7l8 5 8-5-8-5zM2 13l8 5 8-5M2 10l8 5 8-5" />
            </svg>
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white">
              PE Due Diligence AI
            </h1>
            <p className="text-[10px] uppercase tracking-[0.15em] text-[var(--text-muted)]">
              Investment Committee Platform
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="rounded-full border border-[var(--slate-border)] px-3 py-1 text-[11px] font-medium text-[var(--text-muted)]">
            Gemini 2.5 Pro
          </span>
          <span className="text-[10px] uppercase tracking-widest text-[var(--gold-dim)]">
            Confidential
          </span>
        </div>
      </header>

      <div className="flex flex-1 flex-col gap-0">
        {/* ════════ COMMAND BAR ════════ */}
        <section className="border-b border-[var(--slate-border)] bg-[var(--navy)]/60 px-6 py-5">
          <label className="mb-2 block text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)]">
            Target Company
          </label>
          <div className="flex gap-3">
            <div className="relative flex-1 max-w-2xl">
              <input
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="e.g. Mistral AI, Perplexity, Databricks, Wiz"
                className="w-full rounded-lg border border-[var(--slate-border)] bg-[var(--navy-light)] px-4 py-2.5 pr-20 text-sm text-white placeholder-[var(--text-muted)] outline-none transition-all focus:border-[var(--gold-dim)] focus:ring-1 focus:ring-[var(--gold-dim)]"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-[var(--text-muted)]">
                {company.length}/120
              </span>
            </div>
            <button
              onClick={runResearch}
              disabled={loading || !company.trim()}
              className="group flex items-center gap-2 rounded-lg bg-gradient-to-r from-[var(--gold)] to-[var(--gold-dim)] px-6 py-2.5 text-sm font-bold text-[var(--navy)] shadow-lg shadow-amber-900/20 transition-all hover:shadow-amber-900/40 disabled:opacity-40 disabled:shadow-none"
            >
              {loading ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--navy)] border-t-transparent" />
                  Generating...
                </>
              ) : (
                <>
                  Run Diligence
                  <IconArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
                </>
              )}
            </button>
          </div>

          {/* ── Agent Pipeline Status ── */}
          <div className="mt-4 flex items-center gap-2">
            <div className="flex items-center gap-3 rounded-lg border border-[var(--slate-border)] bg-[var(--navy-light)] px-4 py-2.5">
              <div className="flex items-center gap-2">
                <IconSearch className="h-4 w-4 text-[var(--gold)]" />
                <span className="text-xs font-medium text-white">Research Agent</span>
              </div>
              <AgentStatusBadge status={status1} />
            </div>

            <svg className="h-4 w-6 text-[var(--slate-border)]" viewBox="0 0 24 16" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="M2 8h16m0 0l-4-4m4 4l-4 4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>

            <div className="flex items-center gap-3 rounded-lg border border-[var(--slate-border)] bg-[var(--navy-light)] px-4 py-2.5">
              <div className="flex items-center gap-2">
                <svg className="h-4 w-4 text-[var(--gold)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span className="text-xs font-medium text-white">Data Analyst</span>
              </div>
              <AgentStatusBadge status={status2} />
            </div>

            <svg className="h-4 w-6 text-[var(--slate-border)]" viewBox="0 0 24 16" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="M2 8h16m0 0l-4-4m4 4l-4 4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>

            <div className="flex items-center gap-3 rounded-lg border border-[var(--slate-border)] bg-[var(--navy-light)] px-4 py-2.5">
              <div className="flex items-center gap-2">
                <IconChart className="h-4 w-4 text-[var(--gold)]" />
                <span className="text-xs font-medium text-white">Presentation</span>
              </div>
              <AgentStatusBadge status={status3} />
            </div>
          </div>

          {error && (
            <div className="mt-3 rounded-lg border border-red-800/50 bg-red-950/30 px-4 py-2.5 text-sm text-red-300">
              {error}
            </div>
          )}
        </section>

        {/* ════════ MAIN CONTENT ════════ */}
        <section className="flex flex-1 gap-0">
          {/* ── Preview Panel ── */}
          <div className="flex flex-1 flex-col border-r border-[var(--slate-border)]">
            {/* Toolbar */}
            <div className="flex items-center justify-between border-b border-[var(--slate-border)] bg-[var(--navy)]/40 px-5 py-2.5">
              <div className="flex items-center gap-3">
                <span className="text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                  Slide Preview
                </span>
                {totalSlides > 0 && (
                  <span className="rounded-md bg-[var(--navy-card)] px-2 py-0.5 text-xs font-mono text-[var(--gold)]">
                    {currentSlideIdx + 1} / {totalSlides}
                  </span>
                )}
                {currentSlide && (
                  <span className="text-xs text-[var(--text-muted)] truncate max-w-[300px]">
                    {currentSlide.title}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={toggleFullscreen}
                  className="flex items-center gap-1.5 rounded-md border border-[var(--slate-border)] px-2.5 py-1 text-xs text-[var(--text-muted)] transition-colors hover:border-[var(--gold-dim)] hover:text-white"
                >
                  <IconExpand />
                  Fullscreen
                </button>
                {result?.pptx_url && (
                  <a
                    href={result.pptx_url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1 text-xs font-semibold text-white transition-colors hover:bg-emerald-500"
                  >
                    <IconDownload />
                    Download .pptx
                  </a>
                )}
              </div>
            </div>

            {/* Reveal.js or empty/loading state */}
            <div ref={previewContainerRef} className="flex-1 bg-[var(--navy)] p-4">
              {!result && !loading && (
                /* Empty state */
                <div className="flex h-full flex-col items-center justify-center text-center" style={{ minHeight: 500 }}>
                  <div className="mb-5 flex h-20 w-20 items-center justify-center rounded-2xl border border-[var(--slate-border)] bg-[var(--navy-light)]">
                    <svg className="h-10 w-10 text-[var(--slate-border)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <h3 className="text-lg font-semibold text-white">No report generated yet</h3>
                  <p className="mt-2 max-w-sm text-sm text-[var(--text-muted)]">
                    Enter a company name above and click Run Diligence to generate an
                    IC-ready investment memo with cited sources.
                  </p>
                  <div className="mt-5 flex gap-2 text-xs text-[var(--text-muted)]">
                    <kbd className="rounded border border-[var(--slate-border)] bg-[var(--navy-light)] px-2 py-0.5 font-mono">Enter</kbd>
                    <span>to run</span>
                  </div>
                </div>
              )}

              {loading && !result && (
                /* Live thinking feed + skeleton */
                <div className="flex h-full flex-col gap-4" style={{ minHeight: 500 }}>
                  {streamEvents.length > 0 ? (
                    <div className="flex flex-1 flex-col rounded-lg border border-[var(--slate-border)] bg-[var(--navy-light)] overflow-hidden">
                      <div className="flex items-center gap-2 border-b border-[var(--slate-border)] px-4 py-2.5">
                        <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse-dot" />
                        <span className="text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                          Live Agent Thinking
                        </span>
                        <span className="ml-auto text-[10px] text-[var(--text-muted)]">
                          {streamEvents.length} events
                        </span>
                      </div>
                      <div className="flex-1 overflow-y-auto p-3">
                        <ThinkingFeed events={streamEvents} />
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-1 flex-col items-center justify-center gap-6">
                      <div className="w-full max-w-xl space-y-4">
                        <div className="h-8 w-3/4 rounded skeleton-shimmer" />
                        <div className="h-5 w-1/2 rounded skeleton-shimmer" />
                        <div className="mt-6 space-y-3">
                          <div className="h-4 w-full rounded skeleton-shimmer" />
                          <div className="h-4 w-5/6 rounded skeleton-shimmer" />
                          <div className="h-4 w-4/6 rounded skeleton-shimmer" />
                        </div>
                      </div>
                      <p className="text-sm text-[var(--text-muted)]">
                        Connecting to research agent...
                      </p>
                    </div>
                  )}
                </div>
              )}

              {result && (
                <div className="reveal" ref={revealRootRef}>
                  <div className="slides">
                    {result.slides.map((slide) => (
                      <section key={slide.slide_number}>
                        <div className="slide-header">
                          <h3>{slide.title}</h3>
                          <h5>{slide.subtitle}</h5>
                        </div>

                        <ul>
                          {slide.bullets.map((bullet, idx) => (
                            <li key={`${slide.slide_number}-b-${idx}`}>{bullet}</li>
                          ))}
                        </ul>

                        {slide.key_stat && (
                          <div className="key-stat-box">{slide.key_stat}</div>
                        )}

                        {slide.dashboard_metrics && slide.dashboard_metrics.length > 0 && (
                          <div className="metric-grid">
                            {slide.dashboard_metrics.slice(0, 6).map((m, idx) => {
                              const t = trendDisplay(m.trend);
                              return (
                                <div key={`${slide.slide_number}-m-${idx}`} className="metric-card">
                                  <div className="metric-label">{m.label}</div>
                                  <div className="metric-value">{m.value}</div>
                                  <div className={`metric-trend ${t.cls}`}>
                                    {t.arrow} {m.trend}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}

                        <div className="source-pills">
                          {slide.source_ids.map((id) => (
                            <button
                              key={`${slide.slide_number}-s-${id}`}
                              onClick={() => setSelectedSource(id)}
                              className={`rounded-md px-2 py-0.5 text-[11px] font-mono transition-colors ${
                                selectedSource === id
                                  ? "bg-[var(--gold)] text-[var(--navy)]"
                                  : "bg-[var(--navy-card)] text-[var(--text-muted)] hover:text-white"
                              }`}
                            >
                              [{id}]
                            </button>
                          ))}
                        </div>
                      </section>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* ── Sources Panel ── */}
          <aside className="flex w-[380px] shrink-0 flex-col bg-[var(--navy)]">
            <div className="flex items-center justify-between border-b border-[var(--slate-border)] px-5 py-3">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                Sources
              </h2>
              {result?.sources && result.sources.length > 0 && (
                <span className="rounded-md bg-[var(--navy-card)] px-2 py-0.5 text-xs font-mono text-[var(--gold)]">
                  {result.sources.length} cited
                </span>
              )}
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-3">
              {!result && (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <p className="text-sm text-[var(--text-muted)]">
                    Sources will appear here after generating a report.
                  </p>
                </div>
              )}

              {result?.sources && (
                <div className="space-y-2">
                  {result.sources.map((source) => {
                    const isSelected = selectedSource === source.id;
                    return (
                      <button
                        key={source.id}
                        onClick={() => setSelectedSource(isSelected ? null : source.id)}
                        className={`w-full rounded-lg border p-3 text-left transition-all ${
                          isSelected
                            ? "border-l-[3px] border-[var(--gold)] bg-[var(--navy-card)]"
                            : "border-[var(--slate-border)] hover:border-[var(--gold-dim)]/40 hover:bg-[var(--navy-light)]"
                        }`}
                      >
                        <div className="flex items-start gap-2.5">
                          <span
                            className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                              isSelected
                                ? "bg-[var(--gold)] text-[var(--navy)]"
                                : "bg-[var(--navy-card)] text-[var(--gold)]"
                            }`}
                          >
                            {source.id}
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium leading-snug text-white">
                              {source.title}
                            </p>
                            <p className="mt-0.5 truncate text-xs text-sky-400/80">
                              {source.url}
                            </p>
                            <p className="mt-1 text-xs italic leading-relaxed text-[var(--text-muted)]">
                              {source.snippet}
                            </p>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}

              {selectedSource !== null && !sourceMap.has(selectedSource) && (
                <p className="mt-3 rounded-lg border border-amber-800/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-300">
                  Citation [{selectedSource}] not found in the source list.
                </p>
              )}
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}
