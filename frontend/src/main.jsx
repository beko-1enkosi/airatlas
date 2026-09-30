import "@fontsource-variable/manrope";
import "@fontsource-variable/inter";
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "leaflet/dist/leaflet.css";
import "./styles/app.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
