import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Check,
  ChevronDown,
  Scale,
  Sparkles,
  BookOpen,
  Landmark,
  ShieldCheck,
  Minus,
} from "lucide-react";
import StandardNavbar from "../components/StandardNavbar";

const plans = [
  {
    id: "explorer",
    name: "Explorer",
    eyebrow: "FOR THE CURIOUS",
    description: "Get familiar with AI-assisted legal practice and the KAYDA courtroom.",
    monthly: 0,
    annual: 0,
    unit: "forever",
    cta: "Start exploring",
    icon: BookOpen,
    features: [
      "Access to sample moot scenarios",
      "Limited AI courtroom sessions",
      "Introductory case analysis",
      "Explore the KAYDA workflow",
    ],
  },
  {
    id: "student",
    name: "Student Pro",
    eyebrow: "FOR LAW STUDENTS",
    description: "Build stronger arguments and prepare for your next moot court round.",
    monthly: 299,
    annual: 2990,
    unit: "per user / month",
    cta: "Choose Student Pro",
    featured: true,
    icon: Sparkles,
    features: [
      "Higher monthly simulation allowance",
      "Prosecution and defense perspectives",
      "Case document analysis",
      "Saved case and session history",
      "Legal research tools where available",
    ],
  },
  {
    id: "advocate",
    name: "Advocate",
    eyebrow: "FOR LEGAL PROFESSIONALS",
    description: "A structured AI assistant for exploring case facts, evidence, and arguments.",
    monthly: 999,
    annual: 9990,
    unit: "per user / month",
    cta: "Choose Advocate",
    icon: Scale,
    features: [
      "Expanded document analysis allowance",
      "Evidence-to-argument exploration",
      "Legal provision and precedent discovery",
      "Organized case workspaces",
      "Source review and verification workflow",
    ],
  },
];

const faqs = [
  {
    q: "Who is KAYDA for?",
    a: "KAYDA is designed for law students, moot court participants, educators, and legal professionals who want to explore legal documents and arguments with AI assistance.",
  },
  {
    q: "Can I use KAYDA as legal advice?",
    a: "No. KAYDA is an AI-assisted research, analysis, and learning tool. Its outputs may be incomplete or incorrect and should be checked against original legal sources and reviewed by a qualified legal professional.",
  },
  {
    q: "What is included in a simulation?",
    a: "A simulation can bring opposing legal perspectives into a structured workflow. The exact features and usage limits depend on the tools currently enabled in your KAYDA account and selected plan.",
  },
  {
    q: "Can a law college or moot court society use KAYDA?",
    a: "Yes. Institutions can contact the KAYDA team to discuss a pilot, classroom use, shared moot scenarios, and the requirements for a suitable institutional plan.",
  },
  {
    q: "Are annual plans available?",
    a: "The page shows proposed annual pricing for planning purposes. Confirm that annual billing and the listed limits are implemented before accepting payments or publishing these as final commercial terms.",
  },
];

function formatPrice(price) {
  return price === 0 ? "₹0" : `₹${price.toLocaleString("en-IN")}`;
}

export default function KaydaPricingPage() {
  const navigate = useNavigate();
  const [billing, setBilling] = useState("monthly");
  const [openFaq, setOpenFaq] = useState(0);

  const displayPlans = useMemo(
    () => plans.map((plan) => ({
      ...plan,
      price: billing === "monthly" ? plan.monthly : plan.annual,
      period: plan.id === "explorer" ? "forever" : billing === "monthly" ? "/ month" : "/ year",
      equivalent: billing === "annual" && plan.id !== "explorer"
        ? `${formatPrice(Math.round(plan.annual / 12))} / month, billed annually`
        : null,
    })),
    [billing]
  );

  const choosePlan = (planId) => {
    if (planId === "institution") {
      navigate("/auth", { state: { inquiry: "institution" } });
      return;
    }
    navigate("/auth", { state: { selectedPlan: planId, billing } });
  };

  return (
    <div className="min-h-screen bg-[#FAF8F5] font-body text-[#2C1810] selection:bg-[#D4AF37]/30">
      <StandardNavbar />

      <main>
        {/* Hero */}
        <section className="relative overflow-hidden px-5 pb-14 pt-32 md:px-12 md:pb-20 md:pt-40">
          <div className="pointer-events-none absolute -right-20 top-20 h-72 w-72 rounded-full bg-[#D4AF37]/10 blur-3xl" />
          <div className="pointer-events-none absolute -left-24 top-52 h-64 w-64 rounded-full bg-[#8C5A3C]/10 blur-3xl" />
          <div className="relative mx-auto max-w-6xl text-center">
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-[#D4AF37]/40 bg-white/70 px-4 py-2 font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-[#8C5A3C] shadow-sm">
              <Scale size={13} /> KAYDA ACCESS & MEMBERSHIP
            </div>
            <h1 className="mx-auto max-w-4xl font-heading text-4xl font-bold leading-[1.08] tracking-[-0.035em] text-[#2C1810] sm:text-5xl md:text-7xl">
              The right tools for
              <span className="block font-normal italic text-[#8C5A3C]">your next argument.</span>
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-sm leading-7 text-[#5D4037] md:text-base">
              Choose how you want to practice, analyze, and explore legal reasoning with KAYDA’s AI-powered courtroom and document workflows.
            </p>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <button onClick={() => choosePlan("explorer")} className="inline-flex w-full items-center justify-center gap-2 rounded-md border border-[#D4AF37] bg-[#2C1810] px-7 py-3.5 text-[11px] font-bold uppercase tracking-[0.14em] text-[#FAF8F5] shadow-sm transition hover:-translate-y-0.5 hover:bg-[#3D2318] sm:w-auto">
                Start with Explorer <ArrowRight size={14} />
              </button>
              <button onClick={() => document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" })} className="w-full rounded-md border border-[#2C1810]/20 bg-white/50 px-7 py-3.5 text-[11px] font-bold uppercase tracking-[0.14em] text-[#2C1810] transition hover:border-[#D4AF37] hover:bg-white sm:w-auto">
                Compare plans
              </button>
            </div>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-[11px] text-[#8C5A3C]">
              <span className="inline-flex items-center gap-1.5"><ShieldCheck size={14} /> Human review stays essential</span>
              <span className="inline-flex items-center gap-1.5"><Check size={14} /> Plans for different workflows</span>
              <span className="inline-flex items-center gap-1.5"><Scale size={14} /> Built around legal reasoning</span>
            </div>
          </div>
        </section>

        {/* Plans */}
        <section id="pricing" className="scroll-mt-28 px-5 pb-20 md:px-12 md:pb-28">
          <div className="mx-auto max-w-6xl">
            <div className="mb-10 flex flex-col items-center justify-between gap-5 md:mb-12 md:flex-row">
              <div className="text-center md:text-left">
                <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.28em] text-[#B18A27]">SELECT YOUR MEMBERSHIP</p>
                <h2 className="font-heading text-3xl font-bold tracking-tight text-[#2C1810] md:text-4xl">Clear plans. Focused practice.</h2>
                <p className="mt-3 max-w-xl text-sm leading-6 text-[#5D4037]">Start small, find your workflow, and upgrade when you need more room to work.</p>
              </div>
              <div className="inline-flex items-center rounded-full border border-[#D4AF37]/40 bg-white p-1.5 shadow-sm" role="group" aria-label="Billing period">
                <button onClick={() => setBilling("monthly")} aria-pressed={billing === "monthly"} className={`rounded-full px-4 py-2 text-xs font-semibold transition ${billing === "monthly" ? "bg-[#2C1810] text-white shadow" : "text-[#8C5A3C] hover:bg-[#FAF8F5]"}`}>Monthly</button>
                <button onClick={() => setBilling("annual")} aria-pressed={billing === "annual"} className={`flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold transition ${billing === "annual" ? "bg-[#2C1810] text-white shadow" : "text-[#8C5A3C] hover:bg-[#FAF8F5]"}`}>
                  Annual <span className={`rounded-full px-2 py-0.5 text-[9px] uppercase tracking-wider ${billing === "annual" ? "bg-[#D4AF37]/20 text-[#F0D78A]" : "bg-[#D4AF37]/15 text-[#8C5A3C]"}`}>Save ~17%</span>
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-5 md:grid-cols-3 md:gap-6">
              {displayPlans.map((plan) => {
                const Icon = plan.icon;
                return (
                  <article key={plan.id} className={`relative flex flex-col border bg-white/85 p-6 shadow-[0_12px_40px_rgba(44,24,16,0.04)] transition duration-300 hover:-translate-y-1 hover:shadow-[0_18px_48px_rgba(44,24,16,0.09)] md:p-7 ${plan.featured ? "border-[#D4AF37] ring-1 ring-[#D4AF37]/35" : "border-[#D4AF37]/25"}`}>
                    {plan.featured && <div className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full border border-[#D4AF37] bg-[#2C1810] px-4 py-1.5 font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-[#F3D77B]">MOST POPULAR</div>}
                    <div className="mb-5 flex items-start justify-between gap-3">
                      <div>
                        <p className="font-mono text-[9px] font-bold uppercase tracking-[0.2em] text-[#A17A22]">{plan.eyebrow}</p>
                        <h3 className="mt-2 font-heading text-2xl font-bold text-[#2C1810]">{plan.name}</h3>
                      </div>
                      <div className={`flex h-11 w-11 shrink-0 items-center justify-center border ${plan.featured ? "border-[#D4AF37]/60 bg-[#D4AF37]/10 text-[#8C5A3C]" : "border-[#D4AF37]/25 bg-[#FAF8F5] text-[#8C5A3C]"}`}><Icon size={20} strokeWidth={1.6} /></div>
                    </div>
                    <p className="min-h-[52px] text-sm leading-6 text-[#6F5144]">{plan.description}</p>
                    <div className="mt-6 border-y border-[#D4AF37]/20 py-5">
                      <div className="flex items-baseline gap-2">
                        <span className="font-heading text-4xl font-bold tracking-tight text-[#2C1810]">{formatPrice(plan.price)}</span>
                        <span className="text-xs text-[#8C5A3C]">{plan.period}</span>
                      </div>
                      {plan.equivalent && <p className="mt-2 text-xs text-[#8C5A3C]">{plan.equivalent}</p>}
                      {plan.id === "explorer" && <p className="mt-2 text-xs text-[#8C5A3C]">No subscription required</p>}
                    </div>
                    <button onClick={() => choosePlan(plan.id)} className={`mt-5 flex w-full items-center justify-center gap-2 rounded-md border px-4 py-3.5 text-[10px] font-bold uppercase tracking-[0.14em] transition ${plan.featured ? "border-[#D4AF37] bg-[#2C1810] text-[#FAF8F5] hover:bg-[#3D2318]" : "border-[#2C1810]/20 bg-transparent text-[#2C1810] hover:border-[#D4AF37] hover:bg-[#FAF8F5]"}`}>
                      {plan.cta} <ArrowRight size={13} />
                    </button>
                    <div className="mt-7">
                      <p className="mb-4 font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-[#8C5A3C]">PLAN INCLUDES</p>
                      <ul className="space-y-3">
                        {plan.features.map((feature) => <li key={feature} className="flex items-start gap-2.5 text-xs leading-5 text-[#5D4037]"><span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-[#D4AF37]/15 text-[#8C5A3C]"><Check size={10} strokeWidth={2.5} /></span><span>{feature}</span></li>)}
                      </ul>
                    </div>
                  </article>
                );
              })}
            </div>
            <div className="mt-5 flex flex-col items-start justify-between gap-3 border border-[#D4AF37]/20 bg-white/55 px-5 py-4 sm:flex-row sm:items-center">
              <div className="flex items-start gap-3"><Landmark className="mt-0.5 shrink-0 text-[#A17A22]" size={19} /><div><p className="font-heading text-base font-bold text-[#2C1810]">Need KAYDA for your institution?</p><p className="mt-1 text-xs leading-5 text-[#6F5144]">Discuss a law-college pilot, shared moot exercises, and team access.</p></div></div>
              <button onClick={() => choosePlan("institution")} className="inline-flex shrink-0 items-center gap-2 text-[10px] font-bold uppercase tracking-[0.12em] text-[#8C5A3C] transition hover:text-[#2C1810]">Talk to our team <ArrowRight size={13} /></button>
            </div>
            <p className="mt-4 text-center text-[10px] leading-5 text-[#8C5A3C]/80">Pricing and feature allowances are proposed launch values. Confirm availability, usage limits, billing, and applicable taxes before accepting payment.</p>
          </div>
        </section>

        {/* Value proposition */}
        <section className="border-y border-[#D4AF37]/20 bg-white/60 px-5 py-16 md:px-12 md:py-20">
          <div className="mx-auto max-w-6xl">
            <div className="mx-auto mb-10 max-w-2xl text-center">
              <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.28em] text-[#B18A27]">MORE THAN A CHAT WINDOW</p>
              <h2 className="font-heading text-3xl font-bold tracking-tight text-[#2C1810] md:text-4xl">A courtroom built for critical thinking.</h2>
              <p className="mt-4 text-sm leading-7 text-[#5D4037]">KAYDA brings legal work into a structured environment where users can examine facts, compare arguments, and reflect on reasoning.</p>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              {[
                { n: "01", title: "Explore both sides", text: "Examine competing prosecution and defense arguments instead of relying on a single response." },
                { n: "02", title: "Connect the record", text: "Use document analysis and legal knowledge connections to investigate facts and related legal concepts." },
                { n: "03", title: "Review the reasoning", text: "Treat generated analysis as a starting point, then check cited authorities and source documents." },
              ].map((item) => <div key={item.n} className="border border-[#D4AF37]/20 bg-[#FAF8F5] p-6"><span className="font-mono text-xs font-bold tracking-[0.18em] text-[#B18A27]">{item.n}</span><h3 className="mt-4 font-heading text-xl font-bold text-[#2C1810]">{item.title}</h3><p className="mt-2 text-xs leading-6 text-[#6F5144]">{item.text}</p></div>)}
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="scroll-mt-28 px-5 py-16 md:px-12 md:py-24">
          <div className="mx-auto grid max-w-6xl gap-10 md:grid-cols-[0.8fr_1.2fr] md:gap-16">
            <div>
              <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.28em] text-[#B18A27]">QUESTIONS BEFORE PROCEEDINGS</p>
              <h2 className="font-heading text-3xl font-bold tracking-tight text-[#2C1810] md:text-4xl">A few things to know.</h2>
              <p className="mt-4 max-w-sm text-sm leading-7 text-[#5D4037]">Have a question about a plan or institutional access? Get in touch with the KAYDA team.</p>
              <button onClick={() => choosePlan("institution")} className="mt-6 inline-flex items-center gap-2 border-b border-[#D4AF37] pb-1 text-xs font-bold uppercase tracking-[0.1em] text-[#8C5A3C] hover:text-[#2C1810]">Contact KAYDA <ArrowRight size={13} /></button>
            </div>
            <div className="border-t border-[#D4AF37]/25">
              {faqs.map((faq, index) => {
                const isOpen = openFaq === index;
                return <div key={faq.q} className="border-b border-[#D4AF37]/25">
                  <button className="flex w-full items-center justify-between gap-4 py-5 text-left" onClick={() => setOpenFaq(isOpen ? -1 : index)} aria-expanded={isOpen}>
                    <span className="font-heading text-base font-bold text-[#2C1810]">{faq.q}</span>
                    {isOpen ? <Minus size={16} className="shrink-0 text-[#A17A22]" /> : <ChevronDown size={16} className="shrink-0 text-[#A17A22]" />}
                  </button>
                  {isOpen && <p className="max-w-2xl pb-5 pr-8 text-xs leading-6 text-[#6F5144]">{faq.a}</p>}
                </div>;
              })}
            </div>
          </div>
        </section>

        {/* Disclaimer */}
        <section className="px-5 pb-10 md:px-12">
          <div className="mx-auto flex max-w-6xl items-start gap-3 border border-[#D4AF37]/20 bg-white/55 p-4 text-[10px] leading-5 text-[#8C5A3C]">
            <ShieldCheck size={16} className="mt-0.5 shrink-0" />
            <p>KAYDA provides AI-assisted legal research, document analysis, and educational simulation. It does not replace qualified legal counsel. AI-generated content can be incomplete or inaccurate; independently verify legal authorities and case-specific conclusions.</p>
          </div>
        </section>
      </main>

      <footer className="border-t border-[#D4AF37]/25 bg-[#2C1810] px-5 py-8 text-[#FAF8F5] md:px-12">
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
          <div><p className="font-heading text-xl font-bold tracking-tight">KAYDA<span className="text-[#D4AF37]">.</span></p><p className="mt-1 text-[10px] tracking-wide text-white/55">Legal reasoning, reimagined.</p></div>
          <div className="flex flex-wrap gap-5 text-[10px] uppercase tracking-[0.12em] text-white/65"><button onClick={() => navigate("/")} className="transition hover:text-[#D4AF37]">Home</button><button onClick={() => document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" })} className="transition hover:text-[#D4AF37]">Plans</button><button onClick={() => document.getElementById("faq")?.scrollIntoView({ behavior: "smooth" })} className="transition hover:text-[#D4AF37]">FAQ</button></div>
          <p className="text-[10px] text-white/45">© {new Date().getFullYear()} KAYDA. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
