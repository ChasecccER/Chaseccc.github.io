# Desktop pre-market mover scan

A mover-probability model that runs on **your desktop** every weekday morning,
alerts you (including the **deposit rule** — if the day's optimal option
contract costs more than your available cash, it tells you the exact shortfall
before the open), and pushes its signals to this repo so the **cloud Claude
Code session** can pick them up and act on them with you.

```
your desktop (schedule)                    GitHub repo                 cloud session
┌──────────────────────────┐    push    ┌────────────────────┐  pull  ┌────────────────┐
│ scan.py → signals/*.json │ ─────────▶ │ trading/signals/   │ ─────▶ │ reads latest,  │
│ Claude Code /premarket-  │            │ latest.json        │        │ EV + execution │
│ scan skill + notification│            └────────────────────┘        │ with you       │
└──────────────────────────┘                                          └────────────────┘
```

## One-time setup (desktop)

```bash
git clone https://github.com/ChasecccER/Chaseccc.github.io && cd Chaseccc.github.io
git checkout claude/chat-session-rapkwz   # or merge this folder to main
python3 -m pip install yfinance pandas scikit-learn
echo '{"available_cash": 650}' > trading/config.json   # keep this current
python3 trading/scan.py                                 # test run
```

`trading/config.json` is gitignored — your cash number never leaves the machine.

## Scheduling

**Option A — Claude Code desktop app (recommended):** open this repo in the
Claude Code desktop app and create a scheduled task for weekdays at 9:00 AM ET
with the prompt `/premarket-scan`. The skill runs the scanner, applies the
deposit rule, notifies you, and pushes the signals.

**Option B — plain cron (macOS/Linux):**
```cron
0 9 * * 1-5 cd ~/Chaseccc.github.io && python3 trading/scan.py && git add trading/signals && git commit -m "signals: $(date +\%F)" -q && git push -q
```

**Option C — Windows Task Scheduler:** run
`python C:\path\to\Chaseccc.github.io\trading\scan.py` weekdays 9:00 AM,
followed by the same git add/commit/push.

## Talking to the cloud session

After the morning push, open your cloud Claude Code session and say
"check this morning's signals" — it reads `trading/signals/latest.json`
(git pull) and takes it from there: live option-chain EV, contract selection,
and (only on your explicit instruction) execution via the connected brokerage.

## What the model is

Logistic regression, P(|next-day return| ≥ 2%) over 60 large/mid caps,
~6 months of daily bars, leakage-safe features: volatility clustering, ATR%,
range compression (squeeze), volume trend, momentum, gap frequency, distance
from highs. Backtest on held-out weeks: AUC ≈ 0.65, top-decile hit rate ≈ 1.6×
base rate. It predicts *that* a name moves, not the direction.

**This is decision support, not financial advice. Options can go to zero.**
