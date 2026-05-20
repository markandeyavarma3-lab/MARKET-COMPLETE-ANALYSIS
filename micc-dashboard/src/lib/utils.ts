export function fmtNum(n: any, d = 2): string {
  if (n == null || isNaN(Number(n))) return "--";
  return Number(n).toLocaleString("en-IN", {
    maximumFractionDigits: d,
    minimumFractionDigits: d,
  });
}

export function fmtPct(n: any, d = 2): string {
  if (n == null || isNaN(Number(n))) return "--";
  const v = Number(n);
  return (v >= 0 ? "+" : "") + v.toFixed(d) + "%";
}

export function fmtCr(n: any): string {
  if (n == null || isNaN(Number(n))) return "--";
  const v = Number(n);
  const abs = Math.abs(v);
  const sign = v >= 0 ? "+" : "-";
  if (abs >= 100000) return sign + "Rs." + (abs / 100000).toFixed(1) + "L Cr";
  if (abs >= 1000)   return sign + "Rs." + (abs / 1000).toFixed(1) + "K Cr";
  return sign + "Rs." + abs.toFixed(0) + " Cr";
}

export function colorPct(n: any): string {
  if (n == null || isNaN(Number(n))) return "var(--muted)";
  return Number(n) >= 0 ? "var(--pos)" : "var(--neg)";
}

export function colorCr(n: any): string {
  return colorPct(n);
}

export function regimeCls(regime: string): string {
  const r = (regime || "").toUpperCase();
  if (r.includes("BULL") || r.includes("INSTITUTIONAL") || r.includes("TRENDING")) return "pill-bull";
  if (r.includes("RISK") || r.includes("BEAR") || r.includes("DIST")) return "pill-bear";
  if (r.includes("CONSOL") || r.includes("CAUTION") || r.includes("FEAR")) return "pill-warn";
  return "pill-neut";
}

export function scoreColor(s: number): string {
  if (s >= 8) return "var(--pos)";
  if (s >= 5) return "var(--accent)";
  if (s >= 3) return "var(--warn)";
  return "var(--neg)";
}
