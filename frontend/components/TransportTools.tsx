"use client";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  BusFront,
  CalendarClock,
  Info,
  MapPin,
  Radio,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import { useTransit } from "./TransitContext";
import { useLocale } from "./Locale";
import { Stop, Meta, request, clock, sourceLabel } from "./types";
import ScheduledServices from "./ScheduledServices";
import DemoTracking from "./DemoTracking";
const Map = dynamic(() => import("./Map"), {
  ssr: false,
  loading: () => <div className="map-loading">Preparing the corridor map…</div>,
});
type RouteDetail = {
  id: string;
  name: string;
  stops: Stop[];
  geometry: [number, number][];
  geometry_source?: string;
};
type Arrival = {
  vehicle_id: string;
  route_id: string;
  route_name: string;
  minutes: number;
  arrival_at: string;
  scheduled_at: string;
  crowding: string;
  metadata: Meta;
};

export function ToolHeading({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: React.ReactNode;
}) {
  const { t } = useLocale();
  return (
    <div className="rl-page-heading">
      <div>
        <h1>{t(title)}</h1>
        <p>{description}</p>
      </div>
      {children}
    </div>
  );
}
export function DataNotice() {
  const { status, error, refresh } = useTransit();
  return error ? (
    <div className="rl-error" role="alert">
      {error} Cached information may be out of date.
      <button onClick={refresh}>Retry</button>
    </div>
  ) : (
    <div className="rl-note">
      <Info size={17} />
      <p>
        {!status
          ? "Connecting to the transport source…"
          : status.mode === "simulation"
            ? "You’re exploring a simulated Bengaluru corridor. Vehicles, times and crowding are demonstration data, not a live BMTC service."
            : `${sourceLabel(status.active_source || status.mode)}. Positions and times depend on source freshness. Missing positions stay unavailable.`}
      </p>
      <Link href="/insights" aria-label="Check data source">
        <ArrowUpRight size={16} />
      </Link>
    </div>
  );
}
export function StopSelect({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (id: string) => void;
}) {
  const { stops } = useTransit();
  const { t } = useLocale();
  return (
    <label className="rl-field">
      {t(label)}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {stops.length ? (
          stops.map((s) => (
            <option value={s.id} key={s.id}>
              {s.name}
            </option>
          ))
        ) : (
          <option value="">Loading stops…</option>
        )}
      </select>
    </label>
  );
}
function useRouteDetail(id: string) {
  const [data, setData] = useState<RouteDetail | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    if (!id) { setData(null); setError(""); return; }
    let active = true;
    setData(null);
    setError("");
    request<RouteDetail>("/api/routes/" + encodeURIComponent(id))
      .then((r) => {
        if (active) setData(r);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [id]);
  return { data, error };
}

export function TrackBus() {
  const { vehicles, status } = useTransit();
  const [view, setView] = useState<"scheduled" | "observed" | "demo">("scheduled");
  useEffect(() => {
    const vehicle = new URLSearchParams(window.location.search).get("vehicle");
    if (vehicle && !vehicle.startsWith("scheduled:")) setView("observed");
  }, []);
  const observedCount = vehicles.filter((v) => !v.completed && v.metadata.source !== "schedule").length;
  return <main>
    <ToolHeading title="Track a Bus" description="Find published bus services and upcoming departures, or inspect a bus with an observed source position." />
    <DataNotice />
    <div className="rl-service-tabs" role="group" aria-label="Bus data view">
      <button aria-pressed={view === "scheduled"} onClick={() => setView("scheduled")}><CalendarClock size={16} /> Scheduled services</button>
      <button aria-pressed={view === "observed"} onClick={() => setView("observed")}><Radio size={16} /> Observed buses ({observedCount})</button>
      <button aria-pressed={view === "demo"} onClick={() => setView("demo")}><BusFront size={16} /> Preview demo tracking</button>
    </div>
    {status?.mode === "schedule" && <p className="rl-meta" style={{ marginBottom: 20 }}>Live BMTC GPS is not connected. You can browse real published routes and schedules below. Scheduled services are not observed buses.</p>}
    {view === "scheduled" ? <ScheduledServices /> : view === "demo" ? <DemoTracking onClose={()=>setView("scheduled")}/> : <ObservedBuses />}
  </main>;
}

function ObservedBuses() {
  const { vehicles, stops, status, loading, refresh } = useTransit();
  const { t } = useLocale();
  const [query, setQuery] = useState(""),
    [selected, setSelected] = useState("");
  useEffect(() => {
    setSelected(
      new URLSearchParams(window.location.search).get("vehicle") || "",
    );
  }, []);
  const available = vehicles.filter(
    (v) =>
      !v.completed &&
      v.metadata.source !== "schedule" &&
      `${v.id} ${v.route_name}`.toLowerCase().includes(query.toLowerCase()),
  );
  const vehicle = available.find((v) => v.id === selected) || available[0];
  const { data: route, error: routeError } = useRouteDetail(
    vehicle?.route_id || "",
  );
  const stopName = (id: string) => stops.find((s) => s.id === id)?.name || id;
  const positioned =
    !!vehicle &&
    vehicle.lat !== null &&
    vehicle.lon !== null &&
    vehicle.metadata.confidence !== "Low" &&
    vehicle.metadata.source !== "schedule";
  return (
    <div>
      <div className="rl-two-columns">
        <section className="rl-panel">
          <label className="rl-field">
            {t("Search")}
            <div className="rl-search-input">
              <Search size={17} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Route or vehicle ID…"
                aria-label="Search buses"
              />
            </div>
          </label>
          <p className="rl-meta" style={{ margin: "12px 0" }}>
            {loading
              ? "Loading vehicles…"
              : `${available.length} matching observed vehicles · refreshes every 10 seconds`}
          </p>
          <div className="rl-vehicle-list">
            {available.map((v) => (
              <button
                key={v.id}
                className={
                  "rl-vehicle-row" +
                  (vehicle?.id === v.id ? " is-selected" : "")
                }
                onClick={() => setSelected(v.id)}
                aria-pressed={vehicle?.id === v.id}
              >
                <div>
                  <strong>
                    <BusFront size={17} />
                    {v.route_name}
                  </strong>
                  <small>{v.id}</small>
                </div>
                <p>Next: {stopName(v.next_stop)}</p>
                <div style={{ marginTop: 9 }}>
                  <span className="rl-tag neutral">
                    {sourceLabel(v.metadata.source)}
                  </span>
                  <ArrowUpRight size={14} />
                </div>
              </button>
            ))}
          </div>
          {!loading && !available.length && (
            <div className="rl-empty">
              <Search size={25} />
              <h2>Live positions unavailable</h2>
              <p>
                No observed vehicles match this search. Use Scheduled services
                above to browse the published network. Live positions require an authorized feed.
              </p>
              <button
                className="rl-secondary"
                onClick={() => {
                  setQuery("");
                  refresh();
                }}
              >
                Clear & retry
              </button>
            </div>
          )}
        </section>
        <div>
          <div className="rl-tool-map">
            <Map
              journey={null}
              stops={route?.stops || []}
              vehicles={vehicle ? [vehicle] : []}
              geometry={route?.geometry}
              sourceMode={status?.mode || "simulation"}
            />
            <div className="rl-map-caption">
              {vehicle
                ? positioned
                  ? `${vehicle.route_name} · ${vehicle.id} · observed ${clock(vehicle.metadata.observed_at)} IST`
                  : "This vehicle has no usable fresh position. No location marker is shown."
                : "Choose an active vehicle to inspect its location."}{" "}
              {route?.geometry_source || "Stop geometry"}.
            </div>
          </div>
          {routeError && (
            <p role="alert" className="rl-error">
              Route details: {routeError}
            </p>
          )}
          {vehicle && (
            <section className="rl-panel rl-vehicle-detail">
              <div className="rl-panel-heading">
                <h2>
                  <BusFront size={18} />
                  {vehicle.route_name}
                  <span className="rl-tag neutral">{vehicle.id}</span>
                </h2>
                <span className="rl-tag">
                  {vehicle.metadata.confidence} confidence
                </span>
              </div>
              <div className="rl-detail-kpis">
                <div>
                  <small>Next stop</small>
                  <strong>{stopName(vehicle.next_stop)}</strong>
                </div>
                <div>
                  <small>
                    {vehicle.metadata.source === "simulation"
                      ? "Simulated onboard"
                      : "Reported onboard"}
                  </small>
                  <strong>
                    {vehicle.passengers !== null && vehicle.capacity !== null
                      ? `${vehicle.passengers} / ${vehicle.capacity}`
                      : "Unknown"}
                  </strong>
                </div>
                <div>
                  <small>Position</small>
                  <strong>{positioned ? "Available" : "Unavailable"}</strong>
                </div>
              </div>
              <p className="rl-meta">
                {sourceLabel(vehicle.metadata.source)} · Observation{" "}
                {clock(vehicle.metadata.observed_at)} IST. Current onboard load
                is separate from a boarding-stop crowd forecast.
              </p>
              <Link
                href="/planner"
                className="rl-text-link"
                style={{ marginTop: 16 }}
              >
                Compare a journey <ArrowRight size={15} />
              </Link>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

export function LiveRoute() {
  const { routes, vehicles, stops, status, loading } = useTransit();
  const { t } = useLocale();
  const [selected, setSelected] = useState("");
  const [routeQuery, setRouteQuery] = useState("");
  const [searchError, setSearchError] = useState("");
  const [matches, setMatches] = useState<typeof routes | null>(null);
  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      request<typeof routes>("/api/routes?q=" + encodeURIComponent(routeQuery))
        .then((r) => {
          if (active) {
            setMatches(r);
            setSearchError("");
          }
        })
        .catch(() => {
          if (active) setSearchError("Route search could not load. Try again.");
        });
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [routeQuery]);
  const catalog = matches || routes;
  const routeId = catalog.some((r) => r.id === selected)
    ? selected
    : catalog[0]?.id || "";
  const { data: route, error } = useRouteDetail(routeId);
  const buses = vehicles.filter(
    (v) =>
      !v.completed &&
      v.metadata.source !== "schedule" &&
      v.route_id === routeId,
  );
  return (
    <main>
      <ToolHeading
        title="Track a Live Route"
        description="Follow a route’s stop sequence and vehicle activity. The source label tells you whether it is live, replayed or simulated."
      />
      <DataNotice />
      <label className="rl-field">
        Search all imported routes
        <input
          value={routeQuery}
          onChange={(e) => setRouteQuery(e.target.value)}
          placeholder="Route name, e.g. 500-F…"
        />
      </label>
      {searchError && (
        <p role="alert" className="rl-error">
          {searchError}
        </p>
      )}
      <div className="rl-toolbar">
        <label className="rl-field">
          {t("Route")}
          <select value={routeId} onChange={(e) => setSelected(e.target.value)}>
            {catalog.length ? (
              catalog.map((r) => (
                <option value={r.id} key={r.id}>
                  {r.name} · {r.id}
                </option>
              ))
            ) : (
              <option value="">No routes available</option>
            )}
          </select>
        </label>
        <span className="rl-tag">
          <Radio size={12} />
          {buses.length} active vehicles
        </span>
      </div>
      {error && (
        <p role="alert" className="rl-error">
          {error}
        </p>
      )}
      {!loading && !catalog.length ? (
        <div className="rl-empty">
          <Radio size={28} />
          <h2>No route patterns available</h2>
          <p>Check the source connection in Insights.</p>
          <Link href="/insights" className="rl-secondary">
            Open insights
          </Link>
        </div>
      ) : (
        <div className="rl-two-columns">
          <section className="rl-panel">
            <h2 className="rl-tool-title">{route?.name || "Loading route…"}</h2>
            <p className="rl-meta" style={{ marginBottom: 22 }}>
              {route?.stops.length || "—"} supported stops. Stop order is
              directional; reverse service may use a different pattern.
            </p>
            <ol className="rl-stop-list">
              {route?.stops.map((s) => (
                <li key={s.id}>
                  <Link href={"/timetable?stop=" + encodeURIComponent(s.id)}>
                    {s.name}
                  </Link>
                  <small>{s.context}</small>
                </li>
              ))}
            </ol>
          </section>
          <div>
            <div className="rl-tool-map">
              <Map
                journey={null}
                stops={route?.stops || []}
                vehicles={buses}
                geometry={route?.geometry}
                sourceMode={status?.mode || "simulation"}
              />
              <div className="rl-map-caption">
                {route?.name} · {buses.length} active vehicles ·{" "}
                {status
                  ? sourceLabel(status.active_source || status.mode)
                  : "Connecting…"}
                . {route?.geometry_source || "Stop geometry"}.
              </div>
            </div>
            <section className="rl-panel" style={{ marginTop: 20 }}>
              <h2 className="rl-tool-title">Vehicles on this pattern</h2>
              {buses.length ? (
                buses.map((v) => (
                  <Link
                    href={"/track-bus?vehicle=" + encodeURIComponent(v.id)}
                    className="rl-saved-row"
                    key={v.id}
                  >
                    <span className="rl-saved-icon">
                      <BusFront size={18} />
                    </span>
                    <span>
                      <strong>{v.id}</strong>
                      <small>
                        Next:{" "}
                        {stops.find((s) => s.id === v.next_stop)?.name ||
                          v.next_stop}
                      </small>
                    </span>
                    <ArrowUpRight size={17} />
                  </Link>
                ))
              ) : (
                <p className="rl-meta">
                  No active vehicles on this pattern. This does not establish
                  that the service is cancelled.
                </p>
              )}
            </section>
          </div>
        </div>
      )}
    </main>
  );
}

export function TimeTable() {
  const { routes, status, stops } = useTransit();
  const { t } = useLocale();
  const [stop, setStop] = useState("silk"),
    [filter, setFilter] = useState("");
  const [arrivals, setArrivals] = useState<Arrival[] | null>(null),
    [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const query = new URLSearchParams(window.location.search).get("stop");
    if (query) setStop(query);
  }, []);
  useEffect(() => {
    let active = true;
    setArrivals(null);
    setError("");
    async function load() {
      try {
        const data = await request<Arrival[]>(
          "/api/stops/" + encodeURIComponent(stop) + "/arrivals",
        );
        if (active) {
          setArrivals(data);
          setError("");
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    }
    load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [stop, revision]);
  const visible = arrivals?.filter((a) => !filter || a.route_id === filter);
  return (
    <main>
      <ToolHeading
        title="Time Table"
        description="Upcoming arrivals at your stop, with scheduled and predicted times kept separate."
      />
      <DataNotice />
      <div className="rl-toolbar">
        <StopSelect label="Select a stop" value={stop} onChange={setStop} />
        <label className="rl-field">
          {t("Route")}
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">{t("All routes")}</option>
            {routes.map((r) => (
              <option value={r.id} key={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <button
          className="rl-secondary"
          onClick={() => setRevision((r) => r + 1)}
        >
          <RefreshCw size={15} />
          Refresh
        </button>
      </div>
      <div className="rl-section-heading">
        <h2>{stops.find((s) => s.id === stop)?.name || "Selected stop"}</h2>
        <span className="rl-tag neutral">
          IST · {status?.mode === "simulation" ? "Demo clock" : "Source clock"}
        </span>
      </div>
      {error && (
        <p className="rl-error" role="alert">
          {error}
        </p>
      )}
      {!arrivals && !error && (
        <p className="rl-meta" role="status">
          Loading upcoming arrivals…
        </p>
      )}
      {visible && visible.length > 0 ? (
        <div className="rl-table-wrap">
          <table className="rl-table">
            <caption className="sr-only">
              Upcoming source-clock arrivals at the selected stop
            </caption>
            <thead>
              <tr>
                <th>Service</th>
                <th>Scheduled arrival</th>
                <th>Predicted arrival</th>
                <th>Wait</th>
                <th>Boarding crowding</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((a) => (
                <tr key={a.vehicle_id}>
                  <td>
                    <strong>{a.route_name}</strong>
                    <small>{a.vehicle_id}</small>
                  </td>
                  <td>{clock(a.scheduled_at)}</td>
                  <td>
                    <strong>{clock(a.arrival_at)}</strong>
                    <small>{a.metadata.confidence} confidence</small>
                  </td>
                  <td>{Math.max(0, Math.ceil(a.minutes))} min</td>
                  <td>
                    <span
                      className={
                        "rl-tag " +
                        (a.crowding === "High"
                          ? "amber"
                          : a.crowding === "Unknown"
                            ? "neutral"
                            : "")
                      }
                    >
                      {a.crowding}
                    </span>
                  </td>
                  <td>{sourceLabel(a.metadata.source)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : arrivals && !error ? (
        <div className="rl-empty">
          <CalendarClock size={28} />
          <h2>No upcoming arrivals for this selection</h2>
          <p>
            Choose another stop or route. Schedules depend on the service date
            and operating hours. You can plan a later departure in Journey
            Planner.
          </p>
          <Link href="/planner" className="rl-secondary">
            Open planner
          </Link>
        </div>
      ) : null}
      <p className="rl-meta" style={{ marginTop: 18 }}>
        Times refresh every 5 seconds against the active source clock. This is a
        corridor arrival board, not a complete official BMTC timetable. A
        prediction is not an observed arrival.
      </p>
    </main>
  );
}

export function Facilities() {
  const { stops, loading } = useTransit();
  const [query, setQuery] = useState("");
  const matching = stops.filter((s) =>
    `${s.name} ${s.context}`.toLowerCase().includes(query.toLowerCase()),
  );
  const visible = matching.slice(0, 60);
  return (
    <main>
      <ToolHeading
        title="Facilities"
        description="Find supported stops and nearby context before you travel."
      />
      <div className="rl-note">
        <ShieldCheck size={18} />
        <p>
          Stop locations and route coverage are available. Shelter, toilets,
          seating and step-free access have not been independently surveyed;
          their availability is unverified.
        </p>
      </div>
      <div className="rl-toolbar">
        <label className="rl-field">
          Find a stop
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search a stop or area…"
          />
        </label>
        <span className="rl-tag neutral">
          Showing {visible.length} of {matching.length} matching stops
        </span>
      </div>
      {loading && <p role="status">Loading stop directory…</p>}
      <div className="rl-card-grid">
        {visible.map((s) => (
          <article className="rl-panel rl-stop-card" key={s.id}>
            <span className="rl-service-icon blue">
              <MapPin size={23} />
            </span>
            <h2>{s.name}</h2>
            <p>{s.context}</p>

            <div className="rl-amenities">
              <span className="rl-tag neutral">Shelter: unverified</span>
              <span className="rl-tag neutral">Access: unverified</span>
            </div>
            <Link
              href={"/timetable?stop=" + encodeURIComponent(s.id)}
              className="rl-text-link"
            >
              View arrivals <ArrowRight size={14} />
            </Link>
            <details className="rl-stop-location">
              <summary>Stop location</summary>
              <p>
                {s.lat.toFixed(5)}, {s.lon.toFixed(5)} · approximate corridor
                geography.
              </p>
            </details>
          </article>
        ))}
      </div>
      {!loading && !visible.length && (
        <div className="rl-empty">
          <Search size={26} />
          <h2>No matching supported stops</h2>
          <p>Try Bellandur, Silk Board or Marathahalli.</p>
          <button className="rl-secondary" onClick={() => setQuery("")}>
            Clear search
          </button>
        </div>
      )}
    </main>
  );
}
