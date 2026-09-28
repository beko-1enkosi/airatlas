import { useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { apiPath, useResource } from "../services/api.js";
import {
  byUnit,
  locationName,
  number,
  pollutant,
  shortDate,
} from "../services/format.js";
import { SectionHeading, State, PollutantTabs } from "./Shared.jsx";

function DataTable({ rows, fields }) {
  return (
    <details className="chart-data">
      <summary>View chart data</summary>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {fields.map(([key, title]) => (
                <th key={key}>{title}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                {fields.map(([key]) => (
                  <td key={key}>
                    {typeof row[key] === "number"
                      ? number(row[key])
                      : (row[key] ?? "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function DailyPlot({
  rows,
  unit,
  value = "average_value",
  name = "Average concentration",
}) {
  return (
    <>
      <div
        className="chart"
        role="img"
        aria-label={`${name} by UTC date in ${unit}. Chart data is available below.`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={rows}
            margin={{ top: 20, right: 20, bottom: 15, left: 4 }}
          >
            <CartesianGrid stroke="#e6eeed" vertical={false} />
            <XAxis
              dataKey="measurement_date_utc"
              tickFormatter={shortDate}
              tickLine={false}
              axisLine={false}
              minTickGap={30}
              tick={{ fontSize: 12 }}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              width={54}
              tick={{ fontSize: 12 }}
            />
            <Tooltip
              labelFormatter={(date) => `${date} · UTC`}
              formatter={(value) => [`${number(value)} ${unit}`, name]}
            />
            <Line
              type="linear"
              dataKey={value}
              stroke="#356267"
              strokeWidth={2.5}
              dot={{ r: 3, fill: "#356267", stroke: "white", strokeWidth: 2 }}
              activeDot={{ r: 6 }}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <DataTable
        rows={rows}
        fields={[
          ["measurement_date_utc", "UTC date"],
          [value, `${name} (${unit})`],
          ["observation_count", "Observations"],
        ]}
      />
    </>
  );
}

export function TrendPanel({
  locations,
  selected,
  onSelect,
  title = "Air quality over time",
}) {
  const [parameter, setParameter] = useState("pm25");
  const [dates, setDates] = useState({ date_from: "", date_to: "" });
  const resource = useResource(
    selected
      ? apiPath("trends", { parameter, location_id: selected, ...dates })
      : null,
  );
  return (
    <section className="card">
      <SectionHeading eyebrow="Daily observations" title={title}>
        <PollutantTabs value={parameter} onChange={setParameter} />
      </SectionHeading>
      <div className="filters">
        <label>
          Location
          <select
            value={selected || ""}
            onChange={(event) => onSelect(Number(event.target.value))}
          >
            <option value="" disabled>
              Select a location
            </option>
            {locations.map((location) => (
              <option key={location.location_id} value={location.location_id}>
                {locationName(location)}
              </option>
            ))}
          </select>
        </label>
        <label>
          From (UTC)
          <input
            type="date"
            value={dates.date_from}
            max={dates.date_to || undefined}
            onChange={(event) =>
              setDates({ ...dates, date_from: event.target.value })
            }
          />
        </label>
        <label>
          To (UTC)
          <input
            type="date"
            value={dates.date_to}
            min={dates.date_from || undefined}
            onChange={(event) =>
              setDates({ ...dates, date_to: event.target.value })
            }
          />
        </label>
        <button
          className="text-button"
          onClick={() => setDates({ date_from: "", date_to: "" })}
        >
          Reset dates
        </button>
      </div>
      <p className="chart-note">
        Daily {pollutant(parameter)} averages · observation-weighted · UTC
        period-end dates. Blank dates use the latest 90 stored days.
      </p>
      <State
        resource={resource}
        empty={!resource.data?.rows.length}
        message="No observations in this range. Choose a location or try different dates."
      >
        {resource.data?.truncated && (
          <p role="status" className="notice">
            Result limit reached. Narrow the date range to see a complete
            series.
          </p>
        )}
        {byUnit(resource.data?.rows || []).map((group) => (
          <div key={group.unit}>
            <p className="unit-label">
              {pollutant(parameter)} · {group.unit}
            </p>
            <DailyPlot {...group} />
          </div>
        ))}
      </State>
    </section>
  );
}

export function ComparisonPanel() {
  const [parameter, setParameter] = useState("pm25");
  const resource = useResource(apiPath("comparison/locations", { parameter }));
  return (
    <section className="card">
      <SectionHeading
        eyebrow="Across the network"
        title="Pollution by location"
      >
        <PollutantTabs value={parameter} onChange={setParameter} />
      </SectionHeading>
      <p className="chart-note">
        Observation-weighted averages across all stored dates.
      </p>
      <State
        resource={resource}
        empty={!resource.data?.length}
        message="Location summaries will appear when observations are available."
      >
        {byUnit(resource.data || []).map(({ unit, rows }) => (
          <div key={unit}>
            <p className="unit-label">
              {pollutant(parameter)} · {unit}
            </p>
            <div
              className="chart"
              role="img"
              aria-label={`Average ${pollutant(parameter)} by location in ${unit}. Chart data follows.`}
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={rows.map((row) => ({
                    ...row,
                    label: locationName(row),
                  }))}
                  layout="vertical"
                  margin={{ left: 2, right: 24, top: 12, bottom: 12 }}
                >
                  <CartesianGrid stroke="#e6eeed" horizontal={false} />
                  <XAxis type="number" axisLine={false} tickLine={false} />
                  <YAxis
                    dataKey="label"
                    type="category"
                    width={115}
                    tick={{ fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    formatter={(value) => [
                      `${number(value)} ${unit}`,
                      "Average",
                    ]}
                  />
                  <Bar
                    dataKey="average_value"
                    fill="#41737c"
                    radius={[0, 5, 5, 0]}
                    maxBarSize={24}
                    isAnimationActive={false}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <DataTable
              rows={rows}
              fields={[
                ["location_name", "Location"],
                ["average_value", `Average (${unit})`],
                ["observation_count", "Observations"],
              ]}
            />
          </div>
        ))}
      </State>
    </section>
  );
}

const weatherMetrics = {
  average_temperature_2m_c: ["Temperature", "°C"],
  average_relative_humidity_2m_pct: ["Relative humidity", "%"],
  average_wind_speed_10m_kmh: ["Wind speed", "km/h"],
  average_precipitation_mm: ["Hourly precipitation", "mm"],
};

export function WeatherPanel({ selected }) {
  const [parameter, setParameter] = useState("pm25");
  const [metric, setMetric] = useState("average_temperature_2m_c");
  const resource = useResource(
    selected
      ? apiPath("weather-context", { parameter, location_id: selected })
      : null,
  );
  const [name, weatherUnit] = weatherMetrics[metric];
  return (
    <section className="card">
      <SectionHeading
        eyebrow="Environmental conditions"
        title="Weather context"
      >
        <PollutantTabs value={parameter} onChange={setParameter} />
      </SectionHeading>
      <p className="chart-note">
        Selected location · latest 90 stored days. Conditions during matched
        observations; context, not causation.
      </p>
      <label className="weather-select">
        Weather variable
        <select
          value={metric}
          onChange={(event) => setMetric(event.target.value)}
        >
          {Object.entries(weatherMetrics).map(([key, [label]]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <State
        resource={resource}
        empty={!resource.data?.rows.length}
        message="No matched weather context for this location and pollutant."
      >
        {resource.data?.truncated && (
          <p className="notice">Showing a limited weather series.</p>
        )}
        {byUnit(resource.data?.rows || []).map(({ unit, rows }) => (
          <div key={unit}>
            <p className="unit-label">
              {pollutant(parameter)} ({unit}) with {name.toLowerCase()} (
              {weatherUnit})
            </p>
            <div
              className="chart"
              role="img"
              aria-label={`Daily pollution and ${name.toLowerCase()} on separately labelled axes. Data below.`}
            >
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={rows}
                  margin={{ left: 0, right: 0, top: 25, bottom: 10 }}
                >
                  <CartesianGrid vertical={false} stroke="#e6eeed" />
                  <XAxis
                    dataKey="measurement_date_utc"
                    tickFormatter={shortDate}
                    minTickGap={40}
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                  />
                  <YAxis
                    yAxisId="pollution"
                    width={50}
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                    label={{
                      value: unit,
                      position: "top",
                      offset: 8,
                    }}
                  />
                  <YAxis
                    yAxisId="weather"
                    orientation="right"
                    width={48}
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                    label={{
                      value: weatherUnit,
                      position: "top",
                      offset: 8,
                    }}
                  />
                  <Tooltip
                    labelFormatter={(date) => `${date} · UTC`}
                    formatter={(value, key) => [
                      `${number(value)} ${key === "Pollution" ? unit : weatherUnit}`,
                      key,
                    ]}
                  />
                  <Line
                    yAxisId="pollution"
                    dataKey="average_pollution_value"
                    name="Pollution"
                    stroke="#356267"
                    strokeWidth={2}
                    dot={{ r: 2 }}
                    isAnimationActive={false}
                  />
                  <Line
                    yAxisId="weather"
                    dataKey={metric}
                    name={name}
                    stroke="#798a60"
                    strokeDasharray="5 4"
                    strokeWidth={2}
                    connectNulls={false}
                    dot={{ r: 2 }}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="chart-note">
              Solid: {pollutant(parameter)} · Dashed: {name}.
              Observation-weighted averages; precipitation is not a daily total.
            </p>
            <DataTable
              rows={rows}
              fields={[
                ["measurement_date_utc", "UTC date"],
                ["average_pollution_value", `Pollution (${unit})`],
                [metric, `${name} (${weatherUnit})`],
              ]}
            />
          </div>
        ))}
      </State>
    </section>
  );
}
