"use client";
import { useEffect, useRef, useState } from "react";
import PilotObservation from "./PilotObservation";
import * as Dialog from "@radix-ui/react-dialog";
import { Bell, Users, Eye, X, ArrowRight, ShieldCheck } from "lucide-react";
import { Journey, Stop, request, clock, sourceLabel } from "./types";
type Watch = {
  id: string;
  trip_id: string;
  current: Journey | null;
  available: boolean;
  alerts: { id: string; kind: string; message: string; created_at: string }[];
  alternative: Journey | null;
  phase: "waiting" | "onboard" | "arrived";
  current_stop: Stop;
  progress_stops: Stop[];
  incident: "none" | "breakdown" | "diversion";
  monitoring_note: string;
  alternatives_note: string;
  checked_at: string;
  disruptions: { id: string; message: string }[];
};
type CloseArrival = {
  route_id: string;
  label: string;
  gap_minutes: number;
  explanation: string;
};
export default function JourneyIntelligence({
  journey,
  preference,
  alertsEnabled,
  expanded,
  onUpdate,
  onSelect,
}: {
  journey: Journey;
  preference: string;
  alertsEnabled: boolean;
  expanded: boolean;
  onUpdate: () => void;
  onSelect: (j: Journey) => void;
}) {
  const [watch, setWatch] = useState<Watch | null>(null),
    [watchId, setWatchId] = useState(""),
    [reportOpen, setReportOpen] = useState(false),
    [notice, setNotice] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [close, setClose] = useState<CloseArrival[]>([]);
  const [progressStop, setProgressStop] = useState("");
  const [incident, setIncident] = useState<Watch["incident"]>("none");
  const idRef = useRef("");
  const watchedTrip = useRef("");
  useEffect(() => {
    setNotice("");
    setError("");
    if (idRef.current && watchedTrip.current !== journey.id) {
      request("/api/watches/" + idRef.current, { method: "DELETE" }).catch(() => {});
      idRef.current = "";
      setWatchId("");
      setWatch(null);
      setProgressStop("");
      setIncident("none");
    }
  }, [journey.id]);
  useEffect(
    () => () => {
      if (idRef.current)
        request("/api/watches/" + idRef.current, { method: "DELETE" }).catch(
          () => {},
        );
    },
    [],
  );
  useEffect(() => {
    let active = true;
    async function update() {
      try {
        const notices = await request<CloseArrival[]>(
          "/api/stops/" + journey.origin.id + "/close-arrivals",
        );
        if (active)
          setClose(notices.filter((n) => n.route_id === journey.route_id));
      } catch {
        if (active) setClose([]);
      }
    }
    update();
    const timer = setInterval(update, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [journey.origin.id, journey.route_id]);
  useEffect(() => {
    if (!watchId) return;
    let active = true;
    let pending = false;
    const update = async () => {
      if (pending || document.hidden) return;
      pending = true;
      try {
        const state = await request<Watch>(
          "/api/watches/" +
            watchId +
            "?preference=" +
            preference +
            "&alerts_enabled=" +
            alertsEnabled,
        );
        if (active) {
          setWatch(state);
          setError("");
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      } finally {
        pending = false;
      }
    };
    update();
    const timer = setInterval(update, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [watchId, preference, alertsEnabled]);
  async function toggleWatch() {
    setBusy(true);
    setError("");
    try {
      if (watchId) {
        await request("/api/watches/" + watchId, { method: "DELETE" });
        idRef.current = "";
        setWatchId("");
        setWatch(null);
      } else {
        const state = await request<{ id: string }>("/api/watches", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            trip_id: journey.id,
            service_date: journey.service_date || null,
            origin: journey.origin.id,
            destination: journey.destination.id,
            preference,
            alerts_enabled: alertsEnabled,
          }),
        });
        idRef.current = state.id;
        watchedTrip.current = journey.id;
        setProgressStop("");
        setIncident("none");
        setWatchId(state.id);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function report(level: string) {
    setBusy(true);
    setError("");
    try {
      const status = await request<{ generation: string }>(
        "/api/system/status",
      );
      const v = await request<{
        next_stop: string;
        progress: number;
        route_id: string;
        trip_id: string;
      }>("/api/vehicles/" + journey.vehicle_id);
      const route = await request<{ stops: { id: string }[] }>(
        "/api/routes/" + v.route_id,
      );
      const at =
        route.stops[
          Math.max(0, Math.min(route.stops.length - 1, Math.floor(v.progress)))
        ].id;
      await request("/api/crowd-reports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          vehicle_id: journey.vehicle_id,
          trip_id: v.trip_id,
          route_id: v.route_id,
          stop_id: at,
          level,
          generation: status.generation,
        }),
      });
      setReportOpen(false);
      setNotice(
        "Demo report accepted. Your observation now contributes to this trip’s forecast.",
      );
      onUpdate();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function decide(action: "accept" | "keep") {
    if (!watchId) return;
    setBusy(true);
    try {
      const state = await request<Watch>(
        "/api/watches/" + watchId + "/decision",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action }),
        },
      );
      setWatch(state);
      if (action === "accept" && state.current) {
        watchedTrip.current = state.current.id;
        setProgressStop("");
        setIncident("none");
        onSelect(state.current);
      }
      onUpdate();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function confirmProgress() {
    if (!watch) return;
    const at = progressStop || watch.current_stop.id;
    setBusy(true);
    setError("");
    try {
      const state = await request<Watch>("/api/watches/" + watch.id + "/progress", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_stop: at, phase: at === journey.destination.id ? "arrived" : "onboard", incident }),
      });
      setWatch(state);
      setProgressStop("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="intelligence" aria-label="Journey intelligence">
      {(
        <div className="intelligence-actions">
          <div>
            <span className="eyebrow">A LITTLE HELP ALONG THE WAY</span>
            <p>
              {sourceLabel(journey.metadata.source)} · open-page monitoring only
            </p>
          </div>
          <button
            className={watchId ? "enabled" : ""}
            disabled={busy}
            onClick={toggleWatch}
          >
            <Eye size={16} />
            {watchId ? "Stop watching" : "Watch Journey"}
          </button>
          {expanded && (journey.id.startsWith("demo-") ? (
            <button
              disabled={busy}
              onClick={() => {
                setError("");
                setReportOpen(true);
              }}
            >
              <Users size={16} />
              Report crowding
            </button>
          ) : (
            <PilotObservation />
          ))}
        </div>
      )}
      {close.map((n, i) => (
        <div className="close-notice" key={i}>
          <ShieldCheck size={16} />
          <span>
            <strong>
              {n.label} · {n.gap_minutes} min apart
            </strong>
            <small>{n.explanation}</small>
          </span>
        </div>
      ))}
      {notice && (
        <div className="intelligence-notice" role="status">
          {notice}
          <button
            aria-label="Dismiss report confirmation"
            onClick={() => setNotice("")}
          >
            <X size={14} />
          </button>
        </div>
      )}
      {error && !reportOpen && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {watchId && (
        <div className="watch-panel">
          <header>
            <span>
              <Bell size={16} /> Watching{" "}
              {watch?.current?.route_name ||
                watch?.trip_id ||
                journey.route_name}
            </span>
            <small>
              While this page is open ·{" "}
              {sourceLabel(
                watch?.current?.metadata.source || journey.metadata.source,
              )}
            </small>
          </header>
          {watch && <p className="monitoring-note">{watch.monitoring_note} Checked {clock(watch.checked_at)}.</p>}
          {watch?.phase === "arrived" && <p role="status">Journey completed at your confirmed destination.</p>}
          {watch && !watch.available && watch.phase !== "arrived" && (
            <p role="status">
              A usable ETA for the selected journey is unavailable. Review departures from your confirmed stop.
            </p>
          )}
          {watch?.current && (
            <p>
              {watch.phase === "onboard"
                ? `Destination ETA ${clock(watch.current.arrival_at)} · ${Math.ceil(watch.current.total_minutes)} min remaining`
                : `Bus expected in ${Math.ceil(watch.current.wait_minutes)} min`} ·{" "}
              {watch.current.crowding} crowding ·{" "}
              {watch.current.metadata.confidence} confidence
            </p>
          )}
          {watch && watch.phase !== "arrived" && (
            <div className="journey-progress">
              <div>
                <strong>{watch.phase === "onboard" ? "Journey in progress" : "Start your journey"}</strong>
                <p>Confirm your current stop to monitor the remaining journey. Location is self-reported and stays within this watch.</p>
              </div>
              <label>
                Current confirmed stop
                <select value={progressStop || watch.current_stop.id} onChange={(e) => setProgressStop(e.target.value)} disabled={busy}>
                  {watch.progress_stops.slice(Math.max(0, watch.progress_stops.findIndex((s) => s.id === watch.current_stop.id))).map((s) => <option value={s.id} key={s.id}>{s.name}</option>)}
                </select>
              </label>
              <label>
                Your travel status
                <select value={incident} onChange={(e) => setIncident(e.target.value as Watch["incident"])} disabled={busy}>
                  <option value="none">No issue reported</option>
                  <option value="breakdown">Bus stopped / breakdown</option>
                  <option value="diversion">Route diverted</option>
                </select>
              </label>
              <button onClick={confirmProgress} disabled={busy}>
                {(progressStop || watch.current_stop.id) === journey.destination.id ? "Confirm arrival" : watch.phase === "waiting" ? "I’ve boarded — start monitoring" : "Confirm progress and check alternatives"}
              </button>
              <small>For alternatives, confirm the stop where you can safely board another bus. Board or alight only where permitted.</small>
            </div>
          )}
          {!!watch?.disruptions.length && <div role="status">{watch.disruptions.map((d) => <p key={d.id}>{d.message}</p>)}</div>}
          {watch?.alternative && (
            <div className="alternative">
              <strong>
                Better option available · {watch.alternative.route_name}
              </strong>
              <p>
                {watch.current
                  ? `${Math.abs(Math.round(watch.current.total_minutes - watch.alternative.total_minutes))} min ${watch.current.total_minutes >= watch.alternative.total_minutes ? "sooner" : "longer"}; ${watch.alternative.crowding.toLowerCase()} predicted crowding.`
                  : "An eligible departure is available."}
              </p>
              <p>Board at {watch.alternative.origin.name} · {clock(watch.alternative.boarding_at)}. Destination {clock(watch.alternative.arrival_at)} · {sourceLabel(watch.alternative.metadata.source)}.</p>
              <div>
                <button disabled={busy} onClick={() => decide("accept")}>
                  I’m at this stop — switch journey <ArrowRight size={13} />
                </button>
                <button disabled={busy} onClick={() => decide("keep")}>
                  Keep current journey
                </button>
              </div>
            </div>
          )}
          {watch && watch.phase !== "arrived" && <p>{watch.alternatives_note}</p>}
          <div className="recent-alerts" role="log" aria-live="polite">
            {watch?.alerts.length ? (
              watch.alerts
                .slice(-4)
                .reverse()
                .map((a) => (
                  <p key={a.id}>
                    <span>{clock(a.created_at)}</span>
                    {a.message}
                  </p>
                ))
            ) : (
              <p>
                {alertsEnabled
                  ? "No new alerts. We’ll flag meaningful changes here."
                  : "Journey alerts are disabled in your saved preferences."}
              </p>
            )}
          </div>
        </div>
      )}
      <Dialog.Root open={reportOpen} onOpenChange={setReportOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content report-dialog">
            <Dialog.Close
              aria-label="Close crowd reporting"
              className="dialog-close"
            >
              <X size={20} />
            </Dialog.Close>
            <div className="info-icon">
              <Users size={24} />
            </div>
            <Dialog.Title>How crowded is this bus?</Dialog.Title>
            <Dialog.Description>
              {journey.route_name} · {journey.vehicle_id}. This is a demo report
              about the vehicle’s current or last stop, not a real BMTC
              observation.
            </Dialog.Description>
            <div className="report-options">
              {[
                ["Low", "Plenty of standing space."],
                ["Moderate", "Some crowding; standing may be required."],
                ["High", "Very crowded; limited standing space."],
              ].map(([level, description]) => (
                <button
                  key={level}
                  className={level.toLowerCase()}
                  disabled={busy}
                  onClick={() => report(level)}
                >
                  <Users size={21} />
                  <span>
                    <strong>{level} crowding</strong>
                    <small>{description}</small>
                  </span>
                  <ArrowRight size={16} />
                </button>
              ))}
            </div>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <p className="report-footnote">
              Reports influence forecasts gradually, expire after 15 minutes,
              and stay attached to this specific demo trip.
            </p>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}
