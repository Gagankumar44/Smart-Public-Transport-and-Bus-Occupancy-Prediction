"use client";

import { useEffect, useState } from "react";

import { request, clock } from "./types";

type Health = {

  serving_scope: { routes: number; stops: number };

  mode: string;

  live_connected: boolean;

  message: string;

  verified_labels: number;

  sources: {

    id: string;

    mode: string;

    synthetic: boolean;

    status: string;

    latest_observation_at: string | null;

    observation_age_seconds: number | null;

    counts: Record<string, number>;

  }[];

  calibration: { available: boolean; message: string };

  note: string;

};

export default function DataHealth() {

  const [network, setNetwork] = useState<{routes:number;stops:number;trips:number;validation:string;source?:string;imported_at?:string;feed_info?:{feed_version:string}[];rejected_trips?:number;quarantined_shapes?:number} | null>(null);

  useEffect(() => { request<typeof network>("/api/network/status").then(setNetwork).catch(() => {}); }, []);

  const [health, setHealth] = useState<Health | null>(null),

    [error, setError] = useState("");

  useEffect(() => {

    let active = true;

    let version = 0;

    async function load() {

      const seq = ++version;

      try {

        const result = await request<Health>("/api/data-health");

        if (active && seq === version) {

          setHealth(result);

          setError("");

        }

      } catch (e) {

        if (active && seq === version) setError((e as Error).message);

      }

    }

    load();

    const timer = setInterval(load, 15000);

    return () => {

      active = false;

      clearInterval(timer);

    };

  }, []);

  return (

    <section className="data-health">

      <h2>Real BMTC Data Status</h2>

      {network && <div><p>{network.source || "No full network imported"} · version {network.feed_info?.[0]?.feed_version || "unavailable"}</p><div className="health-summary"><span>Imported routes<strong>{network.routes}</strong></span><span>Imported stops<strong>{network.stops}</strong></span><span>Imported trips<strong>{network.trips}</strong></span></div><p>Validation: {network.validation}. Imported: {network.imported_at || "unavailable"}. Quarantined trips: {network.rejected_trips ?? 0}; shapes: {network.quarantined_shapes ?? 0}.</p><p>Vonter / BMTC, ODbL-1.0. Unofficial schedules may be incorrect; static coordinates do not establish live tracking.</p></div>}

      <span className="eyebrow">DATA HEALTH</span>

      <h2>Know what powers your prediction.</h2>

      {error ? (

        <p role="alert">{error}</p>

      ) : health ? (

        <>

          <p

            className={

              health.live_connected ? "connected-status" : "disconnected-status"

            }

          >

            {health.message}

          </p>

          <div className="health-summary">

            <span>

              Serving mode <strong>{health.mode}</strong>

            </span>

            <span>

              Verified pilot labels <strong>{health.verified_labels}</strong>

            </span>

            <span>

              Calibration{" "}

              <strong>

                {health.calibration.available

                  ? "Eligible scope active"

                  : "Unavailable"}

              </strong>

            </span>

          </div>

          {health.serving_scope && (

            <p>

              Serving scope: {health.serving_scope.routes} route patterns ·{" "}

              {health.serving_scope.stops} supported stops.

            </p>

          )}

          {health.sources.filter(s=>!s.synthetic).length ? (

            <ul>

              {health.sources.filter(s=>!s.synthetic).map((s) => (

                <li key={s.id}>

                  <strong>

                    {s.id} · {s.synthetic ? "Synthetic fixture" : s.mode}

                  </strong>

                  <p>

                    {s.status} ·{" "}

                    {s.latest_observation_at

                      ? `Last observed ${clock(s.latest_observation_at)} IST (${Math.round(s.observation_age_seconds || 0)} seconds old)`

                      : "No accepted observations"}

                  </p>

                  <p>

                    {Object.entries(s.counts)

                      .map(([key, n]) => `${n} ${key}`)

                      .join(" · ")}

                  </p>

                </li>

              ))}

            </ul>

          ) : (

            <p>

              No external provider or replay source has been ingested.

              Simulation remains available.

            </p>

          )}

          <p>{health.calibration.message}</p>

          <small>{health.note}</small>

        </>

      ) : (

        <p role="status">Loading data health…</p>

      )}

    </section>

  );

}

