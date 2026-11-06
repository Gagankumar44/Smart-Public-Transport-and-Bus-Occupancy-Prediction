"use client";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, RefreshCw } from "lucide-react";
import { Journey, Meta, request, clock, sourceLabel } from "./types";
type Point = {
  stop_id: string;
  stop_name: string;
  arrival_at: string;
  minutes: number;
  crowding: string;
  utilization: number | null;
  metadata: Meta;
  uncertainty: {
    occupancy_uncertainty: string;
    lower_minutes: number;
    upper_minutes: number;
  };
};
export default function CrowdForecast({
  journey,
  controls,
  onUpdate,
}: {
  journey: Journey;
  controls: boolean;
  onUpdate: () => void;
}) {
  const [points, setPoints] = useState<Point[]>([]),
    [error, setError] = useState(""),
    [all, setAll] = useState(false),
    [busy, setBusy] = useState(false);
  const sequence = useRef(0);
  useEffect(() => {
    let active = true;
    const load = async () => {
      const version = ++sequence.current;
      try {
        const result = await request<Point[]>(
          "/api/vehicles/" + journey.vehicle_id + "/forecast",
        );
        if (active && version === sequence.current) {
          setPoints(result);
          setError("");
        }
      } catch (e) {
        if (active && version === sequence.current) {
          setError((e as Error).message);
          setPoints([]);
        }
      }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [journey.vehicle_id, journey.metadata.generation]);
  async function observe() {
    setBusy(true);
    try {
      await request("/api/demo/observation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          vehicle_id: journey.vehicle_id,
          advance_seconds: 60,
        }),
      });
      onUpdate();
      const result = await request<Point[]>(
        "/api/vehicles/" + journey.vehicle_id + "/forecast",
      );
      sequence.current++;
      setPoints(result);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const start = points.findIndex((p) => p.stop_id === journey.origin.id),
    end = points.findIndex((p) => p.stop_id === journey.destination.id);
  const relevant = points.slice(
    Math.max(0, start),
    end < 0 ? undefined : end + 1,
  );
  return (
    <section className="crowd-forecast" aria-label="Future stop crowd forecast">
      <header>
        <div>
          <span className="eyebrow">A LOOK AHEAD</span>
          <h3>Crowding along your journey</h3>
          <p>
            {journey.id.startsWith("demo-") ? (
              <>
                After modeled boarding at each stop ·{" "}
                {journey.metadata.demand_profile || "morning"} demand profile ·{" "}
                {sourceLabel(journey.metadata.source)}
              </>
            ) : (
              <>
                Forward crowding is unknown without a validated stop-level model
                · {sourceLabel(journey.metadata.source)}
              </>
            )}
          </p>
        </div>
        {controls && (
          <button disabled={busy} onClick={observe}>
            <RefreshCw size={14} />
            {busy ? "Updating…" : "Fresh demo observation"}
          </button>
        )}
      </header>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!points.length && !error && (
        <p role="status">No upcoming forecasts available for this departure.</p>
      )}
      <ol className="forecast-sequence">
        {(all ? relevant : relevant.slice(0, 6)).map((p, i) => (
          <li key={p.stop_id}>
            <div>
              <span className={"crowd " + p.crowding.toLowerCase()}>
                {p.crowding}
              </span>
              <strong>{p.stop_name}</strong>
              <small>
                {clock(p.arrival_at)} IST ·{" "}
                {p.uncertainty.occupancy_uncertainty.toLowerCase()} uncertainty
              </small>
            </div>
            {i < relevant.length - 1 && <ArrowRight size={14} />}
          </li>
        ))}
      </ol>
      {relevant.length > 6 && (
        <button className="forecast-more" onClick={() => setAll(!all)}>
          {all ? "Show fewer stops" : `Show all ${relevant.length} stops`}
        </button>
      )}
      <details>
        <summary>How to read these forecasts</summary>
        <p>
          {journey.id.startsWith("demo-")
            ? "One passenger-flow model projects alighting and boarding, caps the vehicle load, and blends fresh reports about this demo trip."
            : "Provider GPS does not determine passenger counts. Current occupancy status remains separate from future-stop forecasts."}
          Scenario uncertainty grows over more stops and when observations age
          or reports conflict. These are heuristic bounds, not validated
          accuracy.
        </p>
        <p>
          ETA method: {journey.metadata.method.replaceAll("_", " ")}.{" "}
          {journey.metadata.uncertainty?.label}
        </p>
      </details>
    </section>
  );
}
