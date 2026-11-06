"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Bookmark,
  Calculator,
  Check,
  Download,
  History,
  Info,
  MessageSquare,
  Route,
  Star,
} from "lucide-react";
import { useTransit } from "./TransitContext";
import { StopSelect, ToolHeading } from "./TransportTools";
import { request } from "./types";
import CommuterPanel, { CommuterProfile } from "./CommuterPanel";

const money = (value: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
type FareRecord = {
  route_id: string;
  route_name: string;
  fare_id: string;
  amount: number;
  currency: string;
};
type FareQuote = {
  fares: FareRecord[];
  source: string;
  version: string | null;
  note: string;
};
export function FareCalculator() {
  const [origin, setOrigin] = useState("silk"),
    [destination, setDestination] = useState("marathahalli");
  const [quote, setQuote] = useState<FareQuote | null>(null),
    [error, setError] = useState(""),
    [selected, setSelected] = useState(""),
    [riders, setRiders] = useState("1"),
    [calculated, setCalculated] = useState(false);
  useEffect(() => {
    let active = true;
    setQuote(null);
    setError("");
    setCalculated(false);
    setSelected("");
    request<FareQuote>(
      "/api/network/fares?" + new URLSearchParams({ origin, destination }),
    )
      .then((result) => {
        if (active) {
          setQuote(result);
          setSelected(
            result.fares[0]
              ? result.fares[0].route_id + ":" + result.fares[0].fare_id
              : "",
          );
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [origin, destination]);
  const fare = quote?.fares.find(
    (f) => f.route_id + ":" + f.fare_id === selected,
  );
  const valid =
    origin !== destination &&
    !!fare &&
    +riders >= 1 &&
    +riders <= 20 &&
    Number.isInteger(+riders);
  return (
    <main>
      <ToolHeading
        title="Fare Calculator"
        description="Explore published fare records for a supported direct route."
      />
      <div className="rl-note">
        <Info size={18} />
        <p>
          Fares come from the published BMTC GTFS archive, version{" "}
          {quote?.version || "…"}. They may differ from the current ticket
          price. Confirm the service class, concessions and final fare with the
          operator.
        </p>
      </div>
      <div className="rl-two-columns rl-fare-layout">
        <form
          className="rl-panel"
          onSubmit={(e) => {
            e.preventDefault();
            setCalculated(true);
          }}
        >
          <h2 className="rl-tool-title">Published journey fare</h2>
          <div className="rl-form-grid">
            <StopSelect label="From" value={origin} onChange={setOrigin} />
            <StopSelect
              label="To"
              value={destination}
              onChange={setDestination}
            />
            <label className="rl-field">
              Published route / fare
              <select
                aria-label="Published route fare"
                value={selected}
                onChange={(e) => {
                  setSelected(e.target.value);
                  setCalculated(false);
                }}
              >
                {quote?.fares.length ? (
                  quote.fares.map((f) => (
                    <option
                      value={f.route_id + ":" + f.fare_id}
                      key={f.route_id + ":" + f.fare_id}
                    >
                      {f.route_name} — {money(f.amount)} ({f.fare_id})
                    </option>
                  ))
                ) : (
                  <option value="">
                    {quote ? "No matching published fare" : "Loading fares…"}
                  </option>
                )}
              </select>
            </label>
            <label className="rl-field">
              Travellers
              <input
                type="number"
                min="1"
                max="20"
                step="1"
                value={riders}
                onChange={(e) => {
                  setRiders(e.target.value);
                  setCalculated(false);
                }}
                required
              />
            </label>
          </div>
          {error && (
            <p role="alert" className="rl-error">
              {error}
            </p>
          )}
          {quote && !fare && (
            <p role="status" className="rl-note">
              No exact fare record is available for this stop pair and
              direction. No distance-based price is substituted.
            </p>
          )}
          <button
            className="rl-primary dark"
            style={{ marginTop: 24 }}
            disabled={!valid}
          >
            <Calculator size={17} />
            Calculate published total
          </button>
        </form>
        <section className="rl-budget-result" aria-live="polite">
          <span className="rl-tag">Published schedule dataset</span>
          <h2 style={{ marginTop: 20 }}>
            {calculated && valid
              ? "Published total · one way"
              : "Select a published fare"}
          </h2>
          <strong className="rl-amount">
            {calculated && valid && fare ? money(fare.amount * +riders) : "₹ —"}
          </strong>
          <p>
            {fare
              ? fare.route_name + " · " + fare.fare_id
              : "No exact published fare selected"}
          </p>
          <div className="rl-detail-kpis">
            <div>
              <small>Per traveller</small>
              <strong>{fare ? money(fare.amount) : "—"}</strong>
            </div>
            <div>
              <small>Travellers</small>
              <strong>{riders || "—"}</strong>
            </div>
            <div>
              <small>Currency</small>
              <strong>{fare?.currency || "—"}</strong>
            </div>
          </div>
          <p>{quote?.note || "Loading the published fare source…"}</p>
        </section>
      </div>
    </main>
  );
}

type FeedbackEntry = {
  id: string;
  category: string;
  rating: number;
  message: string;
  createdAt: string;
};
const feedbackKey = "rushless-feedback-v1";
function isEntry(value: unknown): value is FeedbackEntry {
  if (!value || typeof value !== "object") return false;
  const r = value as Partial<FeedbackEntry>;
  return (
    typeof r.id === "string" &&
    typeof r.category === "string" &&
    typeof r.message === "string" &&
    typeof r.createdAt === "string" &&
    Number.isFinite(Date.parse(r.createdAt)) &&
    typeof r.rating === "number" &&
    r.rating >= 1 &&
    r.rating <= 5
  );
}
export function Feedback() {
  const [removed, setRemoved] = useState<FeedbackEntry[] | null>(null);
  const [entries, setEntries] = useState<FeedbackEntry[]>([]),
    [category, setCategory] = useState("Experience"),
    [rating, setRating] = useState(4),
    [message, setMessage] = useState(""),
    [notice, setNotice] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    try {
      const saved: unknown = JSON.parse(
        localStorage.getItem(feedbackKey) || "[]",
      );
      if (Array.isArray(saved)) {
        const clean = saved
          .filter(isEntry)
          .filter((entry) => !entry.message.startsWith("Frontend QA sample:"))
          .slice(0, 20);
        setEntries(clean);
        if (clean.length !== saved.length)
          localStorage.setItem(feedbackKey, JSON.stringify(clean));
      }
    } catch {
      setError(
        "Device storage is unavailable. You can still write and export feedback during this visit.",
      );
    }
  }, []);
  function save(e: React.FormEvent) {
    e.preventDefault();
    if (message.trim().length < 10) {
      setError("Add at least 10 characters to describe your suggestion.");
      return;
    }
    const next = [
      {
        id: crypto.randomUUID(),
        category,
        rating,
        message: message.trim(),
        createdAt: new Date().toISOString(),
      },
      ...entries,
    ].slice(0, 20);
    setEntries(next);
    setMessage("");
    setError("");
    try {
      localStorage.setItem(feedbackKey, JSON.stringify(next));
      setNotice(
        "Feedback saved on this device. It has not been sent to RushLess or BMTC. Export it to share with your project team.",
      );
    } catch {
      setNotice(
        "Feedback kept for this visit only. Device storage is unavailable; export a copy before leaving.",
      );
    }
  }
  function download() {
    const blob = new Blob(
      [
        JSON.stringify(
          {
            app: "RushLess",
            storage: "device-local feedback, not submitted to operator",
            entries,
          },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = "rushless-feedback.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function undoClear() {
    if (!removed) return;
    const restored = [
      ...entries,
      ...removed.filter((old) => !entries.some((entry) => entry.id === old.id)),
    ].slice(0, 20);
    try {
      localStorage.setItem(feedbackKey, JSON.stringify(restored));
      setEntries(restored);
      setRemoved(null);
      setNotice("Local feedback notes restored.");
    } catch {
      setError(
        "Unable to restore device storage. Try again before leaving this page.",
      );
    }
  }
  return (
    <main>
      <ToolHeading
        title="Feedback"
        description="Help shape a calmer commute. Keep suggestions on your device and export them when you’re ready."
      />
      <div className="rl-note">
        <MessageSquare size={18} />
        <p>
          This prototype has no operator feedback connection. Notes stay in this
          browser, with the latest 20 retained. Please leave out names, phone
          numbers, precise personal journeys and other sensitive details.
        </p>
      </div>
      <div className="rl-two-columns rl-feedback-layout">
        <form className="rl-panel" onSubmit={save}>
          <h2 className="rl-tool-title">How was your experience?</h2>
          <label className="rl-field">
            Category
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {[
                "Experience",
                "Journey planning",
                "Bus information",
                "Accessibility",
                "Suggestion",
              ].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <div className="rl-field" style={{ marginTop: 20 }}>
            Your rating
          </div>
          <div
            className="rl-rating"
            role="group"
            aria-label="Experience rating"
          >
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                type="button"
                key={n}
                aria-label={`${n} out of 5 stars`}
                aria-pressed={rating === n}
                onClick={() => setRating(n)}
              >
                <Star size={20} fill={n <= rating ? "currentColor" : "none"} />
              </button>
            ))}
          </div>
          <label className="rl-field">
            Your suggestion
            <textarea
              value={message}
              onChange={(e) => {
                setMessage(e.target.value);
                setNotice("");
              }}
              minLength={10}
              maxLength={1500}
              required
              placeholder="What worked, or what could be better?…"
            />
            <small>{message.length}/1500 characters</small>
          </label>
          <div className="rl-form-actions">
            <p>No account or contact information needed.</p>
            <button className="rl-primary dark">
              Save feedback <Check size={16} />
            </button>
          </div>
          {notice && (
            <p className="rl-success" role="status">
              {notice}
            </p>
          )}
          {error && (
            <p className="rl-error" role="alert">
              {error}
            </p>
          )}
        </form>
        <section className="rl-panel">
          <div className="rl-panel-heading">
            <h2>
              <History size={18} />
              Your saved feedback
            </h2>
            <span className="rl-tag neutral">On this device</span>
          </div>
          {entries.length ? (
            <>
              <button className="rl-secondary" onClick={download}>
                <Download size={16} />
                Export {entries.length} notes
              </button>
              {entries.map((entry) => (
                <article className="rl-feedback-entry" key={entry.id}>
                  <strong>
                    {entry.category} · {entry.rating}/5
                  </strong>
                  <p>{entry.message}</p>
                  <small>
                    {new Intl.DateTimeFormat("en-IN", {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(entry.createdAt))}
                  </small>
                </article>
              ))}
              <button
                className="rl-secondary"
                style={{ marginTop: 20 }}
                onClick={() => {
                  try {
                    localStorage.removeItem(feedbackKey);
                    setRemoved(entries);
                    setEntries([]);
                    setNotice("Local feedback notes cleared.");
                  } catch {
                    setError(
                      "Unable to clear device storage. Use your browser’s site-data settings.",
                    );
                  }
                }}
              >
                Clear local notes
              </button>
            </>
          ) : (
            <div className="rl-empty">
              <MessageSquare size={28} />
              <h3>A small suggestion can help.</h3>
              <p>
                Your saved notes will appear here. They stay in this browser
                until you clear them.
              </p>
            </div>
          )}
          {removed && (
            <button
              className="rl-secondary"
              style={{ marginTop: 16 }}
              onClick={undoClear}
            >
              Undo clear
            </button>
          )}
        </section>
      </div>
    </main>
  );
}

export function SavedJourneys() {
  const { profile, stops, refreshProfile } = useTransit();
  const [current, setCurrent] = useState<CommuterProfile | null>(profile);
  useEffect(() => {
    setCurrent(profile);
  }, [profile]);
  const name = (id: string) => stops.find((s) => s.id === id)?.name || id;
  return (
    <main className="rl-saved-page">
      <ToolHeading
        title="Saved journeys"
        description="Your regular routes, ready when you are. Every new search checks current trip availability."
      />
      <CommuterPanel
        profile={current}
        origin={null}
        destination={null}
        stops={stops}
        onProfile={(p) => {
          setCurrent(p);
          refreshProfile();
        }}
        onChoose={(origin, destination) => {
          window.location.href =
            "/planner?" + new URLSearchParams({ origin, destination });
        }}
        onReset={refreshProfile}
      />
      <div className="rl-guide-grid">
        <section className="rl-panel">
          <h2 className="rl-tool-title">
            <Bookmark size={19} /> Saved stop pairs
          </h2>
          {current?.saved.length ? (
            current.saved.map((s) => (
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
                  <Route size={20} />
                </span>
                <span>
                  <strong>{s.name}</strong>
                  <small>
                    {name(s.origin)}
                    <ArrowRight size={12} />
                    {name(s.destination)}
                  </small>
                </span>
                <ArrowUpRight size={17} />
              </Link>
            ))
          ) : (
            <div className="rl-empty">
              <Bookmark size={28} />
              <h3>No saved journeys yet</h3>
              <p>
                Choose two stops in Journey Planner, then save the pair for
                another day.
              </p>
              <Link href="/planner" className="rl-primary dark">
                Plan a journey <ArrowRight size={16} />
              </Link>
            </div>
          )}
        </section>
        <section className="rl-panel">
          <h2 className="rl-tool-title">
            <History size={19} /> Recent searches
          </h2>
          {current?.recent.length ? (
            current.recent.map((s, i) => (
              <Link
                className="rl-saved-row"
                href={"/planner?" + new URLSearchParams(s)}
                key={i}
              >
                <span className="rl-saved-icon">
                  <History size={18} />
                </span>
                <span>
                  <strong>{name(s.origin)}</strong>
                  <small>to {name(s.destination)}</small>
                </span>
                <ArrowUpRight size={16} />
              </Link>
            ))
          ) : (
            <p className="rl-meta">
              Your five most recent stop-pair searches will appear here.
            </p>
          )}
          <p className="rl-meta" style={{ marginTop: 20 }}>
            Saved journeys and settings use an anonymous cookie. Manage names,
            clear recent searches or reset your profile using the button above.
            Feedback notes are stored separately on this device.
          </p>
        </section>
      </div>
    </main>
  );
}
