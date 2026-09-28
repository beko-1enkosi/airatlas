import test from "node:test";
import assert from "node:assert/strict";
import {
  byUnit,
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
test("timestamp display uses UTC explicitly", () => {
  assert.match(timestamp("2026-09-01T12:00:00+02:00"), /10:00 UTC$/);
  assert.equal(pollutant("pm25"), "PM2.5");
  assert.equal(pollutant("pm10"), "PM10");
});
