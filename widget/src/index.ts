import type { ChatRAGOptions } from "./types";
import { ChatRAGWidget } from "./widget";

export type { ChatRAGOptions };
export { ChatRAGWidget };

// Singleton instance for the simple init() API
let _instance: ChatRAGWidget | null = null;

/**
 * Initialize the ChatRAG widget on the page.
 *
 * @example
 * // ES module
 * import { ChatRAG } from 'chatrag-widget';
 * ChatRAG.init({ conversationId: 'your-conversation-id' });
 *
 * @example
 * // Script tag (UMD)
 * ChatRAG.init({ conversationId: 'your-conversation-id' });
 */
export const ChatRAG = {
  /**
   * Create and mount the chat widget.
   * If a widget is already mounted, it will be destroyed first.
   */
  init(options: ChatRAGOptions): ChatRAGWidget {
    if (_instance) {
      _instance.destroy();
      _instance = null;
    }
    _instance = new ChatRAGWidget(options);
    return _instance;
  },

  /** Open the chat window */
  open(): void {
    _instance?.open();
  },

  /** Close the chat window */
  close(): void {
    _instance?.close();
  },

  /** Toggle the chat window */
  toggle(): void {
    _instance?.toggle();
  },

  /** Destroy the widget and remove it from the page */
  destroy(): void {
    _instance?.destroy();
    _instance = null;
  },
};

// Auto-attach to window for UMD/script-tag usage
if (typeof window !== "undefined") {
  (window as any).ChatRAG = ChatRAG;
}
