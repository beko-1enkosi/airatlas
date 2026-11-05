import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  AskAirMarkdown,
  safeMarkdownUrl,
} from "../src/components/AskAirMarkdown.js";
import { askAir, apiPath } from "../src/services/api.js";
import {
  SUGGESTED_PROMPTS,
  askAirReducer,
  conversationHistory,
  createAskAirState,
} from "../src/services/askAirState.js";

test("launcher state opens and closes without losing the conversation", () => {
  const initial = createAskAirState();
  const opened = askAirReducer(initial, { type: "open" });
  const closed = askAirReducer(opened, { type: "close" });
  assert.equal(initial.open, false);
  assert.equal(opened.open, true);
  assert.equal(closed.open, false);
  assert.deepEqual(closed.messages, initial.messages);
});

test("suggested prompts submit a user question and enter loading state", () => {
  const initial = { ...createAskAirState(), open: true };
  const payload = {
    question: SUGGESTED_PROMPTS[0],
    section: "overview",
    history: [],
  };
  const loading = askAirReducer(initial, {
    type: "send-start",
    id: "user-1",
    payload,
  });
  assert.equal(SUGGESTED_PROMPTS.length, 6);
  assert.equal(loading.pending, true);
  assert.equal(loading.draft, "");
  assert.equal(loading.messages.at(-1).content, "What does PM2.5 mean?");
  assert.deepEqual(loading.lastRequest, payload);
});

test("loading, error, retry and success states remain recoverable", () => {
  const payload = { question: "What is PM10?", history: [] };
  let state = askAirReducer(createAskAirState(), {
    type: "send-start",
    id: "user-1",
    payload,
  });
  state = askAirReducer(state, {
    type: "send-error",
    message: "Please try again.",
  });
  assert.equal(state.pending, false);
  assert.equal(state.error, "Please try again.");

  state = askAirReducer(state, { type: "retry-start" });
  assert.equal(state.pending, true);
  assert.equal(state.error, null);
  state = askAirReducer(state, {
    type: "send-success",
    id: "assistant-1",
    answer: "PM10 is made of inhalable particles.",
  });
  assert.equal(state.pending, false);
  assert.equal(state.messages.at(-1).role, "assistant");
});

test("clear resets session-only conversation and history stays bounded", () => {
  const messages = Array.from({ length: 9 }, (_, index) => ({
    id: `message-${index}`,
    role: index % 2 ? "assistant" : "user",
    content: "x".repeat(700),
  }));
  const history = conversationHistory(messages);
  assert.equal(history.length, 6);
  assert.ok(history.every((message) => message.content.length === 600));

  const cleared = askAirReducer(
    { ...createAskAirState(), open: true, messages, error: "error" },
    { type: "clear" },
  );
  assert.equal(cleared.open, true);
  assert.equal(cleared.messages.length, 1);
  assert.equal(cleared.error, null);
});

test("Ask Air API posts JSON while existing API paths remain unchanged", async () => {
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return new Response(JSON.stringify({ answer: "  A clear answer.  " }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    const result = await askAir({ question: "Hello", history: [] });
    assert.deepEqual(result, { answer: "A clear answer." });
    assert.equal(captured.url, "http://localhost:8000/api/ask-air");
    assert.equal(captured.options.method, "POST");
    assert.equal(captured.options.headers["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(captured.options.body), {
      question: "Hello",
      history: [],
    });
    assert.equal(
      apiPath("trends", { parameter: "pm25", date_from: "" }),
      "/api/trends?parameter=pm25",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Ask Air API exposes friendly backend errors", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ detail: "Free limit reached." }), {
      status: 429,
      headers: { "Content-Type": "application/json" },
    });
  try {
    await assert.rejects(
      askAir({ question: "Hello" }),
      /Free limit reached/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

function renderMarkdown(markdown) {
  return renderToStaticMarkup(
    createElement(AskAirMarkdown, null, markdown),
  );
}

test("assistant Markdown renders emphasis, paragraphs and lists", () => {
  const html = renderMarkdown(
    "**PM2.5** is *fine particulate matter*.\n\n- Smaller particles\n- Short explanation\n\n1. Check the date\n2. Check the unit",
  );

  assert.match(html, /<strong>PM2\.5<\/strong>/);
  assert.match(html, /<em>fine particulate matter<\/em>/);
  assert.match(html, /<p>.*<\/p>\s*<ul>/s);
  assert.match(html, /<ul>\s*<li>.*<\/li>\s*<li>.*<\/li>\s*<\/ul>/s);
  assert.match(html, /<ol>\s*<li>.*<\/li>\s*<li>.*<\/li>\s*<\/ol>/s);
});

test("assistant Markdown keeps plain text readable and links safe", () => {
  const html = renderMarkdown(
    "A plain answer with `µg/m³`. [Source](https://example.com/data)",
  );

  assert.match(html, /^<p>A plain answer/);
  assert.match(html, /<code>µg\/m³<\/code>/);
  assert.match(html, /href="https:\/\/example\.com\/data"/);
  assert.match(html, /target="_blank"/);
  assert.match(html, /rel="noopener noreferrer"/);
});

test("assistant Markdown drops raw HTML, images and unsafe links", () => {
  const html = renderMarkdown(
    "Safe <script>alert('no')</script> text. " +
      "[Bad](javascript:alert('no')) ![tracking](https://example.com/pixel.png)",
  );

  assert.doesNotMatch(html, /<script|<img|javascript:/i);
  assert.doesNotMatch(html, /href=/);
  assert.match(html, /<p>Safe .* text\. <span>Bad<\/span> <\/p>/);
  assert.equal(safeMarkdownUrl("data:text/html,unsafe"), "");
  assert.equal(safeMarkdownUrl("/relative/path"), "");
});

test("assistant controls and reduced-motion treatment are present", () => {
  const directory = fileURLToPath(new URL("../src/", import.meta.url));
  const component = readFileSync(`${directory}components/AskAir.jsx`, "utf8");
  const styles = readFileSync(`${directory}styles/app.css`, "utf8");
  assert.match(component, /aria-label="Open Ask Air assistant"/);
  assert.match(component, /aria-label="Close Ask Air"/);
  assert.match(component, /aria-label="Clear conversation"/);
  assert.match(component, /event\.key === "Enter" && !event\.shiftKey/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(styles, /\.ask-air-launcher/);
  assert.match(styles, /\.ask-air-messages\s*{[^}]*overflow-y:\s*auto/s);
  assert.match(styles, /\.ask-air-message\.assistant :is\(ul, ol\)/);
});
