"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import DeparturePicker, { istIso, istParts } from "./DeparturePicker";
import CommuterPanel, { CommuterProfile } from "./CommuterPanel";
import PilotObservation from "./PilotObservation";
import CrowdForecast from "./CrowdForecast";
import JourneyIntelligence from "./JourneyIntelligence";
import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowRight,
  ArrowUpDown,
  ArrowUpRight,
  BusFront,
  Check,
  ChevronDown,
  ChevronRight,
  Clock3,
  Info,
  Leaf,
  MapPin,
  Navigation,
  Route,
  ShieldCheck,
  Sparkles,
  Users,
  X,
  Zap,
  RefreshCw,
} from "lucide-react";
import { Stop, Journey, Vehicle, request, clock, sourceLabel } from "./types";
const Map = dynamic(() => import("./Map"), {
  ssr: false,
  loading: () => <div className="map-loading">Preparing your corridor…</div>,
});
type Status = {
  mode?: string;
  active_source?: string;
  demand_profile?: string;
  scenario: string;
  simulation_time: string;
  data_note: string;
  demo_controls: boolean;
};
export function StopInput({
  label,
  value,
  onChange,
  placeholder,
  prominent = false,
}: {
  label: string;
  value: Stop | null;
  onChange: (s: Stop | null) => void;
  placeholder?: string;
  prominent?: boolean;
}) {
  const [query, setQuery] = useState(value?.name || "");
  const [open, setOpen] = useState(false);
  const [matches, setMatches] = useState<Stop[]>([]);
  const [active, setActive] = useState(0);
  const [error, setError] = useState("");
  const wrap = useRef<HTMLDivElement>(null);
  const previousValue = useRef(value);
  useEffect(() => {
    if (value) setQuery(value.name);
    else if (previousValue.current) {
      const previousName = previousValue.current.name;
      setQuery((current) => current === previousName ? "" : current);
    }
    previousValue.current = value;
  }, [value]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const timer = setTimeout(
      () =>
        request<Stop[]>("/api/stops/search?q=" + encodeURIComponent(query), {signal:controller.signal})
          .then((r) => {
            if (!controller.signal.aborted) {
              setMatches(r);
              setActive(0);
              setError("");
            }
          })
          .catch(() => {
            if (!controller.signal.aborted)
              setError("Stop search is unavailable. Try again.");
          }),
      180,
    );
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, open]);
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  function select(s: Stop) {
    onChange(s);
    setQuery(s.name);
    setOpen(false);
  }
  return (
    <div className={"stop-field" + (prominent ? " stop-field-prominent" : "")} data-selected={!!value} ref={wrap}>
      <label className={prominent ? "sr-only" : undefined} htmlFor={"stop-" + label}>{label}</label>
      <div className="input-row">
        {prominent ? <span className="stop-prompt-icon" aria-hidden="true">{label === "From" ? <Navigation size={23} strokeWidth={1.8} /> : <MapPin size={24} strokeWidth={1.8} />}</span> : <span className={label === "From" ? "origin-dot" : "destination-dot"} />}
        <input
          id={"stop-" + label}
          role="combobox"
          aria-expanded={open}
          aria-controls={"list-" + label}
          aria-autocomplete="list"
          aria-activedescendant={
            open && matches[active]
              ? "option-" + label + "-" + active
              : undefined
          }
          title={value?.context || undefined}
          autoComplete="off"
          placeholder={placeholder ?? (
            label === "From"
              ? "Where are you starting?"
              : "Where are you going?"
          )}
          value={query}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            onChange(null);
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setOpen(true);
              setActive((a) => Math.min(matches.length - 1, a + 1));
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(0, a - 1));
            }
            if (e.key === "Enter" && open) {
              e.preventDefault();
              if (matches[active]) select(matches[active]);
            }
            if (e.key === "Escape") setOpen(false);
          }}
        />
        {query && (
          <button
            type="button"
            className="clear"
            aria-label={"Clear " + label}
            onClick={() => {
              onChange(null);
              setQuery("");
              setOpen(true);
            }}
          >
            <X size={14} />
          </button>
        )}
      </div>
      {prominent && <span className="stop-prompt-hint">{label === "From" ? "Choose your starting stop" : "Choose your destination"}</span>}
      {open && (
        <ul className="suggestions" id={"list-" + label} role="listbox">
          {matches.map((s, i) => (
            <li
              key={s.id}
              id={"option-" + label + "-" + i}
              role="option"
              aria-selected={i === active}
            >
              <button
                type="button"
                className={i === active ? "active" : ""}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => select(s)}
              >
                <MapPin size={16} />
                <span>
                  {s.name}
                  <small>{s.context}</small>
                </span>
                {s.id === value?.id && <Check size={15} />}
              </button>
            </li>
          ))}
          {(!matches.length || error) && (
            <li className="suggestion-message">
              {error || "No supported stop matches. Try Bellandur."}
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
export default function JourneyPlanner() {
  const [commuter, setCommuter] = useState<CommuterProfile | null>(null);
  const [stops, setStops] = useState<Stop[]>([]),
    [vehicles, setVehicles] = useState<Vehicle[]>([]),
    [status, setStatus] = useState<Status | null>(null);
  const [origin, setOrigin] = useState<Stop | null>(null),
    [destination, setDestination] = useState<Stop | null>(null),
    [preference, setPreference] = useState("comfortable");
  const [journeys, setJourneys] = useState<Journey[]>([]),
    [selected, setSelected] = useState(""),
    [searched, setSearched] = useState(false),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [offline, setOffline] = useState(false),
    [details, setDetails] = useState(false),
    [info, setInfo] = useState(false),
    [changed, setChanged] = useState(false);
  const [plannedDeparture, setPlannedDeparture] = useState("");
  const [departureInput, setDepartureInput] = useState("");
  const [searchRevision, setSearchRevision] = useState(0);
  const [mobileView, setMobileView] = useState("list");
  const activeRequests = useRef(0);
  const requestSequence = useRef(0);
  const searchPair = useRef<{ origin: string; destination: string } | null>(
      null,
    ),
    lastRecommended = useRef("");
  const selectedSnapshot = useRef<Journey | null>(null);
  const selectedJourney = searched
    ? journeys.find((j) => j.id === selected) ||
      (selectedSnapshot.current?.id === selected
        ? selectedSnapshot.current
        : null) ||
      (selected ? null : journeys[0]) ||
      null
    : null;
  if (selectedJourney) selectedSnapshot.current = selectedJourney;
  const refresh = useCallback(async () => {
    try {
      const [v, s] = await Promise.all([
        request<Vehicle[]>("/api/vehicles"),
        request<Status>("/api/system/status"),
      ]);
      setVehicles(v);
      setStatus(s);
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);
  useEffect(() => {
    Promise.all([
      request<Stop[]>("/api/stops/search?limit=10000"),
      request<CommuterProfile>("/api/profile").catch(() => null),
    ])
      .then(([s, profile]) => {
        setCommuter(profile);
        const params = new URLSearchParams(window.location.search);
        if (profile) setPreference(params.get("preference") === "fastest" || params.get("preference") === "comfortable" ? params.get("preference")! : profile.preference);
        try {
          const saved = params.get("depart_at") || sessionStorage.getItem("rushless.planner.departure") || "";
          const timestamp = saved.includes("+") || saved.endsWith("Z") ? new Date(saved) : saved ? new Date(istIso(saved)) : null;
          if (timestamp && timestamp.getTime() >= Date.now()) { const parts = istParts(timestamp); setDepartureInput(parts.date + "T" + parts.time); }
        } catch { /* Invalid saved departures revert to Leave now. */ }
        setStops(s);
        setOrigin(
          s.find(
            (x) =>
              x.id ===
              (new URLSearchParams(window.location.search).get("origin") ||
                profile?.last_context?.origin ||
                "silk"),
          ) || null,
        );
        setDestination(
          s.find(
            (x) =>
              x.id ===
              (new URLSearchParams(window.location.search).get("destination") ||
                profile?.last_context?.destination ||
                "marathahalli"),
          ) || null,
        );
      })
      .catch(() => setOffline(true));
    refresh();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 10000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    if (!commuter || commuter.preference === preference) return;
    let active = true;
    request<CommuterProfile>("/api/profile/preferences", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preference }),
    })
      .then((p) => {
        if (active) setCommuter(p);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [preference, commuter]);
  const loadJourneys = useCallback(
    async (
      pair: { origin: string; destination: string },
      mode: string,
      quiet = false,
    ) => {
      if (quiet && activeRequests.current > 0) return;
      activeRequests.current++;
      const sequence = ++requestSequence.current;
      if (!quiet) setLoading(true);
      try {
        const result = await request<{ journeys: Journey[] }>(
          "/api/journeys?" +
            new URLSearchParams({
              ...pair,
              preference: mode,
              max_transfers: "1",
              allow_demo: "true",
              ...(plannedDeparture
                ? { depart_at: istIso(plannedDeparture) }
                : {}),
            }),
        );
        if (sequence !== requestSequence.current) return;
        setJourneys(result.journeys);
        setSelected((old) => old || result.journeys[0]?.id || "");
        if (
          lastRecommended.current &&
          lastRecommended.current !== result.journeys[0]?.id
        )
          setChanged(true);
        lastRecommended.current = result.journeys[0]?.id || "";
        setError("");
        setOffline(false);
      } catch (e) {
        if (sequence === requestSequence.current) {
          setError((e as Error).message);
          setJourneys([]);
        }
      } finally {
        activeRequests.current--;
        if (sequence === requestSequence.current) setLoading(false);
      }
    },
    [plannedDeparture],
  );
  useEffect(() => {
    if (!searched || !searchPair.current) return;
    loadJourneys(searchPair.current, preference);
    if (plannedDeparture) return;
    const timer = setInterval(() => {
      if (searchPair.current && document.visibilityState === "visible")
        loadJourneys(searchPair.current, preference, true);
    }, 30000);
    return () => clearInterval(timer);
  }, [searched, preference, loadJourneys, plannedDeparture, searchRevision]);
  function search(e?: React.FormEvent) {
    e?.preventDefault();
    if (!origin || !destination) {
      setError("Choose a starting stop and destination from the suggestions.");
      return;
    }
    if (origin.id === destination.id) {
      setError("Choose two different stops.");
      return;
    }
    if (departureInput) {
      let timestamp;
      try { timestamp = new Date(istIso(departureInput)).getTime(); } catch { timestamp = NaN; }
      if (!Number.isFinite(timestamp) || timestamp < Date.now() - 60000 || timestamp > Date.now() + 30 * 86400000) { setError("Choose an IST departure between now and 30 days ahead, or select Leave now."); return; }
    }
    request<CommuterProfile>("/api/profile/recent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ origin: origin.id, destination: destination.id }),
    })
      .then(setCommuter)
      .catch(() => {});
    searchPair.current = { origin: origin.id, destination: destination.id };
    setSelected("");
    selectedSnapshot.current = null;
    setSearched(true);
    setDetails(false);
    setPlannedDeparture(departureInput);
    setSearchRevision((old) => old + 1);
    window.history.replaceState(null, "", "/planner?" + new URLSearchParams({origin:origin.id,destination:destination.id,preference,...(departureInput?{depart_at:istIso(departureInput)}:{})}));
  }
  function choosePreference(mode:string) { setPreference(mode); setSelected(""); selectedSnapshot.current=null; const url=new URL(window.location.href);url.searchParams.set("preference",mode);window.history.replaceState(null,"",url.pathname+url.search); }
  const firstLeg=selectedJourney?.transfers?selectedJourney.legs?.[0]:null;
  const monitoredJourney=firstLeg && selectedJourney ? {...selectedJourney,...firstLeg,id:firstLeg.trip_id,transfers:0,legs:[],recommended:false}:selectedJourney;
  return (
    <main className="rl-planner-screen" data-mobile-view={mobileView}>
      <div className="rl-planner-view-switch" aria-label="Planner mobile view"><button aria-pressed={mobileView==="list"} onClick={()=>setMobileView("list")}>Journey list</button><button aria-pressed={mobileView==="map"} onClick={()=>setMobileView("map")}>Route map</button></div>
      <div className="workspace">
        <section className={"planner " + (searched ? "results-mode" : "")}>
          <p className="rl-note">Real schedules are searched first. If none are found, clearly labeled demo connections are shown. Demo times and lines are illustrative, not actual bus services.</p>
          <div className="intro">
            <div className="eyebrow">
              <span /> Journey Planner
            </div>
            <h1>Plan your journey</h1>
            <p>Find the quickest or most comfortable way across Bengaluru.</p>
          </div>
          <form className="search-panel" onSubmit={search}>
            <div className="search-top">
              <span>WHERE ARE WE HEADED?</span>
              <span className="local-label">Bengaluru · ORR</span>
            </div>
            <div className="location-fields">
              <StopInput label="From" value={origin} onChange={setOrigin} />
              <div className="swap-divider">
                <span />
                <button
                  type="button"
                  aria-label="Swap source and destination"
                  onClick={() => {
                    setOrigin(destination);
                    setDestination(origin);
                  }}
                >
                  <ArrowUpDown size={16} />
                </button>
              </div>
              <StopInput
                label="To"
                value={destination}
                onChange={setDestination}
              />
            </div>
            <DeparturePicker value={departureInput} onChange={(value)=>{setDepartureInput(value);sessionStorage.setItem("rushless.planner.departure",value);}} />
            <button
              className="search-button"
              disabled={loading || !origin || !destination}
              type="submit"
            >
              {loading ? "Finding your journeys…" : "Find buses"}
              {loading ? (
                <RefreshCw size={18} className="spin" />
              ) : (
                <ArrowRight size={19} />
              )}
            </button>
            <div className="search-foot">
              <ShieldCheck size={14} /> No sign-up. Just a better way there.
            </div>
          </form>
          <div className="rl-planner-preference"><span>Travel preference</span><div className="preferences" aria-label="Journey preference"><button aria-pressed={preference==="fastest"} className={preference==="fastest"?"active":""} onClick={()=>choosePreference("fastest")}><Zap size={14}/>Fastest</button><button aria-pressed={preference==="comfortable"} className={preference==="comfortable"?"active":""} onClick={()=>choosePreference("comfortable")}><Leaf size={14}/>Comfortable</button></div><p>{journeys.length && journeys.every(j=>j.crowding==="Unknown")?"Crowding unknown. Comfortable uses available time, transfers and source confidence; both modes can recommend the same bus.":"Fastest compares total time. Comfortable balances crowding, changes and reliability where known."}</p></div>
          {error && (
            <div role="alert" className="error">
              {error}
              <button onClick={() => search()}>Try again</button>
            </div>
          )}
          {offline && (
            <div role="status" className="error">
              Backend disconnected. Start the API server, then{" "}
              <button
                onClick={() => {
                  refresh();
                  if (!stops.length) location.reload();
                }}
              >
                retry
              </button>
              .
            </div>
          )}
          {!searched ? (
            <>
              <div className="try-route">
                <span>TRY A CORRIDOR</span>
                <button
                  onClick={() => {
                    setOrigin(stops.find((s) => s.id === "silk") || null);
                    setDestination(
                      stops.find((s) => s.id === "marathahalli") || null,
                    );
                  }}
                >
                  Silk Board <ArrowRight size={13} /> Marathahalli{" "}
                  <ArrowUpRight size={13} />
                </button>
              </div>
              <div className="benefits">
                <div>
                  <span>
                    <Clock3 size={19} />
                  </span>
                  <strong>Less guessing.</strong>
                  <p>Clear arrival estimates.</p>
                </div>
                <div>
                  <span>
                    <Users size={19} />
                  </span>
                  <strong>More breathing room.</strong>
                  <p>Crowding before boarding.</p>
                </div>
                <div>
                  <span>
                    <Sparkles size={19} />
                  </span>
                  <strong>A better choice.</strong>
                  <p>Journeys that suit you.</p>
                </div>
              </div>
              <div className="coverage">
                <Route size={16} />
                <p>
                  A small corridor. A meaningful start.
                  <br />
                  <span>
                    {status?.mode && status.mode !== "simulation"
                      ? "Matched GTFS corridor · source details in Data Health"
                      : "Published BMTC stops and route patterns."}
                  </span>
                </p>
                <button
                  aria-label="About coverage"
                  onClick={() => setInfo(true)}
                >
                  <Info size={16} />
                </button>
              </div>
            </>
          ) : (
            <section className="results" aria-live="polite">
              <div className="results-heading">
                <div>
                  <span className="eyebrow">YOUR OPTIONS</span>
                  <h2>
                    {loading
                      ? "Finding your ride…"
                      : journeys.length ? `${journeys.length} available ${journeys.length===1?"journey":"journeys"}` : "Available journeys"}
                  </h2>
                </div>
                <Link className="rl-text-link" href={"/route-explorer?"+new URLSearchParams({origin:origin?.id||"",destination:destination?.id||"",...(plannedDeparture?{depart_at:istIso(plannedDeparture)}:{})})}>Explore more routes <ArrowUpRight size={13}/></Link>
              </div>
              <p className="rl-note">Direct + one same-stop change. Bounded search; three-minute transfer buffer. Check boarding locations.</p>
              {plannedDeparture && (
                <p className="rl-note">
                  Scheduled departure:{" "}
                  {new Date(istIso(plannedDeparture)).toLocaleString("en-IN", {
                    timeZone: "Asia/Kolkata",
                  })}{" "}
                  IST · Timetable only. Monitoring is available for current departures.
                </p>
              )}
              {changed && (
                <button className="changed" onClick={() => setChanged(false)}>
                  Recommendation updated as conditions changed. <X size={13} />
                </button>
              )}
              {loading && !journeys.length && <div className="skeleton" />}
              {!loading && !journeys.length && !error && (
                <div className="empty">
                  <BusFront />
                  <h3>No available journey found</h3>
                  <p>We couldn&apos;t find a supported journey for these stops and departure time. Directional platforms, the timetable and the one-transfer search limit matter.</p>
                  <div className="rl-empty-actions"><button onClick={()=>document.getElementById("departure-date")?.focus()}>Change departure</button><button onClick={()=>{setOrigin(null);document.getElementById("stop-From")?.focus();}}>Choose another stop</button><Link href="/live-route">View supported routes</Link><button onClick={()=>{setOrigin(stops.find(s=>s.id==="silk")||null);setDestination(stops.find(s=>s.id==="marathahalli")||null);setSearched(false);}}>Try Silk Board → Marathahalli</button></div>
                  {stops.filter(s=>s.name===destination?.name&&s.id!==destination.id).map(s=><button className="rl-other-platform" key={s.id} onClick={()=>{setDestination(s);setSearched(false);}}>Other direction: {s.name} · {s.context}</button>)}
                </div>
              )}
              {journeys.map((j) => (
                <button
                  key={j.id}
                  className={
                    "journey-card " +
                    (selectedJourney?.id === j.id ? "selected " : "") +
                    (j.recommended ? "recommended" : "")
                  }
                  onClick={() => {
                    setSelected(j.id);
                    setDetails(true);
                    setMobileView("map");
                  }}
                >
                  {j.recommended && (
                    <div className="recommend-label">
                      <Sparkles size={12} /> Recommended for you{" "}
                      <span>
                        {preference === "comfortable"
                          ? "A little less rush"
                          : "Get there sooner"}
                      </span>
                    </div>
                  )}
                  <div className="card-main">
                    <div className="route-badge">
                      <BusFront size={15} />
                      {j.route_name}
                    </div>
                    <span className={"crowd " + j.crowding.toLowerCase()}>
                      <Users size={13} />
                      {j.crowding === "Unknown"
                        ? "Crowding unknown"
                        : j.crowding + " crowding"}
                    </span>
                    <ChevronRight size={17} />
                  </div>
                  <div className="card-times">
                    <div>
                      <strong>
                        {Math.ceil(j.wait_minutes)}
                        <small> min</small>
                      </strong>
                      <span>until your bus</span>
                      {j.metadata.uncertainty && (
                        <span className="eta-range">
                          About{" "}
                          {Math.floor(j.metadata.uncertainty.lower_minutes)}–
                          {Math.ceil(j.metadata.uncertainty.upper_minutes)} min
                          ·{" "}
                          {j.metadata.uncertainty.calibrated
                            ? "calibrated"
                            : "heuristic"}
                        </span>
                      )}
                    </div>
                    <div>
                      <b>{Math.ceil(j.total_minutes)} min</b>
                      <span>total journey</span>
                    </div>
                    <div>
                      <b>{clock(j.arrival_at)}</b>
                      <span>at destination</span>
                    </div>
                  </div>
                  <div className="card-explain">{j.explanation}</div>
                  <div className="card-bottom">
                    <span>
                      <ShieldCheck size={12} />
                      {j.metadata.confidence} confidence ·{" "}
                      {sourceLabel(j.metadata.source)}
                    </span>
                    <span>{j.transfers?"1 transfer":"Direct"} · {j.stop_count} stops</span>
                  </div>
                </button>
              ))}
            </section>
          )}
          <div className="planner-commuter">
            <CommuterPanel
              profile={commuter}
              origin={origin}
              destination={destination}
              stops={stops}
              onProfile={setCommuter}
              onChoose={(from, to) => {
                setOrigin(stops.find((s) => s.id === from) || null);
                setDestination(stops.find((s) => s.id === to) || null);
                setSearched(false);
              }}
              onReset={() => {
                setPreference("comfortable");
                setOrigin(null);
                setDestination(null);
                setSearched(false);
              }}
            />
          </div>
        </section>
        <section className="map-section" aria-label="Journey map">
          <div className="map-top-label">
            <span className="map-location">
              <Navigation size={14} /> BENGALURU <span> / </span> JOURNEY MAP
            </span>
            <button onClick={() => setInfo(true)} aria-label="Map information">
              <Info size={17} />
            </button>
          </div>
          <Map
            journey={selectedJourney}
            stops={
              selectedJourney?.stops ||
              [origin, destination].filter((s): s is Stop => !!s)
            }
            vehicles={vehicles}
            sourceMode={status?.mode || "schedule"}
            legGeometries={selectedJourney?.legs?.map((leg,i)=>({geometry:leg.geometry,color:i?"#246dce":"#176b5d"}))}
            transferStops={selectedJourney?.transfers?selectedJourney.legs?.slice(0,-1).map(l=>l.destination):[]}
          />
          <div className="map-demo">
            <span className="pulse" />{" "}
            {status?.mode && status.mode !== "simulation"
              ? "GTFS CORRIDOR"
              : "GTFS NETWORK"}{" "}
            <span>
              {status?.mode === "authorized"
                ? "See Data Health for freshness"
                : status?.mode === "replay"
                  ? "Historical replay, not live"
                  : "Not live BMTC data"}
            </span>
          </div>
          {!searched && (
            <div className="map-story">
              <span className="story-icon">
                <BusFront size={23} />
              </span>
              <div>
                <span className="eyebrow">Your corridor, at a glance</span>
                <h2>
                  Good journeys start
                  <br />
                  before you board.
                </h2>
                <p>
                  Arrivals, crowding, and a little peace of mind.
                  <br />
                  All in one place.
                </p>
              </div>
              <span className="story-route">
                SILK BOARD <ArrowRight size={15} /> MARATHAHALLI
              </span>
            </div>
          )}
          {selectedJourney && (
            <div className="map-summary">
              <span className="story-icon">
                <BusFront size={22} />
              </span>
              <div>
                <strong>
                  {selectedJourney.route_name}{" "}
                  <span>· {Math.ceil(selectedJourney.total_minutes)} min</span>
                </strong>
                <p>
                  {selectedJourney.origin.name} <ArrowRight size={12} />{" "}
                  {selectedJourney.destination.name}
                </p>
              </div>
              <button onClick={() => setDetails(!details)}>
                {details ? "Hide" : "Details"} <ChevronDown size={16} />
              </button>
            </div>
          )}
          <div className="map-legend">
            <span>
              <i className="line-key" />
              Selected corridor
            </span>
            <span>
              <i className="bus-key" />
              {status?.mode === "simulation"
                ? "Simulated bus"
                : status?.mode === "replay"
                  ? "Replayed vehicle"
                  : "Observed vehicle"}
            </span>
            <span>
              <i className="stop-key" />
              Bus stop
            </span>
          </div>
        </section>
      </div>
      {monitoredJourney && monitoredJourney.metadata.source !== "demo_journey" && !plannedDeparture && (
        <div className="rl-planner-watch-wrap">
        {!!selectedJourney?.transfers && <p className="rl-note">This journey changes buses. Monitoring below covers the first bus to {monitoredJourney.destination.name}. Confirm your progress before planning the next leg.</p>}
        <JourneyIntelligence
          journey={monitoredJourney}
          preference={preference}
          alertsEnabled={commuter?.alerts_enabled ?? true}
          expanded={details}
          onUpdate={() => {
            if (searchPair.current)
              loadJourneys(searchPair.current, preference, true);
          }}
          onSelect={(j) => {
            setJourneys((old) => [j, ...old.filter((x) => x.id !== j.id)]);
            setSelected(j.id);
          }}
        />
        </div>
      )}
      {details && selectedJourney && (
        <section className="detail-panel">
          <div className="detail-header">
            <div>
              <span className="eyebrow">Your journey, step by step</span>
              <h2>
                {selectedJourney.origin.name} to{" "}
                {selectedJourney.destination.name}
              </h2>
            </div>
            <button
              onClick={() => setDetails(false)}
              aria-label="Close journey details"
            >
              <X size={20} />
            </button>
          </div>
          {!plannedDeparture && !selectedJourney.transfers && selectedJourney.metadata.source !== "demo_journey" && (
            <CrowdForecast
              journey={selectedJourney}
              controls={!!status?.demo_controls}
              onUpdate={() => {
                refresh();
                if (searchPair.current)
                  loadJourneys(searchPair.current, preference, true);
              }}
            />
          )}
          <div className="detail-grid">
            <div className="timeline">
              {selectedJourney.stops.map((s, i) => (
                <div key={s.id}>
                  <span>
                    {i === 0 ? (
                      <Navigation size={14} />
                    ) : i === selectedJourney.stops.length - 1 ? (
                      <MapPin size={14} />
                    ) : (
                      <i />
                    )}
                  </span>
                  <p>
                    <strong>{s.name}</strong>
                    {i === 0 && (
                      <small>
                        Board {selectedJourney.route_name} around{" "}
                        {clock(selectedJourney.boarding_at)}
                      </small>
                    )}
                    {i === selectedJourney.stops.length - 1 && (
                      <small>
                        Alight around {clock(selectedJourney.arrival_at)}
                      </small>
                    )}
                  </p>
                </div>
              ))}
            </div>
            <div className="detail-trust">
              <ShieldCheck size={24} />
              <h3>A clear picture of your prediction</h3>
              <p>
                {selectedJourney.crowding} crowding forecast at{" "}
                {selectedJourney.origin.name},{" "}
                {status?.mode === "simulation"
                  ? "after modeled boarding and alighting."
                  : "without inventing passenger counts from GPS."}
              </p>
              <p>
                {selectedJourney.metadata.report_count ? (
                  <span>
                    {selectedJourney.metadata.report_count} recent demo
                    report(s).{" "}
                    {selectedJourney.metadata.report_conflict
                      ? "Conflicting reports; reduced confidence."
                      : "Limited report data; model estimate retained."}
                    <br />
                  </span>
                ) : null}
                Source: {selectedJourney.metadata.source}.{" "}
                {selectedJourney.metadata.confidence} confidence within the
                active data source.
              </p>
              <p>
                Observation: {clock(selectedJourney.metadata.observed_at)} IST.
                <br />
                Forecast: {clock(selectedJourney.metadata.generated_at)} IST.
              </p>
              <button onClick={() => setInfo(true)}>
                Understand these estimates <ArrowUpRight size={14} />
              </button>
            </div>
          </div>
        </section>
      )}
      <div className="commuter-tools">
        <PilotObservation />
      </div>
      <footer>
        <a href="/insights" className="insights-link">
          Corridor insights
        </a>
        <span>Made for a calmer Bengaluru commute.</span>
        <span>
          <span className="footer-dot" />{" "}
          {status
            ? `${status.mode === "simulation" ? "Demo clock" : "Source clock"} ${clock(status.simulation_time)} IST`
            : "Connecting to schedules…"}
          <button onClick={() => setInfo(true)}>
            Data & transparency <ArrowUpRight size={12} />
          </button>
        </span>
      </footer>
      <Dialog.Root open={info} onOpenChange={setInfo}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content">
            <Dialog.Close
              className="dialog-close"
              aria-label="Close data explanation"
            >
              <X size={20} />
            </Dialog.Close>
            <div className="info-icon">
              <ShieldCheck size={26} />
            </div>
            <Dialog.Title>Useful estimates. Honest data.</Dialog.Title>
            <Dialog.Description>
              RushLess uses published BMTC schedules for journey planning.
            </Dialog.Description>
            <div className="info-sections">
              <section>
                <h3>What you’re seeing</h3>
                <p>
                  {status?.data_note ||
                    "Published BMTC schedule data. Live tracking is not connected."}{" "}
                  {status?.mode === "simulation"
                    ? "Vehicles, timetables, demand and forecasts are simulated. The clock starts at 8:30 AM IST when a scenario resets."
                    : "Published GTFS schedules can be inaccurate. Static route geometry does not establish live vehicle positions. No passenger counts are inferred from GPS."}
                </p>
              </section>
              <section>
                <h3>What crowding means</h3>
                <p>
                  Low: below 40% capacity. Moderate: 40–75%. High: above 75%.
                  These are demo thresholds, not official BMTC standards or a
                  promise of seats. Forecasts include modeled boarding at your
                  stop.
                </p>
              </section>
              <section>
                <h3>How much to trust it</h3>
                <p>
                  A recent authorized observation can support a higher
                  confidence level. Missing GPS uses a labeled timetable
                  fallback with Low confidence and Unknown crowding. Confidence
                  is a heuristic, never measured accuracy. No trained model is
                  active without verified evidence.
                </p>
              </section>
              <section>
                <h3>Maps & transport data</h3>
                <p>
                  Map © OpenStreetMap contributors. Route shapes come from
                  published GTFS. Fallback lines connect stops and may not
                  follow roads. The repository includes a separate GTFS
                  validation/import utility. The included corridor was extracted
                  from the feed; arbitrary imports do not automatically replace
                  it.
                </p>
                <a
                  href="https://github.com/Vonter/bmtc-gtfs"
                  target="_blank"
                  rel="noreferrer"
                >
                  Unofficial BMTC GTFS source <ArrowUpRight size={13} />
                </a>
              </section>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </main>
  );
}
