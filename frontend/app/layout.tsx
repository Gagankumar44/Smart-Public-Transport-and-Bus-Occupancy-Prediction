import type { Metadata } from "next";
import "./globals.css";
import "./redesign.css";
import AppShell from "../components/AppShell";
import localFont from "next/font/local";
const manrope = localFont({
  src: "./fonts/Manrope.ttf",
  variable: "--font-body",
  display: "swap",
});
const outfit = localFont({
  src: "./fonts/Outfit.ttf",
  variable: "--font-display",
  display: "swap",
});
export const metadata: Metadata = {
  title: "RushLess — Your city. Your journey.",
  description:
    "Plan a Bengaluru bus journey, explore vehicle and route activity, compare arrivals and crowding, and keep your regular journeys together.",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${manrope.variable} ${outfit.variable}`}>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
