export function istParts(date = new Date()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone:"Asia/Kolkata",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23" }).formatToParts(date).map((p) => [p.type,p.value]));
  return { date:`${parts.year}-${parts.month}-${parts.day}`, time:`${parts.hour}:${parts.minute}` };
}
export function istIso(value: string) {
  if (!value) return "";
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) throw new Error("Choose a valid IST date and time.");
  const parsed = new Date(value + ":00+05:30");
  if (!Number.isFinite(parsed.getTime())) throw new Error("Invalid departure.");
  const parts=istParts(parsed);
  if (parts.date+"T"+parts.time!==value) throw new Error("Invalid calendar date or time.");
  return parsed.toISOString();
}
