# Kill Signals & Health Checks

## Philosophy

Every position needs **pre-defined kill signals** — specific, measurable conditions that, if triggered, mean the thesis is broken. These aren't vague ("the stock goes down") — they're concrete checkpoints tied to the original investment thesis.

Without kill signals, you'll hold losers too long ("it'll come back") and sell winners too early ("I should lock in profits"). Kill signals enforce discipline.

## What Makes a Good Kill Signal

A kill signal should be:
- **Specific**: "Gross margin drops below 60%" not "margins deteriorate"
- **Measurable**: You can check it with data, not opinion
- **Tied to the thesis**: It should contradict a specific reason you bought
- **Actionable**: If triggered, you know what to do

### Examples by Thesis Type

| Thesis | Kill Signal |
|--------|-------------|
| Regulatory moat (banking) | "Customer churn exceeds 5%" |
| Pricing power (SaaS) | "Gross margin drops below 60%" |
| Steady compounder | "Revenue growth negative for 2+ quarters" |
| Capital-light business | "Capex/Revenue exceeds 15% for 2 years" |
| Low customer cost concentration | "Customer concentration: top 10 exceeds 50%" |
| Market leader | "Market share drops below 30%" |

## Health Check Process

The 🩺 Health Check evaluates a position against its original thesis and kill signals:

1. **Fetch fresh data** from yfinance (price, margins, growth, debt)
2. **Re-score** the company using the 8-KPI framework
3. **Update portfolio** with current `score`, `max_score`, `score_breakdown`
4. **Send thesis + kill signals + current data to LLM** for evaluation
5. **Log results** to `kill_signal_log` table

### LLM Evaluation

The LLM receives the original thesis, kill signals, and current metrics. It evaluates:

1. **Is the original thesis still valid?** What's changed?
2. **Have any kill signals been triggered?** At what severity?
3. **Are there new risks** not in the original kill signals?
4. **What action is recommended?** With what confidence?

### Thesis Status

| Status | Meaning |
|--------|---------|
| **INTACT** | Thesis is holding, no signals triggered, continue holding |
| **WEAKENED** | Some deterioration, signals at WARNING level, put on watch |
| **BROKEN** | Thesis is no longer valid, CRITICAL signal triggered, consider selling |

### Recommended Actions

| Action | When |
|--------|------|
| **HOLD** | Thesis INTACT, no signals triggered |
| **WATCH** | Thesis WEAKENED, some warning signals |
| **SELL** | Thesis BROKEN, critical signal triggered |
| **BUY_MORE** | Thesis INTACT, price dropped below buy-under (rare) |

## Kill Signal Log

Every health check is logged to the `kill_signal_log` table:

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `ticker` | TEXT | Company ticker |
| `check_date` | TEXT | ISO datetime |
| `signal_type` | TEXT | Which signal was evaluated |
| `severity` | TEXT | OK / WARNING / CRITICAL |
| `details` | TEXT | What was found |
| `action` | TEXT | HOLD / SELL / BUY_MORE / WATCH |
| `current_price` | REAL | Price at time of check |

This creates an audit trail — you can see how the thesis evolved over time and whether signals were gradual or sudden.

## Portfolio-Wide Health Checks

The **"🩺 Health Check All"** button runs health checks on every portfolio position sequentially:

1. Fetches fresh data for each position
2. Runs thesis evaluation via LLM
3. Updates scores and logs signals
4. Shows a summary of results

For positions without a recorded thesis or kill signals, the health check notes "No thesis recorded" and recommends setting one up before the next check.

## Best Practices

- **Run health checks regularly** — at least monthly for active positions
- **Don't override signals** — if a CRITICAL signal fires, the framework says sell. If you disagree, document *why* in notes, not by ignoring the signal
- **Update kill signals when the thesis changes** — if you bought for a regulatory moat and the company pivots to a new market, your old kill signals may no longer apply
- **Track score changes over time** — a KPI going from ✅ to ❌ is a leading indicator, even if it hasn't triggered a kill signal yet (future enhancement: score deltas)
