import { lazy, Suspense, useState } from "react";
import { apiPath, useResource } from "../services/api.js";
import {
  locationName,
  number,
  timestamp,
  validCoordinates,
} from "../services/format.js";
import {
  Metrics,
  PipelineCard,
  Skeleton,
  State,
} from "../components/Shared.jsx";
import LocationDetail from "../components/LocationDetail.jsx";
const LocationMap = lazy(() => import("../components/LocationMap.jsx"));
const TrendPanel = lazy(() =>
  import("../components/Charts.jsx").then((m) => ({ default: m.TrendPanel })),
);
const ComparisonPanel = lazy(() =>
  import("../components/Charts.jsx").then((m) => ({
    default: m.ComparisonPanel,
  })),
);
const WeatherPanel = lazy(() =>
  import("../components/Charts.jsx").then((m) => ({ default: m.WeatherPanel })),
);

export default function Dashboard() {
  const summary = useResource(apiPath("summary"));
  const locations = useResource(apiPath("locations"));
  const audit = useResource(apiPath("data-health"));
  const [selection, setSelection] = useState(null);
  const rows = locations.data || [];
  const selected = rows.some((row) => row.location_id === selection)
    ? selection
    : rows[0]?.location_id;
  return (
    <>
      <section
        id="overview"
        className="section overview"
        aria-labelledby="overview-title"
      >
        <div className="section-index">
          <span>01 / A little perspective</span>
          <span>Public data &middot; South Africa</span>
        </div>
        <div className="intro-grid">
          <h2 id="overview-title">
            A clearer picture.
            <br />
            <span>One observation at a time.</span>
          </h2>
          <div>
            <div className="updated">
              <span>Latest observation</span>
              <strong>{timestamp(summary.data?.latest_observation)}</strong>
            </div>
          </div>
        </div>
        <Metrics resource={summary} />
        <State resource={summary} skeleton="summary">
          <div className="observation-strip">
            <span>
              <strong>{number(summary.data?.observation_count)}</strong>{" "}
              observations, connected.
            </span>
            <span>
              {timestamp(summary.data?.earliest_observation)}
              <br />
              to {timestamp(summary.data?.latest_observation)}
            </span>
          </div>
        </State>
      </section>
      <section
        id="locations"
        className="section locations-section"
        aria-labelledby="locations-title"
      >
        <div className="section-index">
          <span>02 / Grounded in place</span>
          <span>Explore the network</span>
        </div>
        <div className="editorial-heading">
          <h2 id="locations-title">
            Different places.
            <br />
            <span>The same sky.</span>
          </h2>
          <p>
            Every point is a real monitoring station. Choose one to see its
            latest observations and environmental context.
          </p>
        </div>
        <State
          resource={locations}
          skeleton="map"
          empty={!rows.length}
          message="No monitoring locations are available yet."
        >
          <div className="map-grid">
            <div className="network-map">
              <Suspense fallback={<Skeleton kind="map" />}>
                <LocationMap
                  locations={rows}
                  selected={selected}
                  onSelect={setSelection}
                />
              </Suspense>
              <div
                className="station-list"
                role="group"
                aria-label="Select a monitoring location"
              >
                {rows.map((location) => (
                  <button
                    key={location.location_id}
                    onClick={() => setSelection(location.location_id)}
                    aria-pressed={selected === location.location_id}
                  >
                    <span className="station-choice-dot" />
                    {locationName(location)}
                    {!validCoordinates(location) && (
                      <small> - coordinates unavailable</small>
                    )}
                  </button>
                ))}
              </div>
            </div>
            <LocationDetail id={selected} recent />
          </div>
        </State>
      </section>
      <section
        id="trends"
        className="section trends-section"
        aria-labelledby="trends-title"
      >
        <div className="section-index">
          <span>03 / Patterns, not predictions</span>
          <span>Follow the observations</span>
        </div>
        <div className="editorial-heading">
          <h2 id="trends-title">
            Give the numbers
            <br />
            <span>a little room.</span>
          </h2>
          <p>
            A day-by-day view of PM2.5 and PM10. Change the station, pollutant,
            or date range to explore what was recorded.
          </p>
        </div>
        <State resource={locations} skeleton="chart">
          <Suspense fallback={<Skeleton kind="chart" />}>
            <TrendPanel
              locations={rows}
              selected={selected}
              onSelect={setSelection}
            />
          </Suspense>
        </State>
      </section>
      <section
        className="section comparison-section"
        aria-label="Location comparison"
      >
        <div className="comparison-intro">
          <p className="eyebrow">04 / Side by side</p>
          <h2>
            A change
            <br />
            of scenery.
          </h2>
          <p>
            Compare the network's recorded averages. Each pollutant and unit
            keeps its own place in the picture.
          </p>
          <span className="editorial-symbol" aria-hidden="true">
            &#8595;
          </span>
        </div>
        <Suspense fallback={<Skeleton kind="chart" />}>
          <ComparisonPanel />
        </Suspense>
      </section>
      <section className="weather-band" aria-label="Weather context">
        <div className="section weather-layout">
          <div className="weather-intro">
            <p className="eyebrow">05 / The bigger picture</p>
            <h2>
              There's more
              <br />
              in the air.
            </h2>
            <p>
              Temperature, humidity, wind, and rain. Environmental conditions
              during matched observations, without assuming cause and effect.
            </p>
            <p className="selected-context">
              Exploring{" "}
              <strong>
                {selected
                  ? locationName(
                      rows.find((r) => r.location_id === selected) || {
                        location_id: selected,
                      },
                    )
                  : "your selected station"}
              </strong>
            </p>
            <a href="#locations" className="text-link">
              Choose a different station &#8599;
            </a>
          </div>
          <Suspense fallback={<Skeleton kind="chart" />}>
            <WeatherPanel selected={selected} />
          </Suspense>
        </div>
      </section>
      <section
        id="data-health"
        className="section health-section"
        aria-labelledby="health-title"
      >
        <div className="section-index">
          <span>06 / Behind the scenes</span>
          <span>From source to screen</span>
        </div>
        <div className="editorial-heading">
          <h2 id="health-title">
            Good data has
            <br />
            <span>a backstory.</span>
          </h2>
          <p>
            Follow the journey behind the observations. Pipeline status and
            coverage, made visible.
          </p>
        </div>
        <ol className="pipeline-flow">
          {[
            "OpenAQ",
            "Processing",
            "Parquet",
            "Weather",
            "PostgreSQL",
            "dbt",
            "Dashboard",
          ].map((stage, i) => (
            <li key={stage}>
              <span>{String(i + 1).padStart(2, "0")}</span>
              <strong>{stage}</strong>
            </li>
          ))}
        </ol>
        <div className="health-grid">
          <div className="card">
            <PipelineCard resource={audit} full />
          </div>
          <aside className="health-aside">
            <p className="eyebrow">Context counts</p>
            <State resource={summary} skeleton="detail">
              <strong className="hero-number">
                {number(summary.data?.weather_coverage)}
                <small>%</small>
              </strong>
              <p>
                of observations have matched weather context. Missing values
                remain missing.
              </p>
              <dl className="window">
                <dt>Observations stored</dt>
                <dd>{number(summary.data?.observation_count)}</dd>
                <dt>Latest observation</dt>
                <dd>{timestamp(summary.data?.latest_observation)}</dd>
              </dl>
            </State>
          </aside>
        </div>
        <p className="chart-note">
          Airflow coordinates the pipeline. A PostgreSQL run audit records the
          outcome; detailed task history and logs stay in Airflow.
        </p>
      </section>
    </>
  );
}
