"use client";
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  Bookmark,
  History,
  Trash2,
  X,
  ArrowRight,
  ShieldCheck,
} from "lucide-react";
import { Stop, request } from "./types";
export type CommuterProfile = {
  preference: "fastest" | "comfortable";
  alerts_enabled: boolean;
  saved: { id: string; name: string; origin: string; destination: string }[];
  recent: { origin: string; destination: string }[];
  last_context: { origin: string; destination: string } | null;
};
export default function CommuterPanel({
  profile,
  origin,
  destination,
  stops,
  onProfile,
  onChoose,
  onReset,
}: {
  profile: CommuterProfile | null;
  origin: Stop | null;
  destination: Stop | null;
  stops: Stop[];
  onProfile: (p: CommuterProfile) => void;
  onChoose: (origin: string, destination: string) => void;
  onReset: () => void;
}) {
  const [open, setOpen] = useState(false),
    [name, setName] = useState("Daily commute"),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [draft, setDraft] = useState<Record<string, string>>({});
  const stopName = (id: string) =>
    stops.find((s) => s.id === id)?.name || "Unsupported stop";
  async function mutate(path: string, method: string, body?: object) {
    setBusy(true);
    setMessage("");
    try {
      const result = await request<CommuterProfile>("/api/profile" + path, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      onProfile(result);
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function reset() {
    setBusy(true);
    try {
      await request("/api/profile", { method: "DELETE" });
      onProfile(await request<CommuterProfile>("/api/profile"));
      onReset();
      setMessage("Saved data and previous anonymous identity cleared.");
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="commuter-access">
        <button onClick={() => setOpen(true)}>
          <Bookmark size={15} />
          Saved journeys & recent searches
        </button>
        {origin && destination && origin.id !== destination.id && (
          <button
            disabled={busy || !profile}
            onClick={async () => {
              await mutate("/saved-journeys", "POST", {
                name: "Saved commute",
                origin: origin.id,
                destination: destination.id,
              });
              setOpen(true);
            }}
          >
            Save this journey
          </button>
        )}
      </div>
      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content commuter-dialog">
            <Dialog.Close
              className="dialog-close"
              aria-label="Close saved journeys"
            >
              <X size={20} />
            </Dialog.Close>
            <div className="info-icon">
              <Bookmark size={24} />
            </div>
            <Dialog.Title>Your everyday journeys</Dialog.Title>
            <Dialog.Description>
              Saved on this server using an anonymous first-party cookie. No
              account or continuous location history. Trip availability is
              checked again when you search.
            </Dialog.Description>
            {!profile ? (
              <p role="status">
                Saved settings are unavailable. Reopen the app to retry; journey
                search still works.
              </p>
            ) : (
              <>
                <section className="profile-section">
                  <h3>Saved journeys</h3>
                  {profile.saved.length ? (
                    profile.saved.map((j) => (
                      <article key={j.id} className="saved-item">
                        <button
                          onClick={() => {
                            onChoose(j.origin, j.destination);
                            setOpen(false);
                          }}
                        >
                          <strong>{j.name}</strong>
                          <small>
                            {stopName(j.origin)} → {stopName(j.destination)}
                          </small>
                        </button>
                        <input
                          aria-label={"Rename " + j.name}
                          maxLength={60}
                          value={draft[j.id] ?? j.name}
                          onChange={(e) =>
                            setDraft({ ...draft, [j.id]: e.target.value })
                          }
                        />
                        <div>
                          <button
                            disabled={busy || !(draft[j.id] ?? j.name).trim()}
                            onClick={() =>
                              mutate("/saved-journeys/" + j.id, "PATCH", {
                                name: (draft[j.id] ?? j.name).trim(),
                              })
                            }
                          >
                            Rename
                          </button>
                          <button
                            disabled={busy}
                            aria-label={"Delete " + j.name}
                            onClick={() =>
                              mutate("/saved-journeys/" + j.id, "DELETE")
                            }
                          >
                            <Trash2 size={14} />
                            Remove
                          </button>
                        </div>
                      </article>
                    ))
                  ) : (
                    <p>No journeys saved yet.</p>
                  )}
                  {origin && destination && origin.id !== destination.id && (
                    <form
                      className="save-form"
                      onSubmit={(e) => {
                        e.preventDefault();
                        mutate("/saved-journeys", "POST", {
                          name: name.trim(),
                          origin: origin.id,
                          destination: destination.id,
                        });
                      }}
                    >
                      <label htmlFor="saved-name">
                        Name the current stop pair
                      </label>
                      <input
                        id="saved-name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        maxLength={60}
                        required
                      />
                      <button disabled={busy || !name.trim()}>
                        Save journey <Bookmark size={14} />
                      </button>
                    </form>
                  )}
                </section>
                <section className="profile-section">
                  <h3>
                    <History size={15} />
                    Recent searches
                  </h3>
                  {profile.recent.length ? (
                    profile.recent.map((p, i) => (
                      <button
                        className="recent-pair"
                        key={i}
                        onClick={() => {
                          onChoose(p.origin, p.destination);
                          setOpen(false);
                        }}
                      >
                        {stopName(p.origin)} <ArrowRight size={13} />
                        {stopName(p.destination)}
                      </button>
                    ))
                  ) : (
                    <p>No recent searches.</p>
                  )}
                  <button
                    className="profile-text-button"
                    disabled={busy || !profile.recent.length}
                    onClick={() => mutate("/recent", "DELETE")}
                  >
                    Clear recent searches
                  </button>
                </section>
                <section className="profile-section">
                  <h3>
                    <ShieldCheck size={15} />
                    Your settings & privacy
                  </h3>
                  <p>
                    Travel preference: {profile.preference}. Watch monitoring
                    runs only while the page is open and never resumes an
                    expired bus automatically.
                  </p>
                  <label className="alert-preference">
                    <input
                      type="checkbox"
                      checked={profile.alerts_enabled}
                      onChange={(e) =>
                        mutate("/preferences", "PATCH", {
                          alerts_enabled: e.target.checked,
                        })
                      }
                    />{" "}
                    Enable in-app journey alerts
                  </label>
                  <p>
                    Anonymous settings expire after 30 inactive days by default.
                    Saved stop pairs and names stay on the server; no email,
                    phone, fingerprint or device location is required.
                  </p>
                  <button
                    className="profile-text-button"
                    disabled={busy}
                    onClick={reset}
                  >
                    Reset all anonymous saved data
                  </button>
                </section>
              </>
            )}
            {message && (
              <p className="profile-message" role="status">
                {message}
              </p>
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
