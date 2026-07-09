import {
  Sparkles,
  Crosshair,
  Wallet,
  History,
  FlaskConical,
  Trophy,
  SlidersHorizontal,
  Gauge,
  ListChecks,
  HandCoins,
  ShieldCheck,
  CheckCircle2,
  Wrench,
  Map,
  ArrowRight,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Card, Badge } from "@/components/ui";
import { cn } from "@/lib/utils";

/**
 * Client-facing "What's New" / update guide. Everything added since the last
 * stable version, in plain English — grouped by theme, followed by the latest
 * reliability fixes and an honest note on what is deliberately NOT automated.
 */
export default function WhatsNewPage() {
  return (
    <div className="max-w-4xl mx-auto pb-16">
      {/* ── Hero ───────────────────────────────────────────── */}
      <div className="text-center py-8">
        <div className="inline-flex items-center gap-2 rounded-full border border-brand/30 bg-brand/10 px-3 py-1 text-xs font-semibold text-brand mb-4">
          <Sparkles className="h-3.5 w-3.5" /> What's New
        </div>
        <h1 className="text-3xl sm:text-4xl font-extrabold text-white leading-tight">
          Everything added<br className="hidden sm:block" /> since your last version
        </h1>
        <p className="text-gray-400 mt-4 max-w-2xl mx-auto leading-relaxed">
          Ten upgrades across three areas — a brand-new{" "}
          <span className="text-gray-200 font-medium">options income engine</span>, a way to{" "}
          <span className="text-gray-200 font-medium">test AI models</span> against each other, and a
          rebuilt <span className="text-gray-200 font-medium">safer portfolio core</span>. The one rule
          never changed: <span className="text-gray-200 font-medium">the platform suggests, you decide.
          Nothing trades on its own.</span>
        </p>
      </div>

      {/* ═══ THEME 1 — Options income engine ═══════════════════ */}
      <Theme
        tag="New module"
        title="An options income engine"
        blurb="A completely separate segment that turns the strong stocks the platform already finds into an options play — buying a stock's expected earnings jump when the market is pricing it too cheaply, then getting out before the announcement. It is walled off from your equity portfolio and never touches its cash."
      >
        <FeatureCard
          icon={<Crosshair className="h-5 w-5" />}
          title="Earnings-Straddle Scanner"
          badge="S&P 500"
          to="/options"
          linkLabel="Open Scanner"
          what="Every weekday it scans the whole S&P 500 (plus your watchlist and holdings) for stocks whose upcoming earnings move looks underpriced — where the options market expects a smaller jump than the stock has actually made on its past 8–12 earnings. It ranks how cheap each one is, stars any that your AI research also loves ('dual signal'), and — importantly — lists what it rejected and exactly why (too pricey, thin trading, wide spread). Suggest-only, with a plain-English Telegram digest when something qualifies."
        />
        <FeatureCard
          icon={<Wallet className="h-5 w-5" />}
          title="Paper Positions + P&L Breakdown"
          to="/options/positions"
          linkLabel="Open Positions"
          what="'Track' any candidate as a practice trade and follow it live. Each morning it re-prices the trade and tells you — in everyday language — WHERE the profit or loss came from: rising anticipation, the stock actually moving, or time decay. It sets a hard 'exit by' deadline the day before earnings and sends escalating Telegram warnings as it nears, so you always sell before the print. It re-plans automatically if a company moves its earnings date, and keeps a running record (win rate, average win/loss). It never sells for you."
        />
        <FeatureCard
          icon={<History className="h-5 w-5" />}
          title="Track Record (Historical Backtest)"
          what="For any stock the scanner flags or rejects, a 'Track record' link shows how this exact strategy would really have performed on that stock's past earnings — using genuine historical option prices, not estimates. It walks event by event (what was implied, what the stock really did, whether it would have qualified, what the trade returned) using only information available at the time — no hindsight. And it's honest about data it can't trust: if a stock split makes old numbers unreliable, it skips that event and says so rather than showing a bogus figure. This turns 'trust me' into evidence."
        />
      </Theme>

      {/* ═══ THEME 2 — AI model lab ════════════════════════════ */}
      <Theme
        tag="New tools"
        title="A lab to test AI models against each other"
        blurb="Evidence for a real decision: are cheaper / open-source AI models good enough to replace or supplement the premium ones — and is buying dedicated hardware worth it? Both tools are isolated from the live pipeline."
      >
        <FeatureCard
          icon={<FlaskConical className="h-5 w-5" />}
          title="Model Lab — Compare Mode"
          to="/model-lab"
          linkLabel="Open Model Lab"
          what="Runs the same stock through several AI models at once (Claude alongside open models like DeepSeek, GLM and Qwen) and lays their answers side by side — verdict, conviction, target, stop, bull case, bear case, and the tiny cost of each run. A banner tells you at a glance whether they agree. Since every model gets identical data, you're comparing the models themselves."
        />
        <FeatureCard
          icon={<Trophy className="h-5 w-5" />}
          title="Full-Pipeline Bake-off + Scorecard"
          to="/pipeline-test"
          linkLabel="Open Pipeline Test"
          what="The deep version: it runs the platform's COMPLETE 11-analyst pipeline end-to-end on each model stack and compares them expert-by-expert, down to the final client message, cost and time. You choose which models to include (the pricey premium one is off by default). Every run is saved to a growing History, and a Scorecard accumulates across all your tests — how often each model agreed with production, average conviction, reliability, cost and speed. A running evidence base for the 'buy the hardware or not' call."
        />
      </Theme>

      {/* ═══ THEME 3 — Safer portfolio core ════════════════════ */}
      <Theme
        tag="Rebuilt"
        title="A safer, smarter portfolio core"
        blurb="The heart of the platform got more trustworthy: the AI now tailors risk to each stock, the best ideas are no longer held back, and — most importantly — automatic selling is switched off entirely. You manage every exit."
      >
        <FeatureCard
          icon={<SlidersHorizontal className="h-5 w-5" />}
          title="Dynamic, per-stock risk (AI sizing & stops)"
          what="Instead of treating every position the same, the AI now decides how big each holding should be and where its stop-loss sits on a stock-by-stock basis — larger for calmer high-conviction names, smaller for choppier ones, with each stop set from that stock's own volatility. Every decision carries a one-line plain-English reason. It also re-rates open positions daily (hold / trim / add / adjust stop) as a suggestion — always within the hard per-stock cap you set."
        />
        <FeatureCard
          icon={<Gauge className="h-5 w-5" />}
          title="Fixed conviction score"
          what="Corrects a flaw where the confidence rating was tied to how lopsided the internal bull-vs-bear debate was, which quietly capped scores so genuinely strong buys never got a full-size green light. Conviction now reflects the real strength of the case (7–8 for a normal strong idea, 9–10 for exceptional) — so your best opportunities are no longer artificially throttled."
        />
        <FeatureCard
          icon={<ListChecks className="h-5 w-5" />}
          title="Editable position limit & per-stock cap"
          badge="Default 30 / ≤10%"
          to="/"
          linkLabel="Portfolio settings"
          what="Two guardrails you control from the Portfolio page. The maximum number of holdings is now editable (default 30, up from a fixed 20) — the AI honors it, and adding beyond it is blocked with a clear message instead of failing silently. And a hard maximum weight for any single stock (default 10% of the fund) the AI must size within, so concentration can't creep past your comfort. Changing these never disturbs existing holdings."
        />
        <FeatureCard
          icon={<HandCoins className="h-5 w-5" />}
          title="Automatic selling disabled (notify-only)"
          badge="You decide"
          what="The system will never sell a position on its own again. The two paths that used to auto-close trades (a trailing stop, and the morning cycle acting on 'exit' calls) now send a single Telegram alert suggesting the action and leave the position untouched. A stop alert won't spam you — it fires once per breach and re-arms only if the price recovers and dips again. There's also a new 'undo a close' to restore any position closed by mistake (it reverses the cash too)."
        />
        <FeatureCard
          icon={<ShieldCheck className="h-5 w-5" />}
          title="Outage-proof AI (automatic backup model)"
          what="When the primary AI is overloaded and refuses requests — which used to fail an entire stock's analysis — the platform now quietly retries and, if the outage persists, switches to a backup model automatically and carries on, validating its answer just like the primary's. Invisible in normal use; the benefit is simply that research keeps succeeding through provider outages."
        />
      </Theme>

      {/* ═══ Latest reliability fixes ══════════════════════════ */}
      <section className="mt-12">
        <div className="flex items-center gap-3 mb-2">
          <span className="h-8 w-8 rounded-lg bg-warn/15 text-warn flex items-center justify-center shrink-0">
            <Wrench className="h-4.5 w-4.5" />
          </span>
          <div>
            <h2 className="text-lg font-bold text-white">Latest reliability fixes</h2>
            <p className="text-xs text-gray-500">
              An independent audit of the new options backtest caught three accuracy bugs — all now fixed.
            </p>
          </div>
        </div>
        <div className="space-y-2.5 mt-4">
          <FixRow
            title="Backtest prices were read one day early on the server"
            detail="The Track Record backtest was matching option prices against the wrong calendar day once deployed to the live (UTC) server — pulling each entry and exit price a trading day too early, or dropping events entirely. Now fixed to match the correct trading day regardless of server time zone, so the backtest reads the same on the live site as it does locally."
          />
          <FixRow
            title="Implied-move maths mixed two price scales"
            detail="On stocks that had a split or paid dividends between a past earnings date and today, the 'how cheap is this' calculation was comparing prices measured on two different scales, inflating the number. It now prices everything on one consistent, point-in-time scale — so cheapness on names with corporate actions is accurate."
          />
          <FixRow
            title="High-volatility names were being wrongly discarded"
            detail="A safety check meant to catch broken data was too strict and threw out legitimately high-volatility earnings events — the exact ones the strategy targets. The check is now a pure data-error backstop, so real high-vol candidates come through."
          />
        </div>
      </section>

      {/* ═══ What's deliberately NOT automated / roadmap ═══════ */}
      <section className="mt-12">
        <div className="flex items-center gap-3 mb-2">
          <span className="h-8 w-8 rounded-lg bg-brand/15 text-brand flex items-center justify-center shrink-0">
            <Map className="h-4.5 w-4.5" />
          </span>
          <h2 className="text-lg font-bold text-white">On the roadmap / by design</h2>
        </div>
        <p className="text-sm text-gray-400 mb-4">
          A few things are intentionally left out — either because they'd break the "you decide"
          principle, or because the data simply isn't available yet. Being upfront about them:
        </p>
        <div className="grid sm:grid-cols-2 gap-3">
          <RoadmapCard
            kind="By design"
            title="No auto-execution of options trades (Phase 4)"
            body="The options engine stops at 'here's a strong, cheap trade — and here's exactly when to get out.' It will not place or close option orders for you. That stays a deliberate manual step, same as the equity side."
          />
          <RoadmapCard
            kind="Data limit"
            title="No historical implied-volatility charts (yet)"
            body="Our data provider only computes implied volatility live, for today — there's no historical IV feed to buy. The backtest works around this by using real historical option prices directly, which is what actually matters. IV-over-time visuals would need us to compute it ourselves — a future nice-to-have."
          />
          <RoadmapCard
            kind="Operational"
            title="Scanner speed on the full S&P 500"
            body="Scanning 500 names calls the options data provider heavily and can hit its per-minute rate limit. The daily scan is paced to stay within it; a very large on-demand 'scan everything now' may need a moment. Not a correctness issue — just timing."
          />
          <RoadmapCard
            kind="Reminder"
            title="You still execute in your own broker"
            body="Every buy, sell and options trade happens in your real account, by you. The platform is your research desk and risk manager — it prepares the decision and the exit plan; you pull the trigger."
          />
        </div>
      </section>

      <p className="text-center text-xs text-gray-500 mt-12 max-w-xl mx-auto leading-relaxed">
        Everything here is additive — none of it changes how the core portfolio, watchlist or evening
        research already work. It only gives you more: a new income strategy, harder evidence, and a
        safer, more transparent core.
      </p>
    </div>
  );
}

// ── Building blocks ─────────────────────────────────────────────────────────
function Theme({
  tag, title, blurb, children,
}: {
  tag: string; title: string; blurb: string; children: React.ReactNode;
}) {
  return (
    <section className="mt-10">
      <div className="mb-4">
        <div className="inline-flex items-center gap-1.5 rounded-full border border-line bg-bg-hover/50 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-2">
          {tag}
        </div>
        <h2 className="text-xl font-bold text-white">{title}</h2>
        <p className="text-sm text-gray-400 mt-1.5 leading-relaxed">{blurb}</p>
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function FeatureCard({
  icon, title, what, badge, to, linkLabel,
}: {
  icon: React.ReactNode; title: string; what: string;
  badge?: string; to?: string; linkLabel?: string;
}) {
  return (
    <Card>
      <div className="flex items-center gap-3 mb-2 flex-wrap">
        <span className="h-9 w-9 rounded-lg bg-brand/15 text-brand flex items-center justify-center shrink-0">
          {icon}
        </span>
        <span className="font-bold text-white">{title}</span>
        {badge && (
          <Badge className="border-brand/40 bg-brand/10 text-brand">{badge}</Badge>
        )}
        {to && linkLabel && (
          <Link
            to={to}
            className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
          >
            {linkLabel} <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        )}
      </div>
      <p className="text-sm text-gray-300 leading-relaxed">{what}</p>
    </Card>
  );
}

function FixRow({ title, detail }: { title: string; detail: string }) {
  return (
    <Card className="flex gap-3 items-start border-line/70">
      <CheckCircle2 className="h-5 w-5 text-pos shrink-0 mt-0.5" />
      <div>
        <div className="text-sm font-semibold text-white">{title}</div>
        <p className="text-sm text-gray-400 mt-1 leading-relaxed">{detail}</p>
      </div>
    </Card>
  );
}

function RoadmapCard({ kind, title, body }: { kind: string; title: string; body: string }) {
  const tone =
    kind === "By design"
      ? "text-pos border-pos/30 bg-pos/10"
      : kind === "Data limit"
      ? "text-warn border-warn/30 bg-warn/10"
      : "text-gray-300 border-line bg-bg-hover/50";
  return (
    <Card>
      <span className={cn("inline-block rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide mb-2", tone)}>
        {kind}
      </span>
      <div className="text-sm font-semibold text-white">{title}</div>
      <p className="text-sm text-gray-400 mt-1 leading-relaxed">{body}</p>
    </Card>
  );
}
