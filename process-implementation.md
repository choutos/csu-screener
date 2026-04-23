# Process Implementation: The Individual's "University"

*How to implement the 4-step CSU process as an individual investor.*

---

## 1. Define Strict Criteria (Your "5 KPIs")

✅ **Done.** See `scoring-template.md` for the full 8-KPI card.

### What CSU Does
CSU has 5 KPIs they watch "like beasts" after every acquisition. If you're green, you're autonomous. If you're yellow/red, the army arrives.

### What You Do
Your 8 KPIs are defined. But the key discipline is:

**Every company gets scored BEFORE you look at the stock price.**
- Run the screener first → get the numbers
- Then look at price and valuation
- If you look at price first, your brain will rationalize the score

### Refinement Process
- After each quarter, review: did any KPI not predict what matters?
- After 12 months, you should have enough data to adjust weights
- CSU took 20+ years to industrialize. You'll iterate. That's the point.

---

## 2. Only Buy What Fits (Say No to 99%)

### The 99% Rule
CSU screens 10,000+ companies/year. They buy ~120. That's a 98.8% rejection rate.

For you:
- The screener will flag STRONG and MODERATE fits
- **STRONG = investigate further** (not buy — investigate)
- **MODERATE = watchlist** (not investigate — watch)
- **WEAK or below = pass**

### The "CSU-Style" Decision Tree

```
New company appears
│
├─ Run screener → NOT FIT? → Pass (1 minute)
│
├─ WEAK? → Add to watchlist, revisit in 6 months (5 minutes)
│
├─ MODERATE? → Read last 2 annual reports (2-3 hours)
│   └─ Still interesting? → Fill out company card (1-2 hours)
│   └─ Not interesting? → Pass, keep on watchlist
│
└─ STRONG? → Full deep dive (10-20 hours)
    ├─ Read 3-5 years of annual reports
    ├─ Read investor presentations, conference call transcripts
    ├─ Map the competitive landscape
    ├─ Talk to people in the industry
    ├─ Fill out company card + qualitative assessment
    ├─ Write the thesis in 3 sentences
    │
    └─ Thesis still holds?
        ├─ YES + Price is right → Buy (start small, 2-3% position)
        ├─ YES + Price is wrong → Track, wait for entry
        └─ NO → Pass, document why
```

### The Rejection Log
CSU has a database of every company they've ever looked at. You need one too.

**Create a file:** `rejection-log.md`

Every time you pass on a company, log it:
```
| Date | Ticker | Reason for Passing | Would anything change my mind? |
|------|--------|--------------------|--------------------------------|
| 2026-04-23 | PAGS | Negative FCF, fintech risk | FCF turns positive, retention data |
```

**Why this matters:**
1. Prevents you from re-analyzing the same company from scratch
2. If circumstances change, you know immediately what to check
3. Over time, you'll see patterns in what you reject (your personal "anti-portfolio")

---

## 3. Track Outcomes and Refine (Your "Universities")

### What CSU Does
Every 3 months, CSU brings people together to share:
- What's working in one unit → replicate in others
- What's not working → diagnose and fix
- New patterns in the data → update the acquisition model

### Your Quarterly Review

Schedule: **First Saturday of each quarter** (Jan, Apr, Jul, Oct)

**Part 1: Review Your Analyses (2 hours)**
- Read through all company cards from the past quarter
- Score yourself: Did your initial thesis hold? Where were you wrong?
- Flag companies where the score was wrong (over/under estimated)
- Update scoring template if a KPI consistently mis-predicts

**Part 2: Review Your Portfolio (1 hour)**
- Check each position against kill signals
- Has any thesis changed? If yes → act immediately, don't wait for the next quarter
- Are positions sized correctly? (Your best conviction = biggest position)

**Part 3: Review Your Watchlist (30 min)**
- Any companies ready for promotion to "investigate"?
- Any companies to remove? (If you've passed on them 3+ times, they're probably not for you)
- Add 2-3 new companies from discovery sources

**Part 4: Write Your "Quarterly Letter" (1 hour)**
Like Mark Leonard's letters, write a short letter to yourself:
- What did I learn this quarter?
- What mistakes did I make?
- What patterns am I seeing?
- What's my highest-conviction idea right now?

Save these in `quarterly-letters/`. After 2-3 years, they'll be your most valuable document.

### Annual Calibration

Once a year, do a rigorous calibration:

1. **For every company you scored:** Compare the score to the stock's performance
2. **For every company you bought:** Did the thesis play out?
3. **For every company you passed on:** Would buying have been better?

This is painful. Do it anyway. CSU didn't get good by celebrating wins — they got good by being honest about failures.

---

## 4. Compound Knowledge Over Decades

### The Long Game

CSU's moat took 20+ years to build. Yours will too. But:

- **Year 1:** You have a process and a database. You know more than 90% of retail investors.
- **Year 3:** You have 200+ company analyses. You start seeing patterns automatically.
- **Year 5:** You have deep expertise in 1-2 sectors. You spot opportunities before the market does.
- **Year 10:** You have a network, a database, and a track record. This is where the real compounding kicks in.

### Knowledge Compounding Mechanics

**The Analysis Archive**
Every company card, rejection log entry, and quarterly letter is building block. Never delete — only update.

**The "7-Year Relationship" Principle**
CSU follows targets for 7-9 years. You should too.
- When you find a STRONG fit at the wrong price → track it religiously
- Set price alerts for 20-30% below current
- Re-read the thesis every 6 months
- When the price comes to you, you'll be ready to act in hours, not months

**The Network Effect**
- After 1-2 years, start sharing your analyses with 2-3 trusted people
- They'll share theirs with you
- This is your "6,000-person M&A team" — except it's 3 people. That's fine. Quality > quantity.

### The Anti-Fragile Aspect

CSU's system gets *stronger* with every acquisition because the database grows. Your system gets *stronger* with every analysis — whether you buy or not.

Every rejection teaches you what you DON'T want.
Every mistake teaches you what the scoring template missed.
Every quarter, you're a better investor than the last.

**This is the compound interest that nobody talks about.**

---

## Implementation Checklist

### Week 1 (Setup)
- [x] Screener script running
- [x] Scoring template defined
- [ ] Choose your 1-2 sectors
- [ ] Create first sector deep-dive
- [ ] Create `company-cards/` directory
- [ ] Create `rejection-log.md`

### Week 2-3 (First Pass)
- [ ] Run screener on seed tickers
- [ ] Deep-dive the top 3 STRONG fits
- [ ] Fill out company cards
- [ ] Write first rejection log entries
- [ ] Add 10 new tickers to watchlist from your sectors

### Month 2-3 (Building the Habit)
- [ ] Run screener weekly
- [ ] Deep-dive one company per week
- [ ] Start reading Mark Leonard's letters (find the compilation)
- [ ] Begin your personal "knowledge database" notes

### Month 4+ (The Flywheel)
- [ ] First quarterly review
- [ ] First quarterly letter
- [ ] Begin sharing analyses with trusted contacts
- [ ] Refine scoring template based on experience

---

## Files to Create

```
screener/
├── screener.py               ✅ Automated screener
├── watchlist.json             ✅ Tickers to track
├── scoring-template.md         ✅ The 8-KPI card
├── sector-guide.md             ✅ How to pick sectors
├── process-implementation.md   ✅ This file
├── screener-database.csv       ✅ Results database
├── results/                    ✅ Exported snapshots
├── company-cards/              📁 Per-company deep analyses
├── sector-deep-dives/          📁 Per-sector analysis
├── quarterly-letters/          📁 Your quarterly letters
├── rejection-log.md            📄 Companies you passed on
└── README.md                   ✅ System overview
```
