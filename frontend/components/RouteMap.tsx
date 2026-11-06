"use client";
import { MapContainer, TileLayer, Polyline, CircleMarker, Marker, Popup, Tooltip, useMap } from "react-leaflet";
import { divIcon, type Marker as LeafletMarker, type DivIcon } from "leaflet";
import { useEffect, useMemo, useRef, useState } from "react";
import { Maximize2 } from "lucide-react";
import "leaflet/dist/leaflet.css";
import { Journey, Stop, Vehicle, clock, sourceLabel } from "./types";

const endpoint = (label: string) => divIcon({ className: "rl-endpoint-marker", html: `<span>${label}</span>`, iconSize: [28, 28], iconAnchor: [14, 14] });
const originIcon = endpoint("A"), destinationIcon = endpoint("B");
const busIcon = divIcon({ className: "rl-vehicle-marker", html: '<span><svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="5" y="3" width="14" height="17" rx="3"/><path d="M5 11h14M8 3v8M16 3v8M8 20v2M16 20v2"/><circle cx="8.5" cy="16" r="1"/><circle cx="15.5" cy="16" r="1"/></svg></span>', iconSize: [40, 40], iconAnchor: [20, 20] });
const demoBusIcon=divIcon({...busIcon.options,className:"rl-vehicle-marker is-demo"});
function PositionedBus({v,icon,children}:{v:Vehicle;icon:DivIcon;children:React.ReactNode}) {
  const marker=useRef<LeafletMarker|null>(null),initial=useRef<[number,number]>([v.lat!,v.lon!]);
  const previous=useRef({stamp:v.metadata.observed_at,generation:v.metadata.generation});
  useEffect(()=>{
    if (!marker.current) return;
    const target:[number,number]=[v.lat!,v.lon!],old=previous.current;
    previous.current={stamp:v.metadata.observed_at,generation:v.metadata.generation};
    if (v.metadata.source!=="simulation"||v.paused||old.generation!==v.metadata.generation||matchMedia("(prefers-reduced-motion: reduce)").matches) { marker.current.setLatLng(target);return; }
    const start=marker.current.getLatLng(),duration=Math.min(1000,Math.max(100,Date.parse(v.metadata.observed_at)-Date.parse(old.stamp)));
    const began=performance.now();let frame=0;
    const move=(now:number)=>{const fraction=Math.min(1,(now-began)/duration);marker.current?.setLatLng([start.lat+(target[0]-start.lat)*fraction,start.lng+(target[1]-start.lng)*fraction]);if(fraction<1)frame=requestAnimationFrame(move);};
    frame=requestAnimationFrame(move);return()=>cancelAnimationFrame(frame);
  },[v.lat,v.lon,v.metadata.observed_at,v.metadata.generation,v.metadata.source,v.paused]);
  return <Marker ref={marker} position={initial.current} icon={icon} title={v.route_name+" bus "+v.id} zIndexOffset={1000}>{children}</Marker>;
}

function MapTools({ points }: { points: [number, number][] }) {
  const map = useMap();
  const fitted = useRef("");
  const key = points.map((p) => p.join(",")).join(";");
  useEffect(() => {
    if (!points.length || fitted.current === key) return;
    fitted.current = key;
    map.fitBounds(points, { padding: [38, 38], maxZoom: 14 });
  }, [map, points, key]);
  return <div className="rl-map-tools"><button type="button" aria-label="Fit entire route" onClick={(e) => { e.stopPropagation(); if (points.length) map.fitBounds(points, { padding: [38, 38], maxZoom: 14 }); }}><Maximize2 size={15} /> Fit route</button></div>;
}

export default function TransitMap({ journey, stops, vehicles, sourceMode, geometry, selectedStopIndex, onStopSelect, comparisonGeometry, legGeometries, transferStops = [], stopDetails }: {
  journey: Journey | null; stops: Stop[]; vehicles: Vehicle[]; sourceMode: string; geometry?: [number, number][];
  selectedStopIndex?: number; onStopSelect?: (stop: Stop, index: number) => void;
  comparisonGeometry?: [number, number][];
  legGeometries?: { geometry: [number, number][]; color: string }[];
  transferStops?: Stop[];
  stopDetails?: Record<string, { routes: string; arrival_at: string | null }>;
}) {
  const [failed, setFailed] = useState(false);
  const points = useMemo(() => journey?.geometry || (geometry?.length ? geometry : stops.map((s) => [s.lat, s.lon] as [number, number])), [journey?.geometry, geometry, stops]);
  const routeStops = journey?.stops || stops;
  const bounds = useMemo(() => comparisonGeometry?.length ? [...points, ...comparisonGeometry] : points, [points, comparisonGeometry]);
  const positioned = vehicles.filter((v) => {
    const reference = v.metadata.source === "real_observed" ? Date.now() : Date.parse(v.metadata.generated_at);
    const age = (reference - Date.parse(v.metadata.observed_at)) / 1000;
    return !v.completed && v.lat !== null && v.lon !== null && Number.isFinite(v.lat) && Number.isFinite(v.lon) && v.metadata.source !== "schedule" && age >= -30 && age <= 120 && (!journey || journey.route_id === v.route_id);
  });
  return <>
    <MapContainer center={[12.944, 77.68]} zoom={12} scrollWheelZoom={false} className="map-canvas">
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' eventHandlers={{ tileerror: () => setFailed(true) }} />
      <MapTools points={bounds} />
      {!!comparisonGeometry?.length && <Polyline positions={comparisonGeometry} pathOptions={{ color: "#8c6bb1", weight: 5, opacity: .8, dashArray: "8 6" }} />}
      {points.length > 1 && (journey || geometry?.length || sourceMode === "simulation") && <>
        <Polyline positions={points} pathOptions={{ color: "#fff", weight: 8, opacity: .95 }} />
        {legGeometries?.length ? legGeometries.map((l,i) => <Polyline key={i} positions={l.geometry} pathOptions={{ color: l.color, weight: 5, opacity: .95 }} />) : <Polyline positions={points} pathOptions={{ color: "#246dce", weight: 4, opacity: .95, lineCap: "round", lineJoin: "round" }} />}
      </>}
      {routeStops.map((s, i) => {
        const first = i === 0, last = i === routeStops.length - 1, selected = i === selectedStopIndex;
        const detail = stopDetails?.[s.id];
        const content = <><strong>{s.name}</strong><br />Stop {i + 1} of {routeStops.length}{selected && <><br />Selected arrival stop</>}<br />{sourceMode === "simulation" ? "Demonstration stop" : "Published bus stop"}{detail && <><br />Routes on this journey: {detail.routes}<br />{detail.arrival_at ? `Scheduled passing: ${clock(detail.arrival_at)} IST` : "Passing estimate unavailable"}</>}{onStopSelect && <><br /><button onClick={() => onStopSelect(s, i)}>Show arrivals at this stop</button></>}</>;
        return first || last ? <Marker key={s.id + ":" + i} position={[s.lat, s.lon]} icon={first ? originIcon : destinationIcon} title={(first ? "Origin: " : "Destination: ") + s.name} eventHandlers={{ click: () => onStopSelect?.(s, i) }}>
          <Tooltip direction="top">{first ? "A · " : "B · "}{s.name}</Tooltip><Popup>{content}</Popup>
        </Marker> : <CircleMarker key={s.id + ":" + i} center={[s.lat, s.lon]} radius={selected ? 7 : 3} pathOptions={{ color: selected ? "#102e52" : "#246dce", fillColor: selected ? "#246dce" : "#fff", fillOpacity: 1, weight: selected ? 3 : 1.5 }} eventHandlers={{ click: () => onStopSelect?.(s, i) }}>
          <Tooltip direction="top">{i + 1} · {s.name}</Tooltip><Popup>{content}</Popup>
        </CircleMarker>;
      })}
      {transferStops.map((s) => <CircleMarker key={'transfer:'+s.id} center={[s.lat,s.lon]} radius={9} pathOptions={{ color: '#805600', fillColor:'#f1bd54', fillOpacity:1, weight:3 }}><Tooltip>Change buses · {s.name}</Tooltip><Popup><strong>Transfer at {s.name}</strong><br />Same-stop connection. Check the next boarding time.</Popup></CircleMarker>)}
      {positioned.map((v) => <PositionedBus key={v.id} v={v} icon={v.metadata.source==="simulation"?demoBusIcon:busIcon}>
        <Tooltip direction="top">{v.route_name} · {v.movement === "moving" ? "Moving" : v.movement === "stopped" ? "Stopped" : sourceLabel(v.metadata.source)}</Tooltip>
        <Popup><strong>{v.route_name} · {v.id}</strong><br />Next: {stops.find((s) => s.id === v.next_stop)?.name || v.next_stop}<br />{v.speed_kmh != null ? `${v.speed_kmh} km/h · provider reported` : "Speed unavailable"}<br />{sourceLabel(v.metadata.source)} · observed {clock(v.metadata.observed_at)}<br />{v.passengers !== null && v.capacity !== null ? `Reported count: ${v.passengers}/${v.capacity}` : "Passenger counts unavailable"}</Popup>
      </PositionedBus>)}
    </MapContainer>
    <div className="rl-map-legend" aria-label="Map legend"><span><i /> Bus stop</span><span><b>A</b> Start</span><span><b>B</b> End</span><span>▣ {positioned.length} GPS / source buses</span></div>
    {failed && <div className="map-warning">Map tiles unavailable. Route lines and stop details remain available.</div>}
  </>;
}
