"use client";

import { useState, useEffect, useRef, useCallback } from "react";

export interface SearchResult {
  symbol: string;
  name: string;
  type: "stock" | "index" | "global";
}

interface Props {
  value?: string;
  onSelect: (symbol: string, result?: SearchResult) => void;
  placeholder?: string;
  disabled?: boolean;
  autoFocus?: boolean;
  width?: number | string;
  clearAfterSelect?: boolean;
}

const TYPE_COLORS: Record<string, string> = {
  stock:  "#60a5fa",
  index:  "#34d399",
  global: "#fbbf24",
};

const TYPE_LABELS: Record<string, string> = {
  stock:  "NSE",
  index:  "INDEX",
  global: "GLOBAL",
};

export default function SymbolSearch({
  value = "",
  onSelect,
  placeholder = "Search symbol or company name...",
  disabled = false,
  autoFocus = false,
  width = "100%",
  clearAfterSelect = false,
}: Props) {
  const [query,   setQuery]   = useState(value);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open,    setOpen]    = useState(false);
  const [idx,     setIdx]     = useState(-1);
  const [loading, setLoading] = useState(false);
  const ref   = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync external value
  useEffect(() => { setQuery(value); }, [value]);

  // Click outside to close
  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  // Debounced search
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    if (!query.trim() || query.length < 1) {
      setResults([]); setOpen(false); return;
    }
    setLoading(true);
    timer.current = setTimeout(async () => {
      try {
        const r = await fetch(
          "/api/search?q=" + encodeURIComponent(query) + "&limit=12"
        );
        const d = await r.json();
        const res = (d.results || []) as SearchResult[];
        setResults(res);
        setOpen(res.length > 0);
        setIdx(-1);
      } catch {}
      setLoading(false);
    }, 180);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [query]);

  const pick = useCallback((result: SearchResult) => {
    onSelect(result.symbol, result);
    if (clearAfterSelect) {
      setQuery("");
    } else {
      setQuery(result.symbol);
    }
    setResults([]); setOpen(false); setIdx(-1);
  }, [onSelect, clearAfterSelect]);

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault(); setIdx(i => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault(); setIdx(i => Math.max(i - 1, -1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (idx >= 0 && results[idx]) {
        pick(results[idx]);
      } else if (query.trim()) {
        onSelect(query.trim().toUpperCase());
        if (clearAfterSelect) setQuery("");
        setOpen(false);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div ref={ref} style={{ position: "relative", width }}>
      <div style={{ position: "relative" }}>
        <input
          value={query}
          onChange={e => setQuery(e.target.value.toUpperCase())}
          onKeyDown={onKey}
          onFocus={() => results.length && setOpen(true)}
          placeholder={placeholder}
          disabled={disabled}
          autoFocus={autoFocus}
          autoComplete="off"
          spellCheck={false}
          style={{
            width: "100%",
            padding: "9px 36px 9px 14px",
            background: "#1e293b",
            border: "1px solid " + (open ? "#3b82f6" : "#334155"),
            borderRadius: 8,
            color: "#f8fafc",
            fontSize: 13,
            outline: "none",
            boxSizing: "border-box",
            opacity: disabled ? 0.45 : 1,
            transition: "border-color 0.15s",
          }}
        />
        {/* Search icon / spinner */}
        <div style={{
          position: "absolute", right: 10, top: "50%",
          transform: "translateY(-50%)",
          color: "#475569", fontSize: 14, pointerEvents: "none",
        }}>
          {loading ? "..." : "⌕"}
        </div>
      </div>

      {/* Dropdown */}
      {open && results.length > 0 && (
        <div style={{
          position: "absolute", top: "calc(100% + 4px)",
          left: 0, right: 0, zIndex: 9999,
          background: "#1e293b",
          border: "1px solid #334155",
          borderRadius: 8,
          boxShadow: "0 12px 40px rgba(0,0,0,0.7)",
          overflow: "hidden",
          maxHeight: 320,
          overflowY: "auto",
        }}>
          {results.map((r, i) => (
            <div
              key={r.symbol}
              onMouseDown={e => { e.preventDefault(); pick(r); }}
              onMouseEnter={() => setIdx(i)}
              style={{
                padding: "9px 14px",
                cursor: "pointer",
                background: i === idx ? "#334155" : "transparent",
                display: "flex",
                alignItems: "center",
                gap: 10,
                borderBottom: i < results.length - 1 ? "1px solid #0f172a" : "none",
                transition: "background 0.1s",
              }}
            >
              <span style={{
                fontFamily: "monospace",
                fontWeight: 700,
                fontSize: 13,
                color: TYPE_COLORS[r.type] || "#f8fafc",
                minWidth: 110,
              }}>
                {r.symbol}
              </span>
              {r.name && r.name !== r.symbol && (
                <span style={{
                  fontSize: 11,
                  color: "#64748b",
                  flex: 1,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}>
                  {r.name}
                </span>
              )}
              <span style={{
                fontSize: 9,
                fontWeight: 700,
                padding: "1px 6px",
                borderRadius: 4,
                color: TYPE_COLORS[r.type] || "#94a3b8",
                background: (TYPE_COLORS[r.type] || "#94a3b8") + "22",
                flexShrink: 0,
              }}>
                {TYPE_LABELS[r.type] || r.type}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
