# Embed ChatRAG on Your Website

This guide explains how to embed a ChatRAG chatbot on any website. Pre-configure your chatbot at [chatrag.app](https://chatrag.app) by uploading documents, then embed it so your users can ask questions and get AI-powered answers with source citations.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Get Your Conversation ID](#get-your-conversation-id)
3. [Embedding Methods](#embedding-methods)
   - [Method 1: Script Tag (Recommended)](#method-1-script-tag-recommended)
   - [Method 2: NPM Package](#method-2-npm-package)
   - [Method 3: iframe (Inline)](#method-3-iframe-inline)
   - [Method 4: iframe (Full Page)](#method-4-iframe-full-page)
4. [Configuration Options](#configuration-options)
5. [Programmatic Control](#programmatic-control)
6. [Framework Examples](#framework-examples)
7. [Self-Hosted Instances](#self-hosted-instances)
8. [Error Handling](#error-handling)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- A conversation created at [chatrag.app](https://chatrag.app) with uploaded documents
- The conversation must be in **"ready"** status (processing complete)
- Your conversation ID (see below)

---

## Get Your Conversation ID

1. Go to [chatrag.app](https://chatrag.app)
2. Upload your files (PDFs, text files, images) — these become the chatbot's knowledge base
3. Wait for processing to complete (you'll see a "ready" status)
4. Copy the conversation ID from the URL bar:

```
https://chatrag.app/c/NGYWXPoSMBSjY69f
                       └──────────────┘
                       This is your conversation ID
```

---

## Embedding Methods

### Method 1: Script Tag (Recommended)

The simplest way. Add two lines before your closing `</body>` tag:

```html
<script src="https://unpkg.com/chatrag-widget"></script>
<script>
  ChatRAG.init({ conversationId: 'YOUR_CONVERSATION_ID' });
</script>
```

A purple chat bubble will appear in the bottom-right corner. Click it to open the chat.

**Full page example:**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>My Website</title>
</head>
<body>
  <h1>Welcome to ACME Corp</h1>
  <p>Your website content here...</p>

  <!-- ChatRAG Widget — add before </body> -->
  <script src="https://unpkg.com/chatrag-widget"></script>
  <script>
    ChatRAG.init({ conversationId: 'NGYWXPoSMBSjY69f' });
  </script>
</body>
</html>
```

### Method 2: NPM Package

For JavaScript/TypeScript apps built with bundlers (Webpack, Vite, etc.):

**Install:**

```bash
npm install chatrag-widget
```

**Use:**

```js
import { ChatRAG } from 'chatrag-widget';

ChatRAG.init({ conversationId: 'YOUR_CONVERSATION_ID' });
```

### Method 3: iframe (Inline)

Embed the chat directly in your page layout — no floating widget, the chat appears where you place it. Good for product pages or support sections.

```html
<iframe
  src="https://chatrag.app/embed/YOUR_CONVERSATION_ID"
  width="400"
  height="600"
  style="border: none; border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.1);"
  title="Product Support Chat"
  allow="clipboard-write"
></iframe>
```

### Method 4: iframe (Full Page)

For a dedicated chat/support page:

```html
<iframe
  src="https://chatrag.app/embed/YOUR_CONVERSATION_ID"
  style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; border: none;"
  title="Support Chat"
  allow="clipboard-write"
></iframe>
```

---

## Configuration Options

Pass these to `ChatRAG.init()`:

| Option           | Type       | Default              | Description                                          |
|------------------|------------|----------------------|------------------------------------------------------|
| `conversationId` | `string`   | **(required)**       | Your conversation ID from chatrag.app                |
| `host`           | `string`   | `https://chatrag.app`| Custom host URL (for self-hosted instances)          |
| `position`       | `string`   | `"bottom-right"`     | `"bottom-right"` or `"bottom-left"`                  |
| `buttonLabel`    | `string`   | `"Chat"`             | Tooltip text on hover over the chat bubble           |
| `open`           | `boolean`  | `false`              | Start with the chat window already open              |
| `zIndex`         | `number`   | `99999`              | CSS z-index for the widget                           |
| `onReady`        | `function` | —                    | Callback when conversation loads successfully        |
| `onError`        | `function` | —                    | Callback when an error occurs (receives error string)|

**Example with options:**

```html
<script src="https://unpkg.com/chatrag-widget"></script>
<script>
  ChatRAG.init({
    conversationId: 'NGYWXPoSMBSjY69f',
    position: 'bottom-left',
    buttonLabel: 'Ask about this product',
    open: true,
    onReady: function () {
      console.log('Chatbot loaded!');
    },
    onError: function (error) {
      console.error('Chatbot error:', error);
    }
  });
</script>
```

---

## Programmatic Control

After calling `ChatRAG.init()`, you can control the widget:

```js
ChatRAG.open();    // Open the chat window
ChatRAG.close();   // Close the chat window
ChatRAG.toggle();  // Toggle open/closed
ChatRAG.destroy(); // Remove the widget from the page
```

Or use the returned instance:

```js
const widget = ChatRAG.init({ conversationId: 'YOUR_ID' });
widget.open();
widget.close();
widget.toggle();
widget.destroy();
```

---

## Framework Examples

### React

```jsx
import { useEffect } from 'react';
import { ChatRAG } from 'chatrag-widget';

function App() {
  useEffect(() => {
    ChatRAG.init({ conversationId: 'YOUR_CONVERSATION_ID' });
    return () => ChatRAG.destroy(); // Cleanup on unmount
  }, []);

  return <div>My App</div>;
}
```

### Vue 3

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

### Angular

```typescript
import { Component, OnInit, OnDestroy } from '@angular/core';
import { ChatRAG } from 'chatrag-widget';

@Component({ selector: 'app-root', template: '<h1>My App</h1>' })
export class AppComponent implements OnInit, OnDestroy {
  ngOnInit() {
    ChatRAG.init({ conversationId: 'YOUR_CONVERSATION_ID' });
  }
  ngOnDestroy() {
    ChatRAG.destroy();
  }
}
```

### Next.js

```jsx
'use client';
import { useEffect } from 'react';

export default function ChatWidget() {
  useEffect(() => {
    import('chatrag-widget').then(({ ChatRAG }) => {
      ChatRAG.init({ conversationId: 'YOUR_CONVERSATION_ID' });
    });
    return () => {
      import('chatrag-widget').then(({ ChatRAG }) => ChatRAG.destroy());
    };
  }, []);

  return null;
}
```

### Static HTML / WordPress / Squarespace / Wix

Use the script tag method. Paste this before `</body>` in your theme's HTML or in a "Custom Code" block:

```html
<script src="https://unpkg.com/chatrag-widget"></script>
<script>
  ChatRAG.init({ conversationId: 'YOUR_CONVERSATION_ID' });
</script>
```

---

## Self-Hosted Instances

If you run your own ChatRAG server, point the widget to your host:

**Script/NPM:**
```js
ChatRAG.init({
  conversationId: 'YOUR_CONVERSATION_ID',
  host: 'https://your-server.example.com'
});
```

**iframe:**
```html
<iframe src="https://your-server.example.com/embed/YOUR_CONVERSATION_ID" ...></iframe>
```

---

## Error Handling

### Console Logging

All widget messages are prefixed with `[chatrag-widget]` in the browser console:

| Scenario                   | Console Message                                                     |
|----------------------------|---------------------------------------------------------------------|
| Widget initialized         | `[chatrag-widget] Widget initialized for conversation "...".`       |
| Conversation loaded        | `[chatrag-widget] Conversation "..." loaded successfully.`          |
| Missing conversation ID    | `[chatrag-widget] ChatRAG.init() requires an options object...`     |
| Invalid conversation ID    | `[chatrag-widget] Invalid conversationId: "..."`                    |
| Conversation not found     | `[chatrag-widget] Conversation "..." not found...`                  |
| Access denied              | `[chatrag-widget] Access denied...`                                 |
| Network error              | `[chatrag-widget] Failed to load conversation: ...`                 |

### Error Callback

```js
ChatRAG.init({
  conversationId: 'YOUR_CONVERSATION_ID',
  onError: function (error) {
    // Log to your analytics
    analytics.track('chatbot_error', { error });

    // Optionally remove the broken widget
    ChatRAG.destroy();

    // Or show a fallback
    document.getElementById('chat-fallback').style.display = 'block';
  }
});
```

### iframe Error Handling

When using the iframe directly, listen for postMessage events:

```html
<iframe id="chatrag" src="https://chatrag.app/embed/YOUR_CONVERSATION_ID" ...></iframe>
<script>
  window.addEventListener('message', function (event) {
    if (event.data && event.data.source === 'chatrag-embed') {
      if (event.data.type === 'ready') {
        console.log('Chat is ready!');
      } else if (event.data.type === 'error') {
        console.error('Chat error:', event.data.error);
      }
    }
  });
</script>
```

---

## Troubleshooting

| Problem                         | Solution                                                              |
|---------------------------------|-----------------------------------------------------------------------|
| Widget doesn't appear           | Check browser console for errors. Verify the script loaded.           |
| "Conversation not found"        | Double-check the conversation ID. Make sure it exists at chatrag.app. |
| Chat shows "Processing..."      | The conversation is still indexing. Wait for it to finish.            |
| Widget hidden behind other elements | Increase the `zIndex` option (e.g., `zIndex: 999999`).          |
| iframe is blank                 | Check that the URL is correct and the server is reachable.            |
| CORS errors in console          | The chatrag.app server allows all origins by default. If self-hosted, ensure CORS is configured. |

---

## Example: IKEA-style Product Support Bot

A company wants to embed a chatbot for a specific product (e.g., a vacuum cleaner).

**Step 1:** Go to [chatrag.app](https://chatrag.app) and upload:
- Product manual (PDF)
- Internal instructions (PDF)
- Product specifications (text file)
- Product image

**Step 2:** Wait for processing to complete.

**Step 3:** Copy the conversation ID from the URL.

**Step 4:** Add to the product page:

```html
<script src="https://unpkg.com/chatrag-widget"></script>
<script>
  ChatRAG.init({
    conversationId: 'abc123xyz',
    buttonLabel: 'Ask about this product',
    position: 'bottom-right'
  });
</script>
```

Now customers visiting the product page can click the chat bubble and ask questions like:
- "How do I replace the filter?"
- "What's the warranty period?"
- "Is this compatible with hardwood floors?"

The chatbot answers using the uploaded documents as its knowledge base, with source citations.
