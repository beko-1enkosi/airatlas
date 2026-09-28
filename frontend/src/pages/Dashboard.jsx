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
  PageHeading,
  PipelineCard,
  SectionHeading,
  State,
} from "../components/Shared.jsx";
import LocationDetail from "../components/LocationDetail.jsx";

const LocationMap = lazy(() => import("../components/LocationMap.jsx"));
const TrendPanel = lazy(() =>
  import("../components/Charts.jsx").then((module) => ({
    default: module.TrendPanel,
  })),
);
const ComparisonPanel = lazy(() =>
  import("../components/Charts.jsx").then((module) => ({
    default: module.ComparisonPanel,
  })),
);
const WeatherPanel = lazy(() =>
  import("../components/Charts.jsx").then((module) => ({
    default: module.WeatherPanel,
  })),
);
const loading = (
  <div className="state" role="status">
    Preparing this view…
  </div>
);

export default function Dashboard({ page }) {
  const summary = useResource(apiPath("summary"));
  const locations = useResource(apiPath("locations"));
  const audit = useResource(apiPath("data-health"));
  const [selection, setSelection] = useState(null);
  const rows = locations.data || [];
  const selected = rows.some((row) => row.location_id === selection)
    ? selection
    : rows[0]?.location_id;
  if (page === "health")
    return (
      <>
        <PageHeading
          eyebrow="Behind the observations"
          title="Data health"
          updated={summary.data?.latest_observation}
        >
          A clear view of the journey from source to insight.
        </PageHeading>
        <section className="card">
          <PipelineCard resource={audit} full />
        </section>
        <div className="health-metrics">
          <article className="card">
            <p className="eyebrow">Environmental context</p>
            <h2>Weather coverage</h2>
            <State resource={summary}>
              <strong className="hero-number">
                {number(summary.data?.weather_coverage)}
                <small>%</small>
              </strong>
              <p className="muted">
                Share of stored air-quality observations with matched weather.
                Missing context stays missing.
              </p>
            </State>
          </article>
          <article className="card">
            <p className="eyebrow">Observation window</p>
            <h2>Data in the warehouse</h2>
            <State resource={summary}>
              <p className="large-value">
                {number(summary.data?.observation_count)} observations
              </p>
              <dl className="window">
                <dt>Earliest observation</dt>
                <dd>{timestamp(summary.data?.earliest_observation)}</dd>
                <dt>Latest observation</dt>
                <dd>{timestamp(summary.data?.latest_observation)}</dd>
              </dl>
            </State>
          </article>
        </div>
        <section className="card">
          <SectionHeading
            eyebrow="The AirAtlas pipeline"
            title="Every observation has a journey"
          />
          <ol className="pipeline-flow">
            {[
              "OpenAQ",
              "Processing",
              "Parquet",
              "Weather",
              "PostgreSQL",
              "dbt",
              "Dashboard",
            ].map((stage, index) => (
              <li key={stage}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{stage}</strong>
              </li>
            ))}
          </ol>
          <p className="chart-note">
            Airflow coordinates the data pipeline. PostgreSQL retains a concise
            run audit; detailed task history and logs remain in Airflow.
          </p>
        </section>
      </>
    );
  return (
    <>
      <PageHeading
        eyebrow="South Africa · Environmental observations"
        title={
          page === "locations"
            ? "Explore the network"
            : page === "trends"
              ? "A closer look at the air"
              : "Air quality, in perspective."
        }
        updated={summary.data?.latest_observation}
      >
        {page === "locations"
          ? "Get to know the monitoring locations behind each observation."
          : page === "trends"
            ? "Follow daily pollutant observations through time and place."
            : "Explore monitoring locations and the environmental conditions around them."}
      </PageHeading>
      {page === "overview" && <Metrics resource={summary} />}
      {(page === "overview" || page === "locations") && (
        <section className="card network-card">
          <SectionHeading
            eyebrow="Monitoring network"
            title="Connected by the air we share"
          >
            <span className="source-tag">OpenAQ · South Africa</span>
          </SectionHeading>
          <State
            resource={locations}
            empty={!rows.length}
            message="No monitoring locations are available yet."
          >
            <div className="map-grid">
              <div>
                <Suspense fallback={loading}>
                  <LocationMap
                    locations={rows}
                    selected={selected}
                    onSelect={setSelection}
                  />
                </Suspense>
                <div
                  className="station-list"
                  aria-label="Select a monitoring location"
                >
                  {rows.map((location) => (
                    <button
                      key={location.location_id}
                      onClick={() => setSelection(location.location_id)}
                      aria-pressed={selected === location.location_id}
                    >
                      {locationName(location)}
                      {!validCoordinates(location) && (
                        <small> · coordinates unavailable</small>
                      )}
                    </button>
                  ))}
                </div>
              </div>
              <LocationDetail id={selected} recent={page === "locations"} />
            </div>
          </State>
        </section>
      )}
      <State resource={locations}>
        <Suspense fallback={loading}>
          <TrendPanel
            locations={rows}
            selected={selected}
            onSelect={setSelection}
          />
        </Suspense>
      </State>
      {page !== "locations" && (
        <Suspense fallback={loading}>
          <div className="chart-grid">
            <ComparisonPanel />
            <WeatherPanel selected={selected} />
          </div>
        </Suspense>
      )}
      {page === "overview" && (
        <section className="card">
          <PipelineCard resource={audit} />
        </section>
      )}
    </>
  );
}
