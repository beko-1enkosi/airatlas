import { useEffect, useState } from "react";

const base = (
  import.meta.env?.VITE_API_BASE_URL || "http://localhost:8000"
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

export async function askAir(payload, { signal } = {}) {
  const response = await fetch(`${base}/api/ask-air`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    signal,
  });
  let data = {};
  try {
    data = await response.json();
  } catch {
    // A friendly fallback below handles non-JSON upstream/proxy responses.
  }
  if (!response.ok) {
    const message =
      typeof data.detail === "string"
        ? data.detail
        : "Ask Air could not answer just now. Please try again.";
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  if (typeof data.answer !== "string" || !data.answer.trim())
    throw new Error("Ask Air returned an incomplete answer. Please try again.");
  return { answer: data.answer.trim() };
}
