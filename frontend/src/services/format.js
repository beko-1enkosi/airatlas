export const pollutant = (value) =>
  ({ pm25: "PM2.5", pm10: "PM10" })[value] || value;
export const number = (value) =>
  value == null
    ? "—"
    : new Intl.NumberFormat("en-ZA", { maximumFractionDigits: 1 }).format(
        value,
      );
export const DISPLAY_TIMEZONE = "Africa/Johannesburg";
export const timestamp = (value) => {
  if (value == null || Number.isNaN(new Date(value).getTime()))
    return "Not available";
  return `${new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: DISPLAY_TIMEZONE,
    hourCycle: "h23",
  }).format(new Date(value))} SAST`;
};
// Date-only mart keys describe UTC aggregation buckets. Display their start in
// SAST; never shift filters or imply these are regrouped SAST daily averages.
export const bucketTimestamp = (value) => timestamp(`${value}T00:00:00Z`);
export const shortDate = (value) =>
  new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: DISPLAY_TIMEZONE,
  }).format(new Date(`${value}T00:00:00Z`));
export const locationName = (location) =>
  location.location_name || `Location ${location.location_id}`;
export const validCoordinates = (location) =>
  Number.isFinite(location.latitude) &&
  Number.isFinite(location.longitude) &&
  Math.abs(location.latitude) <= 90 &&
  Math.abs(location.longitude) <= 180;
export function byUnit(rows) {
  return [...new Set(rows.map((row) => row.unit))]
    .sort()
    .map((unit) => ({ unit, rows: rows.filter((row) => row.unit === unit) }));
}
