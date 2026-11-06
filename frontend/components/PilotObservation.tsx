"use client";
import { useState, useEffect } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { ClipboardCheck, X } from "lucide-react";
import { request, Stop } from "./types";
type Catalog = {
  routes: {
    id: string;
    name: string;
    direction: string;
    stops: string[];
    synthetic: boolean;
  }[];
  stops: Stop[];
};
export default function PilotObservation() {
  const [open, setOpen] = useState(false),
    [catalog, setCatalog] = useState<Catalog | null>(null),
    [kind, setKind] = useState("arrival"),
    [route, setRoute] = useState(""),
    [stop, setStop] = useState(""),
    [trip, setTrip] = useState(""),
    [category, setCategory] = useState("Moderate"),
    [event, setEvent] = useState(""),
    [date, setDate] = useState(""),
    [note, setNote] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    let active = true;
    request<Catalog>("/api/observations/catalog")
      .then((c) => {
        if (active) {
          setCatalog(c);
          setRoute(c.routes[0]?.id || "");
          setStop(c.routes[0]?.stops[0] || "");
        }
      })
      .catch((e) => {
        if (active) setMessage(e.message);
      });
    const now = new Date();
    setEvent(
      new Date(now.getTime() - now.getTimezoneOffset() * 60000)
        .toISOString()
        .slice(0, 16),
    );
    setDate(now.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }));
    return () => {
      active = false;
    };
  }, [open]);
  const selected = catalog?.routes.find((r) => r.id === route);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await request<{
        id: string;
        status: string;
        source_type: string;
        message: string;
      }>(
        "/api/observations/" + (kind === "arrival" ? "arrivals" : "occupancy"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            route_id: route,
            stop_id: stop,
            direction: selected.direction,
            service_date: date.replaceAll("-", ""),
            trip_id: trip.trim() || null,
            event_at: new Date(event).toISOString(),
            method: "volunteer_manual",
            category: kind === "occupancy" ? category : null,
            note,
          }),
        },
      );
      setMessage(
        `${result.source_type === "simulation" ? "Practice" : "Pilot"} observation recorded (${result.status}). Reference ${result.id}. Not independently verified.`,
      );
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        className="pilot-access"
        onClick={() => {
          setOpen(true);
          setMessage("");
        }}
      >
        <ClipboardCheck size={15} />
        Record a pilot observation
      </button>
      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content pilot-dialog">
            <Dialog.Close
              className="dialog-close"
              aria-label="Close pilot observation"
            >
              <X size={20} />
            </Dialog.Close>
            <div className="info-icon">
              <ClipboardCheck size={24} />
            </div>
            <Dialog.Title>Record what you observed</Dialog.Title>
            <Dialog.Description>
              For a controlled pilot. Submit after safely boarding or stopping.
              Record actual events, not predicted times. No photos, passenger
              identities or number plates are needed.
            </Dialog.Description>
            <form className="pilot-form" onSubmit={submit}>
              <label>
                Observation type
                <select value={kind} onChange={(e) => setKind(e.target.value)}>
                  <option value="arrival">Actual bus arrival</option>
                  <option value="occupancy">Observed crowd category</option>
                </select>
              </label>
              <label>
                Route & direction
                <select
                  value={route}
                  onChange={(e) => {
                    setRoute(e.target.value);
                    setStop(
                      catalog?.routes.find((r) => r.id === e.target.value)
                        ?.stops[0] || "",
                    );
                  }}
                >
                  {catalog?.routes.map((r) => (
                    <option value={r.id} key={r.id}>
                      {r.name} · {r.direction} ·{" "}
                      {r.synthetic ? "Demo practice" : "GTFS pilot"}
                    </option>
                  ))}
                </select>
              </label>
              {selected?.synthetic && (
                <p className="pilot-practice">
                  Demo practice only. This route cannot create a genuine
                  evaluation label.
                </p>
              )}
              <label>
                Observed stop
                <select value={stop} onChange={(e) => setStop(e.target.value)}>
                  {selected?.stops.map((id) => (
                    <option key={id} value={id}>
                      {catalog?.stops.find((s) => s.id === id)?.name || id}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Trip ID, if confidently known
                <input
                  value={trip}
                  maxLength={100}
                  onChange={(e) => setTrip(e.target.value)}
                  placeholder="Leave blank when uncertain"
                />
              </label>
              <label>
                Service date (Bengaluru)
                <input
                  required
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                />
              </label>
              <label>
                Actual observed time (your device timezone)
                <input
                  required
                  type="datetime-local"
                  value={event}
                  onChange={(e) => setEvent(e.target.value)}
                />
              </label>
              {kind === "occupancy" && (
                <label>
                  Observed crowding
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                  >
                    {["Low", "Moderate", "High"].map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
              )}
              <label>
                Optional operational note
                <input
                  value={note}
                  maxLength={200}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="No personal information"
                />
              </label>
              <button disabled={busy || !selected} type="submit">
                {busy ? "Recording…" : "Submit observation"}
              </button>
            </form>
            {message && (
              <p role="status" className="profile-message">
                {message}
              </p>
            )}
            <p className="report-footnote">
              Submission is unverified. Missing or uncertain trips remain
              unresolved. Only reviewed, matched genuine observations enter
              real-world evaluation.
            </p>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
