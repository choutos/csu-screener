# CSU-Inspired Scoring Template

*The 8 KPIs that define a Constellation-quality company.*

---

## How to Use

Fill this out for **every** company you analyze — whether you end up buying or not.
The value is in the *discipline* of the process, not any single score.

**Scoring:** Each KPI is 0–3 (0 = fail, 1 = weak, 2 = pass, 3 = exceptional)
**Threshold:** Total ≥ 18 with ≥ 6 passes = STRONG fit

---

## The 8 KPIs

### 1. FCF Margin (Cash Generation)
*What CSU looks for: Companies that generate tons of free cash flow. Software verticals with 20%+ FCF margins.*

| Score | Criteria |
|-------|----------|
| 3 | FCF margin ≥ 20% |
| 2 | FCF margin 10–20% |
| 1 | FCF margin 5–10% |
| 0 | FCF margin < 5% |

**Why it matters:** CSU's model depends on companies sending cash UP to the parent. Low FCF = dead weight in the system.

---

### 2. Gross Margin (Software Economics)
*What CSU looks for: 70%+ gross margins typical of software. High gross margin = incremental revenue is nearly pure profit.*

| Score | Criteria |
|-------|----------|
| 3 | Gross margin ≥ 70% |
| 2 | Gross margin 50–70% |
| 1 | Gross margin 30–50% |
| 0 | Gross margin < 30% |

**Why it matters:** Low gross margin means you're selling effort, not knowledge. CSU buys knowledge.

---

### 3. Revenue Stability (Retention Proxy)
*What CSU looks for: Customer lifetime 20+ years. Revenue doesn't swing year to year.*

| Score | Criteria |
|-------|----------|
| 3 | Revenue volatility ≤ 10% (std/mean) |
| 2 | Revenue volatility 10–20% |
| 1 | Revenue volatility 20–30% |
| 0 | Revenue volatility > 30% |

**Why it matters:** This is the *best public-market proxy for retention*. If revenue is bumpy, either customers churn or the business is cyclical. CSU avoids both.

**Better data if available:** If you can find NRR (net revenue retention) or gross retention in filings/investor presentations, use that instead. 95%+ gross retention = score 3.

---

### 4. Growth Profile (Durability, Not Speed)
*What CSU looks for: Moderate, predictable growth. Not hypergrowth, not shrinking.*

| Score | Criteria |
|-------|----------|
| 3 | Revenue CAGR 2–15% (sweet spot) |
| 2 | Revenue CAGR 0–2% (stable but slow) |
| 1 | Revenue CAGR 15–30% (growing fast, less CSU-like) |
| 0 | Revenue CAGR > 30% or < -5% (wrong model or dying) |

**Why it matters:** CSU explicitly avoids "PR-worthy" high-growth software. High growth attracts competition. Low growth with high retention = durability.

---

### 5. FCF Yield (Valuation Discipline)
*What CSU looks for: Buy at a price where the cash flow justifies the entry.*

| Score | Criteria |
|-------|----------|
| 3 | FCF yield ≥ 5% |
| 2 | FCF yield 3–5% |
| 1 | FCF yield 2–3% |
| 0 | FCF yield < 2% |

**Why it matters:** CSU demands 25–30% TIR on acquisitions. You can't calculate TIR for public stocks, but FCF yield is the equivalent — "what am I earning on my purchase price?"

**Note:** A great company at a terrible price is a terrible investment. This KPI keeps you disciplined.

---

### 6. Debt Discipline
*What CSU looks for: Acquired companies have minimal debt. The parent handles capital allocation.*

| Score | Criteria |
|-------|----------|
| 3 | Debt/Equity ≤ 0.5 |
| 2 | Debt/Equity 0.5–1.0 |
| 1 | Debt/Equity 1.0–2.0 |
| 0 | Debt/Equity > 2.0 |

**Why it matters:** High debt = the business is funding itself, not sending cash up. CSU doesn't buy leverage stories.

---

### 7. Size Fit (Mid-Cap Sweet Spot)
*What CSU looks for: Small enough to be under the radar, big enough to be stable.*

| Score | Criteria |
|-------|----------|
| 3 | Market cap $500M–$10B (sweet spot) |
| 2 | Market cap $200–500M or $10–30B |
| 1 | Market cap > $30B |
| 0 | Market cap < $200M (too illiquid) |

**Why it matters:** CSU buys companies at $5–50M. You can't. But the public equivalent is mid-cap vertical software that's too boring for growth funds and too small for mega-caps.

---

### 8. Industry Fit (Vertical/Niche)
*What CSU looks for: Software for a specific industry, not horizontal. Bus scheduling, not productivity suites.*

| Score | Criteria |
|-------|----------|
| 3 | Direct vertical software (industry-specific) |
| 2 | Adjacent (tech services, data, payments) |
| 1 | Horizontal software (compete with big tech) |
| 0 | Not software/tech |

**Why it matters:** Vertical = high switching cost + low competition + captive customers. Horizontal = the opposite.

---

## Qualitative Add-Ons (Not Scored, But Mandatory)

These can't be automated but MUST be assessed manually for any STRONG/MODERATE fit:

- **Switching Cost Type:** Is it contractual, technical, regulatory, or data-driven? (Technical + regulatory = strongest)
- **% of Customer's Costs:** Is the software 0.1–1% of the customer's total costs? (If >5%, it's a target for cost-cutting)
- **Mission Criticality:** If the software goes down, does the customer lose money immediately? (Payroll, compliance = yes; analytics = maybe)
- **Competitive Landscape:** Are there 2–5 competitors or 50? (Few = good, means the niche is too small for big tech)
- **Management Skin in Game:** Does management own significant stock? (CSU culture: leaders are owners, not renters)
- **Pricing Power:** Can they raise prices 3–5% annually without churn? (Check historical price increases in filings)

---

## Kill Signals (When to Sell)

CSU's kill signal is "recurrence dropping." For public investors:

1. **Gross retention drops below 90%** — customers are leaving
2. **FCF margin compresses >5pp** — either pricing pressure or cost creep
3. **Revenue volatility spikes** — the business has changed
4. **Acquisition spree into unfamiliar verticals** — management is empire-building
5. **Management turnover in key operational roles** — the culture machine is breaking
6. **The thesis premise changes** — e.g., AI makes the switching cost irrelevant

**Important:** Price decline is NOT a kill signal. Thesis change IS a kill signal.

---

## Recording Template

For each company analyzed, create a file in `company-cards/`:

```markdown
# [TICKER] — [Company Name]
Date: YYYY-MM-DD
Score: X/24 | Fit: STRONG/MODERATE/WEAK/NOT FIT

## KPI Scores
| KPI | Score | Value |
|-----|-------|-------|
| FCF Margin | X | XX% |
| Gross Margin | X | XX% |
| Revenue Stability | X | XX% vol |
| Growth Profile | X | XX% CAGR |
| FCF Yield | X | XX% |
| Debt Discipline | X | X.XX D/E |
| Size Fit | X | $XXM |
| Industry Fit | X | [description] |

## Qualitative Assessment
- Switching Cost Type: 
- % of Customer's Costs: 
- Mission Criticality: 
- Competitive Landscape: 
- Management Skin in Game: 
- Pricing Power: 

## Thesis
[1-3 sentences: Why does this company compound?]

## Kill Signals
[What would make me sell?]

## Notes
[Anything else worth remembering]
```
