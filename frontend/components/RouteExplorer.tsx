"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { ArrowRight, ArrowUpDown, BusFront, Check, Clock3, Compass, GitCompareArrows, MapPin, RefreshCw, Route, Search, X } from "lucide-react";
import { StopInput } from "./JourneyPlanner";
import JourneyIntelligence from "./JourneyIntelligence";
import DeparturePicker, { istIso, istParts } from "./DeparturePicker";
import { useTransit } from "./TransitContext";
import { Journey, Meta, Stop, clock, request, sourceLabel } from "./types";
const Map = dynamic(() => import("./Map"), { ssr: false, loading: () => <div className="map-loading">Preparing your route map…</div> });

type TimedStop = Stop & { order: number; arrival_at: string | null };
type Leg = {
  id: string; trip_id: string; service_date: string; route_id: string; route_name: string; vehicle_id: string;
  origin: Stop; destination: Stop; boarding_at: string; arrival_at: string; wait_minutes: number; total_minutes: number;
  ride_minutes: number; stop_count: number; stops: TimedStop[]; geometry: [number, number][];
  distance_km: number; distance_method: string; measured: boolean; crowding: string; utilization: number | null; metadata: Meta;
};
type Path = {
  id: string; origin: Stop; destination: Stop; legs: Leg[]; transfers: number; transfer_stop: Stop | null;
  distance_km: number; distance_measured: boolean; walking_km: number; total_minutes: number; wait_minutes: number;
  boarding_wait_minutes: number; transfer_wait_minutes: number; ride_minutes: number; boarding_at: string; arrival_at: string;
  stop_count: number; intermediate_stops: number; stops: TimedStop[]; geometry: [number, number][];
  crowding: string; metadata: Meta; badges: string[]; explanation: string;
};
type Results = {
  journeys: Path[]; total: number; search_id: string; generated_at: string; departure_at: string;
  has_more: boolean; next_offset: number;
  coverage: { limited: boolean; templates_searched: number; patterns_in_network: number; max_transfers: number;
    departure_window_minutes: number; journey_limit_minutes: number; transfer_buffer_seconds: number; scope: string; distance_note: string; transfer_policy: string };
};
type Context = { origin: string; destination: string; depart: string; transfers: number; window: number; duration: number };
const orders = [ ["recommended", "Recommended"], ["shortest", "Shortest distance"], ["fastest", "Fastest journey"], ["fewest_transfers", "Fewest transfers"], ["comfortable", "Most comfortable"] ];
const routeNames = (p: Path) => p.legs.map((l) => l.route_name).join(" → ");
const distance = (p: Path) => `${p.distance_measured ? "" : "≈"}${p.distance_km.toFixed(1)} km`;
const dateTime = (s: string) => new Date(s).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" });

export default function RouteExplorer() {
  const { stops, vehicles, status, profile } = useTransit();
  const [origin, setOrigin] = useState<Stop | null>(null), [destination, setDestination] = useState<Stop | null>(null);
  const [depart, setDepart] = useState(""), [transfers, setTransfers] = useState(1), [windowMinutes, setWindowMinutes] = useState(120), [duration, setDuration] = useState(240);
  const [sort, setSort] = useState("recommended"), [results, setResults] = useState<Results | null>(null);
  const [selected, setSelected] = useState<Path | null>(null), [comparison, setComparison] = useState<Path | null>(null);
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false), [moreLoading, setMoreLoading] = useState(false), [monitorLeg, setMonitorLeg] = useState(0);
  const context = useRef<Context | null>(null), currentResults = useRef<Results | null>(null), signature = useRef("");
  const controller = useRef<AbortController | null>(null), sequence = useRef(0), currentSort = useRef(sort);
  const mapPanel = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!stops.length) return;
    const params=new URLSearchParams(window.location.search);
    if (params.get("origin")) setOrigin(stops.find(s=>s.id===params.get("origin"))||null);
    if (params.get("destination")) setDestination(stops.find(s=>s.id===params.get("destination"))||null);
    const departure=params.get("depart_at");
    if (departure && Number.isFinite(Date.parse(departure))) { const parts=istParts(new Date(departure));setDepart(parts.date+"T"+parts.time); }
  }, [stops]);

  const load = useCallback(async (ctx: Context, order: string, append = false, fresh = false) => {
    controller.current?.abort();
    const abort = new AbortController(); controller.current = abort;
    const ticket = ++sequence.current;
    const nextSignature = JSON.stringify(ctx), changed = signature.current !== nextSignature;
    const prior = currentResults.current;
    if (append) setMoreLoading(true); else setLoading(true);
    setError("");
    const params = new URLSearchParams({ origin: ctx.origin, destination: ctx.destination, sort: order,
      allow_demo: "true", max_transfers: String(ctx.transfers), window_minutes: String(ctx.window), duration_minutes: String(ctx.duration),
      limit: "8", offset: append && prior ? String(prior.next_offset) : "0" });
    if (ctx.depart) params.set("depart_at", ctx.depart);
    if (prior && !changed && !fresh) params.set("search_id", prior.search_id);
    try {
      let response: Results;
      try { response = await request<Results>("/api/journeys/explore?" + params, { signal: abort.signal }); }
      catch (e) {
        if (!abort.signal.aborted && params.has("search_id") && (e as Error).message.includes("snapshot")) {
          params.delete("search_id"); params.set("offset", "0"); append = false;
          response = await request<Results>("/api/journeys/explore?" + params, { signal: abort.signal });
        } else throw e;
      }
      if (abort.signal.aborted || ticket !== sequence.current) return;
      const merged = append && prior ? { ...response, journeys: [...new globalThis.Map([...prior.journeys, ...response.journeys].map((j) => [j.id, j])).values()] } : response;
      currentResults.current = merged; signature.current = nextSignature; setResults(merged);
      if (changed) { setSelected(response.journeys[0] || null); setComparison(null); setMonitorLeg(0); setNotice(""); }
      else {
        setSelected((old) => response.journeys.find((j) => j.id === old?.id) || old || response.journeys[0] || null);
        setComparison((old) => response.journeys.find((j) => j.id === old?.id) || (append ? old : null));
        const previousBest = prior?.journeys.find((j) => j.badges.includes("Recommended"));
        const nextBest = response.journeys.find((j) => j.badges.includes("Recommended"));
        if (fresh && previousBest && nextBest && previousBest.id !== nextBest.id && previousBest.total_minutes - nextBest.total_minutes >= 3)
          setNotice(`A faster planning option is available from ${nextBest.origin.name}. Your active watch uses your confirmed progress.`);
      }
    } catch (e) { if (!abort.signal.aborted && ticket === sequence.current) setError((e as Error).message); }
    finally { if (ticket === sequence.current) { setLoading(false); setMoreLoading(false); controller.current = null; } }
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      if (context.current && !context.current.depart && !document.hidden && !controller.current) load(context.current, currentSort.current, false, true);
    }, 30000);
    return () => { clearInterval(timer); controller.current?.abort(); };
  }, [load]);

  function search(event: React.FormEvent) {
    event.preventDefault();
    if (!origin || !destination || origin.id === destination.id) { setError("Choose two different stops from the search suggestions."); return; }
    let planned="";
    try { planned=istIso(depart); } catch { setError("Choose a valid departure date and time in IST.");return; }
    const ctx = { origin: origin.id, destination: destination.id, depart: planned, transfers, window:windowMinutes, duration };
    context.current = ctx; load(ctx, sort, false, true);
  }
  function choose(path: Path) {
    setSelected(path); setMonitorLeg(0);
    if (comparison?.id === path.id) setComparison(null);
    if (matchMedia("(max-width: 800px)").matches) mapPanel.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  const leg = selected?.legs[Math.min(monitorLeg, selected.legs.length - 1)];
  const watched: Journey | null = leg ? {
    id: leg.trip_id, service_date: leg.service_date, route_id: leg.route_id, route_name: leg.route_name, vehicle_id: leg.vehicle_id,
    origin: leg.origin, destination: leg.destination, wait_minutes: leg.wait_minutes, ride_minutes: leg.ride_minutes,
    total_minutes: leg.total_minutes, arrival_at: leg.arrival_at, boarding_at: leg.boarding_at, stop_count: leg.stop_count,
    transfers: 0, crowding: leg.crowding, utilization: leg.utilization, metadata: leg.metadata, geometry: leg.geometry,
    stops: leg.stops, explanation: "Monitor this bus leg from your confirmed stop.", recommended: false,
  } : null;
  const mapLegs = useMemo(() => selected?.legs.map((l, i) => ({ geometry: l.geometry, color: i ? "#246dce" : "#176b5d" })), [selected]);
  const stopDetails = useMemo(() => {
    const details: Record<string, { routes: string; arrival_at: string | null }> = {};
    selected?.legs.forEach((l) => l.stops.forEach((s) => { details[s.id] = { routes: details[s.id] ? details[s.id].routes + ", " + l.route_name : l.route_name, arrival_at: s.arrival_at }; }));
    return details;
  }, [selected]);
  const currentVehicles = useMemo(() => vehicles.filter((v) => selected?.legs.some((l) => l.route_id === v.route_id)), [vehicles, selected]);
  const pastPage = selected && !results?.journeys.some((j) => j.id === selected.id);

  return <main className="rl-explorer">
    <header className="rl-page-heading"><div><span className="rl-explorer-eyebrow"><Compass size={14} /> SMART ROUTE EXPLORER</span><h1>Discover your better way.</h1><p>Compare distance, arrival time and changes. Choose what works for your journey.</p></div><span className="rl-tag neutral">Published BMTC network</span></header>
    <p className="rl-note">Real schedules first. Unsupported pairs show labeled demo connections with illustrative straight-line geometry and synthetic times; these are not BMTC services.</p>
    <form className="rl-panel rl-explorer-form" onSubmit={search}>
      <StopInput label="From" value={origin} onChange={setOrigin} />
      <button type="button" className="rl-swap" aria-label="Swap route explorer stops" onClick={() => { setOrigin(destination); setDestination(origin); }}><ArrowUpDown size={17} /></button>
      <StopInput label="To" value={destination} onChange={setDestination} />
      <button className="rl-primary dark" disabled={!stops.length}><Search size={17} /> {loading ? "Searching…" : "Explore routes"}</button>
      <details className="rl-explorer-options"><summary>Departure & search options</summary><div>
        <DeparturePicker value={depart} onChange={setDepart}/>
        <label className="rl-field">Changes<select value={transfers} onChange={(e) => setTransfers(Number(e.target.value))}><option value={1}>Direct + one same-stop transfer</option><option value={0}>Direct buses only</option></select></label>
        <label className="rl-field">Board within<select value={windowMinutes} onChange={(e) => setWindowMinutes(Number(e.target.value))}><option value={60}>1 hour</option><option value={120}>2 hours</option><option value={240}>4 hours</option></select></label>
        <label className="rl-field">Maximum journey<select value={duration} onChange={(e) => setDuration(Number(e.target.value))}><option value={120}>2 hours</option><option value={240}>4 hours</option><option value={360}>6 hours</option></select></label>
      </div></details>
    </form>
    <p className="rl-explorer-try">Try a published corridor: <button onClick={() => { setOrigin(stops.find((s) => s.id === "silk") || null); setDestination(stops.find((s) => s.id === "marathahalli") || null); }}>Silk Board <ArrowRight size={12} /> Marathahalli</button></p>
    {error && <p className="rl-error" role="alert">{error}</p>}
    {notice && <div className="rl-note" role="status"><p>{notice}</p><button aria-label="Dismiss route update" onClick={() => setNotice("")}><X size={16} /></button></div>}
    {results && <div className="rl-explorer-coverage"><span><Check size={14} /> {results.total} useful paths found · {results.coverage.templates_searched} templates searched</span><span>{results.coverage.limited ? "Bounded search cap reached" : "Within supported search scope"} · updated {clock(results.generated_at)} IST</span><details><summary>Search scope & data</summary><p>{results.coverage.scope} Boarding window {results.coverage.departure_window_minutes} min; journey limit {results.coverage.journey_limit_minutes} min; up to {results.coverage.max_transfers} transfer.</p><p>{results.coverage.transfer_policy}</p><p>{results.coverage.distance_note}</p><p>Live GPS is {status?.mode === "authorized" ? "subject to source availability" : "not connected"}. Crowding remains unknown without evidence. Planning updates use the search origin; onboard watches use confirmed progress.</p></details></div>}
    {!results && !loading ? <div className="rl-explorer-welcome"><span><Route size={30} /></span><h2>One destination. More possibilities.</h2><p>Pick your stops to discover direct buses and feasible same-stop connections. Compare actual route shapes, waiting time and arrival estimates.</p></div> : <div className="rl-explorer-layout">
      <section aria-label="Available journey paths">
        <div className="rl-explorer-sort"><label>Sort paths<select aria-label="Sort route explorer paths" value={sort} onChange={(e) => { const next = e.target.value; setSort(next); currentSort.current = next; if (context.current) load(context.current, next); }}>{orders.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><button className="rl-secondary" disabled={loading} onClick={() => context.current && load(context.current, sort, false, true)} aria-label="Refresh route explorer"><RefreshCw size={16} /></button></div>
        <p className="rl-meta" role="status">{loading ? "Searching feasible trips and connections…" : `${results?.journeys.length || 0} of ${results?.total || 0} paths shown · ${orders.find(([value]) => value === sort)?.[1]}`}</p>
        {loading && !results && [0,1,2].map((i) => <div className="rl-explorer-skeleton" key={i} />)}
        {results?.journeys.map((j) => <article className={"rl-explorer-card" + (selected?.id === j.id ? " is-selected" : "")} key={j.id}>
          <button className="rl-explorer-card-main" onClick={() => choose(j)} aria-pressed={selected?.id === j.id}>
            <div className="rl-explorer-badges">{j.badges.map((b) => <span key={b}>{b}</span>)}</div>
            <h3><BusFront size={17} />{routeNames(j)}</h3>
            <div className="rl-explorer-metrics"><strong>{Math.ceil(j.total_minutes)} <small>min</small></strong><span>{distance(j)}<small>{j.distance_measured ? "along GTFS shapes" : "stop-segment estimate"}</small></span><span>{j.transfers ? "1 transfer" : "Direct bus"}<small>{j.intermediate_stops} intermediate stops</small></span></div>
            <p>{j.origin.name} <ArrowRight size={11} /> {j.destination.name}</p><p className="rl-explorer-explanation">{j.explanation}</p>
            <div className="rl-explorer-card-meta"><span><Clock3 size={12} /> {Math.ceil(j.boarding_wait_minutes)} min boarding wait</span><span>Arrive {clock(j.arrival_at)} IST</span><span>{j.crowding} crowding</span><span>{sourceLabel(j.metadata.source)} · {j.metadata.confidence} confidence</span></div>
          </button>
          <div className="rl-explorer-card-actions"><button onClick={() => choose(j)}><MapPin size={14} /> View on map</button><button disabled={selected?.id === j.id} aria-pressed={comparison?.id === j.id} onClick={() => setComparison(comparison?.id === j.id ? null : j)}><GitCompareArrows size={14} /> {comparison?.id === j.id ? "Remove comparison" : "Compare"}</button></div>
        </article>)}
        {results && !results.total && !loading && <div className="rl-empty"><Search size={26} /><h2>No feasible paths in this search</h2><p>Try another directional stop, a wider departure window or a later time. Missing routes and transfers are never invented.</p></div>}
        {results?.has_more && <button className="rl-secondary rl-explorer-more" disabled={moreLoading || loading} onClick={() => context.current && load(context.current, sort, true)}>{moreLoading ? "Loading paths…" : "Load more paths"}</button>}
      </section>
      <section className="rl-explorer-map-panel" aria-label="Selected planning route" ref={mapPanel}>
        {selected && <>
          <div className="rl-explorer-selected"><div><span>SELECTED PLANNING PATH</span><h2>{routeNames(selected)}</h2></div><strong>{distance(selected)} · {Math.ceil(selected.total_minutes)} min</strong></div>
          {pastPage && <p className="rl-note">Selected path is from an earlier result page or snapshot. Recheck eligibility before boarding. An active watch continues from its confirmed progress.</p>}
          {comparison && <div className="rl-explorer-compare" role="status"><span><GitCompareArrows size={16} /> Comparing with <strong>{routeNames(comparison)}</strong> · {distance(comparison)} · {Math.ceil(comparison.total_minutes)} min · {comparison.transfers} transfer · {comparison.crowding} crowding</span><button aria-label="Remove comparison route" onClick={() => setComparison(null)}><X size={16} /></button></div>}
          <div className="rl-explorer-map"><Map journey={null} stops={selected.stops} vehicles={currentVehicles} geometry={selected.geometry} sourceMode={status?.mode || "schedule"} legGeometries={mapLegs} comparisonGeometry={comparison?.geometry} transferStops={selected.transfer_stop ? [selected.transfer_stop] : []} stopDetails={stopDetails} /></div>
          <p className="rl-explorer-map-key">Solid teal / blue: selected bus legs · Dashed purple: comparison · Amber: change buses</p>
          <div className="rl-panel rl-explorer-detail"><h3>Your journey, stop by stop</h3><p>{dateTime(selected.boarding_at)} → {clock(selected.arrival_at)} IST · {selected.wait_minutes.toFixed(1)} min total waiting{selected.transfers ? `, including ${selected.transfer_wait_minutes.toFixed(1)} min between buses` : ""}</p>
            {selected.legs.map((l, i) => <div className="rl-explorer-leg" key={l.id}><h4><BusFront size={15} /> {i + 1}. Board {l.route_name} at {l.origin.name}</h4><p>{clock(l.boarding_at)} → {clock(l.arrival_at)} IST · {l.distance_km.toFixed(1)} km · {sourceLabel(l.metadata.source)}</p><details><summary>{l.stops.length} stops · show timeline</summary><ol>{l.stops.map((s, order) => <li key={s.id + order}><span>{s.name}</span><small>{s.arrival_at ? clock(s.arrival_at) + " scheduled" : "Time unavailable"}</small></li>)}</ol></details>{i < selected.legs.length - 1 && <div className="rl-explorer-transfer">Change at {l.destination.name}. Allow the stated same-stop buffer; confirm the boarding point.</div>}</div>)}
            <p className="rl-meta">Distance: {selected.distance_measured ? "ordered GTFS shape geometry" : "includes explicitly estimated stop segments"}. Walking distance: {selected.walking_km} km; no pedestrian links inferred. Uncertainty is heuristic, not a guarantee.</p>
          </div>
          {watched && watched.metadata.source !== "demo_journey" && !context.current?.depart && <div className="rl-panel rl-explorer-watch"><h3>Monitor a bus leg</h3><p className="rl-meta">Boarding and progress must be confirmed. A multi-leg path is monitored one bus at a time; confirm the transfer before watching its next leg. Planning-map comparison does not relocate you.</p>{selected.legs.length > 1 && <label className="rl-field">Bus leg<select value={monitorLeg} onChange={(e) => setMonitorLeg(Number(e.target.value))}>{selected.legs.map((l,i) => <option value={i} key={l.id}>{l.route_name} · {l.origin.name} → {l.destination.name}</option>)}</select></label>}<JourneyIntelligence key={leg?.id} journey={watched} preference={sort === "fastest" ? "fastest" : "comfortable"} alertsEnabled={profile?.alerts_enabled ?? true} expanded={false} onUpdate={() => context.current && load(context.current, sort, false, true)} onSelect={(j) => setNotice(`Watch switched to ${j.route_name} from ${j.origin.name}. The map above remains the selected planning path.`)} /></div>}
        </>}
      </section>
    </div>}
  </main>;
}
