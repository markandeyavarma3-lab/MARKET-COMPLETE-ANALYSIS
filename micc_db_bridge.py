# micc_db_bridge.py - Place in DATA-ANALYSIS root
import sys, json, sqlite3, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
DB = r"D:\marketDB\db\market.db"
def main():
    try:
        raw = sys.stdin.read().strip()
        if not raw: print("[]"); return
        req = json.loads(raw)
        sql, params = req.get("sql",""), req.get("params",[])
        if not sql: print("[]"); return
        conn = sqlite3.connect(DB, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        cur = conn.execute(sql, list(params))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        print(json.dumps(rows, default=str))
    except Exception as e:
        sys.stderr.write(f"Bridge error: {e}\n"); sys.exit(1)
if __name__ == "__main__": main()
