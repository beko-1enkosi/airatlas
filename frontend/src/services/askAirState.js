export const WELCOME_MESSAGE =
  "Hi! I'm Ask Air. ☁️ I can help you understand air quality and explore the AirAtlas data. What would you like to know?";

export const SUGGESTED_PROMPTS = [
  "What does PM2.5 mean?",
  "What's the difference between PM2.5 and PM10?",
  "Which stations are in AirAtlas?",
  "Help me understand the air-quality data.",
  "What does weather coverage mean?",
  "How recent are these observations?",
];

export function createAskAirState() {
  return {
    open: false,
    draft: "",
    messages: [
      { id: "ask-air-welcome", role: "assistant", content: WELCOME_MESSAGE },
    ],
    pending: false,
    error: null,
    lastRequest: null,
  };
}

export function conversationHistory(messages) {
  return messages
    .filter((message) => message.id !== "ask-air-welcome")
    .slice(-6)
    .map(({ role, content }) => ({ role, content: content.slice(0, 600) }));
}

export function askAirReducer(state, action) {
  switch (action.type) {
    case "open":
      return { ...state, open: true };
    case "close":
      return { ...state, open: false };
    case "draft":
      return { ...state, draft: action.value };
    case "send-start":
      return {
        ...state,
        draft: "",
        pending: true,
        error: null,
        lastRequest: action.payload,
        messages: [
          ...state.messages,
          { id: action.id, role: "user", content: action.payload.question },
        ],
      };
    case "retry-start":
      return { ...state, pending: true, error: null };
    case "send-success":
      return {
        ...state,
        pending: false,
        error: null,
        messages: [
          ...state.messages,
          { id: action.id, role: "assistant", content: action.answer },
        ],
      };
    case "send-error":
      return { ...state, pending: false, error: action.message };
    case "clear":
      return { ...createAskAirState(), open: true };
    default:
      return state;
  }
}
