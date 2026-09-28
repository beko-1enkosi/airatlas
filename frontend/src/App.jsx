import { useEffect, useState } from "react";
import Dashboard from "./pages/Dashboard.jsx";

const pages = {
  overview: "Overview",
  locations: "Locations",
  trends: "Trends",
  health: "Data Health",
};
const currentPage = () => window.location.hash.replace("#/", "") || "overview";

export default function App() {
  const [page, setPage] = useState(currentPage);
  useEffect(() => {
    const navigate = () => {
      setPage(currentPage());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", navigate);
    return () => window.removeEventListener("hashchange", navigate);
  }, []);
  useEffect(() => {
    document.title = `${pages[page] || "Page not found"} · AirAtlas`;
  }, [page]);
  return (
    <>
      <a
        className="skip-link"
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main").focus();
        }}
      >
        Skip to content
      </a>
      <header className="topbar">
        <div className="nav-inner">
          <a href="#/overview" className="brand" aria-label="AirAtlas overview">
            <svg viewBox="0 0 40 40" width="38" height="38" aria-hidden="true">
              <rect width="40" height="40" rx="12" fill="#356267" />
              <path
                d="M10 26 20 11l10 15M14 21h12M10 30c7-4 13 4 20 0"
                fill="none"
                stroke="#c2f2f2"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span>
              AirAtlas<span className="brand-dot">.</span>
            </span>
          </a>
          <nav aria-label="Main navigation">
            {Object.entries(pages).map(([key, title]) => (
              <a
                key={key}
                href={`#/${key}`}
                aria-current={page === key ? "page" : undefined}
              >
                {title}
              </a>
            ))}
          </nav>
          <span className="nav-caption">A clearer view.</span>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="shell">
        {pages[page] ? (
          <Dashboard page={page} />
        ) : (
          <section className="state">
            <h1>Page not found</h1>
            <a href="#/overview">Return to Overview</a>
          </section>
        )}
      </main>
      <footer className="footer">
        <a href="#/overview" className="footer-brand">
          AirAtlas.
        </a>
        <p>Environmental observations, thoughtfully connected.</p>
        <span>OpenAQ + Open-Meteo · All times UTC</span>
      </footer>
    </>
  );
}
