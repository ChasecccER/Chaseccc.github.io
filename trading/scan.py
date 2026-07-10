#!/usr/bin/env python3
"""
Pre-market mover scan — runs on the desktop, pushes signals to the repo.

What it does (weekday mornings, before the open):
  1. Pulls ~6 months of daily bars for a 60-name large/mid-cap universe (yfinance).
  2. Trains a logistic "mover" model: P(|next-day return| >= 2%) from
     leakage-safe features (vol clustering, ATR%, range compression, volume
     trend, momentum, gap habit, distance from highs).
  3. Scores every name for TODAY and writes a ranked watchlist.
  4. Deposit rule: estimates the cost of an ATM option on the top setup and,
     if it exceeds AVAILABLE_CASH (config.json or env), leads the output with
     a DEPOSIT ALERT stating the exact shortfall.
  5. Writes signals/latest.json + a dated copy — commit & push these so the
     cloud Claude session can read them.

Usage:  python3 scan.py            (writes signals/, prints report)
        AVAILABLE_CASH=650 python3 scan.py
"""
import json, math, os, sys, datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
UNIVERSE = [
    # large caps
    "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","AVGO","JPM","V",
    "MA","UNH","XOM","LLY","HD","COST","PG","JNJ","BAC","ABBV",
    "CRM","NFLX","AMD","ORCL","KO","PEP","TMO","CSCO","ACN","LIN",
    "MCD","ABT","WMT","GE","CAT","GS","BA","CVX","COP","DIS",
    # mid caps
    "ETSY","DKNG","RBLX","PINS","SNAP","DOCU","CROX","WING","FIVE","DECK",
    "WSM","TPR","RL","URBN","AEO","CZR","MGM","ALK","JBLU","UAA",
]
MIDCAPS = set(UNIVERSE[40:])
THRESH = 0.02
FEATS = ["absret1","rv20","atr14_pct","volratio","rangecomp",
         "mom5","mom21","gapfreq20","disthi60","is_midcap"]


def load_config():
    cfg_path = HERE / "config.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    env_cash = os.environ.get("AVAILABLE_CASH")
    if env_cash:
        cfg["available_cash"] = float(env_cash)
    return cfg


def build_features(sym: str, df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)[["open","high","low","close","volume"]].dropna()
    df["ret"] = df["close"].pct_change()
    pc = df["close"].shift(1)
    df["tr"] = pd.concat([df["high"]-df["low"], (df["high"]-pc).abs(),
                          (df["low"]-pc).abs()], axis=1).max(axis=1)
    df["gap"] = df["open"]/pc - 1
    f = pd.DataFrame(index=df.index)
    f["ticker"] = sym
    f["absret1"]   = df["ret"].abs()
    f["rv20"]      = df["ret"].rolling(20).std()
    f["atr14_pct"] = df["tr"].rolling(14).mean() / df["close"]
    f["volratio"]  = df["volume"].rolling(5).mean() / df["volume"].rolling(20).mean()
    f["rangecomp"] = df["tr"].rolling(5).mean() / df["tr"].rolling(20).mean()
    f["mom5"]      = df["close"].pct_change(5)
    f["mom21"]     = df["close"].pct_change(21)
    f["gapfreq20"] = (df["gap"].abs() > 0.01).rolling(20).mean()
    f["disthi60"]  = df["close"] / df["close"].rolling(60).max() - 1
    f["is_midcap"] = 1.0 if sym in MIDCAPS else 0.0
    f["label"]     = (df["ret"].shift(-1).abs() >= THRESH).astype(float)
    f["has_label"] = df["ret"].shift(-1).notna()
    f["close"]     = df["close"]
    return f


def main():
    cfg = load_config()
    cash = cfg.get("available_cash")
    today = dt.date.today().isoformat()

    print(f"[scan] downloading {len(UNIVERSE)} tickers ...", file=sys.stderr)
    raw = yf.download(UNIVERSE, period="7mo", interval="1d",
                      group_by="ticker", auto_adjust=True, progress=False)

    frames = []
    for sym in UNIVERSE:
        try:
            sub = raw[sym].dropna(how="all")
            if len(sub) >= 70:
                frames.append(build_features(sym, sub))
        except Exception as e:
            print(f"[scan] skip {sym}: {e}", file=sys.stderr)
    panel = pd.concat(frames).dropna(subset=FEATS)

    labeled = panel[panel["has_label"]]
    latest_date = panel.index.max()
    score = panel[panel.index == latest_date].copy()

    scaler = StandardScaler().fit(labeled[FEATS])
    clf = LogisticRegression(max_iter=2000).fit(
        scaler.transform(labeled[FEATS]), labeled["label"])
    score["p_move"] = clf.predict_proba(scaler.transform(score[FEATS]))[:, 1]
    score = score.sort_values("p_move", ascending=False)

    top = score.iloc[0]
    # rough ATM near-dated option cost: 0.4 * S * sigma_daily * sqrt(days) * 100,
    # floored by weekly-vol pricing; refine with a live chain before trading.
    est_contract_cost = round(0.4 * top["close"] * top["rv20"] * math.sqrt(5) * 100, 0)

    alert = None
    if cash is not None and est_contract_cost > cash:
        alert = (f"DEPOSIT ALERT: est. cost of an ATM near-dated contract on "
                 f"{top['ticker']} is ~${est_contract_cost:,.0f} but available cash is "
                 f"${cash:,.0f} — shortfall ~${est_contract_cost - cash:,.0f}. "
                 f"Deposit before the open if you want the optimal contract.")

    signals = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "feature_date": str(latest_date.date()),
        "scan_date": today,
        "threshold": THRESH,
        "deposit_alert": alert,
        "available_cash": cash,
        "top_setup": {
            "ticker": top["ticker"], "p_move": round(float(top["p_move"]), 3),
            "close": round(float(top["close"]), 2),
            "est_atm_contract_cost": est_contract_cost,
        },
        "watchlist": [
            {"ticker": r["ticker"], "p_move": round(float(r["p_move"]), 3),
             "close": round(float(r["close"]), 2)}
            for _, r in score.head(15).iterrows()
        ],
    }

    sig_dir = HERE / "signals"
    sig_dir.mkdir(exist_ok=True)
    (sig_dir / "latest.json").write_text(json.dumps(signals, indent=2))
    (sig_dir / f"{today}.json").write_text(json.dumps(signals, indent=2))

    if alert:
        print(alert)
    print(f"\nMover watchlist for next session (features through {signals['feature_date']}):")
    for w in signals["watchlist"]:
        print(f"  {w['ticker']:<6} P(|move|>=2%) = {w['p_move']:.0%}   (${w['close']})")
    print(f"\nsignals written to {sig_dir}/latest.json — commit & push to share with the cloud session")


if __name__ == "__main__":
    main()
