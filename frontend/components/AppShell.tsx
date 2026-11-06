"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, useRef } from "react";
import {
  LayoutDashboard,
  Route,
  BusFront,
  Radio,
  CalendarClock,
  MapPinned,
  Calculator,
  Bookmark,
  ChartNoAxesCombined,
  BookOpen,
  MessageSquare,
  Headphones,
  ChevronDown,
  MapPin,
  Menu,
  X,
  ArrowUpRight,
  Languages,
  MoveUpRight,
} from "lucide-react";
import { TransitProvider, useTransit } from "./TransitContext";
import { LocaleProvider, useLocale } from "./Locale";
import { sourceLabel } from "./types";
const primary = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/planner", label: "Journey Planner", icon: Route },
  { href: "/route-explorer", label: "Best Route Explorer", icon: MapPinned },
  { href: "/track-bus", label: "Track a Bus", icon: BusFront },
  { href: "/live-route", label: "Track a Live Route", icon: Radio },
  { href: "/timetable", label: "Time Table", icon: CalendarClock },
  { href: "/saved", label: "Saved journeys", icon: Bookmark },
];
const secondary = [
  { href: "/facilities", label: "Facilities", icon: MapPinned },
  { href: "/fare-calculator", label: "Fare Calculator", icon: Calculator },
  { href: "/insights", label: "Corridor insights", icon: ChartNoAxesCombined },
];
function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const { language, setLanguage, t } = useLocale();
  const { status, error, refreshProfile } = useTransit();
  useEffect(() => {
    setOpen(false);
    refreshProfile();
  }, [pathname, refreshProfile]);
  useEffect(() => {
    if (!open) return;
    const menuButton = menuRef.current;
    closeRef.current?.focus();
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
      if (event.key === "Tab") {
        const elements = sidebarRef.current?.querySelectorAll<HTMLElement>(
          "a[href],button:not([disabled])",
        );
        if (!elements?.length) return;
        const first = elements[0],
          last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        }
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("keydown", close);
      menuButton?.focus();
    };
  }, [open]);
  const title =
    [
      ...primary,
      ...secondary,
      { href: "/feedback", label: "Feedback" },
      { href: "/guide", label: "User Guide" },
      { href: "/help", label: "Help & support" },
    ].find((n) => n.href === pathname)?.label || "RushLess";
  const navItems = (items: typeof primary) =>
    items.map(({ href, label, icon: Icon }) => (
      <Link
        key={href}
        href={href}
        className={pathname === href ? "rl-nav-item is-current" : "rl-nav-item"}
        aria-current={pathname === href ? "page" : undefined}
      >
        <Icon size={18} aria-hidden="true" />
        <span>{t(label)}</span>
        {pathname === href && <span className="rl-active-dot" />}
      </Link>
    ));
  return (
    <div className="rl-app">
      <a href="#main-content" className="rl-skip">
        Skip to content
      </a>
      {open && (
        <button
          className="rl-sidebar-scrim"
          aria-label={t("Close menu")}
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        ref={sidebarRef}
        className={"rl-sidebar" + (open ? " is-open" : "")}
        aria-label="Main navigation"
        id="main-navigation"
      >
        <Link href="/" className="rl-brand" aria-label="RushLess home">
          <span className="rl-logo">
            <Route size={25} strokeWidth={2.7} />
          </span>
          <span>
            rushless<span className="rl-brand-dot">.</span>
            <small>Bengaluru, better connected</small>
          </span>
        </Link>
        <button
          ref={closeRef}
          className="rl-mobile-close"
          onClick={() => setOpen(false)}
          aria-label={t("Close menu")}
        >
          <X size={22} />
        </button>
        <nav>
          <p className="rl-nav-label">{t("Your commute")}</p>
          {navItems(primary)}
          <p className="rl-nav-label rl-nav-label-second">
            {t("Explore & more")}
          </p>
          {navItems(secondary)}
        </nav>
        <div className="rl-sidebar-bottom">
          <Link href="/guide" className="rl-nav-item">
            <BookOpen size={18} />
            {t("User Guide")}
          </Link>
          <Link href="/feedback" className="rl-nav-item">
            <MessageSquare size={18} />
            {t("Feedback")}
          </Link>
          <div className="rl-sidebar-note">
            <span className="rl-mini-route">
              <MapPin size={16} /> Built around your commute
            </span>
            <p>{t("Independent transport prototype")}</p>
            <Link href="/insights">
              Our data, explained <ArrowUpRight size={13} />
            </Link>
          </div>
        </div>
      </aside>
      <div className="rl-main-shell" inert={open}>
        <header className="rl-topbar">
          <div className="rl-breadcrumb">
            <button
              ref={menuRef}
              className="rl-menu"
              aria-label={t("Menu")}
              aria-expanded={open}
              aria-controls="main-navigation"
              onClick={() => setOpen(!open)}
            >
              <Menu size={23} />
            </button>
            <span className="rl-breadcrumb-brand">
              Workspace <span>/</span>
            </span>
            <strong>{t(title)}</strong>
          </div>
          <div className="rl-topbar-right">
            <span className="rl-city">
              <MapPin size={15} />
              {t("Bengaluru")}
            </span>
            <Link
              href="/help"
              className="rl-help-link"
              aria-label={t("Help & support")}
            >
              <Headphones size={17} />
              <span>{t("Help & support")}</span>
            </Link>
            <label className="rl-language">
              <Languages size={16} />
              <span className="sr-only">Interface language</span>
              <select
                aria-label="Interface language"
                value={language}
                onChange={(e) => setLanguage(e.target.value as "en" | "kn")}
              >
                <option value="en">English</option>
                <option value="kn">ಕನ್ನಡ</option>
              </select>
              <ChevronDown size={12} />
            </label>
          </div>
        </header>
        <div className="rl-sourcebar">
          <span>
            <i className="rl-dot-offline" />
            {error
              ? "Connection unavailable"
              : status
                ? t(sourceLabel(status.active_source || status.mode))
                : "Connecting…"}
          </span>
          <span>
            {status?.mode === "simulation"
              ? t("No live BMTC connection")
              : "Check source freshness in Data Health"}
            <Link href="/insights" aria-label="Open data health">
              <MoveUpRight size={13} />
            </Link>
          </span>
        </div>
        <div id="main-content" className="rl-content" tabIndex={-1}>
          {children}
        </div>
        <div className="rl-bottomline">
          <span>RushLess © 2026</span>
          <span>A little less rush. A better journey.</span>
          <Link href="/help#privacy">Privacy & data</Link>
        </div>
      </div>
    </div>
  );
}
export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <LocaleProvider>
      <TransitProvider>
        <Shell>{children}</Shell>
      </TransitProvider>
    </LocaleProvider>
  );
}
