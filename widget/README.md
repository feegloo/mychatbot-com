# chatrag-widget

Embed a [ChatRAG.app](https://chatrag.app) chatbot on any website with a single line of code.

Pre-configure your chatbot by uploading documents (PDFs, text files, images) at [chatrag.app](https://chatrag.app), then embed it anywhere so your users can ask questions and get AI-powered answers.

---

## Quick Start

### Option 1: Script Tag (Easiest)

Add this to your HTML — no build tools needed:

```html
<script src="https://unpkg.com/chatrag-widget"></script>
<script>
  ChatRAG.init({ conversationId: 'YOUR_CONVERSATION_ID' });
</script>
```

That's it. A chat bubble appears in the bottom-right corner of your page.

### Option 2: NPM Package

```bash
npm install chatrag-widget
```

```js
import { ChatRAG } from 'chatrag-widget';

ChatRAG.init({ conversationId: 'YOUR_CONVERSATION_ID' });
```

### Option 3: iframe (Direct Embed)

Embed the chat directly without the floating widget:

```html
<iframe
  src="https://chatrag.app/embed/YOUR_CONVERSATION_ID"
  width="400"
  height="600"
  style="border: none; border-radius: 12px;"
  title="ChatRAG Chatbot"
  allow="clipboard-write"
></iframe>
```

---

## Getting Your Conversation ID

1. Go to [chatrag.app](https://chatrag.app)
2. Upload your documents (PDFs, text files, images)
3. Wait for processing to complete
4. Copy the conversation ID from the URL: `https://chatrag.app/c/YOUR_CONVERSATION_ID`

For example, if your URL is `https://chatrag.app/c/NGYWXPoSMBSjY69f`, your conversation ID is `NGYWXPoSMBSjY69f`.

---

## Configuration Options

| Option           | Type       | Default            | Description                                        |
|------------------|------------|--------------------|----------------------------------------------------|
| `conversationId` | `string`   | **(required)**     | The conversation ID from chatrag.app               |
| `host`           | `string`   | `https://chatrag.app` | Custom host URL (for self-hosted instances)     |
| `position`       | `string`   | `"bottom-right"`   | Widget position: `"bottom-right"` or `"bottom-left"` |
| `buttonLabel`    | `string`   | `"Chat"`           | Tooltip text shown on hover                        |
| `open`           | `boolean`  | `false`            | Whether the chat window starts open                |
| `zIndex`         | `number`   | `99999`            | CSS z-index for the widget                         |
| `onReady`        | `function` | —                  | Callback when the conversation loads successfully  |
| `onError`        | `function` | —                  | Callback when an error occurs                      |

### Example with all options

```html
<script src="https://unpkg.com/chatrag-widget"></script>
<script>
  ChatRAG.init({
    conversationId: 'NGYWXPoSMBSjY69f',
    position: 'bottom-left',
    buttonLabel: 'Ask about our products',
    open: true,
    onReady: function () {
      console.log('Chatbot is ready!');
    },
    onError: function (error) {
      console.error('Chatbot error:', error);
    }
  });
</script>
```

---

## API Methods

After initialization, you can control the widget programmatically:

```js
// Initialize
const widget = ChatRAG.init({ conversationId: 'YOUR_ID' });

// Open the chat window
ChatRAG.open();

// Close the chat window
ChatRAG.close();

// Toggle open/closed
ChatRAG.toggle();

// Remove the widget entirely
ChatRAG.destroy();
```

---

## Embedding Methods in Detail

### Method 1: Floating Widget (Script Tag)

Best for: adding a chat assistant to an existing website (like a support bot).

```html
<!DOCTYPE html>
<html>
<head>
  <title>My Website</title>
</head>
<body>
  <h1>Welcome to our store</h1>
  <p>Your website content here...</p>

  <!-- Add before closing body tag -->
  <script src="https://unpkg.com/chatrag-widget"></script>
  <script>
    ChatRAG.init({ conversationId: 'YOUR_CONVERSATION_ID' });
  </script>
</body>
</html>
```

### Method 2: Floating Widget (ES Module)

Best for: JavaScript apps built with frameworks (React, Vue, Angular, etc.).

```js
// Install: npm install chatrag-widget
import { ChatRAG } from 'chatrag-widget';

// Initialize once (e.g., in your app's entry point)
ChatRAG.init({ conversationId: 'YOUR_CONVERSATION_ID' });
```

**React example:**

```jsx
import { useEffect } from 'react';
import { ChatRAG } from 'chatrag-widget';

function App() {
  useEffect(() => {
    ChatRAG.init({ conversationId: 'YOUR_CONVERSATION_ID' });
    return () => ChatRAG.destroy();
  }, []);

  return <div>My App</div>;
}
```

**Vue example:**

```vue
<script setup>
import { onMounted, onUnmounted } from 'vue';
import { ChatRAG } from 'chatrag-widget';

onMounted(() => {
  ChatRAG.init({ conversationId: 'YOUR_CONVERSATION_ID' });
});
onUnmounted(() => {
  ChatRAG.destroy();
});
</script>
```

### Method 3: Inline iframe

Best for: embedding the chat directly within a page layout (e.g., a product support section).

```html
<div style="width: 400px; height: 600px; margin: 0 auto;">
  <iframe
    src="https://chatrag.app/embed/YOUR_CONVERSATION_ID"
    width="100%"
    height="100%"
    style="border: none; border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.1);"
    title="Product Support Chat"
    allow="clipboard-write"
  ></iframe>
</div>
```

### Method 4: Full-page iframe

Best for: a dedicated support/FAQ page.

```html
<iframe
  src="https://chatrag.app/embed/YOUR_CONVERSATION_ID"
  style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; border: none;"
  title="Support Chat"
  allow="clipboard-write"
></iframe>
```

---

## Self-Hosted Instances

If you run your own ChatRAG instance, set the `host` option:

```js
ChatRAG.init({
  conversationId: 'YOUR_CONVERSATION_ID',
  host: 'https://your-chatrag-instance.com'
});
```

For iframe:

```html
<iframe src="https://your-chatrag-instance.com/embed/YOUR_CONVERSATION_ID" ...></iframe>
```

---

## Error Handling

The widget provides detailed error logging in the browser console. All messages are prefixed with `[chatrag-widget]`.

| Scenario                    | Console output                                                  |
|-----------------------------|-----------------------------------------------------------------|
| Missing conversation ID     | `[chatrag-widget] ChatRAG.init() requires an options object...` |
| Invalid conversation ID     | `[chatrag-widget] Invalid conversationId: "..."`                |
| Conversation not found (404)| `[chatrag-widget] Conversation "..." not found.`                |
| Access denied (403)         | `[chatrag-widget] Access denied.`                               |
| Network/server error        | `[chatrag-widget] Failed to load conversation: ...`             |

Use the `onError` callback to handle errors in your application:

```js
ChatRAG.init({
  conversationId: 'YOUR_CONVERSATION_ID',
  onError: function (error) {
    // Hide the widget, show a fallback, or log to your analytics
    console.error('Chat failed:', error);
    ChatRAG.destroy();
  }
});
```

---

## Browser Support

Works in all modern browsers: Chrome, Firefox, Safari, Edge (latest 2 versions).

---

## How It Works

1. The widget script creates a small floating button on your page
2. When clicked, it opens an iframe pointing to `chatrag.app/embed/{conversationId}`
3. The iframe loads a streamlined chat interface connected to your pre-configured conversation
4. Users can ask questions and receive AI-powered answers with source citations
5. The widget communicates with the parent page via `postMessage` for status updates

---

## License

MIT
