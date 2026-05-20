# -*- coding: utf-8 -*-
"""
phase5_build.py
================
MICC Phase 5 build script.

IMPORTANT: agent_epsilon.py is a SEPARATE file in this release.
Copy BOTH files to D:\\MICC\\ before running.

What this script does:
  [1/4] Patch telegram_bot.py    -- adds /options /index /stock /hot
  [2/4] Write /api/stock route   -- stock detail API
  [3/4] Write stock detail page  -- /stocks/[symbol]
  [4/4] Write Epsilon API+hook   -- /api/epsilon + run_pipeline.py Phase 10

agent_epsilon.py (separate file) handles:
  OI spike screen, PCR divergence, high-gamma-near-price, LLM analysis

Usage:
  Copy phase5_build.py and agent_epsilon.py to D:\\MICC\\
  cd D:\\MICC
  py phase5_build.py

Rules:
  - py not python
  - No get_conn() in agent files
  - TSX: zero emoji/Unicode, pure ASCII
  - fo_data always filtered by date
  - DA = 'D:/MICC', DB = 'D:/marketDB/db/market.db'
"""

import sys
from pathlib import Path

BASE = Path(r"D:\MICC")

def find_dashboard():
    for sub in ["micc-dashboard/src", "micc-dashboard"]:
        p = BASE / sub
        if p.is_dir() and (p / "components").is_dir():
            return p / "app", p / "components"
    return None, None

APP, COMP = find_dashboard()
if not APP:
    print("[ERROR] micc-dashboard not found at D:/MICC/micc-dashboard/")
    sys.exit(1)

print(f"[OK] Dashboard: {APP.parent}")

def w(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip("\n"), encoding="utf-8", newline="\n")
    try:
        rel = path.relative_to(BASE)
    except ValueError:
        rel = path
    print(f"  wrote: {rel}")

def probe(path):
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


# =============================================================================
# [1/4] TELEGRAM BOT -- add /options /index /stock /hot
# =============================================================================
print("\n[1/4] Patching telegram_bot.py...")

BOT_PATH = BASE / "telegram_bot.py"
bot_src  = probe(BOT_PATH)

if not bot_src:
    print("  [WARN] telegram_bot.py not found -- skipping")
elif "async def cmd_options" in bot_src:
    print("  Already patched -- skipped")
else:
    # ── 4 new command handlers ────────────────────────────────────────────────
    NEW_CMDS = '''

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5 COMMANDS  (added by phase5_build.py)
# All query DB live -- never depend on cached agent JSON files
# ─────────────────────────────────────────────────────────────────────────────

async def cmd_options(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Live /options -- PCR, Max Pain, GEX from fo_data."""
    import sqlite3 as _sl
    try:
        conn = _sl.connect(r"D:/marketDB/db/market.db")

        latest_row = conn.execute(
            "SELECT MAX(date) FROM fo_data "
            "WHERE instrument IN ('OPTIDX','IDO') AND symbol='NIFTY'"
        ).fetchone()
        latest_date = latest_row[0] if latest_row and latest_row[0] else None

        if not latest_date:
            await update.message.reply_text(
                "No NIFTY options data. Run: py phase2_greeks_calculator.py --daily"
            )
            conn.close()
            return

        exp_row = conn.execute(
            "SELECT MIN(expiry) FROM fo_data "
            "WHERE date=? AND symbol='NIFTY' "
            "AND instrument IN ('OPTIDX','IDO') AND expiry>=?",
            (latest_date, latest_date)
        ).fetchone()
        expiry = exp_row[0] if exp_row and exp_row[0] else "?"

        pcr_rows = conn.execute(
            "SELECT option_typ, SUM(open_int) AS oi FROM fo_data "
            "WHERE date=? AND symbol='NIFTY' "
            "AND instrument IN ('OPTIDX','IDO') AND expiry=? "
            "GROUP BY option_typ",
            (latest_date, expiry)
        ).fetchall()
        pcr_map = {r[0]: r[1] for r in pcr_rows}
        call_oi = float(pcr_map.get("CE") or 0)
        put_oi  = float(pcr_map.get("PE") or 0)
        pcr     = round(put_oi / call_oi, 3) if call_oi > 0 else None

        # Max Pain
        all_strikes = conn.execute(
            "SELECT strike, "
            "SUM(CASE WHEN option_typ='CE' THEN COALESCE(open_int,0) END) AS co, "
            "SUM(CASE WHEN option_typ='PE' THEN COALESCE(open_int,0) END) AS po "
            "FROM fo_data "
            "WHERE date=? AND symbol='NIFTY' "
            "AND instrument IN ('OPTIDX','IDO') AND expiry=? "
            "GROUP BY strike ORDER BY strike",
            (latest_date, expiry)
        ).fetchall()

        max_pain = None
        if all_strikes:
            min_loss = float("inf")
            for K, co, po in all_strikes:
                K = float(K)
                loss = sum(
                    (K - float(s)) * float(c or 0) if float(s) < K else
                    (float(s) - K) * float(p or 0) if float(s) > K else 0
                    for s, c, p in all_strikes
                )
                if loss < min_loss:
                    min_loss = loss
                    max_pain = int(K)

        # Net GEX
        gex_row = conn.execute(
            "SELECT SUM(gamma_exposure) FROM gamma_exposure_daily "
            "WHERE date=(SELECT MAX(date) FROM gamma_exposure_daily WHERE symbol='NIFTY') "
            "AND symbol='NIFTY'"
        ).fetchone()
        net_gex = int(gex_row[0] or 0) if gex_row and gex_row[0] is not None else 0

        # Top 5 OI strikes
        top_oi = conn.execute(
            "SELECT strike, "
            "SUM(CASE WHEN option_typ='CE' THEN open_int END) AS co, "
            "SUM(CASE WHEN option_typ='PE' THEN open_int END) AS po "
            "FROM fo_data "
            "WHERE date=? AND symbol='NIFTY' "
            "AND instrument IN ('OPTIDX','IDO') AND expiry=? "
            "GROUP BY strike "
            "ORDER BY (COALESCE(co,0)+COALESCE(po,0)) DESC LIMIT 5",
            (latest_date, expiry)
        ).fetchall()

        nifty_row = conn.execute(
            "SELECT closing_index_value, change FROM market_snapshot "
            "WHERE index_name='Nifty 50' "
            "AND date=(SELECT MAX(date) FROM market_snapshot)"
        ).fetchone()
        conn.close()

        def _fmt_oi(v):
            if not v: return "--"
            n = float(v)
            if n >= 1e7: return f"{n/1e7:.1f}Cr"
            if n >= 1e5: return f"{n/1e5:.1f}L"
            if n >= 1e3: return f"{n/1e3:.0f}K"
            return str(int(n))

        def _fmt_gex(v):
            a = abs(v)
            if a >= 1e9: return f"{v/1e9:.2f}B"
            if a >= 1e6: return f"{v/1e6:.2f}M"
            return f"{int(v):,}"

        nifty_close  = round(float(nifty_row[0]), 2) if nifty_row and nifty_row[0] else None
        nifty_change = round(float(nifty_row[1]), 2) if nifty_row and nifty_row[1] else None

        pcr_label = (
            "BULLISH (put-heavy)" if pcr and pcr > 1.3 else
            "BEARISH (call-heavy)" if pcr and pcr < 0.7 else
            "NEUTRAL"
        )
        gex_label = "LONG GAMMA (dampens)" if net_gex > 0 else "SHORT GAMMA (amplifies)"

        if nifty_close and nifty_change is not None:
            nifty_str = f"{nifty_close:,} ({'+' if nifty_change >= 0 else ''}{nifty_change:.2f}%)"
        else:
            nifty_str = str(nifty_close or "--")

        lines = [
            "*OPTIONS SNAPSHOT*",
            f"`Date: {latest_date}  |  Expiry: {expiry}`",
            f"Nifty 50: `{nifty_str}`",
            "",
        ]
        if pcr:
            lines.append(f"*PCR:* `{pcr:.3f}` -- {pcr_label}")
        if max_pain:
            lines.append(f"*Max Pain:* `{max_pain:,}`")
        lines.append(f"*Net GEX:* `{_fmt_gex(net_gex)}` -- {gex_label}")
        lines.append(f"Call OI: `{_fmt_oi(call_oi)}`  |  Put OI: `{_fmt_oi(put_oi)}`")
        lines += ["", "*Top OI Strikes:*"]
        for row in top_oi:
            s, co, po = row
            lines.append(f"  `{int(float(s)):,}` CE:{_fmt_oi(co)}  PE:{_fmt_oi(po)}")
        lines.append("")
        lines.append("_Use /stock SYMBOL for stock-level options_")

        await send_chunks(ctx.bot, str(update.effective_chat.id), ["\\n".join(lines)])

    except Exception as e:
        log.error(f"cmd_options error: {e}", exc_info=True)
        await update.message.reply_text(f"Error: {e}")


async def cmd_index(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /index [ND] -- top 5 gainers + decliners.
    e.g. /index 7D  /index 3D  /index 1M
    """
    import sqlite3 as _sl
    try:
        args_text = " ".join(ctx.args or []).strip().upper()
        day_map = {
            "1D": 1, "3D": 3, "5D": 5, "7D": 7,
            "10D": 10, "14D": 14, "20D": 20,
            "1M": 22, "2M": 44, "3M": 66,
        }
        n_days = day_map.get(args_text, 7)
        label  = args_text or "7D"

        conn = _sl.connect(r"D:/marketDB/db/market.db")
        rows = conn.execute(f"""
            WITH ld AS (SELECT MAX(date) AS md FROM market_snapshot),
            sd AS (
              SELECT date FROM (
                SELECT DISTINCT date FROM market_snapshot
                WHERE date <= (SELECT md FROM ld)
                ORDER BY date DESC LIMIT {n_days + 1}
              ) ORDER BY date ASC LIMIT 1
            ),
            s AS (
              SELECT index_name, closing_index_value AS sc
              FROM market_snapshot WHERE date=(SELECT date FROM sd)
            ),
            e AS (
              SELECT index_name, closing_index_value AS ec
              FROM market_snapshot WHERE date=(SELECT md FROM ld)
            )
            SELECT e.index_name,
                   ROUND((e.ec - s.sc) / s.sc * 100, 2) AS pct
            FROM e JOIN s ON e.index_name = s.index_name
            WHERE s.sc > 0 AND e.ec > 0
              AND e.index_name NOT LIKE '%Inverse%'
              AND e.index_name NOT LIKE '%VIX%'
              AND e.index_name NOT LIKE '%1x%'
              AND e.index_name NOT LIKE '%Dividend Points%'
            ORDER BY pct DESC
        """).fetchall()
        conn.close()

        if not rows:
            await update.message.reply_text("No index data available.")
            return

        gainers   = rows[:5]
        decliners = list(reversed(rows))[:5]

        lines = [f"*INDEX PERFORMANCE -- {label}*", ""]
        lines.append("*Top 5 Gainers:*")
        for name, pct in gainers:
            bar = "+" * min(int(abs(float(pct or 0))), 10)
            lines.append(f"  `{_esc(str(name)[:28]):<28}` `{float(pct):+.2f}%` {bar}")
        lines += ["", "*Bottom 5 Decliners:*"]
        for name, pct in decliners:
            bar = "-" * min(int(abs(float(pct or 0))), 10)
            lines.append(f"  `{_esc(str(name)[:28]):<28}` `{float(pct):+.2f}%` {bar}")
        lines += ["", f"_Total: {len(rows)} indices | /index 1D /index 1M_"]

        await send_chunks(ctx.bot, str(update.effective_chat.id), ["\\n".join(lines)])

    except Exception as e:
        log.error(f"cmd_index error: {e}", exc_info=True)
        await update.message.reply_text(f"Error: {e}")


async def cmd_stock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /stock OMAXAUTO -- quick stats: close, 7d return, delivery, streak, insider
    """
    import sqlite3 as _sl
    try:
        if not ctx.args:
            await update.message.reply_text("Usage: /stock SYMBOL\\nExample: /stock OMAXAUTO")
            return

        symbol = ctx.args[0].strip().upper()
        conn   = _sl.connect(r"D:/marketDB/db/market.db")

        price_rows = conn.execute(
            "SELECT date, close, volume FROM stock_data "
            "WHERE symbol=? AND close IS NOT NULL "
            "ORDER BY date DESC LIMIT 10",
            (symbol,)
        ).fetchall()

        deliv_rows = conn.execute(
            "SELECT date, deliv_qty, traded_qty FROM stock_delivery "
            "WHERE symbol=? ORDER BY date DESC LIMIT 7",
            (symbol,)
        ).fetchall()

        streak_row = conn.execute(
            """
            WITH md AS (SELECT MAX(run_date) AS md FROM signals_history)
            SELECT COUNT(DISTINCT run_date) AS days,
                   ROUND(AVG(CAST(score AS REAL)), 1) AS avg_sc,
                   MAX(run_date) AS last_seen,
                   GROUP_CONCAT(DISTINCT screen_tags) AS tags
            FROM signals_history
            WHERE symbol=?
              AND run_date >= date((SELECT md FROM md), '-30 days')
            """,
            (symbol,)
        ).fetchone()

        insider_rows = conn.execute(
            "SELECT filing_date, name, transaction_type, value "
            "FROM insider_trading "
            "WHERE symbol=? ORDER BY filing_date DESC LIMIT 3",
            (symbol,)
        ).fetchall()
        conn.close()

        if not price_rows:
            await update.message.reply_text(
                f"No data for {symbol}. Check symbol spelling."
            )
            return

        close  = float(price_rows[0][1])
        older  = float(price_rows[-1][1]) if price_rows else close
        pct_7d = round((close / older - 1) * 100, 2) if older > 0 else None
        vol    = int(price_rows[0][2] or 0)

        avg_deliv = None
        valid = [
            float(r[1]) / float(r[2]) * 100
            for r in deliv_rows
            if r[1] and r[2] and float(r[2]) > 0
        ]
        if valid:
            avg_deliv = round(sum(valid) / len(valid), 1)

        streak_days = int(streak_row[0] or 0) if streak_row else 0
        streak_sc   = float(streak_row[1] or 0) if streak_row else 0
        streak_last = streak_row[2] if streak_row and streak_row[2] else "--"
        streak_tags = streak_row[3] if streak_row and streak_row[3] else "--"

        conviction = streak_days * streak_sc + (avg_deliv or 0) * 0.1
        grade = "A+" if conviction >= 20 else "A" if conviction >= 12 else "B" if conviction >= 7 else "C" if conviction >= 3 else "--"

        pct_str = (f"{'+' if pct_7d and pct_7d >= 0 else ''}{pct_7d:.2f}%") if pct_7d is not None else "--"
        vol_str = f"{vol/1e5:.1f}L" if vol >= 1e5 else f"{vol/1e3:.0f}K" if vol >= 1e3 else str(vol)

        lines = [
            f"*{_esc(symbol)}*",
            f"Close: `{close:,.2f}`  7d: `{pct_str}`  Vol: `{vol_str}`",
        ]
        if avg_deliv is not None:
            lines.append(f"Avg Delivery: `{avg_deliv:.1f}%`")

        if streak_days > 0:
            flame = "FIRE" if streak_days >= 5 else "HOT" if streak_days >= 3 else ""
            lines += [
                "",
                f"*Streak (30d):* `{streak_days}d` {flame}",
                f"  Score: `{streak_sc:.1f}`  Grade: `{grade}`  Last: `{streak_last}`",
                f"  Screens: `{_esc(str(streak_tags)[:60])}`",
            ]
        else:
            lines.append("\\nNo recent streak signals.")

        if insider_rows:
            lines += ["", "*Insider (last 30d):*"]
            for fdate, name, ttype, val in insider_rows:
                val_str = f"Rs{float(val)/1e5:.1f}L" if val and float(val) > 0 else "--"
                ttype_e = _esc(str(ttype or "")[:15])
                name_e  = _esc(str(name  or "")[:20])
                lines.append(f"  `{fdate}` {name_e} [{ttype_e}] {val_str}")

        lines.append(f"\\n_Dashboard: localhost:3000/stocks/{symbol}_")
        await send_chunks(ctx.bot, str(update.effective_chat.id), ["\\n".join(lines)])

    except Exception as e:
        log.error(f"cmd_stock error: {e}", exc_info=True)
        await update.message.reply_text(f"Error: {e}")


async def cmd_hot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /hot -- symbols appearing 3+ days in last 7
    """
    import sqlite3 as _sl
    try:
        conn = _sl.connect(r"D:/marketDB/db/market.db")
        rows = conn.execute("""
            WITH md AS (SELECT MAX(run_date) AS md FROM signals_history)
            SELECT symbol,
                   COUNT(DISTINCT run_date) AS days,
                   ROUND(AVG(CAST(score AS REAL)), 1) AS avg_sc,
                   ROUND(AVG(CAST(pct_chg AS REAL)), 2) AS avg_ret,
                   ROUND(AVG(CAST(avg_deliv_pct AS REAL)), 1) AS avg_deliv,
                   GROUP_CONCAT(DISTINCT screen_tags) AS tags
            FROM signals_history
            WHERE run_date >= date((SELECT md FROM md), '-7 days')
            GROUP BY symbol
            HAVING days >= 3
            ORDER BY days DESC, avg_sc DESC
            LIMIT 20
        """).fetchall()
        latest = conn.execute(
            "SELECT MAX(run_date) FROM signals_history"
        ).fetchone()[0]
        conn.close()

        if not rows:
            await update.message.reply_text(
                "No hot picks in last 7 days. Run: py micc_engine.py 7 --send"
            )
            return

        lines = [
            "*HOT PICKS -- Last 7 Days*",
            f"`Symbols 3+ days | as of {latest}`",
            "",
        ]
        for sym, days, avg_sc, avg_ret, avg_deliv, tags in rows:
            ret_s   = f"{'+' if float(avg_ret or 0) >= 0 else ''}{float(avg_ret or 0):.1f}%" if avg_ret else "--"
            del_s   = f"d{float(avg_deliv or 0):.0f}%" if avg_deliv else ""
            tag_s   = ",".join(t[:4] for t in str(tags or "").split(",") if t)[:18]
            flame   = "FIRE" if days >= 5 else "HOT"
            lines.append(
                f"{flame} `{_esc(str(sym)):<12}` {days}d "
                f"ret:{ret_s}  sc:{avg_sc}  {del_s}  `{_esc(tag_s)}`"
            )

        lines += [
            "",
            "_/stock SYMBOL for full stats on any pick_",
        ]
        await send_chunks(ctx.bot, str(update.effective_chat.id), ["\\n".join(lines)])

    except Exception as e:
        log.error(f"cmd_hot error: {e}", exc_info=True)
        await update.message.reply_text(f"Error: {e}")

'''

    ANCHOR = "# ── Scheduled job ───"
    if ANCHOR not in bot_src:
        print("  [WARN] Anchor not found in telegram_bot.py -- add commands manually")
    else:
        bot_src = bot_src.replace(ANCHOR, NEW_CMDS + "\n" + ANCHOR)

        # Fix the \n escaping -- they should be real newlines in the joined strings
        bot_src = bot_src.replace('"\\n".join(lines)', '"\\n".join(lines)')

        # Register handlers in main()
        old_reg = '    app.add_handler(CommandHandler("streak", cmd_streak))\n    app.add_handler(CommandHandler("status", cmd_status))'
        new_reg = (
            '    app.add_handler(CommandHandler("streak",  cmd_streak))\n'
            '    app.add_handler(CommandHandler("options", cmd_options))\n'
            '    app.add_handler(CommandHandler("index",   cmd_index))\n'
            '    app.add_handler(CommandHandler("stock",   cmd_stock))\n'
            '    app.add_handler(CommandHandler("hot",     cmd_hot))\n'
            '    app.add_handler(CommandHandler("status",  cmd_status))'
        )
        if old_reg in bot_src:
            bot_src = bot_src.replace(old_reg, new_reg)
        else:
            # fallback: try single-space version
            old_reg2 = '    app.add_handler(CommandHandler("streak", cmd_streak))\n    app.add_handler(CommandHandler("status",  cmd_status))'
            if old_reg2 in bot_src:
                bot_src = bot_src.replace(old_reg2, new_reg)
            else:
                print("  [WARN] Could not auto-register handlers -- add manually in main()")

        # Update console print
        old_p = 'Commands: /start /report /alpha /beta /gamma /delta /streak /status'
        new_p = 'Commands: /start /report /alpha /beta /gamma /delta /streak /options /index /stock /hot /status'
        bot_src = bot_src.replace(old_p, new_p)

        BOT_PATH.write_text(bot_src, encoding="utf-8", newline="\n")
        print("  patched: telegram_bot.py (+4 commands)")

print("[1/4] Telegram commands done")


# =============================================================================
# [2/4] /api/stock/[symbol]/route.ts
# =============================================================================
print("\n[2/4] Writing stock detail API route...")

w(APP / "api" / "stock" / "[symbol]" / "route.ts", r"""
import { NextResponse } from 'next/server'
import { spawnSync }    from 'child_process'
import path             from 'path'

const DA = 'D:/MICC'

function queryDb(sql: string): any[] {
  try {
    const bridge = path.join(DA, 'micc_db_bridge.py')
    const r = spawnSync('py', [bridge], {
      input: JSON.stringify({ sql, params: [] }),
      encoding: 'utf-8', timeout: 25000, cwd: DA,
    })
    if (r.status !== 0) { console.error('[stock]', r.stderr?.slice(0, 200)); return [] }
    const out = r.stdout.trim()
    return out ? JSON.parse(out) : []
  } catch (e: any) { console.error('[stock]', e.message); return [] }
}

export const dynamic = 'force-dynamic'

export async function GET(
  _req: Request,
  { params }: { params: { symbol: string } }
) {
  const sym = (params.symbol ?? '').toUpperCase().trim()
  if (!sym) return NextResponse.json({ error: 'No symbol' }, { status: 400 })

  // ── 90-day price history ─────────────────────────────────────────────────
  const priceRows = queryDb(`
    SELECT date, open, high, low, close, volume
    FROM stock_data
    WHERE symbol = '${sym}' AND close IS NOT NULL
    ORDER BY date DESC LIMIT 90
  `).reverse()

  // ── Delivery history ─────────────────────────────────────────────────────
  const delivRows = queryDb(`
    SELECT date, deliv_qty, traded_qty,
      CASE WHEN traded_qty > 0
        THEN ROUND(CAST(deliv_qty AS REAL) / traded_qty * 100, 1)
        ELSE NULL END AS deliv_pct
    FROM stock_delivery
    WHERE symbol = '${sym}'
    ORDER BY date DESC LIMIT 90
  `).reverse()

  // ── Screen history ────────────────────────────────────────────────────────
  const screenRows = queryDb(`
    SELECT run_date, screen_tags, score, pct_chg, avg_deliv_pct, regime, earnings_flag
    FROM signals_history
    WHERE symbol = '${sym}'
    ORDER BY run_date DESC LIMIT 60
  `)

  // ── Conviction summary (30d) ──────────────────────────────────────────────
  const convRows = queryDb(`
    WITH md AS (SELECT MAX(run_date) AS md FROM signals_history)
    SELECT COUNT(DISTINCT run_date)                      AS streak_days,
           ROUND(AVG(CAST(score          AS REAL)), 2)   AS avg_score,
           MAX(CAST(score                AS REAL))        AS max_score,
           ROUND(AVG(CAST(pct_chg       AS REAL)), 2)   AS avg_pct,
           MAX(CAST(pct_chg             AS REAL))        AS max_pct,
           ROUND(AVG(CAST(avg_deliv_pct AS REAL)), 1)   AS avg_deliv,
           GROUP_CONCAT(DISTINCT screen_tags)             AS all_tags,
           MAX(run_date)                                  AS last_seen,
           MIN(run_date)                                  AS first_seen
    FROM signals_history
    WHERE symbol = '${sym}'
      AND run_date >= date((SELECT md FROM md), '-30 days')
  `)
  const conv = convRows[0] ?? {}

  const convScore = Number(conv.streak_days ?? 0) * Number(conv.avg_score ?? 0)
                  + Number(conv.avg_deliv ?? 0) * 0.1
  const convGrade = convScore >= 20 ? 'A+' : convScore >= 12 ? 'A'
                  : convScore >= 7  ? 'B'  : convScore >= 3  ? 'C' : '--'

  // ── Insider trades (60d) ─────────────────────────────────────────────────
  const insiderRows = queryDb(`
    SELECT filing_date, name, category, transaction_type,
           quantity, price, value, post_holding
    FROM insider_trading
    WHERE symbol = '${sym}'
      AND filing_date >= date('now', '-60 days')
    ORDER BY filing_date DESC LIMIT 20
  `)

  // ── F&O snapshot ─────────────────────────────────────────────────────────
  const foLatest = queryDb(`
    SELECT MAX(date) AS d FROM fo_data
    WHERE symbol = '${sym}' AND instrument = 'OPTSTK'
  `)
  const foDate = foLatest[0]?.d ?? ''
  const foRows = foDate ? queryDb(`
    SELECT option_typ, strike, expiry,
           SUM(open_int) AS oi,
           SUM(volume)   AS vol,
           ROUND(AVG(close), 2) AS avg_ltp
    FROM fo_data
    WHERE symbol = '${sym}' AND instrument = 'OPTSTK' AND date = '${foDate}'
    GROUP BY option_typ, strike, expiry
    ORDER BY oi DESC LIMIT 10
  `) : []

  const foCE = foRows.filter((r:any) => r.option_typ === 'CE').reduce((s:number, r:any) => s + Number(r.oi ?? 0), 0)
  const foPE = foRows.filter((r:any) => r.option_typ === 'PE').reduce((s:number, r:any) => s + Number(r.oi ?? 0), 0)
  const foPCR = foCE > 0 ? Math.round((foPE / foCE) * 1000) / 1000 : null

  // ── Price stats ──────────────────────────────────────────────────────────
  let latestClose = null, pct7d = null, pct20d = null, avgVol20 = null
  if (priceRows.length > 0) {
    latestClose = Number(priceRows[priceRows.length - 1].close)
    if (priceRows.length >= 7) {
      const s7 = Number(priceRows[priceRows.length - 7].close)
      pct7d = s7 > 0 ? Math.round((latestClose / s7 - 1) * 10000) / 100 : null
    }
    if (priceRows.length >= 20) {
      const s20 = Number(priceRows[priceRows.length - 20].close)
      pct20d = s20 > 0 ? Math.round((latestClose / s20 - 1) * 10000) / 100 : null
      const vols = priceRows.slice(-20).map((r:any) => Number(r.volume ?? 0)).filter(v => v > 0)
      avgVol20 = vols.length ? Math.round(vols.reduce((a, b) => a + b, 0) / vols.length) : null
    }
  }

  return NextResponse.json({
    symbol,
    price:   { series: priceRows, latest_close: latestClose, pct7d, pct20d, avg_vol_20: avgVol20 },
    delivery:{ series: delivRows },
    screens: { history: screenRows, conviction: conv, grade: convGrade, score: Math.round(convScore * 10) / 10 },
    insider: insiderRows,
    fo:      { date: foDate, rows: foRows, pcr: foPCR, call_oi: foCE, put_oi: foPE },
  })
}
""")

print("[2/4] Stock API route done")


# =============================================================================
# [3/4] app/stocks/[symbol]/page.tsx
# =============================================================================
print("\n[3/4] Writing stock detail page...")

w(APP / "stocks" / "[symbol]" / "page.tsx", r"""
"use client";
import { useState, useEffect } from "react";
import { useParams }  from "next/navigation";
import NavBar         from "@/components/NavBar";

function fmtNum(v: any, d = 2): string {
  if (v == null || isNaN(Number(v))) return "--";
  return Number(v).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
}
function fmtPct(v: any): string {
  if (v == null) return "--";
  const n = Number(v);
  return (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
}
function pctColor(v: any): string {
  if (v == null) return "var(--dim)";
  return Number(v) >= 0 ? "var(--pos)" : "var(--neg)";
}
function fmtVol(v: any): string {
  const n = Number(v);
  if (!n) return "--";
  if (n >= 1e7) return (n / 1e7).toFixed(1) + "Cr";
  if (n >= 1e5) return (n / 1e5).toFixed(1) + "L";
  if (n >= 1e3) return (n / 1e3).toFixed(0) + "K";
  return String(n);
}
function fmtVal(v: any): string {
  const n = Number(v);
  if (!n || isNaN(n)) return "--";
  if (n >= 1e7) return "Rs" + (n / 1e7).toFixed(1) + "Cr";
  if (n >= 1e5) return "Rs" + (n / 1e5).toFixed(1) + "L";
  return "Rs" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

function Spark({ vals, color = "var(--accent)", w = 120, h = 28 }:
  { vals: number[]; color?: string; w?: number; h?: number }) {
  if (!vals || vals.length < 2) return null;
  const min = Math.min(...vals), max = Math.max(...vals), range = max - min || 1;
  const pad = 2;
  const pts = vals.map((v, i) => {
    const x = pad + (i / (vals.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg width={w} height={h} style={{ display: "block", overflow: "visible" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

function PriceChart({ price, delivery }: { price: any[]; delivery: any[] }) {
  if (!price.length) return (
    <div style={{ color: "var(--dim)", fontFamily: "monospace", fontSize: 11, padding: 20 }}>
      No price data for this symbol.
    </div>
  );

  const closes = price.map(r => Number(r.close ?? 0)).filter(v => v > 0);
  const dates  = price.map(r => String(r.date));
  const W = 580, H = 130, pL = 55, pR = 10, pT = 8, pB = 20;

  const minC = Math.min(...closes), maxC = Math.max(...closes), rng = maxC - minC || 1;
  const toX  = (i: number) => pL + (i / (closes.length - 1)) * (W - pL - pR);
  const toY  = (v: number) => pT + (H - pT - pB) - ((v - minC) / rng) * (H - pT - pB);

  const pts = closes.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(" ");

  const delivMap: Record<string, number> = {};
  delivery.forEach(r => { if (r.deliv_pct) delivMap[r.date] = Number(r.deliv_pct); });
  const maxDeliv = Math.max(...Object.values(delivMap), 1);

  const step = Math.max(1, Math.floor(closes.length / 5));
  const xLabels = closes.map((_, i) => i).filter(i => i % step === 0 || i === closes.length - 1);

  const areaPath =
    `M ${toX(0).toFixed(1)},${(pT + H - pB).toFixed(1)} ` +
    closes.map((v, i) => `L ${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(" ") +
    ` L ${toX(closes.length - 1).toFixed(1)},${(pT + H - pB).toFixed(1)} Z`;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block", overflow: "visible" }}>
      <path d={areaPath} fill="var(--accent)" opacity="0.07" />
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinejoin="round" />
      {dates.map((d, i) => {
        const v = delivMap[d];
        if (!v) return null;
        const bh = ((v / maxDeliv) * (H - pT - pB)) * 0.6;
        return <rect key={i} x={toX(i) - 1} y={H - pB - bh} width={2} height={bh}
                     fill="var(--info)" opacity="0.4" />;
      })}
      <line x1={pL} y1={pT} x2={pL} y2={H - pB} stroke="var(--border)" strokeWidth="0.5" />
      <text x={pL - 4} y={pT + 4}    textAnchor="end" fontSize={8} fill="var(--dim)">{maxC.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</text>
      <text x={pL - 4} y={H - pB + 4} textAnchor="end" fontSize={8} fill="var(--dim)">{minC.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</text>
      {xLabels.map(i => (
        <text key={i} x={toX(i)} y={H - 2} textAnchor="middle" fontSize={8} fill="var(--dim)">
          {(dates[i] ?? "").slice(5)}
        </text>
      ))}
      <rect x={pL + 8}  y={pT} width={8} height={4} fill="var(--accent)" />
      <text x={pL + 20} y={pT + 4} fontSize={8} fill="var(--dim)">Price</text>
      <rect x={pL + 65} y={pT} width={8} height={4} fill="var(--info)" opacity="0.7" />
      <text x={pL + 77} y={pT + 4} fontSize={8} fill="var(--dim)">Delivery%</text>
    </svg>
  );
}

function GradeBadge({ grade }: { grade: string }) {
  const colors: Record<string, string> = {
    "A+": "#26c485", "A": "#58a6ff", "B": "#e3b341", "C": "#f0883e", "--": "#6e7681",
  };
  const c = colors[grade] ?? "#6e7681";
  return (
    <div style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      width: 44, height: 44, borderRadius: "50%",
      border: `2px solid ${c}`, color: c,
      fontFamily: "monospace", fontSize: 16, fontWeight: 700,
    }}>{grade}</div>
  );
}

function TagBadge({ tag }: { tag: string }) {
  const s = tag.toLowerCase();
  const c = s.includes("mom") ? "#58a6ff" : s.includes("del") ? "#26c485"
          : (s.includes("brk") || s.includes("break")) ? "#e3b341"
          : s.includes("con") ? "#f0883e" : "#8b949e";
  return (
    <span style={{
      fontSize: 9, padding: "1px 6px", marginRight: 4,
      background: c + "22", border: `1px solid ${c}55`,
      borderRadius: 3, color: c, fontFamily: "monospace",
    }}>{tag.toUpperCase().slice(0, 6)}</span>
  );
}

function TabBtn({ active, color, onClick, children }: {
  active: boolean; color: string; onClick: () => void; children: any;
}) {
  return (
    <button onClick={onClick} style={{
      padding: "4px 14px", fontSize: 10, cursor: "pointer", fontFamily: "monospace",
      background: active ? color : "var(--surface)",
      color: active ? "#000" : "var(--muted)",
      border: "1px solid var(--border)", borderRadius: 4,
    }}>{children}</button>
  );
}

export default function StockDetailPage() {
  const params = useParams();
  const symbol = (
    Array.isArray(params?.symbol) ? params.symbol[0] : (params?.symbol ?? "")
  ).toUpperCase();

  const [data,    setData]    = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [tab,     setTab]     = useState<"screens" | "insider" | "fo">("screens");

  useEffect(() => {
    if (!symbol) return;
    fetch(`/api/stock/${symbol}`, { cache: "no-store" })
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [symbol]);

  if (loading) return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <NavBar />
      <div style={{ padding: 40, color: "var(--dim)", fontFamily: "monospace" }}>
        Loading {symbol}...
      </div>
    </div>
  );
  if (!data || data.error) return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <NavBar />
      <div style={{ padding: 40, color: "var(--neg)", fontFamily: "monospace" }}>
        {data?.error ?? `No data found for ${symbol}.`}
        <br />Check spelling. Example: /stocks/RELIANCE
      </div>
    </div>
  );

  const { price, delivery, screens, insider, fo } = data;
  const conv    = screens.conviction ?? {};
  const tags    = (conv.all_tags ?? "").split(",").filter(Boolean);
  const histRows= screens.history ?? [];

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <NavBar />
      <div style={{ padding: "16px 20px", maxWidth: 1400, margin: "0 auto" }}>

        {/* Breadcrumb */}
        <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)", marginBottom: 10 }}>
          <a href="/streaks" style={{ color: "var(--dim)", textDecoration: "none" }}>STREAKS</a>
          <span style={{ margin: "0 6px" }}>/</span>
          <span style={{ color: "var(--accent)" }}>{symbol}</span>
        </div>

        {/* Header row */}
        <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 14, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontFamily: "monospace", fontSize: 22, fontWeight: 700, color: "var(--accent)" }}>
              {symbol}
            </div>
            <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)", marginTop: 2 }}>
              90-day window
            </div>
          </div>

          {/* Stats */}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {[
              { l: "CLOSE",     v: fmtNum(price.latest_close),             c: "var(--text)"  },
              { l: "7D",        v: fmtPct(price.pct7d),                    c: pctColor(price.pct7d)  },
              { l: "20D",       v: fmtPct(price.pct20d),                   c: pctColor(price.pct20d) },
              { l: "AVG VOL",   v: fmtVol(price.avg_vol_20),               c: "var(--info)"  },
              { l: "AVG DELIV", v: conv.avg_deliv != null ? Number(conv.avg_deliv).toFixed(1) + "%" : "--", c: "var(--bull)" },
            ].map(({ l, v, c }) => (
              <div key={l} style={{
                padding: "8px 12px", background: "var(--surface)",
                border: "1px solid var(--border)", borderRadius: 6,
              }}>
                <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)", letterSpacing: "0.1em", marginBottom: 2 }}>{l}</div>
                <div style={{ fontFamily: "monospace", fontSize: 14, fontWeight: 700, color: c }}>{v}</div>
              </div>
            ))}
          </div>

          {/* Conviction */}
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <GradeBadge grade={screens.grade ?? "--"} />
            <div>
              <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)", letterSpacing: "0.1em" }}>CONVICTION</div>
              <div style={{ fontFamily: "monospace", fontSize: 12, marginTop: 2 }}>
                {screens.score ?? "--"} pts
              </div>
              <div style={{ marginTop: 4 }}>
                {tags.slice(0, 4).map((t: string) => <TagBadge key={t} tag={t} />)}
              </div>
            </div>
          </div>
        </div>

        {/* Streak bar */}
        {Number(conv.streak_days) > 0 && (
          <div style={{
            padding: "7px 14px", background: "var(--surface)",
            border: "1px solid var(--border)", borderRadius: 6,
            fontFamily: "monospace", fontSize: 11,
            display: "flex", gap: 20, marginBottom: 14, flexWrap: "wrap",
          }}>
            {[
              { l: "STREAK",    v: conv.streak_days + "d",           c: "var(--accent)" },
              { l: "AVG SCORE", v: conv.avg_score,                   c: "var(--text)"   },
              { l: "MAX SCORE", v: conv.max_score,                   c: "var(--accent)" },
              { l: "AVG RET",   v: fmtPct(conv.avg_pct),             c: pctColor(conv.avg_pct) },
              { l: "MAX RET",   v: fmtPct(conv.max_pct),             c: "var(--pos)"    },
              { l: "FIRST",     v: conv.first_seen ?? "--",          c: "var(--dim)"    },
              { l: "LAST",      v: conv.last_seen  ?? "--",          c: "var(--dim)"    },
            ].map(({ l, v, c }) => (
              <span key={l}>
                <span style={{ color: "var(--dim)" }}>{l}: </span>
                <span style={{ color: c, fontWeight: 600 }}>{v}</span>
              </span>
            ))}
          </div>
        )}

        {/* Price + delivery chart */}
        <div style={{
          padding: "12px 14px", background: "var(--surface)",
          border: "1px solid var(--border)", borderRadius: 6, marginBottom: 14,
        }}>
          <div style={{ fontFamily: "monospace", fontSize: 9, color: "var(--dim)", letterSpacing: "0.1em", marginBottom: 8 }}>
            PRICE + DELIVERY (90 DAYS)
          </div>
          <PriceChart price={price.series} delivery={delivery.series} />
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
          <TabBtn active={tab === "screens"} color="var(--accent)" onClick={() => setTab("screens")}>
            SCREEN HISTORY ({histRows.length})
          </TabBtn>
          <TabBtn active={tab === "insider"} color="var(--warn)" onClick={() => setTab("insider")}>
            INSIDER TRADES ({insider?.length ?? 0})
          </TabBtn>
          <TabBtn active={tab === "fo"} color="var(--info)" onClick={() => setTab("fo")}>
            F&amp;O SNAPSHOT
          </TabBtn>
        </div>

        {/* Screen history */}
        {tab === "screens" && (
          histRows.length === 0 ? (
            <div style={{ color: "var(--dim)", fontFamily: "monospace", padding: 20 }}>
              {symbol} has not appeared in any screen in the last 60 days.
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)", letterSpacing: "0.08em" }}>
                  <th style={{ padding: "5px 8px", textAlign: "left" }}>DATE</th>
                  <th style={{ padding: "5px 8px", textAlign: "left" }}>SCREENS</th>
                  <th style={{ padding: "5px 8px", textAlign: "right" }}>SCORE</th>
                  <th style={{ padding: "5px 8px", textAlign: "right" }}>RET%</th>
                  <th style={{ padding: "5px 8px", textAlign: "right" }}>DELIV%</th>
                  <th style={{ padding: "5px 8px", textAlign: "left" }}>REGIME</th>
                  <th style={{ padding: "5px 8px", textAlign: "left" }}>EPS</th>
                </tr>
              </thead>
              <tbody>
                {histRows.map((row: any, i: number) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "5px 8px", color: "var(--dim)" }}>{row.run_date}</td>
                    <td style={{ padding: "5px 8px" }}>
                      {(row.screen_tags ?? "").split(",").filter(Boolean).map((t: string) =>
                        <TagBadge key={t} tag={t} />
                      )}
                    </td>
                    <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--accent)" }}>
                      {row.score != null ? Number(row.score).toFixed(1) : "--"}
                    </td>
                    <td style={{ padding: "5px 8px", textAlign: "right", color: pctColor(row.pct_chg) }}>
                      {fmtPct(row.pct_chg)}
                    </td>
                    <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--info)" }}>
                      {row.avg_deliv_pct != null ? Number(row.avg_deliv_pct).toFixed(1) + "%" : "--"}
                    </td>
                    <td style={{ padding: "5px 8px", color: "var(--dim)", fontSize: 10 }}>
                      {(row.regime ?? "--").slice(0, 14)}
                    </td>
                    <td style={{ padding: "5px 8px", color: "var(--dim)", fontSize: 10 }}>
                      {row.earnings_flag ?? "--"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}

        {/* Insider trades */}
        {tab === "insider" && (
          insider.length === 0 ? (
            <div style={{ color: "var(--dim)", fontFamily: "monospace", padding: 20 }}>
              No insider trades for {symbol} in the last 60 days.
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)", letterSpacing: "0.08em" }}>
                  <th style={{ padding: "5px 8px", textAlign: "left" }}>DATE</th>
                  <th style={{ padding: "5px 8px", textAlign: "left" }}>NAME</th>
                  <th style={{ padding: "5px 8px", textAlign: "left" }}>CATEGORY</th>
                  <th style={{ padding: "5px 8px", textAlign: "left" }}>TYPE</th>
                  <th style={{ padding: "5px 8px", textAlign: "right" }}>QTY</th>
                  <th style={{ padding: "5px 8px", textAlign: "right" }}>PRICE</th>
                  <th style={{ padding: "5px 8px", textAlign: "right" }}>VALUE</th>
                </tr>
              </thead>
              <tbody>
                {insider.map((row: any, i: number) => {
                  const isBuy = (row.transaction_type ?? "").toLowerCase().includes("buy") ||
                                (row.transaction_type ?? "").toLowerCase().includes("acq");
                  return (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "5px 8px", color: "var(--dim)" }}>{row.filing_date}</td>
                      <td style={{ padding: "5px 8px", color: "var(--text)" }}>
                        {String(row.name ?? "--").slice(0, 28)}
                      </td>
                      <td style={{ padding: "5px 8px", color: "var(--dim)", fontSize: 10 }}>
                        {String(row.category ?? "--").slice(0, 16)}
                      </td>
                      <td style={{ padding: "5px 8px", color: isBuy ? "var(--pos)" : "var(--neg)", fontWeight: 600 }}>
                        {row.transaction_type ?? "--"}
                      </td>
                      <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--dim)" }}>
                        {row.quantity != null ? Number(row.quantity).toLocaleString("en-IN") : "--"}
                      </td>
                      <td style={{ padding: "5px 8px", textAlign: "right" }}>{fmtNum(row.price)}</td>
                      <td style={{ padding: "5px 8px", textAlign: "right", color: isBuy ? "var(--pos)" : "var(--neg)", fontWeight: 600 }}>
                        {fmtVal(row.value)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )
        )}

        {/* F&O snapshot */}
        {tab === "fo" && (
          fo.rows.length === 0 ? (
            <div style={{ color: "var(--dim)", fontFamily: "monospace", padding: 20 }}>
              No stock options data for {symbol}. Only F&amp;O-listed stocks have this data.
            </div>
          ) : (
            <div>
              <div style={{ fontFamily: "monospace", fontSize: 10, color: "var(--dim)", marginBottom: 10 }}>
                Date: {fo.date} &nbsp;|&nbsp;
                Call OI: {fmtVol(fo.call_oi)} &nbsp;|&nbsp;
                Put OI: {fmtVol(fo.put_oi)}
                {fo.pcr != null ? ` | PCR: ${fo.pcr.toFixed(3)}` : ""}
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "monospace" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid var(--border)", fontSize: 9, color: "var(--dim)" }}>
                    <th style={{ padding: "5px 8px", textAlign: "right" }}>STRIKE</th>
                    <th style={{ padding: "5px 8px", textAlign: "left" }}>TYPE</th>
                    <th style={{ padding: "5px 8px", textAlign: "left" }}>EXPIRY</th>
                    <th style={{ padding: "5px 8px", textAlign: "right" }}>OI</th>
                    <th style={{ padding: "5px 8px", textAlign: "right" }}>VOL</th>
                    <th style={{ padding: "5px 8px", textAlign: "right" }}>AVG LTP</th>
                  </tr>
                </thead>
                <tbody>
                  {fo.rows.map((row: any, i: number) => (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--info)", fontWeight: 600 }}>
                        {Number(row.strike).toLocaleString("en-IN")}
                      </td>
                      <td style={{ padding: "5px 8px", color: row.option_typ === "CE" ? "var(--neg)" : "var(--pos)", fontWeight: 600 }}>
                        {row.option_typ}
                      </td>
                      <td style={{ padding: "5px 8px", color: "var(--dim)" }}>{row.expiry}</td>
                      <td style={{ padding: "5px 8px", textAlign: "right" }}>{fmtVol(row.oi)}</td>
                      <td style={{ padding: "5px 8px", textAlign: "right", color: "var(--dim)" }}>{fmtVol(row.vol)}</td>
                      <td style={{ padding: "5px 8px", textAlign: "right" }}>{fmtNum(row.avg_ltp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}

      </div>
    </div>
  );
}
""")

print("[3/4] Stock detail page done")


# =============================================================================
# [4/4] Epsilon API route + run_pipeline.py Phase 10 hook
# =============================================================================
print("\n[4/4] Writing Epsilon API + pipeline hook...")

w(APP / "api" / "epsilon" / "route.ts", r"""
import { NextResponse } from 'next/server'
import fs               from 'fs'
import path             from 'path'

const DA = 'D:/MICC'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const p = path.join(DA, 'agents', 'epsilon', 'last_report.json')
    if (!fs.existsSync(p)) {
      return NextResponse.json({
        error: 'No epsilon report. Run: py D:\\MICC\\agent_epsilon.py --send'
      })
    }
    let raw = fs.readFileSync(p, 'utf-8')
    raw = raw.replace(/:\s*NaN([,\}\]])/g,      ': null$1')
             .replace(/:\s*Infinity([,\}\]])/g,  ': null$1')
             .replace(/:\s*-Infinity([,\}\]])/g, ': null$1')
    return NextResponse.json(JSON.parse(raw))
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 })
  }
}
""")

# Patch run_pipeline.py
PIPELINE = BASE / "data_pipeline" / "run_pipeline.py"
pipe_src  = probe(PIPELINE)

EPSILON_HOOK = """
    # Phase 10 -- Agent Epsilon (Options Intelligence)
    epsilon = MICC_DIR / "agent_epsilon.py"
    if epsilon.exists():
        r["epsilon"] = run(epsilon,
                          "Agent Epsilon: Options Intelligence",
                          args=["--send"] if with_engine else [],
                          timeout=300, cwd=MICC_DIR)
    else:
        log("agent_epsilon.py not found -- copy it to D:/MICC/", "WARN")
        r["epsilon"] = False

"""

if not pipe_src:
    print("  [WARN] run_pipeline.py not found at D:/MICC/data_pipeline/")
elif "epsilon" in pipe_src:
    print("  run_pipeline.py already has Epsilon hook -- skipped")
else:
    # Find the health check phase line and inject before it
    for anchor in ["# Phase 8 — Health check", "# Phase 8 - Health check", "check_db_health"]:
        if anchor in pipe_src:
            pipe_src = pipe_src.replace(anchor, EPSILON_HOOK + "    " + anchor.lstrip(), 1)
            PIPELINE.write_text(pipe_src, encoding="utf-8", newline="\n")
            print("  patched: run_pipeline.py (+Phase 10 Epsilon hook)")
            break
    else:
        print("  [NOTE] Could not auto-patch run_pipeline.py -- add Epsilon manually")

print("[4/4] Done")


# =============================================================================
# SUMMARY
# =============================================================================
print()
print("=" * 65)
print("  PHASE 5 COMPLETE")
print("=" * 65)
print("""
  FILES CREATED / MODIFIED:

    telegram_bot.py              +4 commands: /options /index /stock /hot
    app/api/stock/[symbol]/      Stock detail API (price, delivery, screens,
                                  insider trades, F&O snapshot)
    app/stocks/[symbol]/         Stock detail page with price+delivery chart
    app/api/epsilon/             Reads agents/epsilon/last_report.json
    data_pipeline/run_pipeline.py +Phase 10 Epsilon hook

    agent_epsilon.py             (SEPARATE FILE -- copy to D:\\MICC\\ manually)

  RESTART:
    cd D:\\MICC\\micc-dashboard && npm run dev
    cd D:\\MICC && py telegram_bot.py

  TEST:
    Browser:   localhost:3000/stocks/RELIANCE
    Telegram:  /hot
               /options
               /index 7D
               /stock OMAXAUTO

    Epsilon:   cd D:\\MICC && py agent_epsilon.py --send
""")
