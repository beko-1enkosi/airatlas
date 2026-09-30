import { useEffect, useRef, useState } from "react";
import { number } from "../services/format.js";

// Animate presentation only; assistive technology receives the final value.
export default function CountUp({ value, integer = false }) {
  const element = useRef(null);
  const [display, setDisplay] = useState(value);
  useEffect(() => {
    if (!Number.isFinite(value)) return;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame;
    let observer;
    const finish = () => {
      cancelAnimationFrame(frame);
      setDisplay(value);
    };
    if (motion.matches) {
      finish();
      return;
    }
    observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        const start = performance.now();
        const tick = (now) => {
          const progress = Math.min((now - start) / 1100, 1);
          setDisplay(value * (1 - (1 - progress) ** 3));
          if (progress < 1) frame = requestAnimationFrame(tick);
        };
        setDisplay(0);
        frame = requestAnimationFrame(tick);
      },
      { threshold: 0.6 },
    );
    observer.observe(element.current);
    motion.addEventListener("change", finish);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      motion.removeEventListener("change", finish);
    };
  }, [value]);
  return (
    <span ref={element} className="count-up">
      <span className="sr-only">{number(value)}</span>
      <span aria-hidden="true">
        {number(
          integer && Number.isFinite(display) ? Math.round(display) : display,
        )}
      </span>
    </span>
  );
}
