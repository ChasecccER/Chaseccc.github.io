---
name: premarket-scan
description: Run the pre-market mover scan (trading/scan.py), apply the deposit rule, summarize the watchlist, and push signals to the repo so the cloud session can read them. Use every weekday morning before the open, or whenever the user asks for a market scan or mover watchlist.
---

# Pre-market mover scan

You are running on the user's desktop. Steps:

1. Run the scanner:
   ```bash
   python3 trading/scan.py
   ```
   If `AVAILABLE_CASH` should be current, ask the user or read `trading/config.json`
   (`{"available_cash": <dollars>}`) — update it if they give you a number.

2. Read `trading/signals/latest.json` and report to the user, in this order:
   - **Deposit alert first** if `deposit_alert` is non-null — this is a standing
     user instruction: when the optimal contract costs more than available cash,
     lead with the exact shortfall so they can deposit before the open.
   - Top setup and the top-10 watchlist with probabilities.
   - Anything notable (several names clustered in one sector, unusually high
     top probability, etc.).

3. Commit and push the signals so the cloud Claude session can read them:
   ```bash
   git add trading/signals && git commit -m "signals: $(date +%F)" && git push
   ```

4. Do NOT place trades. This skill is analysis + alerting only. Trades happen
   only when the user explicitly instructs, in whichever session they choose.

Notes:
- The model predicts *that* a name moves (|return| >= 2%), not the direction.
- If yfinance fails (rate limit), wait a minute and retry once; report failure
  honestly rather than inventing a watchlist.
