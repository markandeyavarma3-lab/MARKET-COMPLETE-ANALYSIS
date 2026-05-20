"use client";
import React from "react";

interface Props {
  text: unknown;
  maxHeight?: number;
}

// Safely coerce ANY value to string (handles object/array/null from LLM JSON)
function toStr(v: unknown): string {
  if (typeof v === "string") return v;
  if (v == null) return "";
  if (Array.isArray(v)) return (v as unknown[]).map(toStr).join("\n");
  if (typeof v === "object") {
    // Try common keys like `analysis`, `summary`, `text`
    const obj = v as Record<string, unknown>;
    if (obj.analysis) return toStr(obj.analysis);
    if (obj.summary)  return toStr(obj.summary);
    if (obj.text)     return toStr(obj.text);
    return JSON.stringify(v, null, 2);
  }
  return String(v);
}

export default function MarkdownText({ text, maxHeight = 520 }: Props) {
  const safe = toStr(text);
  if (!safe.trim()) return null;

  const lines = safe.split("\n");
  const nodes: React.ReactNode[] = [];

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const trimmed = raw.trim();

    // H1-style: ALL CAPS line (LLM headers like "MARKET STRUCTURE")
    if (/^[A-Z][A-Z0-9 _\-]{3,}$/.test(trimmed) && trimmed.length < 60) {
      nodes.push(
        <div key={i} style={{ color: "var(--accent-cyan)", fontWeight: 700,
          marginTop: "0.75rem", marginBottom: "0.2rem", fontSize: "0.75rem",
          letterSpacing: "0.08em" }}>
          {trimmed}
        </div>
      );
      continue;
    }

    // Markdown H2/H3: ## or ###
    if (/^#{1,3}\s/.test(trimmed)) {
      const level = (trimmed.match(/^#+/) || [""])[0].length;
      const content = trimmed.replace(/^#+\s+/, "");
      nodes.push(
        <div key={i} style={{
          color: level === 1 ? "var(--accent-cyan)" : "var(--text-primary)",
          fontWeight: 700,
          marginTop: level === 1 ? "1rem" : "0.5rem",
          marginBottom: "0.2rem",
          fontSize: level === 1 ? "0.8rem" : "0.75rem",
          letterSpacing: "0.05em",
        }}>
          {content}
        </div>
      );
      continue;
    }

    // Bullet: - or * or +
    if (/^[-*+]\s/.test(trimmed)) {
      nodes.push(
        <div key={i} style={{ display: "flex", gap: "0.5rem",
          marginBottom: "0.15rem", paddingLeft: "0.5rem" }}>
          <span style={{ color: "var(--accent-cyan)", flexShrink: 0 }}>-</span>
          <span>{renderInline(trimmed.replace(/^[-*+]\s/, ""))}</span>
        </div>
      );
      continue;
    }

    // Horizontal rule
    if (/^[-=]{3,}$/.test(trimmed)) {
      nodes.push(<hr key={i} style={{ borderColor: "var(--border)", margin: "0.5rem 0" }} />);
      continue;
    }

    // Blank line -> spacing
    if (!trimmed) {
      nodes.push(<div key={i} style={{ height: "0.4rem" }} />);
      continue;
    }

    // Normal paragraph line
    nodes.push(
      <div key={i} style={{ marginBottom: "0.15rem" }}>
        {renderInline(trimmed)}
      </div>
    );
  }

  return (
    <div style={{
      overflowY: "auto",
      maxHeight: `${maxHeight}px`,
      fontSize: "0.75rem",
      lineHeight: 1.6,
      color: "var(--text-secondary)",
    }}>
      {nodes}
    </div>
  );
}

// Render inline bold (**text**) and coloured keywords
function renderInline(line: string): React.ReactNode {
  // Split on **bold** markers
  const parts: React.ReactNode[] = [];
  const re = /\*\*([^*]+)\*\*/g;
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;

  while ((m = re.exec(line)) !== null) {
    if (m.index > last) {
      parts.push(<span key={key++}>{colorize(line.slice(last, m.index))}</span>);
    }
    parts.push(
      <strong key={key++} style={{ color: "var(--text-primary)", fontWeight: 600 }}>
        {m[1]}
      </strong>
    );
    last = m.index + m[0].length;
  }
  if (last < line.length) {
    parts.push(<span key={key++}>{colorize(line.slice(last))}</span>);
  }
  return <>{parts}</>;
}

// Colorize known keywords in plain text spans
function colorize(s: string): React.ReactNode {
  const BULLISH = /\b(BULLISH|BUY|LONG|UPTREND|BREAKOUT|SUPPORT BUILD)\b/g;
  const BEARISH = /\b(BEARISH|SELL|SHORT|DOWNTREND|BREAKDOWN|RESISTANCE BUILD)\b/g;
  const NEUTRAL = /\b(NEUTRAL|SIDEWAYS|CONSOLIDAT\w*)\b/g;

  // Simple: split by known patterns and colour matches
  type Seg = { t: string; col?: string };
  const segs: Seg[] = [{ t: s }];

  function applyColor(pattern: RegExp, col: string) {
    const out: Seg[] = [];
    for (const seg of segs) {
      if (seg.col) { out.push(seg); continue; }
      const txt = seg.t;
      let last2 = 0;
      let m2: RegExpExecArray | null;
      pattern.lastIndex = 0;
      while ((m2 = pattern.exec(txt)) !== null) {
        if (m2.index > last2) out.push({ t: txt.slice(last2, m2.index) });
        out.push({ t: m2[0], col });
        last2 = m2.index + m2[0].length;
      }
      if (last2 < txt.length) out.push({ t: txt.slice(last2) });
    }
    segs.length = 0; segs.push(...out);
  }

  applyColor(BULLISH, "var(--accent-green)");
  applyColor(BEARISH, "var(--accent-red)");
  applyColor(NEUTRAL, "var(--accent-yellow)");

  if (segs.length === 1 && !segs[0].col) return s;

  return (
    <>
      {segs.map((seg, idx) =>
        seg.col
          ? <span key={idx} style={{ color: seg.col, fontWeight: 600 }}>{seg.t}</span>
          : <span key={idx}>{seg.t}</span>
      )}
    </>
  );
}
