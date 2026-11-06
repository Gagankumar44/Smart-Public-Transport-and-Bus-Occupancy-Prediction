"use client";
import { useEffect, useState } from "react";
import { ArrowLeft, BusFront, Clock3, Users } from "lucide-react";
import DataHealth from "../../components/DataHealth";
import PredictionQuality from "../../components/PredictionQuality";
import { request, clock } from "../../components/types";
type Insight = {
  scope: string;
  source: string;
  generated_at: string;
  active_vehicles: number;
  average_delay_minutes: number | null;
  routes: {
    route_id: string;
    name: string;
    vehicles: number;
    utilization: number;
    delay_minutes: number;
  }[];
  reports: {
    count: number;
    reports: {
      id: string;
      level: string;
      vehicle_id: string;
      created_at: string;
    }[];
  };
  warnings: { route_id: string; label: string; gap_minutes: number }[];
  quality: string;
};
export default function Insights() {
  const [data, setData] = useState<Insight | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const result = await request<Insight>("/api/insights/summary");
        if (active) {
          setData(result);
          setError("");
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    }
    load();
    const timer = setInterval(load, 10000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);
  return (
    <main className="insights-page">
      <a href="/planner" className="back-link">
        <ArrowLeft size={16} /> Back to journey planner
      </a>
      <header>
        <span className="eyebrow">Corridor insights</span>
        <h1>
          A clearer view
          <br />
          of the corridor.
        </h1>
        <p>
          {data?.source && data.source !== "simulation"
            ? "Matched GTFS corridor · see Data Health for provenance"
            : "Published BMTC network · Scheduled estimates"}
        </p>
      </header>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {!data && !error && <p role="status">Loading corridor insights…</p>}
      {data && (
        <>
          <div className="insight-kpis">
            <article>
              <BusFront />
              <strong>{data.active_vehicles}</strong>
              <span>
                {data.source === "simulation"
                  ? "Active simulated vehicles"
                  : "Observed / scheduled trips"}
              </span>
            </article>
            <article>
              <Clock3 />
              <strong>
                {data.average_delay_minutes === null
                  ? "—"
                  : `${data.average_delay_minutes} min`}
              </strong>
              <span>
                {data.source === "simulation"
                  ? "Average simulated delay"
                  : "Average delay (when available)"}
              </span>
            </article>
            <article>
              <Users />
              <strong>{data.reports.count}</strong>
              <span>Verified passenger observations</span>
            </article>
          </div>
          <div className="insight-grid">
            <section>
              <h2>Estimated onboard occupancy</h2>
              <p>
                {data.source === "simulation"
                  ? "Current simulated loads, separate from boarding-stop forecasts."
                  : "No inferred passenger counts are used for provider vehicles."}
              </p>
              {data.routes.map((r) => (
                <div className="chart-row" key={r.route_id}>
                  <span>{r.name}</span>
                  <meter
                    min={0}
                    max={1}
                    value={r.utilization}
                    aria-label={r.name + " utilization"}
                  />
                  <b>{Math.round(r.utilization * 100)}%</b>
                </div>
              ))}
            </section>
            <section>
              <h2>Route delay</h2>
              <p>Measured delay appears when fresh authorized observations are available.</p>
              {data.routes.map((r) => (
                <div className="chart-row" key={r.route_id}>
                  <span>{r.name}</span>
                  <meter
                    min={0}
                    max={Math.max(
                      10,
                      ...data.routes.map((r) => r.delay_minutes),
                    )}
                    value={Math.max(0, r.delay_minutes)}
                    aria-label={r.name + " delay"}
                  />
                  <b>{r.delay_minutes}m</b>
                </div>
              ))}
            </section>
            <section>
              <h2>Headway warnings</h2>
              {data.warnings.length ? (
                data.warnings.map((w, i) => (
                  <p key={i}>
                    {w.route_id} · {w.label} · {w.gap_minutes} min apart
                  </p>
                ))
              ) : (
                <p>No verified live headway information available.</p>
              )}
              <p>{data.quality}</p>
            </section>
            <section>
              <h2>Passenger observations</h2>
              {data.reports.reports.length ? (
                data.reports.reports.slice(0, 5).map((r) => (
                  <p key={r.id}>
                    {r.vehicle_id} · {r.level} · {clock(r.created_at)} IST
                  </p>
                ))
              ) : (
                <p>No verified passenger observations available. Record an actual pilot observation from the User Guide.</p>
              )}
            </section>
          </div>
          <DataHealth />
          <PredictionQuality />
          <p className="insights-source">
            Updated {clock(data.generated_at)} IST · {data.source} · Refreshes
            every 10 seconds. No citywide or real-world accuracy claims.
          </p>
        </>
      )}
    </main>
  );
}
