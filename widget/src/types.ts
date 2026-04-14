export interface ChatRAGOptions {
  /** Required. The conversation UUID from chatrag.app */
  conversationId: string;

  /** Host URL of the ChatRAG instance (default: "https://chatrag.app") */
  host?: string;

  /** Widget position on the page (default: "bottom-right") */
  position?: "bottom-right" | "bottom-left";

  /** Custom label for the chat button (default: "Chat") */
  buttonLabel?: string;

  /** Whether the widget starts open (default: false) */
  open?: boolean;

  /** Z-index for the widget (default: 99999) */
  zIndex?: number;

  /** Callback when the widget is ready */
  onReady?: () => void;

  /** Callback when an error occurs */
  onError?: (error: string) => void;
}
