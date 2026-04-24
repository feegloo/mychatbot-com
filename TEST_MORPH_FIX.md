# Next Steps - Testing Morph Effect Fix

## Infrastructure Status ✅
- PostgreSQL (5432) - Running
- Chroma (8000) - Running

## What Has Been Fixed

### Code Changes Applied:
1. **Python Backend** (`python/src/shared/config.py`)
   - Restored `gpt-image-2` as default model (supports partial frames)

2. **Python Backend** (`python/src/shared/image_gen.py`)
   - Added fallback logic: `gpt-image-1` → `gpt-image-2` for streaming

3. **Frontend TypeScript** (`frontend/src/composables/useTextSelectionSpeech.ts`)
   - Fixed missing `WordCaption` import

4. **Docker Configuration** (`docker-compose.yml`)
   - Updated Jaeger image tag to `:latest`

5. **Verified in Place**:
   - SSE parser handles CRLF/LF separators
   - Vue component render condition for morph wrap
   - Unit tests all passing

## How to Test the Fix

### Prerequisites
```bash
# Ensure you have .env configured with:
# - OPENAI_API_KEY=your_key
# - POSTGRES_USER=chatrag
# - POSTGRES_PASSWORD=chatrag
# - POSTGRES_DB=chatrag (if needed)
```

### Option 1: Full Docker Stack (Recommended for Production Testing)
```bash
cd /Users/olek/Downloads/chatrag-app

# Clean up the manually started containers
docker rm -f chatrag-postgres chatrag-chroma

# Let docker-compose handle everything
docker-compose up -d

# Wait for containers to be healthy
sleep 30

# Start backend
npm run dev --workspace=backend

# In another terminal, start frontend
npm run dev --workspace=frontend

# Open http://localhost:5173 and generate an image
```

### Option 2: Manual Services (Faster, Current State)
```bash
# Services already running:
# - postgres on 5432
# - chroma on 8000

# Terminal 1: Start backend
cd /Users/olek/Downloads/chatrag-app/backend
npm install  # if not done
npm run dev

# Terminal 2: Start frontend
cd /Users/olek/Downloads/chatrag-app/frontend
npm install  # if not done
npm run dev

# Terminal 3: Test (if manual testing required)
# Open http://localhost:5173 in browser
```

## Testing the Morph Effect

1. **Navigate to**: http://localhost:5173
2. **Open a conversation** or create one
3. **Enable image generation** (if not already enabled)
4. **Submit image generation request**, e.g.:
   - "Wygeneruj obraz inspirowany: CV - Aleksander Figiel 🎨"
5. **Observe**: 
   - ✅ EXPECTED: "Generating image..." label appears, followed by blurred partial frames animating from very blurry to clear
   - ❌ PROBLEM: Only "Generating..." label, no partial frames appear

## Diagnostic Logging (If Morph Still Doesn't Work)

### Add Temporary Logging to Frontend

**In `frontend/src/api.ts` - `generateImageStream()` function** (around line 550):
```typescript
// Add after parsing event:
if (eventName === 'partial') {
  console.log('[MORPH_DEBUG] Partial event received:', {
    eventName,
    hasData: !!dataLine,
    dataLength: dataLine.length,
    dataPreview: dataLine.substring(0, 100)
  })
}
```

**In `frontend/src/composables/useImageGenStream.ts` - `onPartial` callback:**
```typescript
console.log('[MORPH_DEBUG] onPartial called:', {
  hasUrl: !!imagePartialDataUrl,
  index: imagePartialIndex,
  dataUrlLength: imagePartialDataUrl?.length || 0
})
reactiveMsg.imagePartialDataUrl = imagePartialDataUrl
reactiveMsg.imagePartialIndex = imagePartialIndex
```

### Add Logging to Python Backend

**In `python/src/shared/image_gen.py` - `generate_image_streaming()`:**
```python
for partial_index, image_data in enumerate(response.data):
    print(f'[MORPH_DEBUG] Partial frame {partial_index}: {len(image_data)} bytes')
    yield {'event': 'partial', 'data': {...}}
```

### Check Browser Console
1. Open browser DevTools (F12)
2. Go to Console tab
3. Generate image
4. Look for `[MORPH_DEBUG]` logs
5. Check Network tab for SSE events with "partial" event type

## Troubleshooting

### If partial frames not appearing:

**Check 1: Browser Console Logs**
- Look for `[MORPH_DEBUG]` messages
- If no messages: events aren't reaching frontend

**Check 2: Network Tab**
- Look for EventStream in Network tab
- Check for `event: partial` messages
- If missing: backend not forwarding events

**Check 3: Backend Logs**
- Look for `[MORPH_DEBUG]` in backend console
- If missing: Python not emitting partial events
- Check if OpenAI API returned them

**Check 4: Verify Configuration**
```bash
# Check environment variables
echo $OPENAI_API_KEY  # should not be empty

# Check Python default model
grep "OPENAI_IMAGE_MODEL" /Users/olek/Downloads/chatrag-app/python/src/shared/config.py

# Check if gpt-image-2 is being used
# Look in Python logs for model name
```

## Expected File Sizes (For Debugging)

- Partial frame (low quality): ~50-200 KB base64
- Final frame: ~300-500 KB base64
- Each should be decodable as valid image/jpeg

## Next Steps

1. **Start Services** (use Option 2 for faster setup)
2. **Test Image Generation**
3. **Check Browser Console** for `[MORPH_DEBUG]` logs
4. **If working**: Morph effect is fixed! ✅
5. **If not working**: Share browser console logs to debug further

---

**Git Reference**: Previous working version was at commit `f9c79e7`
**Modified Files**: Check `MORPH_FIX_SUMMARY.md` for complete list
