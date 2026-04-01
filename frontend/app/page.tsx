"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Reveal from "reveal.js";

type Source = {
  id: number;
  title: string;
  url: string;
  snippet: string;
};

type Slide = {
  slide_number: number;
  title: string;
  subtitle: string;
  bullets: string[];
  key_stat: string;
  source_ids: number[];
};

type ApiResponse = {
  company: string;
  generated_at: string;
  slides: Slide[];
  sources: Source[];
  pptx_url: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [company, setCompany] = useState("");
  const [loading, setLoading] = useState(false);
  const [status1, setStatus1] = useState("idle");
  const [status2, setStatus2] = useState("idle");
  const [error, setError] = useState("");
  const [result, setResult] = useState<ApiResponse | null>(null);
  const [selectedSource, setSelectedSource] = useState<number | null>(null);
  const revealRootRef = useRef<HTMLDivElement>(null);
  const revealInstanceRef = useRef<any>(null);
  const previewContainerRef = useRef<HTMLDivElement>(null);

  const sourceMap = useMemo(() => {
    const map = new Map<number, Source>();
    (result?.sources || []).forEach((source) => map.set(source.id, source));
    return map;
  }, [result?.sources]);

  useEffect(() => {
    if (!result || !revealRootRef.current) return;
    if (revealInstanceRef.current) {
      revealInstanceRef.current.destroy();
      revealInstanceRef.current = null;
    }
    const deck = new Reveal(revealRootRef.current, {
      embedded: true,
      controls: true,
      progress: true,
      center: false,
      hash: false,
      transition: "slide",
    });
    deck.initialize();
    revealInstanceRef.current = deck;
  }, [result]);

  const runResearch = async () => {
    if (!company.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);
    setSelectedSource(null);
    setStatus1("running");
    setStatus2("pending");

    try {
      const response = await fetch(`${API_URL}/api/research`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company: company.trim() }),
      });
      setStatus1("done");
      setStatus2("running");

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "Failed to generate report.");
      }

      const payload = (await response.json()) as ApiResponse;
      setResult(payload);
      setStatus2("done");
    } catch (err) {
      setStatus1("error");
      setStatus2("error");
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const toggleFullscreen = async () => {
    const node = previewContainerRef.current;
    if (!node) return;
    if (!document.fullscreenElement) {
      await node.requestFullscreen();
      return;
    }
    await document.exitFullscreen();
  };

  return (
    <main className="min-h-screen bg-[#0f172a] px-6 py-8 text-white">
      <h1 className="text-3xl font-bold">PE Due Diligence AI Agent</h1>
      <p className="mt-2 text-sm text-slate-300">Backend API: {API_URL}</p>

      <div className="mt-6 flex gap-3">
        <input
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          placeholder="Enter company name..."
          className="w-full max-w-xl rounded-md border border-slate-600 bg-slate-900 px-4 py-2"
        />
        <button
          onClick={runResearch}
          disabled={loading}
          className="rounded-md bg-amber-500 px-4 py-2 font-semibold text-black disabled:opacity-60"
        >
          {loading ? "Running..." : "Run"}
        </button>
      </div>

      <div className="mt-4 text-sm">
        <p>Agent 1 (Researcher): {status1}</p>
        <p>Agent 2 (PPT Maker): {status2}</p>
        {error ? <p className="mt-1 text-red-300">{error}</p> : null}
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div
          ref={previewContainerRef}
          className="rounded-md border border-slate-700 bg-black p-3"
        >
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm text-slate-300">Reveal.js preview</p>
            <div className="flex gap-2">
              <button
                onClick={toggleFullscreen}
                className="rounded border border-slate-500 px-3 py-1 text-xs"
              >
                Fullscreen
              </button>
              {result?.pptx_url ? (
                <a
                  href={result.pptx_url}
                  target="_blank"
                  className="rounded bg-emerald-500 px-3 py-1 text-xs font-semibold text-black"
                  rel="noreferrer"
                >
                  Download .pptx
                </a>
              ) : null}
            </div>
          </div>

          <div className="reveal" ref={revealRootRef}>
            <div className="slides">
              {(result?.slides || []).map((slide) => (
                <section key={slide.slide_number}>
                  <h3>{slide.title}</h3>
                  <h5>{slide.subtitle}</h5>
                  <ul>
                    {slide.bullets.map((bullet, idx) => (
                      <li key={`${slide.slide_number}-${idx}`}>{bullet}</li>
                    ))}
                  </ul>
                  <p>
                    <strong>{slide.key_stat}</strong>
                  </p>
                  <p>
                    Sources:{" "}
                    {slide.source_ids.map((id) => (
                      <button
                        key={`${slide.slide_number}-${id}`}
                        onClick={() => setSelectedSource(id)}
                        className="mx-1 rounded bg-slate-700 px-2 py-0.5 text-xs"
                      >
                        [{id}]
                      </button>
                    ))}
                  </p>
                </section>
              ))}
            </div>
          </div>
        </div>

        <aside className="rounded-md border border-slate-700 bg-slate-900 p-4">
          <h2 className="mb-3 text-lg font-semibold">Sources</h2>
          <div className="space-y-3 text-sm">
            {(result?.sources || []).map((source) => (
              <div
                key={source.id}
                className={`rounded border p-2 ${
                  selectedSource === source.id
                    ? "border-amber-400 bg-slate-800"
                    : "border-slate-700"
                }`}
              >
                <p className="font-medium">
                  [{source.id}] {source.title}
                </p>
                <a
                  className="break-all text-sky-300"
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {source.url}
                </a>
                <p className="mt-1 text-slate-300">{source.snippet}</p>
              </div>
            ))}
          </div>
          {selectedSource !== null && !sourceMap.has(selectedSource) ? (
            <p className="mt-3 text-xs text-amber-300">
              Selected citation [{selectedSource}] not found in source list.
            </p>
          ) : null}
        </aside>
      </div>
    </main>
  );
}
