# ChatRAG Chrome Extension

A Chrome extension that adds an AI chat widget to any webpage, powered by [chatrag.app](https://chatrag.app).

## How It Works

1. Click the **ChatRAG** button in the browser toolbar on any webpage
2. The extension sends the current URL to the chatrag.app API, which fetches and indexes the page content
3. While indexing (15–30 seconds), a loading indicator is shown in the popup
4. When ready, a chatbot widget appears in the **bottom-right corner** of the page
5. Chat with the AI about the page content — ask questions, get answers, click suggested actions

## Features

- One-click conversation creation from any webpage
- Persistent conversations per URL (revisiting a page reuses the existing chat)
- Classic chatbot widget UX (floating circle → slide-up iframe)
- Embeds the full ChatRAG conversation interface via iframe
- Dark-themed UI consistent with ChatRAG brand

## Local Development Setup

### 1. Generate Icons

```bash
node scripts/generate-icons.js
```

This creates `icons/icon16.png`, `icons/icon32.png`, `icons/icon48.png`, `icons/icon128.png` using only Node.js built-ins.

### 2. Load the Extension in Chrome

1. Open `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked**
4. Select this `chrome-extension/` folder

The extension is now active. Navigate to any webpage and click the ChatRAG icon in the toolbar.

### Regenerating Icons

Run `node scripts/generate-icons.js` whenever you want to update the icon design.

## Publishing to Chrome Web Store

1. Ensure all icons are generated (`node scripts/generate-icons.js`)
2. Zip the extension folder contents (not the folder itself):
   ```bash
   cd chrome-extension && zip -r ../chatrag-extension.zip . --exclude "scripts/*" --exclude "README.md"
   ```
3. Upload `chatrag-extension.zip` to the [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole)

## File Structure

```
chrome-extension/
├── manifest.json              # MV3 extension manifest
├── background/
│   └── service_worker.js      # API calls, SSE polling, state management
├── popup/
│   ├── popup.html             # Toolbar popup UI
│   ├── popup.js               # Popup logic
│   └── popup.css              # Popup styles
├── content/
│   └── content.js             # Injected chat widget (iframe + toggle button)
├── icons/                     # Generated PNG icons (run generate-icons.js)
│   ├── icon16.png
│   ├── icon32.png
│   ├── icon48.png
│   └── icon128.png
└── scripts/
    └── generate-icons.js      # Pure Node.js icon generator
```

## API

The extension uses the existing chatrag.app backend API:

- `POST https://chatrag.app/api/upload-url` — creates a new conversation from a URL
- `GET https://chatrag.app/api/conversations/:id` — polls for conversation status
- Conversation embed URL: `https://chatrag.app/c/:id?embed=1`

The `?embed=1` query parameter activates embed mode in the chatrag.app frontend, which hides the sidebar navigation and conversation header, showing only the chat interface.

## Frontend Changes Required

The `?embed=1` mode requires these changes in the main chatrag-app frontend (already applied):

- **`App.vue`**: hides `ConversationNav` and sidebar toggle when `embed=1`
- **`ConversationPage.vue`**: hides `ConversationHeader` when `embed=1`  
- **`style.css`**: `.embed-mode` class removes padding and fills full dimensions
