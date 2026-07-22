# Strategy Brief: pmcc_leaps_diagonal

Researched 2026-07-19 for the ATLAS options shadow platform. All quotes were
read from the cited pages during research sessions on 2026-07-19; in the
second pass the load-bearing secondary quotes (TradingBlock, Income Navigator,
Data Driven Options, moomoo) were independently re-fetched and verified
verbatim, and the tastylive primary page plus McMillan's Option Strategist
newsletter were read and added. Anything not readable in a source is marked
UNKNOWN - no invented constants.

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `pmcc_leaps_diagonal`
- **Common names:** Poor Man's Covered Call (PMCC); long call diagonal debit
  spread; LEAPS diagonal.
- **Provenance class:** practitioner (broker/education-desk published
  mechanics), with a textbook antecedent (McMillan's LEAPS-as-stock-substitute
  treatment).
- **PRIMARY citation (read directly this session):**
  - tastylive (tastytrade's education network), "Poor Man's Covered Call - 
    What is it?" - https://www.tastylive.com/concepts-strategies/poor-man-covered-call
    (living page, no visible date; fetched and re-verified 2026-07-19). The
    canonical tastytrade-family PMCC doctrine page. Verbatim rules read there:
    "A poor man's covered call (PMCC) is a long call diagonal debit spread
    that is used to replicate a covered call position"; long leg "deep
    in-the-money (ITM)" with "high delta, so that the price of the call will
    move closely with the underlying stock price"; short leg OTM, "30 to 60
    days out"; **"We also ensure that the total debit paid is not more than
    75% of the width of the strikes."**; the extrinsic-coverage entry rule - 
    check the long call's extrinsic value and "Once we figure that value, we
    ensure that the near term option we sell is equal to or greater than that
    amount."; winner management - positions "closed for a winner if the stock
    price increases significantly in one expiration cycle"; loser management - 
    "For losing trades due to the stock price decreasing, the short call can
    be rolled to a lower strike to collect more credit."; and the universe
    exclusion "We never route poor man's covered calls in volatility
    instruments."
  - tastytrade (the broker's learn center), "What is a Long Call Diagonal
    Spread & How to Trade it?" - 
    https://tastytrade.com/learn/trading-products/options/long-call-diagonal-spread/
    (living page, no visible date; fetched 2026-07-19). Defines the structure - 
    "buying a longer-dated call at a lower strike" and "selling a shorter-dated
    call at a higher strike" - and defines the PMCC as the variant using "an ITM
    call instead of an ATM/OTM call" for the long leg. Structure and management
    doctrine; the delta/DTE constants come from the operational secondaries
    below.
- **Operational-constants source (read directly; treated as co-primary for the
  recipe):** Steve Henry / Kirk Du Plessis / Ryan Hysmith, "Poor Man's Covered
  Call | Option Alpha Guide" - https://optionalpha.com/learn/poor-mans-covered-call
  (last updated 2024-05-17). Publishes a concrete automated template: "This bot
  uses 150 DTE and a 0.80 delta for the long call" and "The bot opens a short
  call 30 days from expiration at the 0.30 delta in this example."
- **INDEPENDENT secondary sources (read directly this session):**
  1. Michael Martin, "Poor Man's Covered Call: Beginner's Visual Guide" - 
     https://www.tradingblock.com/strategies/poor-mans-covered-call-pmcc
     (updated 2026-06-18). Delta bands, 10–45 DTE short window, 75%-of-width
     debit guideline, 50–75% profit-taking, IV-entry preference, assignment
     mechanics.
  2. TradeStation, "A capital-efficient approach to understanding the poor
     man's covered call strategy" - 
     https://www.tradestation.com/insights/2026/04/07/poor-mans-covered-call-strategy/
     (2026-04-07). 0.70–0.85 long delta, >0.90 warning, ex-dividend
     early-assignment mechanics.
  3. moomoo (Futu) learn, "Poor Man's Covered Call: The Ultimate Beginner's
     Guide" - https://www.moomoo.com/us/learn/detail-poor-mans-covered-call-117081-240349051
     (2026-07-09). Long ≥0.75Δ / ≥90 DTE, short <0.35Δ / <60 DTE, max-profit and
     max-loss formulas.
  4. Income Navigator, "Poor Man's Covered Call: The Complete 2026 Guide" - 
     https://www.incomenavigator.com/blog/poor-mans-covered-call-strategy-guide
     (2026-06-16). Strike-floor rule, 21–35 DTE short, 30–50% short profit take,
     touch-roll rule, LEAPS <6-months roll.
  5. Ryan Silk & Lawrence Polatchek, "Poor Man's Covered Call (PMCC)" - 
     https://apexvol.com/strategies/poor-mans-covered-call (2026-06-19).
     Cost-basis strike floor, 0.70–0.85 long delta, 30–45 DTE short, roll
     cadence.
  6. Days to Expiry, "Poor Man's Covered Call: A Capital-Efficient Strategy" - 
     https://www.daystoexpiry.com/blog/poor-mans-covered-call (2026-01-06,
     updated 2026-03-19). 0.80–0.90 long delta, 12+ months ideal, <10% extrinsic
     screen, 21–35 DTE short, <6-months LEAPS exit.
  7. C Allen, "Poor Man's Covered Call" - https://datadrivenoptions.com/poor-mans-covered-call/
     (undated). Roll thresholds (short Δ<0.12 or >0.40; else act at 21 DTE),
     hold/fold/roll management framing.
- **Textbook antecedent:** Lawrence G. McMillan, *Options as a Strategic
  Investment*, 5th edition, Prentice Hall Press, 2012-08-07, ISBN
  9780735204652, 1072 pp. Publisher's page
  (https://www.penguinrandomhouse.com/books/310812/options-as-a-strategic-investment-by-lawrence-g-mcmillan/)
  confirms the book covers "Buy and sell strategies for Long Term Equity
  Anticipation Securities (LEAPS)". Chapter locator NOW VERIFIED: **Chapter 25
  "LEAPS"**, with section headings "The Basics", "Pricing LEAPS", "Comparing
  LEAPS and Short-Term Options", "LEAPS Strategies", "Speculative Option
  Buying with LEAPS", "Selling LEAPS", "Spreads Using LEAPS", "Summary" - TOC
  read on McMillan's own product page
  (https://www.optionstrategist.com/products/options-strategic-investment-5th-edition,
  fetched 2026-07-19). The chapter TEXT itself remains unread online - no
  constant below is attributed to the book text. McMillan's diagonal
  rationale, quoted by a secondary review
  (https://kriminiltrading.com/blogs/must-read-economic-market-books/options-as-a-strategic-investment-by-lawrence-mcmillan-book-summary-review):
  "One wants to own the option that is not so subject to time decay, while
  simultaneously selling the option that is quite subject to time decay."
  [verified-secondary]
- **McMillan's own published treatment of this exact structure (read directly
  this session - verified-primary for the McMillan variant):** "Covered
  Writing Against LEAPS", reprint of *The Option Strategist* newsletter
  **Vol. 10, No. 5, 2001-03-08**, on McMillan's own site:
  https://www.optionstrategist.com/blog/2020/11/covered-writing-against-leaps-1005 .
  His variant: "buy a LEAPS call option that is slightly in-the-money - with
  perhaps two years or so until expiration" and repeatedly write short-term
  (his example: quarterly) calls against it; thesis that "repeatedly writing
  short-term calls should completely cover the cost of the LEAPS call after a
  year or so". NOTE the divergence: McMillan's 2001 form is *slightly* ITM; the
  tastytrade canon we implement is *deep* ITM. We follow the tastytrade form;
  the McMillan variant is recorded, not implemented.
- **tastytrade research segments (episode pages NOT readable this session):**
  Market Measures "Bullish Diagonals: The Poor Man's Covered Call"
  (2016-03-29) and Mike & His Whiteboard "Trade Checklist | Poor Man's Covered
  Call" (2016-04-21) exist (episode listings found) but the episode pages are
  video-JS shells that would not render. The 2016 study's METHODOLOGY is
  consistently recapped by independent secondaries [verified-secondary]: SPY
  2005–2016; long ATM ~50-delta calls tested at 60/90/120/150/180/210/240/
  270/300 DTE; sell 30-delta call nearest 30 DTE; hold until the short call
  expires; metrics = win ratio, P/L after short expiry, and return on capital
  vs long-call DTE. The study's NUMERIC RESULTS remain unread - every result
  number attributed to these segments below is tagged [unverified].
- **Publication dates:** tastylive concepts page and tastytrade learn page
  undated (living, fetched 2026-07-19); McMillan newsletter 2001-03-08
  (reposted 2020-11); Option Alpha 2024-05-17; TradingBlock 2026-06-18;
  TradeStation 2026-04-07; moomoo 2026-07-09; Income Navigator 2026-06-16;
  ApexVol 2026-06-19; Days to Expiry 2026-01-06/2026-03-19; McMillan 5th ed.
  2012; tastytrade segments 2015–2017.

---

## 2. PUBLISHED UNIVERSE & OUR MAPPING

- **What the sources trade:** single stocks and ETFs generically - none of the
  read sources restricts the strategy to one underlying. tastytrade's learn
  page uses a generic "XYZ" example; Option Samurai frames it as "a shorter-term
  call option that's out-of-the-money on the same stock or ETF"; the tastytrade
  Market Measures study reportedly used SPY [unverified - episode unreadable].
  (Option Samurai citation:
  https://optionsamurai.com/blog/poor-mans-covered-call/ - quote located
  there 2026-07-19; it was missing from the §1 source list in the first
  draft.)
  The strategy is explicitly a *covered-call replacement*, so its natural
  habitat is anything you would covered-call: large-cap stocks and index ETFs.
- **Published universe exclusion (primary, verbatim):** "We never route poor
  man's covered calls in volatility instruments." (tastylive). Our universe
  contains no VXX/UVXY-class products, so the exclusion is satisfied by
  construction - recorded as a hard rule anyway (§8 row 31).
- **Our mapping:** SPY / QQQ / IWM plus the liquid mega-cap tier AAPL / NVDA /
  MSFT / TSLA / AMD / META. This is *inside* the published universe (liquid
  stocks and ETFs with listed LEAPS - all nine have LEAPS chains), so unlike
  most of our briefs there is no universe extension to flag.
- **Why the mapping preserves the edge claim:** the claimed edge is structural,
  not signal-based - replicate long-stock exposure with a deep-ITM LEAPS call
  at a fraction of the capital, then harvest short-dated call premium against
  it ("The Diagonal was about 6 times less than the conventional Covered Call
  on a delta equivalent basis" - tastytrade Market Measures episode blurb
  [unverified]). The mechanism (short-leg theta decays faster than long-leg
  theta; McMillan: own "the option that is not so subject to time decay" while
  selling "the option that is quite subject to time decay") is
  underlying-agnostic given liquid chains.
- **Options-only platform fit - NO adaptation needed on the stock axis:** the
  PMCC exists precisely to REMOVE the stock leg from a covered call. Both legs
  are options; no delta-hedging is published or needed. This is the rare
  strategy where our options-only constraint is the published form.
- **LOUD ADAPTATION FLAGS (two real ones):**
  1. **No assignment path in shadow.** American-style equity/ETF options mean
     the short call can be assigned early (esp. through ex-div - §7). Our
     shadow has no exercise/assignment simulation. Adaptation: rule 19 in §8
     (always close/roll ITM shorts before expiration - itself published
     doctrine) plus an assignment-suspect tag whenever a short ITM call's
     extrinsic is small near an ex-div date. Cash-settlement-by-mark of any
     would-have-been-assigned cycle overstates smoothness - graded trades
     crossing that condition must carry the tag.
  2. **Persistent long leg vs per-trade grading.** The published strategy is a
     campaign: ONE long LEAPS held ~a year while many short calls cycle against
     it. Our per-trade grading convention must define the unit: we grade each
     short-call cycle as a trade (entry = sell short call, exit = buy
     back/expire) AND grade the whole diagonal as a campaign at LEAPS
     disposal. Affected constants tagged ADAPTED in §8 (row 26).

---

## 3. EXACT ENTRY RULES

- **Structure (the trigger is structural - no market-timing signal is
  published):** "A poor man's covered call (PMCC) is a long call diagonal
  debit spread that is used to replicate a covered call position" - buy an ITM
  call "in a longer-term expiration cycle", sell an OTM call "in a near-term
  expiration cycle" (tastylive PRIMARY); "buying a longer-dated call at a
  lower strike" and "selling a shorter-dated call at a higher strike"
  (tastytrade learn page); PMCC variant buys "an ITM call instead of an
  ATM/OTM call" (same page); "you want to buy a deep-in-the-money (ITM) call
  while shorting an out-of-the-money (OTM) call" (moomoo). Long leg per the
  primary: "deep in-the-money (ITM)" with "high delta, so that the price of
  the call will move closely with the underlying stock price" (tastylive).
- **Long-leg delta:**
  - Default 0.80: "This bot uses 150 DTE and a 0.80 delta for the long call"
    (Option Alpha).
  - Published band: "a delta in the 0.70 to 0.85 range" (TradeStation); "we
    want a high delta, preferably above 0.75" (TradingBlock); "Consider buying
    a call with a delta above 0.75" (moomoo); "targeting 0.80-0.90 delta"
    (Days to Expiry); "Delta 0.80 or higher. Less and you're paying for too
    much extrinsic." (Income Navigator); "Delta: 0.70-0.85 (deep ITM so it
    tracks stock closely)" (ApexVol).
  - Upper cap rationale: "Going too deep (delta above 0.90) narrows the
    capital advantage over owning shares outright." (TradeStation).
- **Long-leg DTE:**
  - Published range: "a day-to-expiration of at least 90 days" (moomoo, the
    published floor); "150 DTE" (Option Alpha bot example); "6 to 12 months
    out" (TradeStation); "6-24 months out (12+ months ideal)" (Days to
    Expiry); "Days to expiration: 12 months or more. We prefer 14–18 months."
    (Income Navigator).
  - Our default honors the LEAPS name: nearest expiration ≥ 365 days (see §8
    row 6 for the recorded range).
- **Long-leg quality screen (extrinsic):** target "< 10% extrinsic value"
  in the LEAPS price (Days to Expiry); "Most of the LEAPS price should be
  intrinsic value" (ApexVol).
- **Short-leg delta:**
  - Default 0.30: "The bot opens a short call 30 days from expiration at the
    0.30 delta in this example." (Option Alpha).
  - Published band: "Stay below 0.30 delta to reduce the odds of assignment
    while still earning solid premium. Once you get above 0.35, assignment
    risk rises quickly." and "Avoid going below 0.15 delta, since premiums
    become too small to justify the trade." (TradingBlock); "a delta below
    0.35" (moomoo); "20–30" delta (Income Navigator); "0.30 delta (30%
    probability of assignment)" (Days to Expiry).
- **Short-leg DTE:**
  - Primary band: "Shorter-term ... 30 to 60 days out" (tastylive).
  - Default 30 (Option Alpha, above). Published range: "many traders sell
    short calls with 10 to 45 days to expiration to capture the steepest part
    of the decay curve" (TradingBlock); "fewer than 60 days to expire"
    (moomoo, outer cap); "21–35 DTE. Closer than 21 and gamma risk goes
    parabolic." (Income Navigator); "Start with 21-35 DTE. It's the Goldilocks
    zone for PMCC" (Days to Expiry); "Sell 30-45 DTE short calls and roll
    monthly" (ApexVol).
- **Extrinsic-coverage rule (PRIMARY entry constraint, distinct from the <10%
  screen above):** compute the long ITM call's extrinsic value at entry;
  "Once we figure that value, we ensure that the near term option we sell is
  equal to or greater than that amount." (tastylive) - i.e., short-call credit
  ≥ long-call extrinsic value. This guarantees that if the short cycle is
  fully collected, it pays for all the time value bought on the long leg.
- **Strike-floor rule (the classic PMCC no-lock-in-loss constraint):** "Always
  ensure short call strike is above your LEAPS cost basis to avoid a loss on
  assignment" (ApexVol); "Strike: above your LEAP strike. Non-negotiable." and
  "If your short call strike is below the LEAP strike and you get assigned,
  you've locked in a loss" (Income Navigator). Implemented as: short strike ≥
  long strike + net debit paid (per-share) - the cost-basis form.
- **Debit-vs-width rule (PRIMARY, verbatim):** "We also ensure that the total
  debit paid is not more than 75% of the width of the strikes." (tastylive).
  Secondary confirmation: "well within the recommended guideline of 75% or
  less of the strike width" (TradingBlock - note: that page's example
  arithmetic, "$8.24 for a 7-point diagonal spread", does not reduce to the
  "roughly 60%" it claims; the guideline constant 75% is quoted cleanly on
  both pages and is what we record).
- **IV / regime gate:** qualitative only - "ideally entering the entire PMCC
  when IV is relatively low and expected to rise" (TradingBlock). No numeric
  IV-rank threshold is published in any read source - numeric gate UNKNOWN; we
  log VIX percentile at entry as a tag, not a gate (§8 row 13).
- **Entry timing (time of day / T-n to events):** UNKNOWN - no read source
  publishes a time-of-day or event-relative entry rule. Platform scan-window
  policy (§8 row 14).

---

## 4. EXACT EXIT RULES

These override platform exit doctrine for this strategy.

- **Winner exit (PRIMARY doctrine):** positions are "closed for a winner if
  the stock price increases significantly in one expiration cycle"
  (tastylive). Qualitative in the source - no numeric threshold published;
  operationalized via row 21's whole-position profit take, with the tastylive
  trigger recorded as its doctrinal basis.
- **Loser management (PRIMARY doctrine):** "For losing trades due to the
  stock price decreasing, the short call can be rolled to a lower strike to
  collect more credit." (tastylive). CONSTRAINT from McMillan's worked
  failure example (Option Strategist Vol 10 No 5): rolling down too far
  inverts the structure - after his roll-down, "the debit (38) is greater
  than the difference in the strikes (20)", locking in an upside loss. We
  therefore never roll the short below the row-11 cost-basis floor: cumulative
  net debit must stay below the current strike width (ADAPTED inference from
  the quoted example; §8 row 33).
- **Re-write cadence (McMillan variant, recorded):** repeatedly write
  short-term calls against the resident LEAPS; "repeatedly writing short-term
  calls should completely cover the cost of the LEAPS call after a year or so"
  (McMillan 2001 - his example rolls quarterly; the tastytrade canon cycles
  per rows 15–18). This cost-recovery claim is a directly gradeable
  hypothesis (§10).
- **Short-call profit take:** close the short call at 30–50% of max profit - 
  "The last 50% of the premium is the slowest, most dangerous portion to
  collect." (Income Navigator); "30-50%
  profit" (Days to Expiry); fold variant "profit target, say half the maximum
  profit" (Data Driven Options). Default: buy back the short at 50% of the
  credit received, then sell the next cycle (subject to entry rules §3).
- **Short-call time/delta management (roll discipline):** "every two to three
  weeks the short leg gets rolled out in time" with delta thresholds
  (paraphrased from Data Driven Options - verbatim: "say below a 12 Delta in
  two weeks, I'd roll out", "moved to a Delta of 40 or more, I'd roll out",
  "between 12 and 40 ... wait until 21 days left to roll"): roll early if
  short delta < 0.12 or > 0.40; otherwise act at 21 DTE. Roll on strike touch: "Roll the short
  call when the stock touches the short strike. Up and out for a credit."
  (Income Navigator). General roll doctrine: "Before your short expires,
  you'll want to roll it out to another expiration within the above time
  range. Without the short component, you're simply holding a long call with
  high directional exposure and no income offset." (TradingBlock).
- **Never let an ITM short ride into expiration:** "Always close or roll
  before expiration if your short call is ITM" (Days to Expiry); "It is
  crucial to have a plan, like closing or rolling the position before
  expiration, if a short share assignment is not part of your strategy."
  (tastytrade learn page).
- **Long-LEAPS time exit:** "Roll the LEAP when it has less than 6 months
  remaining." (Income Navigator); exit signal "LEAP has < 6 months
  left...theta decay accelerates" (Days to Expiry). Our shadow CLOSES the
  campaign at this point rather than rolling (re-entry then re-qualifies via
  §3) - flagged ADAPTED in §8 row 20.
- **Whole-position profit take:** "Many traders exit when they've captured
  50–75% of the maximum potential profit or when the short call nears
  expiration." (TradingBlock); "25-40% on the total PMCC in a few months" /
  "If you've made 30-50% on the position, take the win" (Days to Expiry).
  Default: close the whole diagonal at 50% of its max profit (the lower bound
  shared across sources; max profit per moomoo formula, §8 row 28).
- **Loss management:** NO consensus hard stop is published. Fragments:
  "equal stop loss or slightly larger stop loss" than the profit target (Data
  Driven Options, its "fold" variant); qualitative exit "If the stock drops
  15-20% and shows no signs of recovery" (Days to Expiry); Option Alpha's bot
  example uses symmetric dollar exits "the profit is greater than $150 or the
  total P/L is -$150" (bot-template example, not doctrine). Hard numeric stop
  recorded UNKNOWN (§8 row 22) - the structural floor is max loss = debit
  paid: "The maximum loss of a poor man's covered call is the cost of
  executing the trade." (moomoo).
- **Hold-to-expiry doctrine:** explicitly rejected for the short leg (quotes
  above); for the long leg the published doctrine is dispose/roll at <6
  months, i.e. LEAPS are never held to expiry either.

---

## 5. SIZING CONVENTION IN SOURCE

- Sizing is per-spread debit; max loss = net debit paid (moomoo quote above).
- Portfolio-level guidance where published: "Cap any single PMCC at 5% of
  account, total PMCC exposure at 25%." (Income Navigator); "Never allocate
  more than 50-60% of your portfolio to PMCC positions" and "5-8 positions to
  diversify risk" (Days to Expiry). These conflict with each other - recorded
  for context only.
- Capital-efficiency framing: the long LEAPS costs "25-40% of stock price"
  (Days to Expiry) vs 100 shares; tastytrade's delta-equivalent buying-power
  claim ("about 6 times less") [unverified].
- **Our shadow always runs 1 published unit** (one 1-lot diagonal per
  underlying), account-blind - all portfolio-% guidance ignored by design.

---

## 6. DOCUMENTED PERFORMANCE

Honest finding: **no rigorous public tearsheet (CAGR / PF / max drawdown) for
the canonical PMCC recipe was readable this session.** What exists:

- McMillan on his own (slightly-ITM, 2-year) variant, read on his own site
  [verified-primary]: "there is roughly a 60% chance that the stock will be
  within that profit range at expiration", cautioned by "those 'improbable'
  events are generally more likely than one would normally envision", overall
  verdict "this strategy seems 'okay' but not great" (Option Strategist Vol
  10 No 5, 2001-03-08). Methodology: single worked example priced at 2001 IV
  levels (LEAPS 32% vs near-term 34%), model probability - not a backtest.
- tastytrade Market Measures "Bullish Diagonals" (2016-03-29): methodology as
  recapped by secondaries [verified-secondary]: SPY 2005–2016, long ATM
  50-delta calls at 60–300 DTE variants, short 30-delta call nearest 30 DTE,
  held to short-call expiry; metrics win ratio / P&L / ROC. Headline claim:
  diagonal required "about 6 times less" buying power "than the conventional
  Covered Call on a delta equivalent basis" [unverified - search-snippet of
  an unreadable episode page; no win rate / P&L numbers readable].
- A tastytrade PMCC-vs-covered-call study relayed by a third-party X post
  (@RolfOptions, 2025): 15-year SPY backtest; short leg 45 DTE / 30Δ; long
  deltas 60/70/80/90 across expirations 45/60/120 DTE and 1 year; conclusion
  that "70 delta and 60DTE provided a nice balance of capital efficiency" and
  PMCCs "were able to recreate almost all of the success of conventional
  covered calls" [unverified - third-hand tweet; episode not readable; note
  its capital-efficiency-optimal 60-DTE long is NOT the LEAPS form we
  implement].
- Data Driven Options (read directly): "greater than 50% probability of
  profit" at entry; illustrative path "if price goes up from 100 to 102 in 21
  days, the profit is around $150, a 20% return on capital for a 2% move";
  position "half as volatile as owning 100 shares of stock for a cost
  equivalent to about 7.5% of owning 100 shares" [verified-secondary - 
  model-based illustration, not a backtest].
- ApexVol (read directly): "That is a 9.1% return on capital in 45 days.
  Repeat 8 times per year for potential annualized income of 70%+"
  [verified-secondary - single worked example extrapolated; marketing-grade,
  no drawdown/win-rate methodology].
- Days to Expiry (read directly): PMCC "12.5% per month" vs "4% per month"
  traditional covered call [verified-secondary - illustrative comparison, no
  stated methodology; treat as promotional].
- CAGR: UNKNOWN. Win rate: UNKNOWN. Profit factor: UNKNOWN. Max drawdown:
  UNKNOWN. Grading must be built from our own shadow ledgers; the e-process
  grader should treat this family as having NO published performance prior.

---

## 7. KNOWN FAILURE MODES

- **Early assignment through ex-div (structural, the classic PMCC accident):**
  "Early assignment risk increases around ex-dividend dates when short calls
  are deep in the money and extrinsic value is small." (TradeStation). If
  assigned, "you'll be required to deliver shares you don't actually own,
  which effectively creates a short stock position" (TradingBlock). All nine
  of our underlyings except (currently) TSLA/AMD have dividends or
  distributions - SPY/QQQ/IWM quarterly ex-divs are the scheduled hazard.
  Shadow has no assignment path → assignment-suspect tagging (§2, §8 row 23).
- **Crash on the long leg (Mar-2020 type):** a deep-ITM 0.80Δ LEAPS loses
  near-stock-like dollars in a fast selloff while the ~0.30Δ short call
  offsets only a sliver; max loss is the whole debit - which is a LARGER
  percentage loss than stock takes, since the debit is ~25–40% of the stock
  price absorbing ~0.8 of the stock's dollar move. The "capital-efficient"
  framing inverts into leverage on the way down.
- **Bear-grind (2022 type):** repeated down-months walk the stock below the
  LEAPS strike; delta bleeds from 0.80 toward 0.50, the position stops
  behaving like stock, short-call income shrinks (calls sold against a falling
  tape at 0.30Δ collect less), and the <10%-extrinsic entry becomes a
  30%+-extrinsic hold. Days to Expiry's qualitative exit ("stock drops 15-20%
  and shows no signs of recovery") exists because of this mode.
- **Melt-up through the short strike (NVDA-2023/24 type):** upside is capped
  at the short strike each cycle; a gap through the short strike converts the
  position to its (bounded) max profit and then underperforms the runaway
  stock - the strategy's regret mode. Touch-roll "up and out for a credit"
  (Income Navigator) mitigates but often rolls into the run repeatedly.
  Whipsaw variant (Aug-2024 vol spike): stock craters (long leg marks down),
  then rips back above the rolled-down short strike - sell-low/cap-low
  sequencing loss. If strikes are set too close (row-12 violation), a big
  enough rally loses outright: "losses occur on both ends, if the stock moves
  far enough" and it fails when "the striking prices are too close together"
  (McMillan, Option Strategist Vol 10 No 5).
- **Roll-down death spiral (McMillan-documented):** successive credit
  roll-downs after declines shrink the strike width until the structure
  inverts - his example ends with "the debit (38) is greater than the
  difference in the strikes (20)", i.e. a locked-in upside loss. Guard: §4
  roll-down constraint / §8 row 33.
- **Volatility instruments:** excluded outright by the primary - "We never
  route poor man's covered calls in volatility instruments." (tastylive).
  N/A for our nine names but binding if the universe ever widens.
- **IV-crush on entry (vega trap):** the LEAPS is long ~all the vega;
  entering when IV is elevated then normalizing marks the long leg down even
  if spot holds - this is why TradingBlock publishes "entering the entire
  PMCC when IV is relatively low and expected to rise". Feb-2018
  Volmageddon-style spikes are the mirror: they mark open LEAPS up briefly
  but crush new-entry economics.
- **Extrinsic mismatch (slow structural bleed):** if the LEAPS is bought with
  fat extrinsic (screen row 7 violated) the short-call credits fail to outrun
  the long leg's own theta - the "theta positive spread" premise silently
  inverts. moomoo's max-profit condition ("If the short call's extrinsic
  value drops to zero, the position will have reached the greatest potential
  for profit") only holds when the long leg kept its value.
- **Liquidity on far-dated legs:** LEAPS chains on single names quote wide;
  entry/exit slippage on the long leg can eat several short-cycle credits.
  (Days to Expiry screens "spread < 2% of the mid-price" on the LEAPS.)
- **Correlated campaign risk:** all nine symbols are equity-beta; one market
  crash marks down all nine long legs simultaneously - lane grading, not
  pooled grading.

---

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | underlying_universe | SPY, QQQ, IWM + AAPL, NVDA, MSFT, TSLA, AMD, META | PLATFORM-POLICY | Sources trade generic liquid stocks/ETFs ("on the same stock or ETF" - Option Samurai); all nine have listed LEAPS - inside the published universe. |
| 2 | long_leg_type | deep-ITM call, far-dated | SOURCE-VERBATIM | "deep in-the-money (ITM)" with "high delta" - tastylive (primary); PMCC buys "an ITM call instead of an ATM/OTM call" - tastytrade learn page; "deep-in-the-money (ITM) call" - moomoo |
| 3 | long_delta_target | 0.80 | SOURCE-RANGE (0.70–0.90; default 0.80) | "a 0.80 delta for the long call" - Option Alpha; "0.70 to 0.85 range" - TradeStation; "0.80-0.90" - Days to Expiry |
| 4 | long_delta_min | 0.70 | SOURCE-VERBATIM | "a delta in the 0.70 to 0.85 range" - TradeStation; "Delta: 0.70-0.85" - ApexVol |
| 5 | long_delta_max | 0.90 | SOURCE-VERBATIM | "Going too deep (delta above 0.90) narrows the capital advantage over owning shares outright." - TradeStation |
| 6 | long_dte_entry | nearest expiration ≥ 365 days; accept 365–545 | SOURCE-RANGE (published 90 DTE–24 months; default 12+ months) | "at least 90 days" - moomoo; "150 DTE" - Option Alpha; "6-24 months out (12+ months ideal)" - Days to Expiry; "Days to expiration: 12 months or more. We prefer 14–18 months." - Income Navigator |
| 7 | long_extrinsic_max_pct | ≤ 10% of LEAPS price | SOURCE-VERBATIM | target "< 10% extrinsic value" - Days to Expiry; "Most of the LEAPS price should be intrinsic value" - ApexVol |
| 8 | short_delta_target | 0.30 | SOURCE-VERBATIM | "a short call 30 days from expiration at the 0.30 delta" - Option Alpha |
| 9 | short_delta_band | 0.15–0.35 | SOURCE-VERBATIM | "Stay below 0.30 delta... above 0.35, assignment risk rises quickly." + "Avoid going below 0.15 delta" - TradingBlock; "below 0.35" - moomoo |
| 10 | short_dte_target | 30 | SOURCE-RANGE (primary band 30–60; secondaries 10–45 / 21–35; default 30) | "30 to 60 days out" - tastylive (primary); "30 days from expiration" - Option Alpha; "10 to 45 days" - TradingBlock; "21–35 DTE" - Income Navigator; "fewer than 60 days" cap - moomoo |
| 11 | short_strike_floor | short strike ≥ long strike + net debit/share (cost basis) | SOURCE-VERBATIM | "Always ensure short call strike is above your LEAPS cost basis to avoid a loss on assignment" - ApexVol; "Strike: above your LEAP strike. Non-negotiable." - Income Navigator |
| 12 | max_debit_pct_of_width | ≤ 75% of (short strike − long strike) | SOURCE-VERBATIM | "We also ensure that the total debit paid is not more than 75% of the width of the strikes." - tastylive (primary); confirmed "guideline of 75% or less of the strike width" - TradingBlock |
| 13 | iv_entry_gate | none numeric; tag VIX 1-yr percentile at entry (prefer low) | SOURCE-RANGE (qualitative only) + PLATFORM-POLICY tag | "ideally entering the entire PMCC when IV is relatively low and expected to rise" - TradingBlock; numeric threshold UNKNOWN in all read sources |
| 14 | entry_time_of_day | UNKNOWN in source; platform: single consistent RTH scan window | PLATFORM-POLICY | No published time-of-day rule found. |
| 15 | short_profit_take_pct | buy back short at 50% of credit | SOURCE-RANGE (30–50%; default 50%) | "Close the short call at 30–50% of max profit." - Income Navigator; "say half the maximum profit" - Data Driven Options |
| 16 | short_roll_dte | act at 21 DTE when short delta in 0.12–0.40 | SOURCE-VERBATIM | "If however, the price keeps Delta between 12 and 40, let's just keep collecting Theta and wait until 21 days left to roll." - Data Driven Options |
| 17 | short_roll_delta_triggers | roll early if short delta < 0.12 or > 0.40 | SOURCE-VERBATIM | "say below a 12 Delta in two weeks, I'd roll out" / "moved to a Delta of 40 or more, I'd roll out" - Data Driven Options |
| 18 | short_touch_roll | on stock touch of short strike: roll up and out, credit required | SOURCE-VERBATIM | "Roll the short call when the stock touches the short strike. Up and out for a credit." - Income Navigator |
| 19 | short_itm_expiry_rule | never hold ITM short into expiration - close or roll | SOURCE-VERBATIM | "Always close or roll before expiration if your short call is ITM" - Days to Expiry; "closing or rolling the position before expiration" - tastytrade learn page |
| 20 | leaps_exit_dte | close campaign when long leg < 180 days (6 months) remain | SOURCE-VERBATIM value, ADAPTED action | "Roll the LEAP when it has less than 6 months remaining." - Income Navigator; source rolls, our shadow closes + re-qualifies (flagged §4) |
| 21 | position_profit_take_pct | close whole diagonal at 50% of max profit | SOURCE-RANGE (50–75% TradingBlock; 25–50% Days to Expiry; default 50%) | "exit when they've captured 50–75% of the maximum potential profit" - TradingBlock; "If you've made 30-50% on the position, take the win" - Days to Expiry |
| 22 | hard_stop_loss | UNKNOWN - no consensus published; structural floor = debit paid; log-only qualitative tag if stock −15% from entry | UNKNOWN + PLATFORM-POLICY tag | "The maximum loss ... is the cost of executing the trade." - moomoo; "If the stock drops 15-20% and shows no signs of recovery" - Days to Expiry (qualitative); "equal stop loss or slightly larger" - Data Driven Options (variant) |
| 23 | exdiv_assignment_guard | tag short-ITM cycles near ex-div as assignment-suspect; numeric extrinsic threshold UNKNOWN | PLATFORM-POLICY | "Early assignment risk increases around ex-dividend dates when short calls are deep in the money and extrinsic value is small." - TradeStation (qualitative; no number published) |
| 24 | earnings_gate | none (faithful to published form); single-name short cycles spanning earnings TAGGED, not blocked | PLATFORM-POLICY | No earnings rule in any read source. |
| 25 | strike_selection_tolerance | nearest listed strike to target delta; tie → further-OTM (short) / deeper-ITM (long) | PLATFORM-POLICY | No published tolerance - UNKNOWN in source. |
| 26 | trade_unit_definition | grade each short-call cycle as a trade; grade full diagonal as a campaign at LEAPS disposal | ADAPTED | Published form is a campaign ("sell multiple covered calls over the life of the LEAP to reduce your cost basis" - Option Alpha); our ledger needs per-trade units. |
| 27 | position_size | 1 diagonal (1 lot per leg), account-blind | PLATFORM-POLICY | Shadow convention; source portfolio-% guidance (§5) ignored. |
| 28 | liquidity_gate | both legs: bid > 0, OI ≥ 100, spread ≤ 15% of mid (long leg also: spread ≤ 2% of mid preferred) | PLATFORM-POLICY (long-leg 2% figure SOURCE-VERBATIM) | "spread < 2% of the mid-price" on the LEAPS - Days to Expiry; rest ours. |
| 29 | capital_at_risk_basis | net debit paid (= max loss) | SOURCE-VERBATIM | "The maximum loss of a poor man's covered call is the cost of executing the trade." - moomoo |
| 30 | max_profit_formula | width of call strikes − net trade cost (per cycle snapshot) | SOURCE-VERBATIM | "Max Profit = Width of call strikes – Trade cost" - moomoo |
| 31 | vol_instrument_exclusion | never trade PMCC on volatility products (VXX/UVXY class) | SOURCE-VERBATIM | "We never route poor man's covered calls in volatility instruments." - tastylive (primary); satisfied by construction on our universe |
| 32 | short_credit_ge_long_extrinsic | at entry: short-call credit ≥ long call's extrinsic value | SOURCE-VERBATIM | "we ensure that the near term option we sell is equal to or greater than that amount [the long call's extrinsic value]" - tastylive (primary) |
| 33 | loser_roll_down | on stock decline: short call may be rolled DOWN for additional credit | SOURCE-VERBATIM | "the short call can be rolled to a lower strike to collect more credit" - tastylive (primary) |
| 34 | roll_down_debit_floor | roll-downs must keep cumulative net debit < current strike width (and respect row 11) | ADAPTED | inference from McMillan's documented failure: after over-rolling, "the debit (38) is greater than the difference in the strikes (20)" - Option Strategist Vol 10 No 5 |

Constants recorded as UNKNOWN in-source: numeric IV/IVR entry gate (row 13),
entry time of day (row 14), hard stop-loss (row 22), ex-div extrinsic
threshold (row 23), strike tolerance (row 25), winner-exit numeric threshold
(tastylive's "increases significantly" - §4), and all headline performance
numbers (§6). McMillan chapter locator is now VERIFIED (Ch. 25 "LEAPS", §1);
the chapter text itself remains unread.

---

## 9. DATA REQUIREMENTS

- **Tradier chains - TWO bands per underlying:**
  1. Short leg: 10–60 DTE (scan for the 0.30Δ call nearest 30 DTE; continuous
     quotes on the held short through its cycle).
  2. Long leg: 365–730+ DTE (LEAPS expirations - verify Tradier serves the
     Jan-LEAPS strikes with usable quotes; far-dated single-name quotes are
     wide and greeks may be stale → compute delta from mid-IV when the feed's
     greeks are missing/stale).
- **Dividend / ex-div calendar:** REQUIRED for row 23 (assignment-suspect
  tagging). NOTE: this is NOT in the platform's standard data menu (chains /
  earnings / FOMC / VIX / history) - flagging the gap loudly; SPY/QQQ/IWM
  quarterly ex-div dates are predictable and can be seeded manually until a
  feed exists.
- **Earnings calendar (date + bmo/amc):** needed only for TAGGING single-name
  short cycles that span earnings (row 24) - not a gate.
- **FOMC/CPI dates:** not required - no published event rule.
- **VIX regime:** daily VIX close + 1-year percentile for the row-13 entry
  tag. IV rank per-underlying preferred once the archive warms (our IV archive
  is cold → VIX-percentile fallback; single-name caveat: VIX understates
  name-specific IV states).
- **Daily history:** required - marks, the −15% qualitative tag (row 22), and
  touch-detection support.
- **1-min bars:** NOT required for entries; desirable for row 18
  (touch-of-short-strike detection intraday). Acceptable degraded mode: use
  daily high ≥ short strike as the touch proxy, evaluated EOD - log which
  detector fired.
- **Mark cadence:** EOD marks on both legs every session; additionally mark at
  every management trigger (short at 50% credit, 21 DTE, touch, roll). No
  continuous intraday marking needed.

---

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** with all 9 underlyings running one diagonal each,
  short-call cycles complete roughly every 2–4 weeks (30 DTE entry, 50%-credit
  take or 21-DTE action) → ~1.3 cycles/symbol/month ≈ **12 graded short-cycle
  trades/month**, plus ~9 campaign entries at bootstrap and ~1 campaign
  disposal/symbol/year. If the platform stages fewer symbols initially, scale
  linearly (~1.3/month per symbol). N≥25 per lane arrives in ~2 months at full
  deployment for the pooled short-cycle lane; campaign-level lane accrues
  ~9/year - campaign grading will be slow by construction, say so in reports.
- **Mark cadence needed:** EOD both legs + event-triggered (see §9). The long
  leg's wide quotes make mid-marks noisy - persist bid/ask/mid and mark
  campaigns on mid with spread recorded, so WORST-grade can re-mark at bid.
- **Multi-leg shape:** 2-leg diagonal, same underlying, 1:1 ratio - long call
  (far-dated, deep ITM) + short call (near-dated, OTM). The long leg PERSISTS
  across short cycles: order/ledger model must support a resident leg with
  rotating opposing legs (same shape as a covered-call book, not a one-shot
  spread). Rolls (rows 16–18) are close+open pairs in the ledger, each leg
  filled separately.
- **Per-family capital-at-risk basis: debit paid** (row 29). Campaign CaR =
  initial net debit; per-cycle CaR for short-cycle grading = campaign debit
  outstanding at cycle open (net of credits collected to date) - record both;
  do NOT use Reg-T CaR (no naked exposure exists; max loss is the debit).
- **1-lot account-blind distortions:** (a) portfolio caps (5%/25%,
  50–60%, 5–8 positions) are ignored - no distortion of per-trade economics,
  only of portfolio claims; (b) the published "reduce your cost basis" compounding
  narrative is bookkeeping - our per-cycle P&L capture is equivalent; (c) the
  real distortion is NO ASSIGNMENT PATH: every would-have-been-assigned cycle
  settles by mark instead of by short-stock creation + unwind. Tag these (row
  23) and report them separately - an assignment-heavy month graded by marks
  will look better than reality.
- **Regret asymmetry to watch in grading:** this family's failure signature is
  not blowups (max loss bounded at debit) but slow modes - extrinsic bleed
  (row 7 violations), bear-grind delta decay, and capped melt-ups. The WORST
  grader should compare each campaign against a buy-and-hold-LEAPS-only
  counterfactual (same long leg, no shorts) to isolate whether the short-call
  overlay actually added premium net of caps - that comparison is the
  strategy's entire published claim. Additionally track cumulative short-call
  credits vs the campaign's initial debit: McMillan's published thesis that
  "repeatedly writing short-term calls should completely cover the cost of
  the LEAPS call after a year or so" is a directly falsifiable per-campaign
  metric.
- **Do not confuse this family with `atm_calendar_low_iv`:** both are
  time-spreads, but the PMCC's long leg is deep-ITM stock-replacement (delta
  edge) while the calendar's is ATM (vega/theta edge). Lane keys must stay
  separate.

---

## 11. VERIFICATION

- **Verdict: CORRECTED** (adversarial fresh-context verification pass,
  2026-07-19).
- **What was checked:** every constant in §3, §4, and §8 tagged
  SOURCE-VERBATIM or SOURCE-RANGE was re-located by independently fetching
  the cited pages this session: tastylive PMCC page (all eight primary
  claims: diagonal-debit definition, deep-ITM/high-delta long, 30–60 DTE OTM
  short, 75%-of-width debit cap, short-credit ≥ long-extrinsic rule, winner
  "increases significantly" doctrine, roll-down-for-credit loser doctrine,
  volatility-instrument exclusion - ALL verbatim on the page); tastytrade
  learn long-call-diagonal page (structure sentence and ITM-variant sentence
  found verbatim; the close-or-roll-before-expiration sentence found);
  Option Alpha (150 DTE / 0.80Δ long, 30 DTE / 0.30Δ short, $150 symmetric
  bot exits, cost-basis campaign quote, 2024-05-17 update date - all
  verbatim); TradingBlock (0.75 long-delta preference, 0.15/0.30/0.35 short
  bands, 10–45 DTE, 75%-of-width guideline + the brief's note about that
  page's broken "$8.24 / 7-point ≈ 60%" arithmetic, 50–75% whole-position
  take, IV-low entry preference, roll doctrine, short-stock assignment
  quote, Michael Martin / 2026-06-18 - all verbatim); TradeStation
  (0.70–0.85 band, >0.90 warning, 6–12 months, ex-div assignment quote,
  2026-04-07 - all verbatim); moomoo (deep-ITM quote, 0.75Δ/90-DTE floor,
  0.35Δ/60-DTE short caps, max-profit formula, max-loss quote,
  extrinsic-zero condition, 2026-07-09 - all verbatim); Income Navigator
  (0.80+ delta, 12-months/14–18-months, 20–30Δ, 21–35 DTE gamma quote,
  strike-floor "Non-negotiable" + locked-in-loss quotes, last-50%-slowest
  quote, touch-roll "Up and out for a credit", <6-months LEAP roll, 5%/25%
  caps, 2026-06-16 - all verbatim); ApexVol (0.70–0.85, 30–45 DTE roll
  monthly, cost-basis floor quote, intrinsic-value quote, 9.1%/70%+ example,
  authors + 2026-06-19 - all verbatim); Days to Expiry (0.80–0.90, 6–24
  months, <10% extrinsic, 21–35 DTE Goldilocks, 0.30Δ, ITM-short
  close-or-roll rule, <6-months theta quote, 15–20% qualitative exit,
  25–40%-of-stock cost, 2%-spread screen, 50–60%/5–8 allocation, 12.5%-vs-4%
  promo figures, dates - all verbatim); Data Driven Options (2–3-week roll
  cadence, 12/40 delta triggers, 21-days-left rule, >50% POP, $150/20%/2%
  illustration, half-as-volatile/7.5% quote, hold/fold/roll - all present;
  the 12/40/21 rule was a compressed paraphrase presented in quote marks in
  the first draft, now fixed to verbatim); McMillan Option Strategist Vol 10
  No 5 reprint on optionstrategist.com (slightly-ITM two-year variant, 60%
  probability, "okay but not great" verdict, debit-38-vs-width-20 failure
  example, both-ends-loss quotes, 32%/34% IVs, volume/date - all verbatim);
  optionstrategist.com product page (Chapter 25 "LEAPS" with all eight
  listed section headings - verbatim); Penguin Random House page (edition,
  ISBN, 1072 pp, LEAPS bullet - verbatim); kriminiltrading review (time-decay
  rationale quote - verbatim); Option Samurai blog (the "same stock or ETF"
  quote - located, URL added in §2); tastytrade Market Measures episode
  metadata (episode exists dated 2016-03-29; SPY-2005+/60–300-DTE/30Δ-30DTE
  methodology recap and the "about 6 times less" blurb corroborated by an
  independent recap - brief's [verified-secondary]/[unverified] tagging is
  accurate and conservative).
- **Result: ZERO invented constants.** Every SOURCE-VERBATIM and
  SOURCE-RANGE value in §3/§4/§8 was located in its cited source. All
  [verified-primary]/[verified-secondary] performance items in §6 were
  found; everything not locatable was already tagged [unverified] or UNKNOWN
  by the brief itself. ADAPTED tags (rows 20, 26, 34; §2 flags) carry real
  rationales and none is presented as published.
- **Corrections applied (all minor):** (1) McMillan cost-recovery quote
  restored to "after a year or so" (was truncated to "after a year") in §1,
  §4, §10; (2) Data Driven Options 12/40/21 roll rule re-rendered as
  verbatim quotes instead of a quoted paraphrase (§4, §8 rows 16–17);
  (3) Income Navigator DTE quote corrected to "Days to expiration: 12 months
  or more. We prefer 14–18 months." (§3, §8 row 6); (4) Income Navigator
  last-50% quote completed ("slowest, most dangerous portion to collect")
  and the 30–50% figure moved outside quote marks (§4); (5) McMillan caution
  quote restored to "those 'improbable' events..." (§6); (6) Option Samurai
  URL added (§2) - it was quoted in §2/§8 row 1 without a citation.
- **Residual doubts:** §8 row 15's locator sentence "Close the short call at
  30–50% of max profit." was confirmed as the page's guidance (30–50% is on
  the page) but its exact sentence form was not independently re-read
  character-for-character; the tastylive extrinsic-coverage lead-in "Once we
  figure that value," was not re-confirmed verbatim (the operative clause
  was); the tastytrade Market Measures NUMERIC results and the @RolfOptions
  15-year study remain unverified exactly as the brief tags them; the
  McMillan book chapter TEXT remains unread (TOC only) - the brief already
  states this and attributes no constant to it. None of these is
  load-bearing.
- Verified by fresh-context adversarial pass, 2026-07-19.
