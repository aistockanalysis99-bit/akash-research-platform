import {
  ArrowDown,
  ArrowUp,
  BarChart3,
  BookOpen,
  CheckCircle2,
  Clock3,
  Info,
  Layers3,
  ShieldCheck,
  TrendingUp,
  TriangleAlert,
  Zap,
} from "lucide-react";

const DoubleCalendarPage = () => {
  return (
    <div className="min-h-screen bg-[#070b12] text-white">
      <main className="mx-auto max-w-[1400px] px-6 py-8">
        {/* Header */}
        <section className="mb-8">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-cyan-400/20 bg-cyan-400/10">
              <Layers3 className="h-5 w-5 text-cyan-400" />
            </div>

            <div>
              <h1 className="text-3xl font-bold tracking-tight">
                Double Calendar Spread
              </h1>

              <p className="mt-1 text-sm text-slate-400">
                Strategy guide, structure, payoff profile, Greeks and risk
                management
              </p>
            </div>
          </div>

          {/* Strategy badges */}
          <div className="mt-5 flex flex-wrap gap-2">
            <span className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1.5 text-xs font-medium text-cyan-300">
              4 LEGS
            </span>

            <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1.5 text-xs font-medium text-emerald-300">
              DEFINED RISK
            </span>

            <span className="rounded-full border border-violet-400/20 bg-violet-400/10 px-3 py-1.5 text-xs font-medium text-violet-300">
              THETA FOCUSED
            </span>

            <span className="rounded-full border border-amber-400/20 bg-amber-400/10 px-3 py-1.5 text-xs font-medium text-amber-300">
              VEGA EXPOSURE
            </span>
          </div>
        </section>

        {/* Overview */}
        <section className="mb-6 grid gap-6 lg:grid-cols-[1.5fr_1fr]">
          <div className="rounded-2xl border border-slate-800 bg-[#0d131e] p-6">
            <div className="mb-4 flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-cyan-400" />

              <h2 className="text-lg font-semibold">
                What is a Double Calendar?
              </h2>
            </div>

            <p className="leading-7 text-slate-300">
              A Double Calendar Spread combines two calendar spreads: one put
              calendar and one call calendar. The trader buys longer-dated
              options and sells shorter-dated options at different strikes.
            </p>

            <p className="mt-4 leading-7 text-slate-400">
              The strategy is designed to benefit from the difference in time
              decay between the near-term options and the longer-term options,
              while also carrying exposure to changes in implied volatility.
            </p>

            <div className="mt-5 rounded-xl border border-cyan-400/10 bg-cyan-400/[0.04] p-4">
              <div className="flex gap-3">
                <Info className="mt-0.5 h-5 w-5 shrink-0 text-cyan-400" />

                <p className="text-sm leading-6 text-slate-300">
                  This is not simply a bet that the market will stay flat. The
                  actual result depends on underlying price, time decay,
                  implied volatility, strike placement, expiry separation and
                  liquidity.
                </p>
              </div>
            </div>
          </div>

          {/* Quick facts */}
          <div className="rounded-2xl border border-slate-800 bg-[#0d131e] p-6">
            <h2 className="mb-5 text-lg font-semibold">Quick Facts</h2>

            <div className="space-y-4">
              <FactRow
                label="Number of legs"
                value="4"
              />

              <FactRow
                label="Entry type"
                value="Net Debit"
              />

              <FactRow
                label="Main drivers"
                value="Theta + Vega"
              />

              <FactRow
                label="Directional exposure"
                value="Usually moderate"
              />

              <FactRow
                label="Risk"
                value="Defined / model-dependent"
              />
            </div>
          </div>
        </section>

        {/* Construction */}
        <section className="mb-6 rounded-2xl border border-slate-800 bg-[#0d131e] p-6">
          <SectionHeader
            icon={<Layers3 className="h-5 w-5 text-cyan-400" />}
            title="How the Strategy Is Built"
            description="A Double Calendar is created by combining a put calendar and a call calendar."
          />

          <div className="mt-6 grid gap-5 md:grid-cols-2">
            {/* Put calendar */}
            <CalendarCard
              title="Put Calendar"
              strike="$195"
              optionType="PUT"
            />

            {/* Call calendar */}
            <CalendarCard
              title="Call Calendar"
              strike="$205"
              optionType="CALL"
            />
          </div>

          <div className="mt-6 flex flex-col items-center justify-center rounded-xl border border-slate-800 bg-[#090e17] p-5 text-center">
            <span className="text-xs font-medium uppercase tracking-widest text-slate-500">
              Combined Structure
            </span>

            <p className="mt-2 text-lg font-semibold text-white">
              Long Far Expiry + Short Near Expiry
            </p>

            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              The put and call calendars use the same expiry pair but different
              strikes, creating the four-leg Double Calendar structure.
            </p>
          </div>
        </section>

        {/* Example structure */}
        <section className="mb-6 rounded-2xl border border-slate-800 bg-[#0d131e] p-6">
          <SectionHeader
            icon={<BarChart3 className="h-5 w-5 text-cyan-400" />}
            title="Example Structure"
            description="Illustrative example — actual premiums and Greeks will come from market data later."
          />

          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <MetricCard
              label="Underlying"
              value="AAPL"
              subtext="Spot: $200"
            />

            <MetricCard
              label="Near Expiry"
              value="7 DTE"
              subtext="Short options"
            />

            <MetricCard
              label="Far Expiry"
              value="35 DTE"
              subtext="Long options"
            />
          </div>

          <div className="mt-6 overflow-hidden rounded-xl border border-slate-800">
            <div className="grid grid-cols-3 border-b border-slate-800 bg-[#111827] px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
              <span>Action</span>
              <span>Expiry</span>
              <span>Strike</span>
            </div>

            <LegRow action="BUY" type="PUT" expiry="Far" strike="$195" />
            <LegRow action="SELL" type="PUT" expiry="Near" strike="$195" />
            <LegRow action="BUY" type="CALL" expiry="Far" strike="$205" />
            <LegRow action="SELL" type="CALL" expiry="Near" strike="$205" />
          </div>
        </section>

        {/* Payoff / P&L Profile */}
        <section className="mb-6 rounded-2xl border border-slate-800 bg-[#0d131e] p-6">
        <SectionHeader
            icon={<TrendingUp className="h-5 w-5 text-cyan-400" />}
            title="Payoff & P/L Profile"
            description="Illustrative profile showing how a Double Calendar can behave around the selected put and call strikes."
        />

        <div className="mt-6 rounded-xl border border-slate-800 bg-[#090e17] p-4 sm:p-6">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
                <p className="text-sm font-semibold text-slate-200">
                Illustrative Double Calendar
                </p>

                <p className="mt-1 text-xs text-slate-500">
                AAPL example · Put strike $195 · Call strike $205
                </p>
            </div>

            <div className="flex items-center gap-4 text-xs text-slate-500">
                <div className="flex items-center gap-2">
                <span className="h-2 w-6 rounded-full bg-cyan-400" />
                P/L
                </div>

                <div className="flex items-center gap-2">
                <span className="h-px w-6 border-t border-dashed border-slate-500" />
                Zero P/L
                </div>
            </div>
            </div>

            <IllustrativePayoffChart />

            <div className="mt-4 grid grid-cols-3 gap-3 text-center">
            <div>
                <p className="text-[11px] uppercase tracking-wide text-slate-600">
                Put Strike
                </p>

                <p className="mt-1 text-sm font-semibold text-slate-300">
                $195
                </p>
            </div>

            <div>
                <p className="text-[11px] uppercase tracking-wide text-slate-600">
                Spot
                </p>

                <p className="mt-1 text-sm font-semibold text-cyan-400">
                $200
                </p>
            </div>

            <div>
                <p className="text-[11px] uppercase tracking-wide text-slate-600">
                Call Strike
                </p>

                <p className="mt-1 text-sm font-semibold text-slate-300">
                $205
                </p>
            </div>
            </div>

            <div className="mt-5 rounded-lg border border-amber-400/10 bg-amber-400/[0.03] p-3">
            <p className="text-xs leading-5 text-slate-500">
                <span className="font-semibold text-amber-400">
                Educational illustration:
                </span>{" "}
                This curve is intentionally static. The production chart will be
                calculated from actual option premiums, implied volatility, time to
                expiry and the four selected option legs.
            </p>
            </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <InfoStat
            label="Initial Debit"
            value="Calculated later"
            />

            <InfoStat
            label="Current P/L"
            value="Calculated later"
            />

            <InfoStat
            label="Breakeven Zone"
            value="Calculated later"
            />
        </div>
        </section>

        {/* How it works */}
        <section className="mb-6 rounded-2xl border border-slate-800 bg-[#0d131e] p-6">
          <SectionHeader
            icon={<Zap className="h-5 w-5 text-amber-400" />}
            title="How the Strategy Makes or Loses Money"
            description="The strategy is driven by several interacting variables."
          />

          <div className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <DriverCard
              title="Theta"
              description="Near-term options generally decay faster as expiry approaches, which can benefit the short legs."
              icon={<Clock3 className="h-5 w-5 text-cyan-400" />}
            />

            <DriverCard
              title="Vega"
              description="Longer-dated options generally have greater volatility sensitivity. A rise in IV can therefore help a net long-Vega structure."
              icon={<TrendingUp className="h-5 w-5 text-violet-400" />}
            />

            <DriverCard
              title="Price Movement"
              description="A large move away from the intended range can create significant directional and Gamma risk."
              icon={<ArrowUp className="h-5 w-5 text-rose-400" />}
            />

            <DriverCard
              title="Time"
              description="The relationship between near and far expiry changes continuously as the trade approaches expiration."
              icon={<Clock3 className="h-5 w-5 text-amber-400" />}
            />
          </div>
        </section>

        {/* Greeks */}
        <section className="mb-6 rounded-2xl border border-slate-800 bg-[#0d131e] p-6">
          <SectionHeader
            icon={<BarChart3 className="h-5 w-5 text-violet-400" />}
            title="Greeks"
            description="Actual values will be calculated dynamically from the selected contracts."
          />

          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <GreekCard
              name="Delta"
              description="Directional exposure"
            />

            <GreekCard
              name="Gamma"
              description="Delta sensitivity"
            />

            <GreekCard
              name="Theta"
              description="Time decay"
            />

            <GreekCard
              name="Vega"
              description="IV sensitivity"
            />

            <GreekCard
              name="Rho"
              description="Rate sensitivity"
            />
          </div>
        </section>

        {/* Ideal conditions */}
        <section className="mb-6 grid gap-6 lg:grid-cols-2">
          <ConditionSection
            title="Ideal Market Conditions"
            positive
            items={[
              "Moderate underlying movement",
              "Meaningful separation between near and far expiry",
              "Reasonable implied-volatility environment",
              "Good option-chain liquidity",
              "Tight bid/ask spreads",
              "No uncontrolled event risk",
            ]}
          />

          <ConditionSection
            title="When to Be Cautious"
            items={[
              "Extremely wide bid/ask spreads",
              "Poor option liquidity",
              "Very large expected move",
              "Major binary event approaching",
              "Near and far expiries are too close",
              "Underlying is far outside the intended range",
            ]}
          />
        </section>

        {/* Risk */}
        <section className="mb-6 rounded-2xl border border-rose-500/20 bg-[#0d131e] p-6">
          <SectionHeader
            icon={<ShieldCheck className="h-5 w-5 text-rose-400" />}
            title="Risk Management"
            description="A good strategy guide must explain failure modes, not just the profit thesis."
          />

          <div className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <RiskCard
              title="Large Upward Move"
              description="Call-side exposure can increase rapidly as the underlying moves beyond the intended range."
            />

            <RiskCard
              title="Large Downward Move"
              description="Put-side exposure can increase rapidly as the underlying moves lower."
            />

            <RiskCard
              title="IV Crush"
              description="A decline in implied volatility can hurt a position with net positive Vega."
            />

            <RiskCard
              title="Liquidity Risk"
              description="Theoretical P/L may differ significantly from executable P/L when spreads are wide."
            />
          </div>
        </section>

        {/* Entry process */}
        <section className="mb-6 rounded-2xl border border-slate-800 bg-[#0d131e] p-6">
          <SectionHeader
            icon={<CheckCircle2 className="h-5 w-5 text-emerald-400" />}
            title="Entry Process"
            description="A systematic process prevents arbitrary strike and expiry selection."
          />

          <div className="mt-6 grid gap-3 md:grid-cols-2 lg:grid-cols-5">
            {[
              "Select underlying",
              "Select near expiry",
              "Select far expiry",
              "Select put & call strikes",
              "Check liquidity",
              "Calculate debit",
              "Calculate Greeks",
              "Review payoff",
              "Check risk limits",
              "Review scenario analysis",
            ].map((step, index) => (
              <div
                key={step}
                className="rounded-xl border border-slate-800 bg-[#090e17] p-4"
              >
                <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-400/10 text-sm font-bold text-cyan-400">
                  {index + 1}
                </div>

                <p className="text-sm font-medium text-slate-200">{step}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Common mistakes */}
        <section className="mb-8 rounded-2xl border border-slate-800 bg-[#0d131e] p-6">
          <SectionHeader
            icon={<TriangleAlert className="h-5 w-5 text-amber-400" />}
            title="Common Mistakes"
            description="These are the mistakes the strategy guide should actively prevent."
          />

          <div className="mt-6 space-y-3">
            <Mistake text="Assuming implied volatility will always rise." />
            <Mistake text="Choosing strikes arbitrarily without considering volatility or Delta." />
            <Mistake text="Ignoring bid/ask spreads and liquidity." />
            <Mistake text="Holding too close to near expiry without understanding Gamma risk." />
            <Mistake text="Confusing expiration payoff with current theoretical P/L." />
            <Mistake text="Looking only at Theta while ignoring Spot, IV and Gamma." />
          </div>
        </section>

        {/* Footer */}
        <div className="rounded-xl border border-slate-800 bg-[#0b111b] p-5 text-sm leading-6 text-slate-500">
          <strong className="text-slate-300">Important:</strong> This guide is
          educational. Strategy behavior depends on the actual option chain,
          volatility, underlying price, time to expiry, contract specifications
          and transaction costs.
        </div>
      </main>
    </div>
  );
};

/* -------------------- Small Components -------------------- */

const SectionHeader = ({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) => (
  <div>
    <div className="flex items-center gap-2">
      {icon}
      <h2 className="text-lg font-semibold">{title}</h2>
    </div>

    <p className="mt-1 text-sm leading-6 text-slate-500">{description}</p>
  </div>
);

const FactRow = ({
  label,
  value,
}: {
  label: string;
  value: string;
}) => (
  <div className="flex items-center justify-between border-b border-slate-800 pb-3 last:border-0 last:pb-0">
    <span className="text-sm text-slate-500">{label}</span>
    <span className="text-sm font-medium text-slate-200">{value}</span>
  </div>
);

const CalendarCard = ({
  title,
  strike,
  optionType,
}: {
  title: string;
  strike: string;
  optionType: string;
}) => (
  <div className="rounded-xl border border-slate-800 bg-[#090e17] p-5">
    <div className="mb-5 flex items-center justify-between">
      <h3 className="font-semibold text-white">{title}</h3>

      <span className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-400">
        {optionType}
      </span>
    </div>

    <div className="space-y-3">
      <LegBox
        action="BUY"
        expiry="Far Expiry"
        strike={strike}
      />

      <div className="h-px bg-slate-800" />

      <LegBox
        action="SELL"
        expiry="Near Expiry"
        strike={strike}
      />
    </div>
  </div>
);

const LegBox = ({
  action,
  expiry,
  strike,
}: {
  action: string;
  expiry: string;
  strike: string;
}) => (
  <div className="flex items-center justify-between">
    <div>
      <span
        className={`text-xs font-bold ${
          action === "BUY" ? "text-emerald-400" : "text-rose-400"
        }`}
      >
        {action}
      </span>

      <p className="mt-1 text-sm text-slate-300">{expiry}</p>
    </div>

    <div className="text-right">
      <p className="text-xs text-slate-500">Strike</p>
      <p className="font-semibold text-white">{strike}</p>
    </div>
  </div>
);

const MetricCard = ({
  label,
  value,
  subtext,
}: {
  label: string;
  value: string;
  subtext: string;
}) => (
  <div className="rounded-xl border border-slate-800 bg-[#090e17] p-4">
    <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
    <p className="mt-2 text-xl font-bold text-white">{value}</p>
    <p className="mt-1 text-xs text-slate-500">{subtext}</p>
  </div>
);

const LegRow = ({
  action,
  type,
  expiry,
  strike,
}: {
  action: string;
  type: string;
  expiry: string;
  strike: string;
}) => (
  <div className="grid grid-cols-3 border-b border-slate-800 px-4 py-4 last:border-0">
    <span
      className={`text-sm font-semibold ${
        action === "BUY" ? "text-emerald-400" : "text-rose-400"
      }`}
    >
      {action} {type}
    </span>

    <span className="text-sm text-slate-300">{expiry}</span>

    <span className="text-sm font-medium text-white">{strike}</span>
  </div>
);

const InfoStat = ({
  label,
  value,
}: {
  label: string;
  value: string;
}) => (
  <div className="rounded-xl border border-slate-800 bg-[#090e17] p-4">
    <p className="text-xs text-slate-500">{label}</p>
    <p className="mt-2 font-semibold text-slate-200">{value}</p>
  </div>
);

const DriverCard = ({
  title,
  description,
  icon,
}: {
  title: string;
  description: string;
  icon: React.ReactNode;
}) => (
  <div className="rounded-xl border border-slate-800 bg-[#090e17] p-5">
    <div className="mb-4 flex h-9 w-9 items-center justify-center rounded-lg bg-slate-800">
      {icon}
    </div>

    <h3 className="font-semibold text-white">{title}</h3>

    <p className="mt-2 text-sm leading-6 text-slate-500">{description}</p>
  </div>
);

const GreekCard = ({
  name,
  description,
}: {
  name: string;
  description: string;
}) => (
  <div className="rounded-xl border border-slate-800 bg-[#090e17] p-4">
    <p className="text-lg font-bold text-white">{name}</p>
    <p className="mt-2 text-xs leading-5 text-slate-500">{description}</p>
    <div className="mt-4 text-sm font-semibold text-slate-600">—</div>
  </div>
);

const ConditionSection = ({
  title,
  items,
  positive = false,
}: {
  title: string;
  items: string[];
  positive?: boolean;
}) => (
  <div className="rounded-2xl border border-slate-800 bg-[#0d131e] p-6">
    <h2 className="text-lg font-semibold">{title}</h2>

    <div className="mt-5 space-y-3">
      {items.map((item) => (
        <div key={item} className="flex gap-3">
          {positive ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
          ) : (
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
          )}

          <p className="text-sm leading-6 text-slate-400">{item}</p>
        </div>
      ))}
    </div>
  </div>
);

const RiskCard = ({
  title,
  description,
}: {
  title: string;
  description: string;
}) => (
  <div className="rounded-xl border border-rose-500/10 bg-[#090e17] p-5">
    <h3 className="font-semibold text-slate-200">{title}</h3>

    <p className="mt-2 text-sm leading-6 text-slate-500">{description}</p>
  </div>
);

const Mistake = ({ text }: { text: string }) => (
  <div className="flex items-start gap-3 rounded-xl border border-slate-800 bg-[#090e17] p-4">
    <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />

    <p className="text-sm leading-6 text-slate-400">{text}</p>
  </div>
);

const IllustrativePayoffChart = () => {
  return (
    <div className="relative h-[330px] w-full overflow-hidden rounded-lg">
      <svg
        viewBox="0 0 1000 330"
        className="h-full w-full"
        preserveAspectRatio="none"
      >
        {/* Horizontal grid lines */}
        <line
          x1="70"
          y1="70"
          x2="950"
          y2="70"
          stroke="rgba(148,163,184,0.08)"
          strokeWidth="1"
        />

        <line
          x1="70"
          y1="125"
          x2="950"
          y2="125"
          stroke="rgba(148,163,184,0.08)"
          strokeWidth="1"
        />

        <line
          x1="70"
          y1="180"
          x2="950"
          y2="180"
          stroke="rgba(148,163,184,0.16)"
          strokeWidth="1"
          strokeDasharray="6 6"
        />

        <line
          x1="70"
          y1="235"
          x2="950"
          y2="235"
          stroke="rgba(148,163,184,0.08)"
          strokeWidth="1"
        />

        <line
          x1="70"
          y1="280"
          x2="950"
          y2="280"
          stroke="rgba(148,163,184,0.08)"
          strokeWidth="1"
        />

        {/* Vertical strike lines */}
        <line
          x1="350"
          y1="45"
          x2="350"
          y2="285"
          stroke="rgba(148,163,184,0.18)"
          strokeWidth="1"
          strokeDasharray="5 6"
        />

        <line
          x1="500"
          y1="45"
          x2="500"
          y2="285"
          stroke="rgba(34,211,238,0.22)"
          strokeWidth="1"
          strokeDasharray="5 6"
        />

        <line
          x1="650"
          y1="45"
          x2="650"
          y2="285"
          stroke="rgba(148,163,184,0.18)"
          strokeWidth="1"
          strokeDasharray="5 6"
        />

        {/* P/L curve */}
        <path
          d="
            M 70 230
            C 130 230, 180 225, 220 215
            C 260 205, 300 165, 330 125
            C 345 105, 360 95, 380 105
            C 410 120, 430 155, 455 165
            C 475 173, 490 172, 500 168
            C 510 172, 525 173, 545 165
            C 570 155, 590 120, 620 105
            C 640 95, 655 105, 670 125
            C 700 165, 740 205, 780 215
            C 820 225, 870 230, 930 230
          "
          fill="none"
          stroke="#22d3ee"
          strokeWidth="4"
          strokeLinecap="round"
        />

        {/* Area below curve */}
        <path
          d="
            M 70 230
            C 130 230, 180 225, 220 215
            C 260 205, 300 165, 330 125
            C 345 105, 360 95, 380 105
            C 410 120, 430 155, 455 165
            C 475 173, 490 172, 500 168
            C 510 172, 525 173, 545 165
            C 570 155, 590 120, 620 105
            C 640 95, 655 105, 670 125
            C 700 165, 740 205, 780 215
            C 820 225, 870 230, 930 230
            L 930 180
            L 70 180
            Z
          "
          fill="rgba(34,211,238,0.035)"
        />

        {/* Strike labels */}
        <text
          x="350"
          y="315"
          textAnchor="middle"
          fill="#94a3b8"
          fontSize="13"
        >
          $195 Put Strike
        </text>

        <text
          x="500"
          y="315"
          textAnchor="middle"
          fill="#22d3ee"
          fontSize="13"
        >
          $200 Spot
        </text>

        <text
          x="650"
          y="315"
          textAnchor="middle"
          fill="#94a3b8"
          fontSize="13"
        >
          $205 Call Strike
        </text>

        {/* Y axis labels */}
        <text
          x="48"
          y="74"
          textAnchor="end"
          fill="#64748b"
          fontSize="11"
        >
          Profit
        </text>

        <text
          x="48"
          y="184"
          textAnchor="end"
          fill="#64748b"
          fontSize="11"
        >
          0
        </text>

        <text
          x="48"
          y="284"
          textAnchor="end"
          fill="#64748b"
          fontSize="11"
        >
          Loss
        </text>
      </svg>
    </div>
  );
};

export default DoubleCalendarPage;