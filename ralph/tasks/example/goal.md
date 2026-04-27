# Goal

Implement full-text search for conversations.

## Layout

- Clicking the `search` icon in the left menu opens an input on top of the icon.
- The input has an `x` on the right; clicking it hides the input. Clicking the
  search icon again also hides the input.

## API

It sends a request to the backend with `fingerprint` in the header, searching a
phrase like `"informacja o bezrobotnym"` through all conversations of the
matching `userId`.

a) Returns an array — whole conversation names plus conversation messages
   matching the phrase (full payload, same shape as
   `GET /conversation/:conversationId`). Array can be empty (no match).
b) If no match — show in the left menu, above the input:
   `no matches in conversations phrase: {user_input}`
c) If match — show found names as the current "tabs" for normal conversations
   of the user, so search effectively *filters* the left-menu items.
d) Clicking a result loads the conversation: first try the API, on error
   fall back to the conversation object already returned by the search call.
