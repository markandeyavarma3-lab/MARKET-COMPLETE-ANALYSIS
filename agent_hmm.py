"""
agent_hmm.py  --  Hidden Markov Model regime detection
3 states: BULL / SIDEWAYS / BEAR
Fits on Nifty50 daily returns, saves to hmm_regime_daily table.
Usage: py agent_hmm.py [--send]
"""
import sys, sqlite3, json
from pathlib import Path
from datetime import datetime

DA      = Path(r'D:\MICC')
DB_PATH = r'D:\marketDB\db\market.db'
send    = '--send' in sys.argv

def log(msg): print(f'  {msg}', flush=True)

# ── Install hmmlearn if needed ────────────────────────────────────────────
try:
    from hmmlearn.hmm import GaussianHMM
    import numpy as np
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install',
                    'hmmlearn', 'numpy', '--break-system-packages', '-q'])
    from hmmlearn.hmm import GaussianHMM
    import numpy as np

print('Agent HMM -- Regime Detection')
print('=' * 40)

# ── Load Nifty50 returns from parquet or DB ───────────────────────────────
def load_nifty_returns():
    log('Loading Nifty50 data...')
    conn = sqlite3.connect(DB_PATH, timeout=15)
    # Try global_indices_daily first
    rows = conn.execute(
        'SELECT date, close FROM global_indices_daily'
        ' WHERE symbol="NIFTY50" ORDER BY date ASC'
    ).fetchall()
    if not rows:
        # Fallback: market_snapshot
        rows = conn.execute(
            'SELECT date, closing_index_value FROM market_snapshot'
            ' WHERE index_name="Nifty 50" ORDER BY date ASC'
        ).fetchall()
    conn.close()
    if len(rows) < 100:
        raise ValueError(f'Not enough data: {len(rows)} rows')
    dates  = [r[0] for r in rows]
    closes = np.array([float(r[1]) for r in rows])
    returns = np.diff(np.log(closes))  # log returns
    dates   = dates[1:]
    log(f'Loaded {len(returns)} returns ({dates[0]} to {dates[-1]})')
    return dates, returns

# ── Fit HMM ──────────────────────────────────────────────────────────────
def fit_hmm(returns, n_states=3):
    log(f'Fitting {n_states}-state Gaussian HMM...')
    X = returns.reshape(-1, 1)
    model = GaussianHMM(
        n_components=n_states,
        covariance_type='full',
        n_iter=200,
        random_state=42
    )
    model.fit(X)
    states = model.predict(X)
    # Assign state labels: highest mean return = BULL, lowest = BEAR
    means = model.means_.flatten()
    order = np.argsort(means)  # [lowest, mid, highest]
    label_map = {
        order[0]: 'BEAR',
        order[1]: 'SIDEWAYS',
        order[2]: 'BULL',
    }
    labels = [label_map[s] for s in states]
    # State stats
    for i, state_num in enumerate(order):
        mask = states == state_num
        name = label_map[state_num]
        mu   = means[state_num] * 100
        sig  = np.sqrt(model.covars_[state_num][0][0]) * 100
        days = mask.sum()
        log(f'  {name:<10} mean={mu:+.3f}%  vol={sig:.3f}%  days={days}')
    return model, states, labels, label_map, means

# ── Get current state probabilities ──────────────────────────────────────
def get_current_state(model, returns):
    X = returns.reshape(-1, 1)
    probs = model.predict_proba(X)
    # Last observation probabilities
    last_probs = probs[-1]
    current_state = np.argmax(last_probs)
    confidence = float(last_probs[current_state])
    return current_state, confidence, last_probs

# ── Save to DB ────────────────────────────────────────────────────────────
def save_to_db(dates, labels, means, model, returns, label_map):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute(
        'CREATE TABLE IF NOT EXISTS hmm_regime_daily ('
        '  date TEXT PRIMARY KEY,'
        '  regime TEXT,'
        '  bull_prob REAL,'
        '  bear_prob REAL,'
        '  sideways_prob REAL,'
        '  updated_at TEXT'
        ')'
    )
    X     = returns.reshape(-1, 1)
    probs = model.predict_proba(X)
    # Map state indices to regime labels
    order = np.argsort(means)
    bear_idx     = int(order[0])
    side_idx     = int(order[1])
    bull_idx     = int(order[2])
    now = datetime.now().isoformat()
    batch = []
    for i, (date, label) in enumerate(zip(dates, labels)):
        batch.append((
            date, label,
            round(float(probs[i][bull_idx]), 4),
            round(float(probs[i][bear_idx]), 4),
            round(float(probs[i][side_idx]), 4),
            now
        ))
    conn.executemany(
        'INSERT OR REPLACE INTO hmm_regime_daily'
        ' (date,regime,bull_prob,bear_prob,sideways_prob,updated_at)'
        ' VALUES (?,?,?,?,?,?)',
        batch
    )
    conn.commit()
    conn.close()
    log(f'Saved {len(batch)} rows to hmm_regime_daily')

# ── Main ─────────────────────────────────────────────────────────────────
try:
    dates, returns = load_nifty_returns()
    model, states, labels, label_map, means = fit_hmm(returns)
    curr_state, confidence, last_probs = get_current_state(model, returns)
    order = np.argsort(means)
    current_regime = label_map[curr_state]
    log(f'')
    log(f'CURRENT REGIME: {current_regime}  (confidence={confidence:.1%})')
    log(f'  Bull prob:     {float(last_probs[order[2]]):.1%}')
    log(f'  Sideways prob: {float(last_probs[order[1]]):.1%}')
    log(f'  Bear prob:     {float(last_probs[order[0]]):.1%}')
    save_to_db(dates, labels, means, model, returns, label_map)
    # Save summary JSON
    out_dir = DA / 'agents' / 'hmm'
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        'agent':          'hmm',
        'date':           datetime.now().strftime('%Y-%m-%d'),
        'current_regime': current_regime,
        'confidence':     round(confidence, 4),
        'bull_prob':      round(float(last_probs[order[2]]), 4),
        'sideways_prob':  round(float(last_probs[order[1]]), 4),
        'bear_prob':      round(float(last_probs[order[0]]), 4),
        'last_date':      dates[-1],
        'n_days':         len(dates),
    }
    (out_dir / 'last_report.json').write_text(
        json.dumps(summary, indent=2), encoding='utf-8'
    )
    print()
    print(f'Current regime: {current_regime} ({confidence:.0%} confidence)')
    if send:
        import re, urllib.request
        env  = (DA / '.env').read_text()
        BOT  = re.search(r'TELEGRAM_TOKEN=([^\n]+)', env).group(1).strip()
        CHAT = re.search(r'TELEGRAM_CHAT_ID=([^\n]+)', env).group(1).strip()
        color = {'BULL':'UP', 'BEAR':'DN', 'SIDEWAYS':'--'}[current_regime]
        msg = ('HMM Regime Update\n'
               f'{color} {current_regime}  ({confidence:.0%} confidence)\n'
               f'Bull={float(last_probs[order[2]]):.0%}  '
               f'Side={float(last_probs[order[1]]):.0%}  '
               f'Bear={float(last_probs[order[0]]):.0%}')
        data = json.dumps({'chat_id':CHAT,'text':msg}).encode()
        urllib.request.urlopen(
            urllib.request.Request(
                f'https://api.telegram.org/bot{BOT}/sendMessage',
                data=data, headers={'Content-Type':'application/json'}
            ), timeout=10
        )
        print('  Telegram: OK')
except Exception as e:
    print(f'HMM failed: {e}')
    import traceback; traceback.print_exc()