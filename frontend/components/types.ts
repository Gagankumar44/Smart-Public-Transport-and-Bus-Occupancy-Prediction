export type Stop = {
  id: string;
  name: string;
  lat: number;
  lon: number;
  context: string;
};
export type Meta = {
  source: string;
  method: string;
  confidence: string;
  observed_at: string;
  generated_at: string;
  reason: string;
  report_count?: number;
  report_conflict?: boolean;
  base_utilization?: number;
  evidence?: string;
  demand_profile?: string;
  generation?: string;
  uncertainty?: {
    kind: string;
    label: string;
    lower_minutes: number;
    upper_minutes: number;
    occupancy_uncertainty: string;
    calibrated: boolean;
    observation_age_seconds: number;
  };
};
export type Journey = {
  id: string;
  route_id: string;
  route_name: string;
  vehicle_id: string;
  origin: Stop;
  destination: Stop;
  wait_minutes: number;
  ride_minutes: number;
  total_minutes: number;
  arrival_at: string;
  boarding_at: string;
  stop_count: number;
  transfers: number;
  crowding: string;
  utilization: number | null;
  metadata: Meta;
  geometry: [number, number][];
  stops: Stop[];
  explanation: string;
  recommended: boolean;
  service_date?: string | null;
  disruptions?: { id: string; message: string; blocking: boolean }[];
  distance_km?: number | null;
  legs?: {
    id: string; trip_id: string; service_date: string; route_id: string; route_name: string; vehicle_id: string;
    origin: Stop; destination: Stop; wait_minutes: number; ride_minutes: number; total_minutes: number;
    boarding_at: string; arrival_at: string; stop_count: number; crowding: string; utilization: number | null;
    metadata: Meta; geometry: [number,number][]; stops: Stop[];
  }[];
};
export type Vehicle = {
  id: string;
  route_id: string;
  route_name: string;
  lat: number | null;
  lon: number | null;
  next_stop: string;
  passengers: number | null;
  capacity: number | null;
  metadata: Meta;
  completed: boolean;
  movement?: "moving" | "stopped" | "unknown";
  speed_kmh?: number | null;
  bearing?: number | null;
  paused?: boolean;
};
export const API = process.env.NEXT_PUBLIC_API_BASE_URL || "";
export async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(API + path, {
    ...options,
    signal: options?.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(12000)]) : AbortSignal.timeout(12000),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : "Could not complete that request. Please try again.",
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
export const clock = (date: string) =>
  new Date(date).toLocaleTimeString("en-IN", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  });

export const sourceLabel = (source: string) =>
  ({
    simulation: "Demo simulation",
    replay: "Historical replay",
    historical_replay: "Historical replay",
    replay_synthetic: "Synthetic replay",
    authorized: "Authorized feed",
    real_observed: "Observed feed",
    schedule: "Scheduled estimate",
    demo_journey: "Demo connection - not a real bus", mixed: "Mixed sources",
    historical: "Historical estimate",
  })[source] || "Source unavailable";
