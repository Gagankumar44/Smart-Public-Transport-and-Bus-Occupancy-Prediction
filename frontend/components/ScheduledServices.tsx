"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, BusFront, Search } from "lucide-react";
import { RoutePattern, useTransit } from "./TransitContext";
import { Stop, request, clock } from "./types";
import RouteMonitor from "./RouteMonitor";
type Detail = { id: string; name: string; stops: Stop[]; geometry: [number, number][]; geometry_source?: string };
type Departures = {
  departures: { trip_id: string; service_date: string; departure_at: string; arrival_at: string; source: string }[];
  generated_at: string;
  note: string;
};
const datedTime = (value: string) => new Date(value).toLocaleString("en-IN", {
  day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata",
});

export default function ScheduledServices() {
  const { stops } = useTransit();
  const names = useMemo(() => new globalThis.Map(stops.map((s) => [s.id, s.name])), [stops]);
  const [query, setQuery] = useState("");
  const [patterns, setPatterns] = useState<RoutePattern[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [catalogError, setCatalogError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [route, setRoute] = useState<Detail | null>(null);
  const [times, setTimes] = useState<Departures | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const detailRef = useRef<HTMLDivElement>(null);
  const routeId = patterns.some((r) => r.id === selected) ? selected : patterns[0]?.id || "";

  useEffect(() => {
    let active = true;
    setLoading(true);
    setCatalogError("");
    const timer = setTimeout(() => {
      request<RoutePattern[]>("/api/routes?limit=50&q=" + encodeURIComponent(query.trim()))
        .then((items) => { if (active) setPatterns(items); })
        .catch((e) => { if (active) { setPatterns([]); setCatalogError((e as Error).message); } })
        .finally(() => { if (active) setLoading(false); });
    }, 200);
    return () => { active = false; clearTimeout(timer); };
  }, [query, revision]);

  useEffect(() => {
    let active = true;
    setRoute(null);
    setTimes(null);
    setDetailError("");
    if (!routeId) { setDetailLoading(false); return; }
    setDetailLoading(true);
    async function load() {
      const [detail, departures] = await Promise.allSettled([
        request<Detail>("/api/routes/" + encodeURIComponent(routeId)),
        request<Departures>("/api/routes/" + encodeURIComponent(routeId) + "/departures"),
      ]);
      if (!active) return;
      if (detail.status === "fulfilled") setRoute(detail.value);
      if (departures.status === "fulfilled") setTimes(departures.value);
      setDetailError(detail.status === "rejected" || departures.status === "rejected" ? "Some service details could not load. Refresh to try again." : "");
      setDetailLoading(false);
    }
    load();
    const timer = setInterval(() => { if (!document.hidden) load(); }, 60000);
    return () => { active = false; clearInterval(timer); };
  }, [routeId, revision]);

  return (
    <div className="rl-two-columns">
      <section className="rl-panel">
        <label className="rl-field">
          Search published bus routes
          <div className="rl-search-input">
            <Search size={17} />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Try 500-F, 500D, or a route name…" aria-label="Search scheduled routes" />
          </div>
        </label>
        <p className="rl-meta" role="status" style={{ margin: "12px 0" }}>
          {loading ? "Searching the published network…" : `Showing ${patterns.length} matching route patterns. Search to narrow the full imported network.`}
        </p>
        {catalogError && <p className="rl-error" role="alert">{catalogError} <button onClick={() => setRevision((r) => r + 1)}>Retry</button></p>}
        <div className="rl-vehicle-list">
          {patterns.map((r) => (
            <button key={r.id} className={"rl-vehicle-row" + (routeId === r.id ? " is-selected" : "")} onClick={() => { setSelected(r.id); detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }} aria-pressed={routeId === r.id}>
              <strong><BusFront size={17} /> {r.name}</strong>
              <p>{names.get(r.stops[0]) || r.stops[0]} <ArrowRight size={12} /> {names.get(r.stops[r.stops.length - 1]) || r.stops[r.stops.length - 1]}</p>
              <small>{r.stops.length} stops · directional pattern</small>
              <span className="rl-tag neutral">Published route · stop arrivals</span>
              <span className="rl-route-open">{routeId === r.id ? "Selected · arrivals open" : "Open route & stop arrivals"} <ArrowRight size={14} /></span>
            </button>
          ))}
        </div>
        {!loading && !patterns.length && !catalogError && <div className="rl-empty">
          <Search size={25} /><h2>No matching published routes</h2><p>Try a route number such as 500 or clear your search.</p>
          <button className="rl-secondary" onClick={() => setQuery("")}>Clear search</button>
        </div>}
      </section>
      <div ref={detailRef} className="rl-bus-focus">
        {routeId ? <RouteMonitor key={routeId} id={routeId} name={patterns.find((p) => p.id === routeId)?.name || "Selected service"} route={route?.id === routeId ? route : null} loading={detailLoading} routeError={detailError} /> : <p>Select a service to open its route monitor.</p>}
        {times && route?.id === routeId && <details className="rl-panel" style={{ marginTop: 18 }} aria-label="Published service details">
            <summary>Published departures from route origin</summary>
            <p className="rl-meta">IST · Next seven days · Refreshed {clock(times.generated_at)}</p>
            {times.departures.length ? <div className="rl-table-wrap"><table className="rl-table">
              <caption className="sr-only">Published origin departures and destination arrivals in Indian Standard Time</caption>
              <thead><tr><th>Origin departure · IST</th><th>Destination arrival · IST</th><th>Source</th></tr></thead>
              <tbody>{times.departures.map((d) => <tr key={d.trip_id + d.service_date}>
                <td><strong>{datedTime(d.departure_at)}</strong><small>Trip {d.trip_id}</small></td>
                <td>{datedTime(d.arrival_at)}</td><td>Published schedule</td>
              </tr>)}</tbody>
            </table></div> : <p className="rl-meta">No origin departures found for this pattern in the next seven days. The route is still part of the published network.</p>}
            <p className="rl-meta" style={{ marginTop: 12 }}>{times.note} The unofficial dataset may contain timetable errors.</p>
        </details>}
      </div>
    </div>
  );
}
