"use client";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import DemoTracking from "./DemoTracking";
import { ArrowRight, BusFront, Clock3, MapPin, Radio, RefreshCw } from "lucide-react";
import { Meta, Stop, Vehicle, clock, request, sourceLabel } from "./types";

const Map = dynamic(() => import("./Map"), { ssr: false });
export type RouteDetail = { id: string; name: string; stops: Stop[]; geometry: [number, number][]; geometry_source?: string };
type Monitor = {
  route_name: string; generated_at: string; mode: string; live_connected: boolean;
  positioned_buses: number; moving_buses: number | null; movement_unknown: number | null;
  vehicles: Vehicle[]; note: string; stop: Stop;
  arrivals: { trip_id: string; vehicle_id: string; route_name: string; minutes: number; arrival_at: string; scheduled_at: string; crowding: string; metadata: Meta }[];
};
const dated = (value: string) => new Date(value).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" });

export default function RouteMonitor({ id, name, route, loading, routeError }: { id: string; name: string; route: RouteDetail | null; loading: boolean; routeError: string }) {
  const [demo,setDemo]=useState(false);
  const [index, setIndex] = useState(0);
  const [state, setState] = useState<Monitor | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true, pending = false;
    setState(null); setError("");
    async function load() {
      if (pending) return;
      pending = true;
      try {
        const next = await request<Monitor>("/api/routes/" + encodeURIComponent(id) + "/monitor?stop_index=" + index);
        if (active) { setState(next); setError(""); }
      } catch (e) { if (active) setError((e as Error).message); }
      finally { pending = false; }
    }
    load();
    const timer = setInterval(() => { if (!document.hidden) load(); }, 10000);
    return () => { active = false; clearInterval(timer); };
  }, [id, index, revision]);
  const next = state?.arrivals[0];
  const at = route?.stops[index];
  return <div className="rl-route-monitor" aria-label="Selected route monitor">
    <section className="rl-panel rl-monitor-summary" aria-live="polite">
      <div className="rl-panel-heading">
        <div className="rl-selected-service"><span><BusFront size={22} /></span><div><small>SELECTED SERVICE</small><h2>{name}</h2></div></div>
        <span className={"rl-tag " + (state?.live_connected ? "" : "neutral")}><Radio size={12} />{state?.live_connected ? "Fresh GPS" : state?.mode === "replay" ? "Historical replay" : "Live GPS unavailable"}</span>
      </div>
      {loading ? <p role="status">Opening {name} route and stop details…</p> : route && <p className="rl-monitor-direction">{route.stops[0]?.name}<ArrowRight size={16} />{route.stops[route.stops.length - 1]?.name}</p>}
      {routeError && <p className="rl-error" role="alert">{routeError}</p>}
      <div className="rl-monitor-stats">
        <div><small><BusFront size={13} /> Confirmed moving buses</small><strong>{state?.moving_buses ?? "Unavailable"}</strong><span>{state?.movement_unknown ? `${state.movement_unknown} with unknown movement` : "Requires fresh provider speed / status"}</span></div>
        <div><small><Radio size={13} /> Fresh GPS positions</small><strong>{state ? state.positioned_buses : "…"}</strong><span>On this directional pattern</span></div>
        <div><small><Clock3 size={13} /> Next {next?.metadata.source === "schedule" ? "scheduled" : "estimated"} arrival</small><strong>{next ? clock(next.arrival_at) : state ? "Unavailable" : "Loading…"}</strong><span>{next ? dated(next.arrival_at) + " · IST" : "Choose a stop below"}</span></div>
      </div>
      <p className="rl-meta">{state?.note || "Checking the route source and upcoming arrivals…"}</p>
      {!!state?.vehicles.length && <div className="rl-monitor-fleet">{state.vehicles.map((v) => <div key={v.id}><strong><BusFront size={15} /> {v.id}</strong><span>{v.movement || "Movement unknown"} · {v.speed_kmh != null ? `${v.speed_kmh} km/h` : "Speed unavailable"}</span><small>{sourceLabel(v.metadata.source)} · seen {clock(v.metadata.observed_at)} IST · {v.lat?.toFixed(5)}, {v.lon?.toFixed(5)}</small></div>)}</div>}
    </section>
    <section className="rl-panel rl-stop-arrivals" aria-label="Arrivals at selected stop">
      <div className="rl-monitor-stop-picker">
        <label className="rl-field"><MapPin size={15} /> Arrival stop
          <select aria-label="Arrival stop" value={index} disabled={!route} onChange={(e) => setIndex(Number(e.target.value))}>
            {route ? route.stops.map((s, i) => <option key={s.id + i} value={i}>{i + 1}. {s.name}</option>) : <option value={0}>Loading stops…</option>}
          </select>
        </label>
        <button className="rl-secondary" onClick={() => setRevision((r) => r + 1)}><RefreshCw size={15} /> Refresh arrivals</button>
      </div>
      {error && <p className="rl-error" role="alert">{error} Previous results may be out of date.</p>}
      {!state && !error && <p role="status">Updating arrivals for this stop…</p>}
      {state && <>
        <p className="rl-meta">{state.stop.name} · checked {clock(state.generated_at)} IST · refreshes every 10 seconds</p>
        {state.arrivals.length ? <div className="rl-table-wrap"><table className="rl-table">
          <caption className="sr-only">Bus arrivals at {state.stop.name}, with source and timetable separated</caption>
          <thead><tr><th>Trip / bus</th><th>Arrival at this stop · IST</th><th>Wait</th><th>Source</th></tr></thead>
          <tbody>{state.arrivals.map((a) => <tr key={a.vehicle_id + a.arrival_at}><td><strong>{a.route_name}</strong><small>{a.metadata.source === "schedule" ? `Trip ${a.trip_id}` : a.vehicle_id}</small></td><td><strong>{dated(a.arrival_at)}</strong>{a.metadata.source !== "schedule" && <small>Scheduled {clock(a.scheduled_at)}</small>}</td><td>{Math.ceil(a.minutes)} min</td><td><span className="rl-tag neutral">{sourceLabel(a.metadata.source)}</span><small>Crowding {a.crowding.toLowerCase()}</small></td></tr>)}</tbody>
        </table></div> : <p>No usable arrival estimate for this stop in the current search window. This does not confirm cancellation.</p>}
      </>}
      {route && at && index < route.stops.length - 1 && <Link className="rl-text-link" href={"/planner?origin=" + encodeURIComponent(at.id) + "&destination=" + encodeURIComponent(route.stops[route.stops.length - 1].id)}>Plan from this stop · watch delays and alternatives <ArrowRight size={14} /></Link>}
    </section>
    {state && !state.arrivals.length && <div className="rl-panel"><p>No real departures available at this stop. Try another stop or explore a clearly labeled corridor simulation.</p><button className="rl-primary" onClick={()=>setDemo(true)}>Preview moving demo bus</button></div>}
    {demo && <DemoTracking onClose={()=>setDemo(false)}/>}
    <div className="rl-tool-map rl-monitor-map">
      <Map journey={null} stops={route?.stops || []} vehicles={state?.vehicles || []} geometry={route?.geometry} sourceMode={state?.mode || "schedule"} selectedStopIndex={index} onStopSelect={(_, i) => setIndex(i)} />
      <div className="rl-map-caption">{name} · {route?.geometry_source || "Published route"}. Small dots are bus stops; A/B mark endpoints. Select a dot to see its arrivals. Bus icons require fresh source GPS.</div>
    </div>
    {route && <details className="rl-panel rl-monitor-stop-list"><summary>View all {route.stops.length} stops</summary><ol>{route.stops.map((s, i) => <li key={s.id + i}><button aria-pressed={index === i} onClick={() => setIndex(i)}><span>{i + 1}</span>{s.name}<small>{index === i ? "Selected" : "Show arrivals"}</small></button></li>)}</ol></details>}
  </div>;
}
