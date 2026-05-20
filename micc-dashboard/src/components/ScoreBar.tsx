import { scoreColor } from "@/lib/utils";

export default function ScoreBar({ score, max = 10 }: { score: number; max?: number }) {
  const pct   = Math.min((score / max) * 100, 100);
  const color = scoreColor(score);
  return (
    <div className="sbar-wrap">
      <div className="sbar-bg">
        <div className="sbar-fill" style={{ width: pct + "%", background: color }} />
      </div>
      <span style={{ fontFamily: "monospace", fontSize: 11, color: color, minWidth: 24 }}>
        {Number(score).toFixed(1)}
      </span>
    </div>
  );
}
