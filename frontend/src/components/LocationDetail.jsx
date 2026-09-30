import { apiPath, useResource } from "../services/api.js";
import {
  locationName,
  number,
  pollutant,
  timestamp,
} from "../services/format.js";
import { State } from "./Shared.jsx";

export default function LocationDetail({ id, recent = false }) {
  const resource = useResource(id ? apiPath(`locations/${id}`) : null);
  const location = resource.data;
  const weather = location?.recent.find((row) => row.has_weather_context);
  return (
    <div className="location-detail">
      <p className="eyebrow">Selected location</p>
      <State
        resource={resource}
        skeleton="detail"
        empty={!location}
        message="Choose a monitoring location to explore its observations."
      >
        {location && (
          <>
            <h2>{locationName(location)}</h2>
            <p className="station-meta">OPENAQ · {location.location_id}</p>
            <div className="latest-values">
              {location.latest.length ? (
                location.latest.map((row) => (
                  <div key={`${row.parameter}-${row.unit}`}>
                    <span>{pollutant(row.parameter)}</span>
                    <strong>
                      {number(row.value)} <small>{row.unit}</small>
                    </strong>
                    <time>{timestamp(row.datetime_to_utc)}</time>
                  </div>
                ))
              ) : (
                <p>No observations for this location.</p>
              )}
            </div>
            <div className="weather-detail">
              <h3>Weather context</h3>
              {weather ? (
                <>
                  <dl>
                    <div>
                      <dt>Temperature</dt>
                      <dd>{number(weather.temperature_2m_c)} °C</dd>
                    </div>
                    <div>
                      <dt>Humidity</dt>
                      <dd>{number(weather.relative_humidity_2m_pct)} %</dd>
                    </div>
                    <div>
                      <dt>Wind speed</dt>
                      <dd>{number(weather.wind_speed_10m_kmh)} km/h</dd>
                    </div>
                  </dl>
                  <small>
                    Most recent matched hour in the last 20 observations
                    <br />
                    {timestamp(weather.weather_hour_utc)}
                  </small>
                </>
              ) : (
                <p className="muted">
                  No weather context in recent observations.
                </p>
              )}
            </div>
            {recent && (
              <details>
                <summary>
                  Recent observations ({location.recent.length})
                </summary>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Period end (SAST)</th>
                        <th>Pollutant</th>
                        <th>Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {location.recent.map((row, index) => (
                        <tr key={index}>
                          <td>{timestamp(row.datetime_to_utc)}</td>
                          <td>{pollutant(row.parameter)}</td>
                          <td>
                            {number(row.value)} {row.unit}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
          </>
        )}
      </State>
    </div>
  );
}
