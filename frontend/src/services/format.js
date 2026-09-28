export const pollutant = (value) =>
  ({ pm25: "PM2.5", pm10: "PM10" })[value] || value;
export const number = (value) =>
  value == null
    ? "—"
    : new Intl.NumberFormat("en-ZA", { maximumFractionDigits: 1 }).format(
        value,
      );
export const timestamp = (value) =>
  value == null
    ? "Not available"
    : `${new Intl.DateTimeFormat("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "UTC",
      }).format(new Date(value))} UTC`;
export const shortDate = (value) =>
  new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
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
