import { createElement } from "react";
import ReactMarkdown from "react-markdown";

export function safeMarkdownUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? value : "";
  } catch {
    return "";
  }
}

function SafeLink({ children, href, node: _node, ...props }) {
  if (!href) return createElement("span", null, children);
  return createElement(
    "a",
    {
      ...props,
      href,
      target: "_blank",
      rel: "noopener noreferrer",
    },
    children,
  );
}

function HiddenImage() {
  return null;
}

const components = {
  a: SafeLink,
  img: HiddenImage,
};

export function AskAirMarkdown({ children }) {
  return createElement(
    ReactMarkdown,
    {
      components,
      skipHtml: true,
      urlTransform: safeMarkdownUrl,
    },
    children,
  );
}
