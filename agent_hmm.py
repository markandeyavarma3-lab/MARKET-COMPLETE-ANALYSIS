"""
agent_hmm.py  --  HMM Regime Detection (pure numpy, no hmmlearn)
3-state Gaussian HMM on Nifty50 log returns via Baum-Welch EM.
States auto-labelled: BULL / SIDEWAYS / BEAR by mean return.
Saves hmm_regime_daily table + agents/hmm/last_report.json

Run: py D:\MICC\agent_hmm.py [--send]
"""
import sys, sqlite3, json
from pathlib import Path
from datetime import datetime

try:
    import numpy as np
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "numpy",
                    "--break-system-packages", "-q"])
    import numpy as np

DA      = Path(r"D:\MICC")
DB_PATH = r"D:\marketDB\db\market.db"
send    = "--send" in sys.argv

def log(msg): print(f"  {msg}", flush=True)

print("Agent HMM -- Regime Detection (pure numpy)")
print("=" * 45)

# ── Load Nifty50 returns ──────────────────────────────────────────────────
def load_returns():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    rows = conn.execute(
        "SELECT date, close FROM global_indices_daily"
        " WHERE symbol='NIFTY50' ORDER BY date ASC"
    ).fetchall()
    if not rows:
        rows = conn.execute(
            "SELECT date, closing_index_value FROM market_snapshot"
            " WHERE index_name='Nifty 50' ORDER BY date ASC"
        ).fetchall()
    conn.close()
    if len(rows) < 100:
        raise ValueError(f"Only {len(rows)} rows -- need 100+")
    dates  = [r[0] for r in rows]
    closes = np.array([float(r[1]) for r in rows])
    rets   = np.diff(np.log(closes))
    return dates[1:], rets

# ── Pure-numpy Gaussian HMM via Baum-Welch ────────────────────────────────
class GaussianHMM:
    """3-state Gaussian HMM, fits with EM (Baum-Welch)."""
    def __init__(self, n=3, n_iter=100, tol=1e-4, seed=42):
        self.n = n
        self.n_iter = n_iter
        self.tol = tol
        rng = np.random.default_rng(seed)
        # Init params
        self.pi  = np.ones(n) / n                    # start probs
        self.A   = rng.dirichlet(np.ones(n), size=n) # transition
        self.mu  = rng.normal(0, 0.01, n)            # means
        self.sig = np.full(n, 0.01)                  # stds

    def _emit(self, x):
        """Emission probabilities: (T, n)"""
        eps = 1e-300
        B = np.zeros((len(x), self.n))
        for k in range(self.n):
            s = max(self.sig[k], 1e-6)
            B[:, k] = (np.exp(-0.5 * ((x - self.mu[k]) / s) ** 2)
                       / (s * np.sqrt(2 * np.pi)) + eps)
        return B

    def _forward(self, B):
        T = len(B)
        alpha = np.zeros((T, self.n))
        alpha[0] = self.pi * B[0]
        scale = np.zeros(T)
        scale[0] = alpha[0].sum() or 1e-300
        alpha[0] /= scale[0]
        for t in range(1, T):
            alpha[t] = (alpha[t-1] @ self.A) * B[t]
            scale[t] = alpha[t].sum() or 1e-300
            alpha[t] /= scale[t]
        return alpha, scale

    def _backward(self, B, scale):
        T = len(B)
        beta = np.zeros((T, self.n))
        beta[-1] = 1.0
        for t in range(T-2, -1, -1):
            beta[t] = (self.A @ (B[t+1] * beta[t+1])) / scale[t+1]
        return beta

    def fit(self, x):
        prev_ll = -np.inf
        for it in range(self.n_iter):
            B = self._emit(x)
            alpha, scale = self._forward(B)
            beta  = self._backward(B, scale)
            gamma = alpha * beta
            gamma /= gamma.sum(axis=1, keepdims=True) + 1e-300
            # xi: (T-1, n, n)
            T = len(x)
            xi = np.zeros((T-1, self.n, self.n))
            for t in range(T-1):
                xi[t] = (alpha[t:t+1].T * self.A
                         * (B[t+1] * beta[t+1]))
                xi[t] /= xi[t].sum() + 1e-300
            # Update
            self.pi = gamma[0] / gamma[0].sum()
            self.A  = xi.sum(0) / (xi.sum(0).sum(1, keepdims=True) + 1e-300)
            self.mu  = (gamma * x[:,None]).sum(0) / (gamma.sum(0) + 1e-300)
            var = (gamma * (x[:,None] - self.mu)**2).sum(0) / (gamma.sum(0) + 1e-300)
            self.sig = np.sqrt(var) + 1e-6
            ll = np.log(scale + 1e-300).sum()
            if abs(ll - prev_ll) < self.tol:
                log(f"  Converged at iter {it+1}  LL={ll:.2f}")
                break
            prev_ll = ll
        self._gamma = gamma
        return self

    def predict(self, x):
        B = self._emit(x)
        alpha, scale = self._forward(B)
        beta = self._backward(B, scale)
        gamma = alpha * beta
        gamma /= gamma.sum(axis=1, keepdims=True) + 1e-300
        return gamma.argmax(axis=1), gamma

# ── Fit + label ───────────────────────────────────────────────────────────
try:
    dates, rets = load_returns()
    log(f"Loaded {len(rets)} Nifty returns ({dates[0]} to {dates[-1]})")

    model = GaussianHMM(n=3, n_iter=200, tol=1e-5)
    model.fit(rets)

    # Assign labels: sort states by mean return
    order = np.argsort(model.mu)   # [lowest_mean, mid, highest_mean]
    label_map = {int(order[0]): "BEAR", int(order[1]): "SIDEWAYS", int(order[2]): "BULL"}

    state_seq, gamma = model.predict(rets)
    labels = [label_map[int(s)] for s in state_seq]

    for i in range(3):
        k    = int(order[i])
        name = label_map[k]
        mask = state_seq == k
        log(f"  {name:<10} mu={model.mu[k]*100:+.3f}%  sig={model.sig[k]*100:.3f}%  days={mask.sum()}")

    current_state = int(state_seq[-1])
    current_regime = label_map[current_state]
    current_probs  = gamma[-1]
    bull_p = float(current_probs[int(order[2])])
    side_p = float(current_probs[int(order[1])])
    bear_p = float(current_probs[int(order[0])])
    confidence = float(current_probs.max())

    log(f"")
    log(f"CURRENT: {current_regime}  (conf={confidence:.1%})")
    log(f"  Bull={bull_p:.1%}  Side={side_p:.1%}  Bear={bear_p:.1%}")

    # ── Save to DB ────────────────────────────────────────────────────────
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS hmm_regime_daily"
        " (date TEXT PRIMARY KEY, regime TEXT,"
        "  bull_prob REAL, bear_prob REAL, sideways_prob REAL, updated_at TEXT)"
    )
    now_ts = datetime.now().isoformat()
    batch = []
    for i, (date, label) in enumerate(zip(dates, labels)):
        g = gamma[i]
        batch.append((
            date, label,
            round(float(g[int(order[2])]), 4),
            round(float(g[int(order[0])]), 4),
            round(float(g[int(order[1])]), 4),
            now_ts
        ))
    conn.executemany(
        "INSERT OR REPLACE INTO hmm_regime_daily"
        " (date,regime,bull_prob,bear_prob,sideways_prob,updated_at)"
        " VALUES (?,?,?,?,?,?)", batch)
    conn.commit()
    conn.close()
    log(f"Saved {len(batch)} rows to hmm_regime_daily")

    # ── Save JSON ─────────────────────────────────────────────────────────
    out_dir = DA / "agents" / "hmm"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "agent": "hmm", "date": datetime.now().strftime("%Y-%m-%d"),
        "current_regime": current_regime, "confidence": round(confidence, 4),
        "bull_prob": round(bull_p, 4), "sideways_prob": round(side_p, 4),
        "bear_prob": round(bear_p, 4), "last_date": dates[-1], "n_days": len(dates),
    }
    (out_dir / "last_report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print()
    print(f"Current regime: {current_regime} ({confidence:.0%} confidence)")
    print(f"Bull={bull_p:.0%}  Sideways={side_p:.0%}  Bear={bear_p:.0%}")

    if send:
        import re, urllib.request
        env  = (DA / ".env").read_text()
        BOT  = re.search(r"TELEGRAM_TOKEN=([^\n]+)", env).group(1).strip()
        CHAT = re.search(r"TELEGRAM_CHAT_ID=([^\n]+)", env).group(1).strip()
        ico  = {"BULL":"UP","BEAR":"DN","SIDEWAYS":"--"}[current_regime]
        msg  = (f"HMM Regime\n{ico} {current_regime} ({confidence:.0%})\n"
                f"Bull={bull_p:.0%} Side={side_p:.0%} Bear={bear_p:.0%}")
        data = json.dumps({"chat_id":CHAT,"text":msg}).encode()
        urllib.request.urlopen(
            urllib.request.Request(
                f"https://api.telegram.org/bot{BOT}/sendMessage",
                data=data, headers={"Content-Type":"application/json"}
            ), timeout=10)
        print("  Telegram: OK")

except Exception as e:
    print(f"HMM failed: {e}")
    import traceback; traceback.print_exc()