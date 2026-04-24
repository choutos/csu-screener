# Valuation: Reverse DCF & Buy-Under Prices

## Philosophy

A quality company at the wrong price is a bad investment. The framework uses a **Reverse DCF** model to calculate a conservative "buy-under" price — the maximum price you should pay given the company's current cash generation.

The goal is not precision. It's **discipline**. The buy-under price creates a rule: buy below it, wait above it. No rationalizing, no "but this one is different."

## The Model

### Inputs

| Input | Source | Notes |
|-------|--------|-------|
| Current FCF | FCF yield × EV, or FCF margin × Revenue | Prefer FCF yield when available (more accurate) |
| Growth assumption | Derived from 3Y revenue CAGR | Capped at 8%, degraded to 70% of historical |
| Discount rate | Fixed at 10% | No adjustments for "quality" |
| Terminal multiple | 15× FCF | Moderate, not aggressive |
| Projection period | 10 years | Standard |
| Terminal growth | 50% of assumed growth | Perpetual slowdown |
| Margin of safety | 25% | Buy Under = Fair Value × 0.75 |

### Growth Assumption Logic

The model deliberately underestimates growth:

| Historical 3Y CAGR | Assumed Growth |
|-------------------|----------------|
| >10% | 8% (hard cap) |
| 3–10% | 70% of historical |
| <3% | 3% (floor for quality companies) |

**Why cap at 8%?** Because nobody grows at 20% forever. A company that's grown 15%/yr for 3 years is not going to do 15% for the next 10. The 8% cap forces the model to be honest about sustainable growth.

**Why the 70% degradation?** Regression to the mean is one of the most powerful forces in business. Companies that grow 10% tend to slow to 7%, then 5%, then 3%. Starting from 70% of historical is a more honest baseline.

**Why a 3% floor?** Quality compounders with pricing power should be able to grow at least at inflation + a small premium. If they can't, the thesis is already weakening.

### Discount Rate: 10%, No Exceptions

The 10% discount rate is **not adjusted** for company quality. This is deliberate:

- A 7% discount rate for "quality" is circular reasoning — you're assuming the company is safe because you've already decided it's safe
- 10% represents the opportunity cost of capital — what you could earn elsewhere
- If a company doesn't clear the bar at 10%, it's not cheap enough to justify the risk

### Terminal Multiple: 15×

15× FCF is moderate. It assumes the company will still be a quality business 10 years from now, but not that it will be worth 25× or 30× FCF (which requires perpetual high growth or perpetually low rates).

### Margin of Safety: 25%

The buy-under price is **25% below fair value**. This means:
- You're paid to own the business at or below buy-under
- Even if your assumptions are slightly wrong, you have a buffer
- Above buy-under, you're relying on things going right — which is speculation, not investing

## Calculation Steps

1. **Estimate current FCF** from FCF yield or FCF margin × market cap
2. **Project FCF** for 10 years using assumed growth rate
3. **Discount each year's FCF** back to present at 10%
4. **Calculate terminal value**: Year 10 FCF × (1 + half growth) × 15× multiple, discounted to present
5. **Fair value** = sum of discounted FCFs + discounted terminal value
6. **Buy-under** = Fair value × 0.75

## Example

A company with:
- Market cap: $2B
- FCF yield: 4.5% → FCF = $90M
- Historical growth: 8% → Assumed growth: 5.6% (70% of 8%)

```
Year 1:  $90M × 1.056 = $95.0M → PV = $86.4M
Year 2:  $95.0M × 1.056 = $100.3M → PV = $82.9M
...
Year 10: $147.6M → PV = $56.9M

Sum of PV of FCFs: ~$700M

Terminal: $147.6M × 1.028 × 15 = $2,276M → PV = $877M

Fair Value = $700M + $877M = $1,577M
Buy-Under = $1,577M × 0.75 = $1,183M
```

If the stock price implies a market cap below $1,183M → **Buy signal**.
If above $1,577M → **No margin of safety**.

## LLM-Supplemented Buy-Under

The reverse DCF is the *primary* valuation method. The LLM advisor can supplement with qualitative reasoning:

- Is the current growth sustainable or cyclical?
- Are there catalysts that could accelerate/decelerate FCF?
- Is the sector at a peak or trough?

The LLM's suggested buy-under is **sanity-checked** against the current price: if the LLM suggests a buy-under more than 50% above the current price, it's discarded (the LLM is being too optimistic).

## When Not to Trust the Model

The reverse DCF is unreliable when:
- **FCF is negative or near-zero**: The model requires positive FCF
- **Growth is highly cyclical**: One good year doesn't make a trend
- **Major acquisitions distort FCF**: Integration costs mask underlying cash generation
- **The company is in transition**: Restructuring, spinoffs, or strategy changes make historical FCF misleading

In these cases, use the score and qualitative thesis as the primary decision tools, and treat the buy-under price as directional, not definitive.
