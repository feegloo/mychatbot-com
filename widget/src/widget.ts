import type { ChatRAGOptions } from "./types";

const PREFIX = "[chatrag-widget]";
const DEFAULT_HOST = "https://chatrag.app";

/** Inject the widget CSS into the document head */
function injectStyles(zIndex: number, position: "bottom-right" | "bottom-left"): void {
  if (document.getElementById("chatrag-widget-styles")) return;

  const isRight = position === "bottom-right";
  const style = document.createElement("style");
  style.id = "chatrag-widget-styles";
  style.textContent = `
    #chatrag-widget-container {
      position: fixed;
      bottom: 20px;
      ${isRight ? "right: 20px" : "left: 20px"};
      z-index: ${zIndex};
      font-family: system-ui, -apple-system, sans-serif;
    }

    #chatrag-widget-bubble {
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: #7c3aed;
      color: #fff;
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 16px rgba(0,0,0,0.2);
      transition: transform 0.2s, background 0.2s;
    }
    #chatrag-widget-bubble:hover {
      transform: scale(1.08);
      background: #6d28d9;
    }
    #chatrag-widget-bubble.chatrag-open {
      transform: scale(0.9);
    }
    #chatrag-widget-bubble svg {
      width: 24px;
      height: 24px;
    }

    #chatrag-widget-label {
      position: absolute;
      bottom: 64px;
      ${isRight ? "right: 0" : "left: 0"};
      background: #1e1b2e;
      color: #e2e8f0;
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 13px;
      white-space: nowrap;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
      pointer-events: none;
      opacity: 0;
      transition: opacity 0.2s;
    }
    #chatrag-widget-bubble:hover + #chatrag-widget-label {
      opacity: 1;
    }

    #chatrag-widget-window {
      display: none;
      position: absolute;
      bottom: 70px;
      ${isRight ? "right: 0" : "left: 0"};
      width: 380px;
      height: 560px;
      max-height: calc(100vh - 100px);
      max-width: calc(100vw - 40px);
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 8px 32px rgba(0,0,0,0.3);
      border: 1px solid rgba(255,255,255,0.08);
      background: #0b0f1a;
    }
    #chatrag-widget-window.chatrag-open {
      display: block;
    }

    #chatrag-widget-iframe {
      width: 100%;
      height: 100%;
      border: none;
      background: #0b0f1a;
    }

    @media (max-width: 480px) {
      #chatrag-widget-window {
        width: calc(100vw - 16px);
        height: calc(100vh - 100px);
        bottom: 70px;
        ${isRight ? "right: -12px" : "left: -12px"};
        border-radius: 12px;
      }
    }
  `;
  document.head.appendChild(style);
}

/** Create the chat icon SVG */
function chatIconSvg(): string {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;
}

/** Create the close icon SVG */
function closeIconSvg(): string {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
}

/**
 * Validate conversation ID format. Must be a non-empty alphanumeric string.
 */
function isValidConversationId(id: unknown): id is string {
  if (typeof id !== "string") return false;
  if (id.trim().length === 0) return false;
  // Allow alphanumeric, hyphens, underscores (typical ID characters)
  return /^[a-zA-Z0-9_-]+$/.test(id);
}

export class ChatRAGWidget {
  private container: HTMLElement | null = null;
  private iframe: HTMLIFrameElement | null = null;
  private isOpen = false;
  private options: Required<Pick<ChatRAGOptions, "conversationId" | "host" | "position" | "buttonLabel" | "zIndex">> & ChatRAGOptions;
  private destroyed = false;
  private messageHandler: ((event: MessageEvent) => void) | null = null;

  constructor(options: ChatRAGOptions) {
    // Validate required options
    if (!options || typeof options !== "object") {
      this.fatal("ChatRAG.init() requires an options object with a conversationId.");
      this.options = null as any;
      return;
    }

    if (!isValidConversationId(options.conversationId)) {
      this.fatal(
        `Invalid conversationId: "${options.conversationId}". ` +
        `Please provide a valid conversation ID from chatrag.app.`
      );
      this.options = null as any;
      return;
    }

    this.options = {
      host: DEFAULT_HOST,
      position: "bottom-right",
      buttonLabel: "Chat",
      open: false,
      zIndex: 99999,
      ...options,
    };

    // Normalize host — strip trailing slash
    this.options.host = this.options.host.replace(/\/+$/, "");

    this.mount();
  }

  private fatal(message: string): void {
    console.error(`${PREFIX} ${message}`);
    this.options?.onError?.(message);
  }

  private mount(): void {
    if (this.destroyed || !this.options) return;

    // Prevent duplicate mounts
    if (document.getElementById("chatrag-widget-container")) {
      console.warn(`${PREFIX} Widget is already mounted. Call destroy() first to re-initialize.`);
      return;
    }

    injectStyles(this.options.zIndex, this.options.position);

    // Container
    this.container = document.createElement("div");
    this.container.id = "chatrag-widget-container";

    // Bubble button
    const bubble = document.createElement("button");
    bubble.id = "chatrag-widget-bubble";
    bubble.setAttribute("aria-label", this.options.buttonLabel);
    bubble.innerHTML = chatIconSvg();
    bubble.addEventListener("click", () => this.toggle());

    // Tooltip label
    const label = document.createElement("div");
    label.id = "chatrag-widget-label";
    label.textContent = this.options.buttonLabel;

    // Chat window
    const chatWindow = document.createElement("div");
    chatWindow.id = "chatrag-widget-window";

    // Iframe
    const embedUrl = `${this.options.host}/embed/${encodeURIComponent(this.options.conversationId)}`;
    this.iframe = document.createElement("iframe");
    this.iframe.id = "chatrag-widget-iframe";
    this.iframe.src = embedUrl;
    this.iframe.setAttribute("title", "ChatRAG Chat Widget");
    this.iframe.setAttribute("allow", "clipboard-write");
    this.iframe.setAttribute("loading", "lazy");

    chatWindow.appendChild(this.iframe);
    this.container.appendChild(chatWindow);
    this.container.appendChild(bubble);
    this.container.appendChild(label);

    document.body.appendChild(this.container);

    // Listen for postMessage from iframe
    this.messageHandler = (event: MessageEvent) => {
      if (!event.data || event.data.source !== "chatrag-embed") return;
      if (event.data.conversationId !== this.options.conversationId) return;

      if (event.data.type === "ready") {
        console.info(`${PREFIX} Conversation "${this.options.conversationId}" loaded successfully.`);
        this.options.onReady?.();
      } else if (event.data.type === "error") {
        this.fatal(event.data.error || "Unknown embed error");
      }
    };
    window.addEventListener("message", this.messageHandler);

    // Auto-open if configured
    if (this.options.open) {
      this.open();
    }

    console.info(`${PREFIX} Widget initialized for conversation "${this.options.conversationId}".`);
  }

  /** Open the chat window */
  open(): void {
    if (this.destroyed) return;
    this.isOpen = true;
    const win = document.getElementById("chatrag-widget-window");
    const bubble = document.getElementById("chatrag-widget-bubble");
    if (win) win.classList.add("chatrag-open");
    if (bubble) {
      bubble.classList.add("chatrag-open");
      bubble.innerHTML = closeIconSvg();
    }
  }

  /** Close the chat window */
  close(): void {
    if (this.destroyed) return;
    this.isOpen = false;
    const win = document.getElementById("chatrag-widget-window");
    const bubble = document.getElementById("chatrag-widget-bubble");
    if (win) win.classList.remove("chatrag-open");
    if (bubble) {
      bubble.classList.remove("chatrag-open");
      bubble.innerHTML = chatIconSvg();
    }
  }

  /** Toggle the chat window open/closed */
  toggle(): void {
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  }

  /** Remove the widget from the page and clean up */
  destroy(): void {
    this.destroyed = true;
    if (this.messageHandler) {
      window.removeEventListener("message", this.messageHandler);
      this.messageHandler = null;
    }
    if (this.container) {
      this.container.remove();
      this.container = null;
    }
    const styles = document.getElementById("chatrag-widget-styles");
    if (styles) styles.remove();
    this.iframe = null;
    console.info(`${PREFIX} Widget destroyed.`);
  }
}
