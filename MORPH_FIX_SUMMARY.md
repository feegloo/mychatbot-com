# Morph Effect Fix - Implementation Summary

## Problem Statement
The morph effect (progressive partial image frames during OpenAI image generation) disappeared after refactoring. The image generation would show a "generating..." label but no partial frames would animate/blur.

## Root Cause Analysis
1. **Model Default Changed**: Previous working version used `gpt-image-2` which emits `partial_images` events during streaming
2. **Broken Version Used**: `gpt-image-1` which does NOT support partial frame streaming
3. **Reference Images Trigger Blocking**: When reference images are provided, the system falls back to blocking edit API which doesn't support streaming

## Code Fixes Implemented

### 1. Python Backend - Config (`python/src/shared/config.py`)
**Status**: ✅ FIXED
- Restored `gpt-image-2` as default model
- Comment added: "Keep gpt-image-2 as default because progressive partial frames"

### 2. Python Backend - Image Generation (`python/src/shared/image_gen.py`)
**Status**: ✅ FIXED
- Added automatic fallback: `gpt-image-1` → `gpt-image-2` for streaming requests
- Reference image streaming now supported with fallback to blocking edit when necessary
- Code pattern: Check if `gpt-image-1`, warn user, automatically switch to `gpt-image-2`

### 3. Frontend - TypeScript Imports (`frontend/src/composables/useTextSelectionSpeech.ts`)
**Status**: ✅ FIXED
- Added missing `WordCaption` import from `../api`
- Resolves TypeScript build error: "Cannot find name 'WordCaption'"

### 4. Frontend - SSE Parser (`frontend/src/api.ts`)
**Status**: ✅ VERIFIED
- Hardened SSE event parser to handle both `\n\n` and `\r\n\r\n` separators
- Fixes brittle parsing that was dropping partial events at boundary conditions

### 5. Frontend - Vue Component (`frontend/src/components/ChatMessage.vue`)
**Status**: ✅ VERIFIED
- Vue render condition changed from `!msg.content && !msg.id` to `msg.generatingImage`
- Less restrictive condition ensures morph wrap renders when generating

## Testing Status

### Unit Tests - ✅ PASSING
- **Python**: 13 tests passed (image generation, streaming, fallback logic)
- **Frontend**: 3 tests passed (including CRLF separator handling)

### End-to-End Testing - ⏳ IN PROGRESS
- Code fixes verified in place
- Builds compile successfully
- Infrastructure (Docker Compose) still initializing
- **Pending**: Real image generation request with OpenAI API

## Data Flow for Morph Effect
```
1. User submits image generation request
   ↓
2. Backend calls generateImageStream() with gpt-image-2
   ↓
3. OpenAI SDK streams partial_images events (intermediate frames)
   ↓
4. Python generator yields: {'event': 'partial', 'data': {...base64image...}}
   ↓
5. Node.js Koa route receives event and sends: event: partial\ndata: {...}\n\n
   ↓
6. Frontend fetch + ReadableStream receives SSE event
   ↓
7. generateImageStream() parser extracts and dispatches event
   ↓
8. useImageGenStream() composable calls onPartial callback
   ↓
9. Sets reactive: msg.imagePartialDataUrl = base64image, msg.imagePartialIndex = 0,1,2...
   ↓
10. ChatMessage.vue renders: <div v-if="msg.generatingImage && msg.imagePartialDataUrl">
    ↓
11. CSS blur filter applied: blur($partialBlurPx) where blur decreases as index increases
    ↓
12. Animation loop: partial frame 0 → frame 1 → frame 2 → final image
```

## Environment Configuration

### Python (for testing)
- Using `python3.11` explicitly (not just `python`)
- OpenAI SDK configured via OPENAI_API_KEY
- Default model: `gpt-image-2`

### Docker Services Required (for end-to-end testing)
- `postgres:16` - Conversation metadata storage
- `chromadb/chroma:1.0.7` - Vector store for RAG
- `jaegertracing/jaeger:latest` - Distributed tracing (optional)
- `gcr.io/google.com/cloudsdktool/cloud-sdk:emulators` - Pub/Sub emulator (optional)

## Next Steps to Validate

### Immediate (Code Complete, Needs Testing)
1. ✅ Ensure all Docker services are running (postgres + chroma)
2. ⏳ Start backend server with environment configuration
3. ⏳ Start frontend dev server  
4. ⏳ Generate a test image and observe partial frames in browser

### Diagnostic Steps (if morph still doesn't work)
Add temporary console logging to identify where partial frames are lost:

**In `frontend/src/api.ts` - generateImageStream():**
```typescript
// Log all parsed events
console.log('[SSE] Parsed event:', eventName, dataLine)
dispatch(eventName, payload)
```

**In `frontend/src/composables/useImageGenStream.ts` - onPartial callback:**
```typescript
console.log('[Image] Partial frame received:', imagePartialIndex, imagePartialDataUrl?.length)
reactiveMsg.imagePartialDataUrl = imagePartialDataUrl
```

**In backend Python `generate_image_streaming()`:**
```python
logger.info(f"Yielding partial event: index={partial_index}, size={len(image_data)} bytes")
yield {'event': 'partial', 'data': {...}}
```

### Production Debugging
1. Check Sentry for backend errors during image generation
2. Check Docker logs: `docker-compose logs backend | grep -E "partial|stream|image"`
3. Check browser DevTools Network tab for SSE events and timing
4. Monitor OpenAI API usage to confirm partial_images requests are being made

## Code Verification Checklist

- [x] `gpt-image-2` set as default in Python config
- [x] Fallback logic implemented (gpt-image-1 → gpt-image-2)
- [x] TypeScript imports all resolved
- [x] SSE parser handles CRLF/LF separators
- [x] Vue component render condition less restrictive
- [x] Unit tests passing (Python + Frontend)
- [ ] Real image generation request executed
- [ ] Partial frames observed in browser
- [ ] Blur animation plays as expected
- [ ] Final image renders after animation

## Files Modified
1. `python/src/shared/config.py` - Default model
2. `python/src/shared/image_gen.py` - Streaming fallback logic
3. `frontend/src/composables/useTextSelectionSpeech.ts` - Missing import
4. `docker-compose.yml` - Jaeger image tag update
5. (Already verified in place: `frontend/src/api.ts`, `frontend/src/components/ChatMessage.vue`)

## Known Limitations
- If OpenAI doesn't emit partial_images for this account/request, fallback is to wait for final image
- Reference images with blocking edit don't support streaming  (this is expected behavior from OpenAI API)
- Jaeger tracing uses older image tag due to registry issues (switched to `:latest`)
