"use client";

const DURATIONS = [
  { label: "1D",  days: 1  },
  { label: "3D",  days: 3  },
  { label: "5D",  days: 5  },
  { label: "7D",  days: 7  },
  { label: "10D", days: 10 },
  { label: "14D", days: 14 },
  { label: "20D", days: 20 },
  { label: "1M",  days: 22 },
  { label: "2M",  days: 44 },
  { label: "3M",  days: 66 },
  { label: "6M",  days: 132 },
];

export default function DurationBar({
  value,
  onChange,
}: {
  value: number;
  onChange: (days: number) => void;
}) {
  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {DURATIONS.map((d) => (
        <button
          key={d.days}
          onClick={() => onChange(d.days)}
          style={{
            padding: "3px 9px",
            borderRadius: 4,
            border: "1px solid",
            borderColor: value === d.days ? "var(--accent)" : "var(--border2)",
            background: value === d.days ? "rgba(88,166,255,.15)" : "var(--surface)",
            color: value === d.days ? "var(--accent)" : "var(--muted)",
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            fontWeight: value === d.days ? 700 : 400,
            cursor: "pointer",
            transition: "all .15s",
          }}
        >
          {d.label}
        </button>
      ))}
    </div>
  );
}
