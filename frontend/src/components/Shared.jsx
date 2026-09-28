import { number, pollutant, timestamp } from "../services/format.js";

export function State({
  resource,
  children,
  empty = false,
  message = "No observations available yet.",
}) {
  if (resource.loading)
    return (
      <div className="state loading" role="status">
        <span className="loading-line" />
        <span>Loading observations…</span>
      </div>
    );
  if (resource.error)
    return (
      <div className="state" role="alert">
        <strong>Data is temporarily unavailable</strong>
        <p>{resource.error}</p>
        <button className="button" onClick={resource.retry}>
          Try again
        </button>
      </div>
    );
  if (empty)
    return (
      <div className="state">
        <span className="empty-symbol" aria-hidden="true">
          ○
        </span>
        <p>{message}</p>
      </div>
    );
  return children;
}

export function PageHeading({ eyebrow, title, children, updated }) {
  return (
    <header className="page-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="subtitle">{children}</p>
      </div>
      {updated && (
        <div className="updated">
          <span>Latest observation</span>
          <strong>{timestamp(updated)}</strong>
        </div>
      )}
    </header>
  );
}

export function SectionHeading({ eyebrow, title, children }) {
  return (
    <div className="section-heading">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h2>{title}</h2>
      </div>
      {children}
    </div>
  );
}

export function Metrics({ resource }) {
  return (
    <State resource={resource}>
      <div className="metrics">
        <article className="metric">
          <span>Monitored locations</span>
          <strong>{number(resource.data?.monitored_locations)}</strong>
          <small>Represented in the warehouse</small>
        </article>
        {["pm25", "pm10"].map((parameter) => (
          <article className="metric" key={parameter}>
            <span>Average {pollutant(parameter)}</span>
            {resource.data?.averages.filter(
              (row) => row.parameter === parameter,
            ).length ? (
              resource.data.averages
                .filter((row) => row.parameter === parameter)
                .map((row) => (
                  <strong key={row.unit}>
                    {number(row.average_value)} <em>{row.unit}</em>
                  </strong>
                ))
            ) : (
              <strong>—</strong>
            )}
            <small>Observation-weighted · all stored dates</small>
          </article>
        ))}
        <article className="metric accent">
          <span>Weather coverage</span>
          <strong>
            {number(resource.data?.weather_coverage)}
            <em>{resource.data?.weather_coverage != null ? "%" : ""}</em>
          </strong>
          <small>Observations with weather context</small>
        </article>
      </div>
    </State>
  );
}

export function PollutantTabs({ value, onChange }) {
  return (
    <div className="segmented" role="group" aria-label="Pollutant">
      {["pm25", "pm10"].map((item) => (
        <button
          key={item}
          aria-pressed={item === value}
          onClick={() => onChange(item)}
        >
          {pollutant(item)}
        </button>
      ))}
    </div>
  );
}

export function PipelineCard({ resource, full = false }) {
  const run = resource.data?.latest_run;
  return (
    <State resource={resource}>
      <div className={`pipeline-card ${full ? "full" : ""}`}>
        <div>
          <p className="eyebrow">Pipeline status</p>
          <h3>
            {run ? (
              <span className={`status ${run.status}`}>{run.status}</span>
            ) : (
              "No pipeline runs yet"
            )}
          </h3>
          <p className="muted">
            {run
              ? timestamp(run.started_at)
              : "Audit history will appear after the first pipeline run."}
          </p>
        </div>
        {run && (
          <dl className="run-details">
            <div>
              <dt>Run mode</dt>
              <dd>{run.run_mode}</dd>
            </div>
            <div>
              <dt>Observations loaded</dt>
              <dd>{number(run.observations_loaded)}</dd>
            </div>
            <div>
              <dt>
                {run.failed_stage ? "Failed stage" : "Current / last stage"}
              </dt>
              <dd>{run.failed_stage || run.current_stage}</dd>
            </div>
            {full && (
              <>
                <div>
                  <dt>Requested start</dt>
                  <dd>{timestamp(run.requested_start)}</dd>
                </div>
                <div>
                  <dt>Requested end</dt>
                  <dd>{timestamp(run.requested_end)}</dd>
                </div>
                <div>
                  <dt>Finished</dt>
                  <dd>{timestamp(run.finished_at)}</dd>
                </div>
                <div>
                  <dt>Location filter</dt>
                  <dd>{run.location_id ?? "All configured locations"}</dd>
                </div>
                <div>
                  <dt>Run ID</dt>
                  <dd>{run.run_id}</dd>
                </div>
              </>
            )}
          </dl>
        )}
        {!full && (
          <a className="text-link" href="#/health">
            View data health <span aria-hidden="true">↗</span>
          </a>
        )}
      </div>
    </State>
  );
}
