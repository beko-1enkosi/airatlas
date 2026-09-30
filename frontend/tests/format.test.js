import test from "node:test";
import assert from "node:assert/strict";
import {
  byUnit,
  bucketTimestamp,
  shortDate,
  number,
  pollutant,
  timestamp,
  validCoordinates,
} from "../src/services/format.js";

test("units stay separate without changing pollutant values", () => {
  const rows = [
    { unit: "µg/m³", value: 3 },
    { unit: "mg/m³", value: 1 },
    { unit: "µg/m³", value: -2 },
  ];
  assert.equal(byUnit(rows).length, 2);
  assert.deepEqual(
    byUnit(rows)
      .find((group) => group.unit === "µg/m³")
      .rows.map((row) => row.value),
    [3, -2],
  );
});
test("missing weather is not rendered as zero", () => {
  assert.equal(number(null), "—");
  assert.equal(number(0), "0");
});
test("map requires valid numeric coordinate pairs", () => {
  assert.equal(validCoordinates({ latitude: null, longitude: 28 }), false);
  assert.equal(validCoordinates({ latitude: -26, longitude: null }), false);
  assert.equal(validCoordinates({ latitude: 91, longitude: 28 }), false);
  assert.equal(validCoordinates({ latitude: -26, longitude: 28 }), true);
});
test("timestamp display uses SAST explicitly", () => {
  assert.match(timestamp("2026-09-01T12:00:00+02:00"), /12:00 SAST$/);
  assert.equal(pollutant("pm25"), "PM2.5");
  assert.equal(pollutant("pm10"), "PM10");
});

test("SAST display rolls over the UTC date without mutating the source", () => {
  const source = "2026-09-29T23:53:00Z";
  assert.equal(timestamp(source), "30 Sept 2026, 01:53 SAST");
  assert.equal(source, "2026-09-29T23:53:00Z");
  assert.equal(timestamp(null), "Not available");
  assert.equal(timestamp("invalid"), "Not available");
});
test("daily UTC buckets show their actual SAST start, not a fabricated local aggregate", () => {
  assert.equal(bucketTimestamp("2026-09-15"), "15 Sept 2026, 02:00 SAST");
  assert.equal(shortDate("2026-09-15"), "15 Sept");
});
