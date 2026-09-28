import { useEffect, useState } from "react";

const base = (
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
).replace(/\/$/, "");

export function apiPath(path, filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== "" && value != null) params.set(key, String(value));
  });
  return `/api/${path}${params.size ? `?${params}` : ""}`;
}

export function useResource(path) {
  const [state, setState] = useState({
    data: null,
    loading: true,
    error: null,
  });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!path) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    let active = true;
    setState({ data: null, loading: true, error: null });
    fetch(`${base}${path}`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            response.status === 422
              ? "Check your filters. Dates must form a valid range."
              : "We could not reach the data service. Please try again.",
          );
        return response.json();
      })
      .then((data) => {
        if (active) setState({ data, loading: false, error: null });
      })
      .catch((error) => {
        if (active)
          setState({
            data: null,
            loading: false,
            error:
              error.name === "AbortError"
                ? "The data service took too long. Please try again."
                : error instanceof TypeError
                  ? "The data service is unavailable. Please try again."
                  : error.message,
          });
      })
      .finally(() => clearTimeout(timeout));
    return () => {
      active = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [path, attempt]);
  return { ...state, retry: () => setAttempt((value) => value + 1) };
}
