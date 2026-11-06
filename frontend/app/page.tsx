"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  ArrowUpDown,
  Route,
  BusFront,
  Radio,
  CalendarClock,
  MapPinned,
  Calculator,
  MessageSquare,
  BookOpen,
  Bookmark,
  ShieldCheck,
  MapPin,
  Users,
} from "lucide-react";
import { useTransit } from "../components/TransitContext";
import { useLocale } from "../components/Locale";
import { StopInput } from "../components/JourneyPlanner";
import BusScene from "../components/BusScene";
import { sourceLabel } from "../components/types";

const services = [
  {
    title: "Journey Planner",
    description: "Compare arrivals and crowding",
    href: "/planner",
    icon: Route,
    color: "mint",
  },
  {
    title: "Track a Bus",
    description: "Find a vehicle on the corridor",
    href: "/track-bus",
    icon: BusFront,
    color: "blue",
  },
  {
    title: "Track a Live Route",
    description: "Explore stops and route activity",
    href: "/live-route",
    icon: Radio,
    color: "violet",
  },
  {
    title: "Time Table",
    description: "See upcoming stop arrivals",
    href: "/timetable",
    icon: CalendarClock,
    color: "amber",
  },
  {
    title: "Facilities",
    description: "Explore the supported stop directory",
    href: "/facilities",
    icon: MapPinned,
    color: "blue",
  },
  {
    title: "Fare Calculator",
    description: "Estimate your journey budget",
    href: "/fare-calculator",
    icon: Calculator,
    color: "amber",
  },
  {
    title: "Feedback",
    description: "Save and export your suggestions",
    href: "/feedback",
    icon: MessageSquare,
    color: "violet",
  },
  {
    title: "User Guide",
    description: "Get to know RushLess",
    href: "/guide",
    icon: BookOpen,
    color: "mint",
  },
];
export default function Dashboard() {
  const { stops, vehicles, routes, status, profile, error, refresh, loading } =
    useTransit();
  const { t } = useLocale();
  const router = useRouter();
  const [from, setFrom] = useState(""),
    [to, setTo] = useState("");
  const [formError, setFormError] = useState("");
  const active = vehicles.filter((v) => !v.completed);
  const stopName = (id: string) => stops.find((s) => s.id === id)?.name || id;
  function plan(event: React.FormEvent) {
    event.preventDefault();
    if (!from || !to || from === to) {
      setFormError("Choose two different stops.");
      return;
    }
    router.push(
      "/planner?" + new URLSearchParams({ origin: from, destination: to }),
    );
  }
  return (
    <main className="rl-dashboard">
      <div className="rl-page-heading">
        <div>
          <h1>{t("Your city. Your journey.")}</h1>
          <p>{t("A little less rush starts here.")}</p>
        </div>
        <span className="rl-city-label">
          <MapPin size={15} /> Bengaluru, India
        </span>
      </div>
      <section className="rl-hero">
        <div className="rl-hero-copy">
          <span className="rl-hero-tag">
            <span /> {t("Explore the corridor")}
          </span>
          <h2>
            {t("Less waiting.")}
            <br />
            {t("More living.")}
          </h2>
          <p>
            {t(
              "Know your bus before you board. Plan a calmer journey across Bengaluru’s Outer Ring Road.",
            )}
          </p>

        </div>
        <div className="rl-hero-art">
          <span className="rl-art-chip">
            <Users size={14} /> A little more breathing room
          </span>
          <BusScene />
          <span className="rl-art-caption">
            Built for the way Bengaluru moves.
          </span>
        </div>
        <form className="rl-quick-plan" onSubmit={plan}>
          <StopInput label="From" prominent placeholder="From" value={stops.find(s=>s.id===from)||null} onChange={s=>setFrom(s?.id||"")} />
        <button
            type="button"
            className="rl-swap"
            aria-label="Swap stops"
            onClick={() => {
              setFrom(to);
              setTo(from);
            }}
          >
            <ArrowUpDown size={17} />
          </button>
          <StopInput label="To" prominent placeholder="To" value={stops.find(s=>s.id===to)||null} onChange={s=>setTo(s?.id||"")} />
        <button className="rl-primary" disabled={!stops.length}>
            {t("Find my journey")}
            <ArrowRight size={18} />
          </button>
        </form>
      </section>
      {formError && (
        <p className="rl-error" role="alert">
          {formError}
        </p>
      )}
      {error && (
        <div className="rl-error" role="alert">
          {error}
          <button onClick={refresh}>Retry</button>
        </div>
      )}
      <section className="rl-services">
        <div className="rl-section-heading">
          <div>
            <h2>{t("Everything for your next ride")}</h2>
            <p>{t("Choose a service and get moving.")}</p>
          </div>
          <span className="rl-small-tag">Made for your everyday</span>
        </div>
        <div className="rl-service-grid">
          {services.map(({ title, description, href, icon: Icon, color }) => (
            <Link href={href} className="rl-service-card" key={href}>
              <div className="rl-service-card-top">
                <span className={"rl-service-icon " + color}>
                  <Icon size={23} strokeWidth={1.7} />
                </span>
                <ArrowUpRight className="rl-service-arrow" size={18} />
              </div>
              <h3>{t(title)}</h3>
              <p>{t(description)}</p>
            </Link>
          ))}
        </div>
      </section>
      <div className="rl-dashboard-bottom">
        <section className="rl-panel rl-saved-preview">
          <div className="rl-panel-heading">
            <h2>
              <Bookmark size={17} />
              {t("Your everyday journeys")}
            </h2>
            <Link href="/saved">
              {t("View all")}
              <ArrowUpRight size={14} />
            </Link>
          </div>
          {profile?.saved.length ? (
            profile.saved.slice(0, 2).map((s) => (
              <Link
                className="rl-saved-row"
                href={
                  "/planner?" +
                  new URLSearchParams({
                    origin: s.origin,
                    destination: s.destination,
                  })
                }
                key={s.id}
              >
                <span className="rl-saved-icon">
                  <Route size={19} />
                </span>
                <span>
                  <strong>{s.name}</strong>
                  <small>
                    {stopName(s.origin)} <ArrowRight size={11} />{" "}
                    {stopName(s.destination)}
                  </small>
                </span>
                <ArrowUpRight size={16} />
              </Link>
            ))
          ) : (
            <div className="rl-saved-empty">
              <span className="rl-saved-icon">
                <Bookmark size={22} />
              </span>
              <div>
                <strong>{t("No journeys saved yet.")}</strong>
                <p>{t("Save a stop pair in the planner to keep it here.")}</p>
              </div>
              <Link href="/planner" aria-label="Plan and save a journey">
                <ArrowUpRight size={18} />
              </Link>
            </div>
          )}
        </section>
        <section className="rl-panel rl-corridor-preview">
          <div className="rl-panel-heading">
            <h2>
              <Radio size={17} />
              {t("On the corridor")}
            </h2>
            <span className="rl-data-label">
              {loading
                ? "Loading…"
                : status
                  ? t(sourceLabel(status.active_source || status.mode))
                  : "Unavailable"}
            </span>
          </div>
          <div className="rl-network-numbers">
            <div>
              <strong>{loading ? "—" : active.length}</strong>
              <span>
                {t(
                  status?.mode === "simulation"
                    ? "Demo vehicles"
                    : "Active vehicles",
                )}
              </span>
            </div>
            <div>
              <strong>{loading ? "—" : routes.length}</strong>
              <span>{t("Route patterns")}</span>
            </div>
            <div>
              <strong>{loading ? "—" : stops.length}</strong>
              <span>{t("Supported stops")}</span>
            </div>
          </div>
          <Link href="/live-route" className="rl-text-link">
            {t("Explore the corridor")}
            <ArrowRight size={15} />
          </Link>
        </section>
      </div>
      <section className="rl-trust-strip">
        <span className="rl-trust-icon">
          <ShieldCheck size={22} />
        </span>
        <div>
          <h3>{t("Data you can understand")}</h3>
          <p>
            Demo data stays labelled. Predictions show their source. Confidence
            is earned, not assumed.
          </p>
        </div>
        <Link href="/insights">
          {t("Open insights")}
          <ArrowUpRight size={16} />
        </Link>
      </section>
    </main>
  );
}
