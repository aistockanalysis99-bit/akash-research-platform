import {
  Bot,
  Briefcase,
  BarChart3,
  Sunrise,
  Moon,
  CalendarRange,
  ShieldCheck,
  Scale,
  CheckCircle2,
  ArrowDown,
  Lightbulb,
  Eye,
  Newspaper,
  LineChart,
  Building2,
  Layers,
  Globe,
  FileDown,
} from "lucide-react";
import { Card } from "@/components/ui";
import { cn } from "@/lib/utils";

export default function GuidePage() {
  return (
    <div className="max-w-4xl mx-auto pb-12">
      {/* ── Hero ───────────────────────────────────────────── */}
      <div className="text-center py-8">
        <div className="inline-flex items-center gap-2 rounded-full border border-brand/30 bg-brand/10 px-3 py-1 text-xs font-semibold text-brand mb-4">
          <Bot className="h-3.5 w-3.5" /> Your Guide
        </div>
        <h1 className="text-3xl sm:text-4xl font-extrabold text-white leading-tight">
          A research team that<br className="hidden sm:block" /> never sleeps
        </h1>
        <p className="text-gray-400 mt-4 max-w-2xl mx-auto leading-relaxed">
          This platform does the heavy research a professional investment firm would —
          then hands you a clear recommendation in plain English. It never spends your
          money. <span className="text-gray-200 font-medium">You always make the final call.</span>
        </p>
      </div>

      {/* ── What it does, in 5 steps ───────────────────────── */}
      <Section n="1" title="What it does, in one minute">
        <div className="space-y-2.5">
          {[
            ["Scans the whole US market", "to find stocks with real momentum behind them."],
            ["Deep-researches each one", "the business, the news, the charts, what big institutions are doing."],
            ["Argues both sides", "a Bull and a Bear debate every stock, then it reaches a verdict."],
            ["Sends you the verdict", "in plain language, straight to your phone on Telegram."],
            ["You decide", "what to actually buy. Nothing happens to your money without you."],
          ].map(([h, b], i) => (
            <div key={i} className="flex gap-3 items-start">
              <span className="shrink-0 mt-0.5 h-6 w-6 rounded-full bg-brand/15 text-brand text-xs font-bold flex items-center justify-center">
                {i + 1}
              </span>
              <p className="text-sm text-gray-300">
                <span className="font-semibold text-white">{h}</span> — {b}
              </p>
            </div>
          ))}
        </div>
      </Section>

      {/* ── The three parts ────────────────────────────────── */}
      <Section n="2" title="The three parts of the platform">
        <div className="space-y-3">
          <PartCard
            icon={<Briefcase className="h-5 w-5" />}
            title="Portfolio"
            tagline="“What I own”"
            points={[
              "Your real account, mirrored on screen — every holding, what you paid, what it's worth now.",
              "Tracks your cash and total account value (cash + holdings).",
              "You add positions manually when you buy in your real broker account.",
            ]}
            why="The AI uses your real holdings to give smarter advice — it warns you before you over-concentrate in one area."
          />
          <PartCard
            icon={<Bot className="h-5 w-5" />}
            title="AI Analysis"
            tagline="“Should I buy this?”"
            points={[
              "Runs a team of 11 specialist AI analysts on any stock.",
              "They study the business, news, charts, big-money flows and market mood.",
              "A Bull and Bear debate it, a Risk Manager applies safety rules, and a Portfolio Manager issues the final verdict.",
            ]}
            why="You get a clear BUY / WATCH / AVOID verdict with a confidence score, price target, and a 'cut losses' level."
          />
          <PartCard
            icon={<BarChart3 className="h-5 w-5" />}
            title="Backtesting"
            tagline="“Does the strategy actually work?”"
            points={[
              "Replays the stock-picking rules across years of real market history.",
              "Shows how the money would have grown, how often it won, and the worst drop.",
              "The same proven rules scan the market for you every evening.",
            ]}
            why="You're not trusting a hunch — you're trusting a method tested against history before it touches your portfolio."
          />
        </div>
      </Section>

      {/* ── The 11 analysts ────────────────────────────────── */}
      <Section n="3" title="Meet the 11-analyst team">
        <p className="text-sm text-gray-400 mb-4">
          For every stock, these specialists work in parallel — then their findings feed a structured debate and a final decision.
        </p>
        <div className="grid sm:grid-cols-2 gap-2.5 mb-5">
          <AnalystRow icon={<LineChart className="h-4 w-4" />} name="Fundamental" q="Is this a healthy, growing business?" />
          <AnalystRow icon={<Newspaper className="h-4 w-4" />} name="News" q="What's happening lately? Insiders buying or selling?" />
          <AnalystRow icon={<BarChart3 className="h-4 w-4" />} name="Technical" q="Is the price in an uptrend or falling?" />
          <AnalystRow icon={<Building2 className="h-4 w-4" />} name="Institutional Flow" q="Is smart money buying or quietly getting out?" />
          <AnalystRow icon={<Layers className="h-4 w-4" />} name="Options Structure" q="Where do big traders expect the price to go?" />
          <AnalystRow icon={<Globe className="h-4 w-4" />} name="Macro Regime" q="Is the whole market calm and rising, or nervous?" />
        </div>
        <div className="flex items-center gap-2 justify-center flex-wrap text-xs">
          <DebateChip icon={<Eye className="h-3.5 w-3.5" />} label="Bull builds the buy case" cls="text-pos border-pos/30 bg-pos/10" />
          <span className="text-gray-600">vs</span>
          <DebateChip icon={<Eye className="h-3.5 w-3.5" />} label="Bear builds the avoid case" cls="text-neg border-neg/30 bg-neg/10" />
          <ArrowDown className="h-3.5 w-3.5 text-gray-600 rotate-[-90deg]" />
          <DebateChip icon={<Scale className="h-3.5 w-3.5" />} label="Judge weighs both" cls="text-gray-300 border-line bg-bg-hover" />
          <DebateChip icon={<ShieldCheck className="h-3.5 w-3.5" />} label="Risk Manager checks safety" cls="text-warn border-warn/30 bg-warn/10" />
          <DebateChip icon={<Briefcase className="h-3.5 w-3.5" />} label="PM decides" cls="text-brand border-brand/30 bg-brand/10" />
        </div>
      </Section>

      {/* ── The journey of a stock (funnel) ────────────────── */}
      <Section n="4" title="How it all fits together">
        <p className="text-sm text-gray-400 mb-5">
          A funnel that filters out noise at every step — from thousands of stocks down to one decision on your phone.
        </p>
        <div className="space-y-1">
          <FunnelStep
            width="100%"
            label="THE WHOLE MARKET"
            sub="~100 large US companies"
            tone="bg-bg-hover border-line"
          />
          <FunnelArrow note="The strategy scans them all — momentum + trend + breakout" />
          <FunnelStep
            width="72%"
            label="TOP SIGNALS"
            sub="~10 strongest stocks today"
            tone="bg-brand/10 border-brand/30"
          />
          <FunnelArrow note="The 11-analyst AI team deeply researches each one" />
          <FunnelStep
            width="50%"
            label="CLEAR VERDICTS"
            sub="BUY / WATCH / AVOID + target + stop"
            tone="bg-pos/10 border-pos/30"
          />
          <FunnelArrow note="Sent to your phone on Telegram" />
          <FunnelStep
            width="34%"
            label="YOU DECIDE"
            sub="add to Portfolio if you agree"
            tone="bg-white/5 border-white/20"
          />
        </div>
        <p className="text-xs text-gray-500 mt-5 text-center italic">
          The strategy decides <span className="text-gray-300">what's worth looking at</span>.
          The AI decides <span className="text-gray-300">whether it's a good idea right now</span>.
          You decide <span className="text-gray-300">what to do</span>.
        </p>
      </Section>

      {/* ── Daily rhythm ───────────────────────────────────── */}
      <Section n="5" title="Your daily rhythm">
        <p className="text-sm text-gray-400 mb-4">
          Everything runs automatically on a fixed schedule. You don't start anything — messages just arrive.
        </p>
        <div className="space-y-3">
          <RhythmRow
            icon={<Sunrise className="h-5 w-5 text-warn" />}
            when="Every morning · 8:00 AM ET"
            title="Morning Briefing"
            desc="A short health check: how the market looks, how your holdings are doing, and anything to watch today."
          />
          <RhythmRow
            icon={<Moon className="h-5 w-5 text-brand" />}
            when="Every evening · 4:30 PM ET"
            title="Evening Research"
            desc="The full scan + AI analysis. A verdict (BUY/WATCH/AVOID) on each strong stock and the stocks you're tracking."
          />
          <RhythmRow
            icon={<CalendarRange className="h-5 w-5 text-pos" />}
            when="Every Friday · 5:00 PM ET"
            title="Weekly Review"
            desc="A bigger-picture look at your whole portfolio, what worked, and the outlook for next week."
          />
        </div>
      </Section>

      {/* ── How to read a message ──────────────────────────── */}
      <Section n="6" title="How to read what it sends you">
        <p className="text-sm text-gray-400 mb-4">
          Every evening, for each stock, you get a message like this. No jargon — just what to do.
        </p>
        <div className="rounded-2xl border border-line bg-bg-soft p-4 max-w-md mx-auto shadow-lg">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-pos font-bold">🟢 MRVL — BUY</span>
            <span className="ml-auto text-xs text-gray-500">Confidence 6/10</span>
          </div>
          <MsgBlock label="Why it's a buy">
            Marvell makes the specialty chips that connect AI data centers. Sales grew 28% vs a
            year ago, and the world's largest fund managers just bought tens of millions of new shares.
          </MsgBlock>
          <MsgBlock label="What could go wrong">
            The stock is expensive and growth is slowing. If next quarter slows further, it could drop 25–30%.
          </MsgBlock>
          <MsgBlock label="The trade">
            <span className="block">• Buy around <b className="text-gray-200">$307</b></span>
            <span className="block">• 6-month target: <b className="text-pos">$370</b> (about +20%)</span>
            <span className="block">• Cut losses at: <b className="text-neg">$283</b> (about −8%)</span>
          </MsgBlock>
        </div>
        <p className="text-xs text-gray-500 mt-4 text-center">
          You get: <span className="text-gray-300">what it is, why it's interesting, what could go wrong, and exactly what to do.</span>
        </p>

        {/* Downloadable PDF callout */}
        <div className="mt-5 flex gap-3 items-start rounded-xl border border-brand/30 bg-brand/[0.05] p-4">
          <FileDown className="h-5 w-5 text-brand shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-semibold text-white">Download a full PDF report</div>
            <p className="text-sm text-gray-400 mt-1 leading-relaxed">
              Open any stock under <span className="text-gray-200">AI Analysis → Decisions</span> and
              click <span className="text-brand font-medium">Download PDF</span>. You get a clean
              one-page research report — the price chart with target and stop levels, all the analyst
              scores, the plain-English verdict, and the bull-vs-bear case — ready to save, print, or
              share. Perfect for keeping a record or reviewing a decision later.
            </p>
          </div>
        </div>
      </Section>

      {/* ── You control vs automatic ───────────────────────── */}
      <Section n="7" title="What you control vs. what's automatic">
        <div className="grid sm:grid-cols-2 gap-3">
          <Card className="border-line/70">
            <div className="text-xs uppercase tracking-wide text-gray-500 mb-3">Runs automatically</div>
            <ul className="space-y-2">
              {[
                "Scans the market every day",
                "Researches stocks with 11 analysts",
                "Sends you verdicts on Telegram",
                "Monitors your holdings each morning",
                "Reviews the portfolio every Friday",
              ].map((t) => (
                <li key={t} className="flex gap-2 text-sm text-gray-300">
                  <Bot className="h-4 w-4 text-gray-500 shrink-0 mt-0.5" /> {t}
                </li>
              ))}
            </ul>
          </Card>
          <Card className="border-brand/30 bg-brand/[0.03]">
            <div className="text-xs uppercase tracking-wide text-brand mb-3">You always control</div>
            <ul className="space-y-2">
              {[
                "Whether to buy anything at all",
                "Which stocks go on your watchlist",
                "How many shares to buy",
                "When to sell",
                "Your cash balance",
              ].map((t) => (
                <li key={t} className="flex gap-2 text-sm text-gray-200">
                  <CheckCircle2 className="h-4 w-4 text-brand shrink-0 mt-0.5" /> {t}
                </li>
              ))}
            </ul>
          </Card>
        </div>
        <p className="text-sm text-center text-gray-300 mt-4 font-medium">
          The system never spends your money. It's an advisor, not an autopilot.
        </p>
      </Section>

      {/* ── How it makes you better ────────────────────────── */}
      <Section n="8" title="How this makes you a better investor">
        <div className="space-y-2.5">
          {[
            ["Discipline replaces emotion", "The same rigorous process runs on every stock, every day — whether the market is euphoric or panicking."],
            ["You always see the bear case", "A dedicated Bear analyst hunts for every reason not to buy, so you go in with eyes open."],
            ["Risk is built in", "Every recommendation comes with a price target and a 'cut your losses' level. You always know your downside."],
            ["It sees your whole portfolio", "A great stock can still be a bad buy if you already own five like it. The system catches that."],
            ["It learns", "After a position closes, it writes down the lesson and applies it to future decisions."],
            ["It respects your time", "A full analyst night of work, delivered to your phone as a few clear messages."],
          ].map(([h, b]) => (
            <div key={h} className="flex gap-3 items-start">
              <Lightbulb className="h-4 w-4 text-warn shrink-0 mt-1" />
              <p className="text-sm text-gray-300">
                <span className="font-semibold text-white">{h}.</span> {b}
              </p>
            </div>
          ))}
        </div>
      </Section>

      {/* ── Glossary ───────────────────────────────────────── */}
      <Section n="9" title="Simple glossary">
        <div className="grid sm:grid-cols-2 gap-x-6 gap-y-3">
          {[
            ["Momentum", "A stock whose price has been steadily climbing. The strategy favors winners that keep winning."],
            ["Breakout", "The price just pushed above its recent ceiling — often the start of a bigger move."],
            ["Conviction (1–10)", "How sure the AI is. It won't recommend a full buy below 5."],
            ["Watchlist", "Stocks the system keeps researching for you, even if you don't own them yet."],
            ["Position", "A stock you own."],
            ["Stop / cut losses at", "The price to sell at to limit a loss if the trade goes wrong."],
            ["Backtest", "Testing the strategy against past market history to prove it works."],
            ["Regime", "The market's overall mood — calm and rising, or nervous and falling."],
          ].map(([term, def]) => (
            <div key={term}>
              <div className="text-sm font-semibold text-brand">{term}</div>
              <div className="text-sm text-gray-400">{def}</div>
            </div>
          ))}
        </div>
      </Section>

      <p className="text-center text-xs text-gray-500 mt-10 max-w-xl mx-auto leading-relaxed">
        This platform combines a proven, tested stock-selection strategy with the research
        depth of an 11-person analyst team — and puts the final decision where it belongs:
        with you. Use it as your trusted second opinion, every single day.
      </p>
    </div>
  );
}

// ── Building blocks ─────────────────────────────────────────────────────────
function Section({ n, title, children }: { n: string; title: string; children: React.ReactNode }) {
  return (
    <section className="mt-10">
      <div className="flex items-center gap-3 mb-4">
        <span className="h-7 w-7 rounded-lg bg-brand/15 text-brand text-sm font-bold flex items-center justify-center shrink-0">
          {n}
        </span>
        <h2 className="text-lg font-bold text-white">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function PartCard({
  icon, title, tagline, points, why,
}: {
  icon: React.ReactNode; title: string; tagline: string; points: string[]; why: string;
}) {
  return (
    <Card>
      <div className="flex items-center gap-3 mb-3">
        <span className="h-9 w-9 rounded-lg bg-brand/15 text-brand flex items-center justify-center shrink-0">
          {icon}
        </span>
        <div>
          <div className="font-bold text-white">{title}</div>
          <div className="text-xs text-gray-500">{tagline}</div>
        </div>
      </div>
      <ul className="space-y-1.5 mb-3">
        {points.map((p) => (
          <li key={p} className="flex gap-2 text-sm text-gray-300">
            <span className="text-brand mt-0.5">•</span> {p}
          </li>
        ))}
      </ul>
      <div className="text-xs text-gray-400 bg-bg-hover/50 rounded-lg p-2.5 border border-line/50">
        <span className="font-semibold text-gray-300">Why it matters: </span>{why}
      </div>
    </Card>
  );
}

function AnalystRow({ icon, name, q }: { icon: React.ReactNode; name: string; q: string }) {
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-line/50 bg-bg-hover/30 px-3 py-2">
      <span className="text-brand shrink-0 mt-0.5">{icon}</span>
      <div>
        <div className="text-sm font-semibold text-gray-200">{name}</div>
        <div className="text-xs text-gray-500">{q}</div>
      </div>
    </div>
  );
}

function DebateChip({ icon, label, cls }: { icon: React.ReactNode; label: string; cls: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-1 font-medium", cls)}>
      {icon} {label}
    </span>
  );
}

function FunnelStep({ width, label, sub, tone }: { width: string; label: string; sub: string; tone: string }) {
  return (
    <div className="flex justify-center">
      <div
        className={cn("rounded-xl border px-4 py-3 text-center transition-all", tone)}
        style={{ width }}
      >
        <div className="text-sm font-bold text-white tracking-wide">{label}</div>
        <div className="text-xs text-gray-400 mt-0.5">{sub}</div>
      </div>
    </div>
  );
}

function FunnelArrow({ note }: { note: string }) {
  return (
    <div className="flex flex-col items-center py-1">
      <ArrowDown className="h-4 w-4 text-gray-600" />
      <span className="text-[11px] text-gray-500 mt-0.5">{note}</span>
    </div>
  );
}

function RhythmRow({ icon, when, title, desc }: { icon: React.ReactNode; when: string; title: string; desc: string }) {
  return (
    <Card className="flex gap-3 items-start">
      <span className="shrink-0 mt-0.5">{icon}</span>
      <div>
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="font-bold text-white">{title}</span>
          <span className="text-xs text-gray-500">{when}</span>
        </div>
        <div className="text-sm text-gray-400 mt-0.5">{desc}</div>
      </div>
    </Card>
  );
}

function MsgBlock({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-2.5 last:mb-0">
      <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-0.5">{label}</div>
      <div className="text-sm text-gray-300 leading-relaxed">{children}</div>
    </div>
  );
}
