import { useEffect } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Tooltip,
  useMap,
} from "react-leaflet";
import { divIcon } from "leaflet";
import { locationName, validCoordinates } from "../services/format.js";

function Bounds({ locations }) {
  const map = useMap();
  const key = locations
    .map((location) => `${location.latitude},${location.longitude}`)
    .join(";");
  useEffect(() => {
    if (locations.length)
      map.fitBounds(
        locations.map((l) => [l.latitude, l.longitude]),
        { padding: [50, 50], maxZoom: 9 },
      );
  }, [map, key]); // Fit when coordinate inputs change, not when a station is selected.
  return null;
}

export default function LocationMap({ locations, selected, onSelect }) {
  const mapped = locations.filter(validCoordinates);
  return (
    <div className="map-wrap">
      <MapContainer
        center={[-29, 25]}
        zoom={5}
        scrollWheelZoom={false}
        className="location-map"
        aria-label="South African monitoring locations"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Bounds locations={mapped} />
        {mapped.map((location) => (
          <Marker
            key={location.location_id}
            position={[location.latitude, location.longitude]}
            title={locationName(location)}
            alt={locationName(location)}
            icon={divIcon({
              className: "station-icon",
              html: `<span class="station-dot ${selected === location.location_id ? "selected" : ""}"></span>`,
              iconSize: [28, 28],
              iconAnchor: [14, 14],
            })}
            eventHandlers={{ click: () => onSelect(location.location_id) }}
          >
            <Tooltip>{locationName(location)}</Tooltip>
          </Marker>
        ))}
      </MapContainer>
      <div className="map-caption">
        <span className="legend-dot" /> Monitoring locations · select a marker
        <span>
          {mapped.length} mapped
          {mapped.length < locations.length
            ? ` · ${locations.length - mapped.length} without coordinates`
            : ""}
        </span>
      </div>
    </div>
  );
}
