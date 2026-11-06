"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useRef,
} from "react";
import { Stop, Vehicle, request } from "./types";
import { CommuterProfile } from "./CommuterPanel";

export type RoutePattern = {
  id: string;
  name: string;
  stops: string[];
  direction?: string;
};
export type TransitStatus = {
  mode: string;
  active_source?: string;
  simulation_time: string;
  demo_controls: boolean;
  scenario: string;
};
type TransitState = {
  stops: Stop[];
  vehicles: Vehicle[];
  routes: RoutePattern[];
  status: TransitStatus | null;
  profile: CommuterProfile | null;
  error: string;
  loading: boolean;
  refresh: () => Promise<void>;
  refreshProfile: () => Promise<void>;
};
const TransitContext = createContext<TransitState | null>(null);

export function TransitProvider({ children }: { children: React.ReactNode }) {
  const [stops, setStops] = useState<Stop[]>([]);
  const [routes, setRoutes] = useState<RoutePattern[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [status, setStatus] = useState<TransitStatus | null>(null);
  const [profile, setProfile] = useState<CommuterProfile | null>(null);

  const [loading, setLoading] = useState(true);
  const refreshProfile = useCallback(async () => {
    try {
      setProfile(await request<CommuterProfile>("/api/profile"));
    } catch {
      /* Planning works without a profile. */
    }
  }, []);
  const polling = useRef(false);
  const catalogLoading = useRef(false);
  const catalogReady = useRef(false);
  const [catalogError, setCatalogError] = useState("");
  const [liveError, setLiveError] = useState("");
  const loadCatalog = useCallback(async () => {
    if (catalogLoading.current || catalogReady.current) return;
    catalogLoading.current = true;
    const [nextStops, nextRoutes] = await Promise.allSettled([
      request<Stop[]>("/api/stops/search?limit=10000"),
      request<RoutePattern[]>("/api/routes"),
    ]);
    if (nextStops.status === "fulfilled") setStops(nextStops.value);
    if (nextRoutes.status === "fulfilled") setRoutes(nextRoutes.value);
    catalogReady.current =
      nextStops.status === "fulfilled" && nextRoutes.status === "fulfilled";
    setCatalogError(
      catalogReady.current
        ? ""
        : "Some network information could not load. Retry to reload the missing catalog.",
    );
    catalogLoading.current = false;
    setLoading(false);
  }, []);
  const refresh = useCallback(async () => {
    loadCatalog();
    if (polling.current) return;
    polling.current = true;
    try {
      const [nextVehicles, nextStatus] = await Promise.allSettled([
        request<Vehicle[]>("/api/vehicles"),
        request<TransitStatus>("/api/system/status"),
      ]);
      if (nextVehicles.status === "fulfilled") setVehicles(nextVehicles.value);
      if (nextStatus.status === "fulfilled") setStatus(nextStatus.value);
      setLiveError(
        nextVehicles.status === "fulfilled" && nextStatus.status === "fulfilled"
          ? ""
          : "Current trip updates are unavailable. Loaded stops and routes remain available; retry the connection.",
      );
    } finally {
      polling.current = false;
    }
  }, [loadCatalog]);
  useEffect(() => {
    refresh();
    refreshProfile();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 10000);
    const focus = () => {
      refresh();
      refreshProfile();
    };
    window.addEventListener("focus", focus);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", focus);
    };
  }, [refresh, refreshProfile]);
  return (
    <TransitContext.Provider
      value={{
        stops,
        routes,
        vehicles,
        status,
        profile,
        error: catalogError || liveError,
        loading,
        refresh,
        refreshProfile,
      }}
    >
      {children}
    </TransitContext.Provider>
  );
}
export function useTransit() {
  const context = useContext(TransitContext);
  if (!context) throw new Error("TransitProvider is required");
  return context;
}
