"use client";
import { useEffect, useState } from "react";
import { request } from "./types";
type Metrics = {
  sample_count: number;
  mae_minutes: number;
  median_absolute_error_minutes: number;
  p90_absolute_error_minutes: number;
};
type Evaluation = {
  paired_comparisons?: Record<
    string,
    {
      sample_count: number;
      method_metrics: Metrics | null;
      schedule_metrics: Metrics | null;
    }
  >;
  dataset_id: string;
  label: string;
  methods: Record<
    string,
    {
      metrics: Metrics | null;
      interval: {
        coverage: number;
        mean_width_minutes: number;
        test_samples: number;
      } | null;
    }
  >;
  split: Record<string, { rows: number; trips: number }>;
  occupancy: {
    forecast: {
      sample_count: number;
      accuracy: number;
      macro_f1: number;
      confusion_matrix: number[][];
      labels: string[];
    } | null;
    majority_baseline: { accuracy: number } | null;
  } | null;
};
type Quality = {
  message: string;
  ml_enabled: boolean;
  real: Evaluation | null;
  simulation: Evaluation | null;
};
function Comparison({ report }: { report: Evaluation }) {
  return (
    <>
      <p>{report.label}</p>
      <div className="quality-table-wrap">
        <table>
          <caption>ETA errors on held-out trips · minutes</caption>
          <thead>
            <tr>
              <th>Method</th>
              <th>Samples</th>
              <th>MAE</th>
              <th>Median</th>
              <th>P90</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(report.methods).map(([method, result]) => (
              <tr key={method}>
                <th>{method.replaceAll("_", " ")}</th>
                <td>{result.metrics?.sample_count ?? 0}</td>
                <td>{result.metrics?.mae_minutes ?? "Unavailable"}</td>
                <td>{result.metrics?.median_absolute_error_minutes ?? "—"}</td>
                <td>{result.metrics?.p90_absolute_error_minutes ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>Split, intervals and occupancy</summary>
        <p>
          {Object.entries(report.split)
            .map(([part, s]) => `${part}: ${s.rows} labels / ${s.trips} trips`)
            .join(" · ")}
          . Trips are separated chronologically; overlapping labels are purged.
        </p>
        {report.paired_comparisons &&
          Object.entries(report.paired_comparisons).map(([method, pair]) => (
            <p key={method}>
              Paired comparison: {method} · {pair.sample_count} same-event
              labels · MAE {pair.method_metrics?.mae_minutes ?? "unavailable"}{" "}
              min versus schedule{" "}
              {pair.schedule_metrics?.mae_minutes ?? "unavailable"} min. Use
              paired sets when method coverage differs.
            </p>
          ))}
        {Object.entries(report.methods).map(([method, value]) => (
          <p key={method}>
            {method}:{" "}
            {value.interval
              ? `${Math.round(value.interval.coverage * 100)}% holdout interval coverage across ${value.interval.test_samples} samples; mean width ${value.interval.mean_width_minutes} min.`
              : "Insufficient calibration labels for empirical intervals."}
          </p>
        ))}
        {report.occupancy?.forecast ? (
          <>
            <p>
              Occupancy: {report.occupancy.forecast.sample_count} held-out
              labels · accuracy {report.occupancy.forecast.accuracy} · macro F1{" "}
              {report.occupancy.forecast.macro_f1} · majority baseline accuracy{" "}
              {report.occupancy.majority_baseline?.accuracy}.
            </p>
            <table>
              <caption>
                Confusion matrix · actual rows, predicted columns
              </caption>
              <thead>
                <tr>
                  <th>Actual</th>
                  {report.occupancy.forecast.labels.map((l) => (
                    <th key={l}>{l}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {report.occupancy.forecast.confusion_matrix.map((row, i) => (
                  <tr key={i}>
                    <th>{report.occupancy!.forecast!.labels[i]}</th>
                    {row.map((n, k) => (
                      <td key={k}>{n}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <p>No usable occupancy labels.</p>
        )}
      </details>
    </>
  );
}
export default function PredictionQuality() {
  const [quality, setQuality] = useState<Quality | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    let sequence = 0;
    async function load() {
      const version = ++sequence;
      try {
        const data = await request<Quality>("/api/insights/prediction-quality");
        if (active && version === sequence) {
          setQuality(data);
          setError("");
        }
      } catch (e) {
        if (active && version === sequence) setError((e as Error).message);
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
    <section className="prediction-quality">
      <span className="eyebrow">PREDICTION QUALITY</span>
      <h2>Evidence before confidence.</h2>
      {error ? (
        <p role="alert">{error}</p>
      ) : quality ? (
        <>
          <p>{quality.message}</p>
          <span className="quality-status">
            Trained-model serving disabled · See Data Health for interval
            eligibility
          </span>
          {quality.real && <Comparison report={quality.real} />}

        </>
      ) : (
        <p role="status">Loading evaluation status…</p>
      )}
    </section>
  );
}
