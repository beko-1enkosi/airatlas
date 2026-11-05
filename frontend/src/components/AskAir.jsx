import { useEffect, useReducer, useRef } from "react";
import { WindMark } from "./Brand.jsx";
import { AskAirMarkdown } from "./AskAirMarkdown.js";
import { askAir } from "../services/api.js";
import {
  SUGGESTED_PROMPTS,
  askAirReducer,
  conversationHistory,
  createAskAirState,
} from "../services/askAirState.js";

export function AskAir({ section }) {
  const [state, dispatch] = useReducer(
    askAirReducer,
    undefined,
    createAskAirState,
  );
  const launcher = useRef(null);
  const input = useRef(null);
  const messageList = useRef(null);
  const requestController = useRef(null);
  const messageSequence = useRef(0);

  const nextId = (role) => {
    messageSequence.current += 1;
    return `ask-air-${role}-${messageSequence.current}`;
  };

  useEffect(() => {
    if (!state.open) return undefined;
    input.current?.focus();
    const closeOnEscape = (event) => {
      if (event.key === "Escape") {
        dispatch({ type: "close" });
        requestAnimationFrame(() => launcher.current?.focus());
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [state.open]);

  useEffect(() => {
    if (state.open && messageList.current)
      messageList.current.scrollTop = messageList.current.scrollHeight;
  }, [state.messages, state.pending, state.open]);

  useEffect(
    () => () => {
      requestController.current?.abort();
    },
    [],
  );

  const performRequest = async (payload) => {
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    try {
      const response = await askAir(payload, { signal: controller.signal });
      dispatch({
        type: "send-success",
        id: nextId("assistant"),
        answer: response.answer,
      });
    } catch (error) {
      if (controller.signal.aborted) return;
      dispatch({
        type: "send-error",
        message:
          error instanceof Error
            ? error.message
            : "Ask Air could not answer just now. Please try again.",
      });
    } finally {
      if (requestController.current === controller)
        requestController.current = null;
    }
  };

  const submitQuestion = (question) => {
    const cleaned = question.trim();
    if (!cleaned || cleaned.length > 1200 || state.pending) return;
    const payload = {
      question: cleaned,
      section,
      history: conversationHistory(state.messages),
    };
    dispatch({ type: "send-start", id: nextId("user"), payload });
    performRequest(payload);
  };

  const close = () => {
    dispatch({ type: "close" });
    requestAnimationFrame(() => launcher.current?.focus());
  };

  const clear = () => {
    requestController.current?.abort();
    requestController.current = null;
    dispatch({ type: "clear" });
    requestAnimationFrame(() => input.current?.focus());
  };

  const retry = () => {
    if (!state.lastRequest || state.pending) return;
    dispatch({ type: "retry-start" });
    performRequest(state.lastRequest);
  };

  return (
    <>
      {state.open && (
        <section
          id="ask-air-panel"
          className="ask-air-panel"
          role="dialog"
          aria-label="Ask Air assistant"
          aria-modal="false"
        >
          <header className="ask-air-header">
            <span className="ask-air-header-mark" aria-hidden="true">
              <WindMark />
            </span>
            <span className="ask-air-title">
              <strong>Ask Air</strong>
              <small>Your friendly AirAtlas guide</small>
            </span>
            <span className="ask-air-header-actions">
              <button
                type="button"
                className="ask-air-clear"
                onClick={clear}
                disabled={state.messages.length === 1 && !state.error}
                aria-label="Clear conversation"
              >
                Clear
              </button>
              <button
                type="button"
                className="ask-air-close"
                onClick={close}
                aria-label="Close Ask Air"
              >
                <span aria-hidden="true">×</span>
              </button>
            </span>
          </header>

          <div
            className="ask-air-messages"
            ref={messageList}
            role="log"
            aria-live="polite"
            aria-relevant="additions"
          >
            {state.messages.map((message) => (
              <div
                className={`ask-air-message ${message.role}`}
                key={message.id}
              >
                {message.role === "assistant" && (
                  <span className="ask-air-message-mark" aria-hidden="true">
                    <WindMark />
                  </span>
                )}
                <div className="ask-air-message-content">
                  {message.role === "assistant" ? (
                    <AskAirMarkdown>{message.content}</AskAirMarkdown>
                  ) : (
                    <p>{message.content}</p>
                  )}
                </div>
              </div>
            ))}

            {state.messages.length === 1 && !state.pending && (
              <div className="ask-air-suggestions" aria-label="Try a question">
                {SUGGESTED_PROMPTS.map((prompt) => (
                  <button
                    type="button"
                    key={prompt}
                    onClick={() => submitQuestion(prompt)}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            )}

            {state.pending && (
              <div className="ask-air-typing" role="status">
                <span className="sr-only">Ask Air is thinking</span>
                <span aria-hidden="true" />
                <span aria-hidden="true" />
                <span aria-hidden="true" />
              </div>
            )}

            {state.error && (
              <div className="ask-air-error" role="alert">
                <p>{state.error}</p>
                <button type="button" onClick={retry} disabled={state.pending}>
                  Try again
                </button>
              </div>
            )}
          </div>

          <form
            className="ask-air-composer"
            onSubmit={(event) => {
              event.preventDefault();
              submitQuestion(state.draft);
            }}
          >
            <label className="sr-only" htmlFor="ask-air-question">
              Ask Air a question
            </label>
            <textarea
              id="ask-air-question"
              ref={input}
              value={state.draft}
              maxLength="1200"
              rows="2"
              placeholder="Ask about the air, stations or data…"
              aria-describedby="ask-air-privacy"
              onChange={(event) =>
                dispatch({ type: "draft", value: event.target.value })
              }
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submitQuestion(state.draft);
                }
              }}
            />
            <button
              type="submit"
              disabled={!state.draft.trim() || state.pending}
              aria-label="Send question"
            >
              <span>Send</span>
              <span aria-hidden="true">↑</span>
            </button>
          </form>
          <p className="ask-air-privacy" id="ask-air-privacy">
            Questions are processed by an external AI provider. Please don&apos;t
            share personal or sensitive information.
          </p>
        </section>
      )}

      <div className="ask-air-launcher-wrap" hidden={state.open}>
        <button
          type="button"
          className="ask-air-launcher"
          ref={launcher}
          onClick={() => dispatch({ type: "open" })}
          aria-expanded={state.open}
          aria-controls="ask-air-panel"
          aria-label="Open Ask Air assistant"
        >
          <span className="ask-air-launcher-label">Ask Air</span>
          <span className="ask-air-launcher-mark" aria-hidden="true">
            <WindMark />
          </span>
        </button>
      </div>
    </>
  );
}
