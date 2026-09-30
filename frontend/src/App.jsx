import { useEffect, useState } from "react";
import Dashboard from "./pages/Dashboard.jsx";
import { SocialIcon } from "./components/SocialIcon.jsx";
import { WindMark } from "./components/Brand.jsx";

const navigation = [
  ["overview", "Overview"],
  ["locations", "Locations"],
  ["trends", "Trends"],
  ["data-health", "Data Health"],
];
const contacts = [
  ["gmail", "Gmail", "mailto:t2bnkosi@gmail.com"],
  ["facebook", "Facebook", "https://facebook.com/thobeka.nkosi.355"],
  [
    "instagram",
    "Instagram",
    "https://www.instagram.com/bekolenkosi_?stkn=aXhnY2FIZTc5aDgy%utm_source=qr",
  ],
  ["linkedin", "LinkedIn", "https://linkedin.com/in/thobeka-nkosi-217640293"],
];

export default function App() {
  const [active, setActive] = useState("overview");
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 40);
    update();
    window.addEventListener("scroll", update, { passive: true });
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries)
          if (entry.isIntersecting) setActive(entry.target.id);
      },
      { rootMargin: "-20% 0px -55% 0px" },
    );
    navigation.forEach(([id]) => {
      const section = document.getElementById(id);
      if (section) observer.observe(section);
    });
    // Retain old dashboard bookmarks while making all navigation in-page.
    const old = window.location.hash.match(
      /^#\/(overview|locations|trends|health)$/,
    );
    if (old)
      window.location.replace(
        `#${old[1] === "health" ? "data-health" : old[1]}`,
      );
    const target = document.getElementById(window.location.hash.slice(1));
    if (target)
      requestAnimationFrame(() =>
        target.scrollIntoView({ behavior: "instant" }),
      );
    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", update);
    };
  }, []);
  return (
    <>
      <a className="skip-link" href="#overview">
        Skip to observations
      </a>
      <header className={`topbar ${scrolled ? "scrolled" : ""}`}>
        <div className="nav-inner">
          <a href="#top" className="brand" aria-label="AirAtlas home">
            <WindMark />
            <span>
              AirAtlas<span className="brand-dot">.</span>
            </span>
          </a>
          <nav aria-label="Main navigation">
            {navigation.map(([id, label]) => (
              <a
                key={id}
                href={`#${id}`}
                aria-current={active === id ? "location" : undefined}
              >
                {label}
              </a>
            ))}
          </nav>
          <a
            className="github-link"
            href="https://github.com/beko-1enkosi/airatlas"
            target="_blank"
            rel="noreferrer"
            aria-label="AirAtlas on GitHub"
          >
            <SocialIcon name="github" />
          </a>
        </div>
      </header>
      <main id="main">
        <section className="hero" id="top" aria-label="AirAtlas cloud artwork">
          <img
            src="/airatlas-cloud-robot.png"
            alt="A white robot with a laptop floats among soft blue and pink clouds."
            fetchPriority="high"
            width="1672"
            height="941"
          />
          <div className="hero-copy">
            <p className="eyebrow">South Africa / A little perspective</p>
            <h1>
              The air around us.
              <br />
              <span>A story in data.</span>
            </h1>
            <p>
              Look closer at South Africa's air. Explore real monitoring
              stations, follow the observations, and discover the weather
              alongside them.
            </p>
          </div>
          <a
            className="scroll-cue"
            href="#overview"
            aria-label="Explore the observations"
          >
            <span>Explore below</span>
            <span aria-hidden="true">&#8595;</span>
          </a>
        </section>
        <Dashboard />
      </main>
      <footer className="footer">
        <div className="footer-top">
          <div className="footer-intro">
            <a href="#top" className="brand">
              <WindMark />
              <span>AirAtlas.</span>
            </a>
            <p>
              AirAtlas is an end-to-end environmental data engineering platform
              using public air-quality and weather data.
            </p>
            <span className="footer-tag">
              A clearer view of the air we share.
            </span>
          </div>
          <div>
            <h2>Explore</h2>
            {navigation.map(([id, label]) => (
              <a key={id} href={`#${id}`}>
                {label}
              </a>
            ))}
          </div>
          <div>
            <h2>Public data. Shared knowledge.</h2>
            <a href="https://openaq.org/" target="_blank" rel="noreferrer">
              OpenAQ &#8599;
            </a>
            <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">
              Open-Meteo &#8599;
            </a>
            <a
              href="https://github.com/beko-1enkosi/airatlas"
              target="_blank"
              rel="noreferrer"
            >
              GitHub &#8599;
            </a>
          </div>
          <div>
            <h2>Get in touch</h2>
            <div className="contact-links">
              {contacts.map(([icon, label, href]) => (
                <a
                  key={icon}
                  href={href}
                  target={icon === "gmail" ? undefined : "_blank"}
                  rel={icon === "gmail" ? undefined : "noreferrer"}
                >
                  <SocialIcon name={icon} />
                  <span>{label}</span>
                  <span aria-hidden="true">&#8599;</span>
                </a>
              ))}
            </div>
            <p>
              Built as an end-to-end Data Engineering project in South Africa.
            </p>
          </div>
        </div>
        <div className="footer-bottom">
          <span>AirAtlas &middot; Environmental observations</span>
          <span>Times displayed in SAST &middot; UTC at source</span>
          <a href="#top">Back to the clouds &#8593;</a>
        </div>
      </footer>
    </>
  );
}
