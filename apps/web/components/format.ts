export function value(v: unknown, unit = "") {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  if (unit === "%")
    return (
      n.toLocaleString("en-GB", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }) + "%"
    );
  if (unit === "average beds" || unit === "beds" || unit === "bed-days")
    return n.toLocaleString("en-GB", { maximumFractionDigits: 2 });
  return n.toLocaleString("en-GB", { maximumFractionDigits: 2 });
}
export function timestamp(v: unknown) {
  if (!v) return "Not recorded";
  const d = new Date(String(v));
  if (Number.isNaN(d.valueOf())) return String(v);
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/London",
    timeZoneName: "short",
  }).format(d);
}
export function publication(v: unknown) {
  if (!v) return "Not stated in source";
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Europe/London",
  }).format(new Date(String(v)));
}
export function month(v: unknown) {
  if (!v) return "No published period";
  return new Intl.DateTimeFormat("en-GB", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(String(v)));
}
export function quarter(v: unknown) {
  if (!v) return "No published quarter";
  const d = new Date(String(v));
  const end = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 2, 1));
  return `${new Intl.DateTimeFormat("en-GB", { month: "short", timeZone: "UTC" }).format(d)}–${month(end.toISOString())}`;
}
