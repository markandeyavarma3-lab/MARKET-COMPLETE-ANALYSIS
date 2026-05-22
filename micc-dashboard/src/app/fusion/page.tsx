"use client";
import NavBar from "@/components/NavBar";
import { useEffect, useState } from "react";

interface Pick {
  symbol: string; n_layers: number; layers_fired: string[];
  reasons: string[]; beta_score: number; regime_score: number;
  insider_score: number; watchlist_score: number;
  seasonal_score: number; conviction_score: number; quant_score: number;
}
interface FusionData {
  picks: Pick[]; date?: string; generated_at?: string;
  meta?: { regime: string; nifty: number; total_picks: number;
           bull_prob?: number; bear_prob?: number; agents_run?: number };
}

const LAYER_DEFS: { key: keyof Pick; label: string; color: string; desc: string }[] = [
  { key: "beta_score",       label: "BETA",       color: "var(--accent)", desc: "Momentum screens" },
  { key: "regime_score",     label: "REGIME",     color: "var(--info)",   desc: "Macro/Alpha signals" },
  { key: "insider_score",    label: "INSIDER",    color: "var(--warn)",   desc: "Corporate events/insider" },
  { key: "watchlist_score",  label: "WATCHLIST",  color: "#a78bfa",       desc: "Manual watchlist" },
  { key: "seasonal_score",   label: "SEASONAL",   color: "var(--bull)",   desc: "Engine seasonality" },
  { key: "conviction_score", label: "CONVICTION", color: "#f472b6",       desc: "FII/DII flows" },
  { key: "quant_score",      label: "QUANT",      color: "#34d399",       desc: "Options/GEX/Global" },
];

function regimeColor(r: string) {
  if (!r) return "var(--dim)";
  r = r.toUpperCase();
  if (r === "BULL" || r === "BULLISH") return "var(--bull)";
  if (r === "BEAR" || r === "BEARISH") return "var(--bear)";
  return "var(--warn)";
}

function LayerBar({ score, color, label }: { score: number; color: string; label: string }) {
  const pct = Math.round(score * 100);
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
        <span style={{ fontSize: 9, color: "var(--dim)", letterSpacing: 1 }}>{label}</span>
        <span style={{ fontSize: 9, color: score > 0 ? color : "var(--muted)" }}>
          {score > 0 ? "HIT" : "miss"}
        </span>
      </div>
      <div style={{ height: 4, background: "var(--bg)", borderRadius: 2 }}>
        <div style={{ height: "100%", width: pct + "%", background: color,
          borderRadius: 2, transition: "width 0.3s ease" }} />
      </div>
    </div>
  );
}

function PickCard({ p, expanded, onToggle }: {
  p: Pick; expanded: boolean; onToggle: () => void;
}) {
  const S: Record<string, React.CSSProperties> = {
    card:  { background: "var(--surface)", border: "1px solid var(--border)",
             borderRadius: 8, marginBottom: 8, overflow: "hidden" },
    header:{ display: "flex", alignItems: "center", gap: 12, padding: "10px 16px",
             cursor: "pointer", userSelect: "none" },
    sym:   { fontSize: 14, fontWeight: 700, color: "var(--accent)", width: 120 },
    badge: { fontSize: 10, padding: "2px 8px", borderRadius: 3,
             background: "var(--accent)22", color: "var(--accent)" },
    layers:{ display: "flex", gap: 4, flex: 1, flexWrap: "wrap" as const },
    ltag:  { fontSize: 9, padding: "2px 6px", borderRadius: 3,
             background: "var(--bg)", border: "1px solid var(--border)", color: "var(--dim)" },
    body:  { padding: "0 16px 16px", borderTop: "1px solid var(--border)" },
    grid:  { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 24px", marginTop: 12 },
    reas:  { marginTop: 12 },
    rtitle:{ fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 6 },
    ritem: { fontSize: 11, color: "var(--text)", lineHeight: 1.7,
             borderBottom: "1px solid var(--border)", paddingBottom: 3, marginBottom: 3 },
  };
  return (
    <div style={S.card}>
      <div style={S.header} onClick={onToggle}>
        <span style={S.sym}>{p.symbol}</span>
        <span style={S.badge}>{p.n_layers}L</span>
        <div style={S.layers}>
          {p.layers_fired.map(l => (
            <span key={l} style={S.ltag}>{l.slice(0, 3).toUpperCase()}</span>
          ))}
        </div>
        <span style={{ fontSize: 12, color: "var(--dim)" }}>{expanded ? "[-]" : "[+]"}</span>
      </div>
      {expanded && (
        <div style={S.body}>
          <div style={S.grid}>
            <div>
              <div style={{ fontSize: 10, color: "var(--dim)", letterSpacing: 1, marginBottom: 8, marginTop: 12 }}>
                LAYER SCORES
              </div>
              {LAYER_DEFS.map(l => (
                <LayerBar key={l.key} score={Number(p[l.key]) || 0}
                  color={l.color} label={l.label} />
              ))}
            </div>
            <div>
              <div style={S.reas}>
                <div style={S.rtitle}>SIGNAL REASONS</div>
                {p.reasons.map((r, i) => (
                  <div key={i} style={S.ritem}>{r}</div>
                ))}
                {p.reasons.length === 0 && (
                  <div style={{ color: "var(--muted)", fontSize: 11 }}>No reasons logged</div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function FusionPage() {
  const [data, setData]     = useState<FusionData | null>(null);
  const [loading, setL]     = useState(true);
  const [error, setE]       = useState("");
  const [search, setSrch]   = useState("");
  const [minL, setMinL]     = useState(2);
  const [expanded, setExp]  = useState<Set<string>>(new Set());
  const [expandAll, setAll] = useState(false);

  useEffect(() => {
    fetch("/api/fusion")
      .then(r => r.json())
      .then(d => { setData(d); setL(false); })
      .catch(e => { setE(e.message); setL(false); });
  }, []);

  const S: Record<string, React.CSSProperties> = {
    page:  { minHeight: "100vh", background: "var(--bg)", fontFamily: "JetBrains Mono, monospace" },
    sub:   { position: "sticky", top: 48, zIndex: 90, background: "var(--surface)",
             borderBottom: "1px solid var(--border)", padding: "6px 20px",
             display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" as const },
    stitle:{ fontSize: 10, color: "var(--dim)", letterSpacing: 2 },
    wrap:  { maxWidth: 1400, margin: "0 auto", padding: "16px 20px" },
    kv:    { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6,
             padding: "10px 16px", display: "inline-block", marginRight: 10, marginBottom: 12 },
    kvk:   { fontSize: 10, color: "var(--dim)", letterSpacing: 1 },
    kvv:   { fontSize: 18, fontWeight: 700, marginTop: 2 },
    input: { background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 4,
             padding: "4px 10px", fontSize: 11, color: "var(--text)", outline: "none" },
    btn:   (active: boolean): React.CSSProperties => ({
      padding: "4px 12px", fontSize: 10, letterSpacing: 1, cursor: "pointer",
      border: "1px solid " + (active ? "var(--accent)" : "var(--border)"),
      borderRadius: 4, background: active ? "var(--accent)22" : "transparent",
      color: active ? "var(--accent)" : "var(--dim)",
    }),
  };

  const picks = (data?.picks || [])
    .filter(p => p.n_layers >= minL)
    .filter(p => !search || p.symbol.toLowerCase().includes(search.toLowerCase()));

  const regime = data?.meta?.regime || "--";
  const nifty  = data?.meta?.nifty;
  const bullP  = data?.meta?.bull_prob;
  const bearP  = data?.meta?.bear_prob;

  function toggleAll() {
    if (expandAll) {
      setExp(new Set());
      setAll(false);
    } else {
      setExp(new Set(picks.map(p => p.symbol)));
      setAll(true);
    }
  }

  function toggleOne(sym: string) {
    setExp(prev => {
      const next = new Set(prev);
      if (next.has(sym)) next.delete(sym);
      else next.add(sym);
      return next;
    });
  }

  return (
    <div style={S.page}>
      <NavBar />
      <div style={S.sub}>
        <span style={S.stitle}>FUSION  /  MULTI-LAYER SIGNAL PICKS</span>
        <input style={S.input} placeholder="search symbol..."
          value={search} onChange={e => setSrch(e.target.value)} />
        {[2,3,4,5].map(n => (
          <button key={n} style={S.btn(minL === n)} onClick={() => setMinL(n)}>
            {n}L+
          </button>
        ))}
        <button style={S.btn(expandAll)} onClick={toggleAll}>
          {expandAll ? "COLLAPSE ALL" : "EXPAND ALL"}
        </button>
        {data?.generated_at && (
          <span style={{ fontSize: 10, color: "var(--dim)", marginLeft: "auto" }}>
            {data.generated_at}
          </span>
        )}
      </div>

      <div style={S.wrap}>
        {loading && <div style={{ color: "var(--dim)", padding: 40, textAlign: "center" }}>Loading fusion picks...</div>}
        {error   && <div style={{ color: "var(--bear)", padding: 20 }}>Error: {error}</div>}

        {data && <>
          {/* Regime + stats banner */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 20 }}>
            <div style={S.kv}>
              <div style={S.kvk}>REGIME (HMM)</div>
              <div style={{ ...S.kvv, color: regimeColor(regime) }}>{regime}</div>
            </div>
            {nifty != null && <div style={S.kv}>
              <div style={S.kvk}>NIFTY 50</div>
              <div style={S.kvv}>{Number(nifty).toLocaleString("en-IN")}</div>
            </div>}
            {bullP != null && <div style={S.kv}>
              <div style={S.kvk}>BULL PROB</div>
              <div style={{ ...S.kvv, color: "var(--bull)" }}>{(bullP * 100).toFixed(0)}%</div>
            </div>}
            {bearP != null && <div style={S.kv}>
              <div style={S.kvk}>BEAR PROB</div>
              <div style={{ ...S.kvv, color: "var(--bear)" }}>{(bearP * 100).toFixed(0)}%</div>
            </div>}
            <div style={S.kv}>
              <div style={S.kvk}>PICKS ({minL}L+)</div>
              <div style={S.kvv}>{picks.length}</div>
            </div>
          </div>

          {/* Layer legend */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
            {LAYER_DEFS.map(l => (
              <span key={l.key} style={{ fontSize: 9, padding: "2px 8px", borderRadius: 3,
                border: "1px solid " + l.color + "44", color: l.color }}>
                {l.label}  {l.desc}
              </span>
            ))}
          </div>

          {/* Picks */}
          {picks.length === 0 && (
            <div style={{ color: "var(--dim)", padding: 40, textAlign: "center" }}>
              No picks for {minL}L+ filter. Try 2L+.
            </div>
          )}
          {picks.map(p => (
            <PickCard key={p.symbol} p={p}
              expanded={expanded.has(p.symbol)}
              onToggle={() => toggleOne(p.symbol)} />
          ))}
        </>}
      </div>
    </div>
  );
}