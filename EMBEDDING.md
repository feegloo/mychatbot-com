# Embedding ChatRAG on Your Website

Embed a live AI chat widget on any page in **one line of HTML**. Visitors get a floating chat circle (bottom-right) that opens a full conversation inside an iframe — no iframe tag, no JavaScript knowledge required.

---

## Prerequisites

You need an existing conversation URL from ChatRAG. It looks like this:

```
https://chatrag.app/c/AYMLu7O0vYgwmK2w
```

The URL must:
- Start with `https://chatrag.app/c/`
- Be followed by the conversation ID

**Invalid URLs that will show a console error and not mount the widget:**
| URL | Why it fails |
|-----|-------------|
| `https://chatrag.app` | Homepage — no conversation |
| `https://chatrag.app/m/abc123` | Shared message link, not a conversation |
| `https://chatrag.app/c/` | Missing conversation ID |
| `http://chatrag.app/c/abc123` | Must use `https://` |

---

## Step 1 — Get a conversation URL

**Option A — Chrome extension (recommended)**
1. Install the [ChatRAG Chrome Extension](#)
2. Open any webpage you want to chat about
3. Click the ChatRAG icon → **"Chat about this page"**
4. Wait for processing, then click **"Copy embed code"** — the snippet is already in your clipboard

**Option B — Manual**
1. Go to [chatrag.app](https://chatrag.app)
2. Upload your PDF, paste a URL, or start a conversation
3. Copy the URL from your browser — e.g. `https://chatrag.app/c/AYMLu7O0vYgwmK2w`

---

## Step 2 — Add one line to your HTML

Paste this before `</body>` in your HTML file:

```html
<script src="https://chatrag.app/embed.js"
        data-conversation="https://chatrag.app/c/AYMLu7O0vYgwmK2w"></script>
```

Replace `AYMLu7O0vYgwmK2w` with your conversation ID.

That's it. The widget is live.

---

## Complete Example

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>My Website</title>
</head>
<body>

  <h1>Welcome to my site</h1>
  <p>Ask our AI assistant anything about our product documentation.</p>

  <!-- ChatRAG embed — chat circle appears bottom-right -->
  <script src="https://chatrag.app/embed.js"
          data-conversation="https://chatrag.app/c/AYMLu7O0vYgwmK2w"></script>

</body>
</html>
```

---

## How it works

| Feature | Detail |
|---------|--------|
| **Position** | Fixed, bottom-right corner — always visible, never overlaps content |
| **Opens** | Click the circle → iframe panel slides up (380 × 580 px) |
| **Closes** | Click the circle again, click ✕, or press `Escape` |
| **User identity** | Each visitor is identified by a browser fingerprint — their conversation history persists across visits |
| **Mobile** | Works on all screen sizes |
| **Zero dependencies** | Pure vanilla JS, no libraries, ~5 KB |

---

## Customisation

The widget uses sensible defaults. If you need to adjust size or position, the script exposes no configuration API by design — the iframe content adapts to its container automatically via ChatRAG's built-in embed mode (`?embed=1`).

For advanced integrations (custom dimensions, custom trigger button), contact us — or fork `embed.js` from the [GitHub repo](#).

---

## Troubleshooting

**Widget does not appear**
- Open browser DevTools → Console and look for a `[ChatRAG]` error message
- Confirm the `data-conversation` URL is a valid `https://chatrag.app/c/...` link
- Confirm the script tag is placed before `</body>`

**"Conversation not found (404)"**
- The conversation URL no longer exists or was deleted
- Create a new conversation and update the embed code

**Iframe shows a blank page**
- This is usually a temporary network issue — reload the page
- Check `https://chatrag.app` is reachable from your network

**Widget appears behind other elements**
- The widget uses `z-index: 2147483647` (maximum). If something still appears on top, that element has an isolated stacking context — check its CSS for `transform`, `isolation: isolate`, or `will-change`

---

## Security & Privacy

- The embed script does **not** set cookies on your domain
- All conversation data is stored on ChatRAG servers, not on your site
- The script fetches `https://chatrag.app/api/conversations/{id}` once on load to verify the conversation exists — no visitor data is sent in this request
- User fingerprints are generated client-side inside the iframe and sent only to ChatRAG
