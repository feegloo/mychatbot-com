# Cloud Function Upload Proxy (GCP)

This folder contains a minimal HTTP Cloud Function that:

- accepts `POST /upload` multipart file uploads
- allows CORS from `https://chatrag.app`
- forwards the upload to the existing Cloud Run API endpoint: `https://chatrag.app/api/upload`
- returns a normalized conversation URL like `https://chatrag.app/c/<conversationId>`

## Environment variables

Copy `.env.example` values into your deployment config:

- `UPSTREAM_UPLOAD_URL` (default: `https://chatrag.app/api/upload`)
- `PUBLIC_APP_BASE_URL` (default: `https://chatrag.app`)
- `ALLOWED_ORIGINS` (default includes `https://chatrag.app`)

## Local run

```bash
cd cloud-function
npm install
npm run dev
```

Default local URL:

- `http://localhost:8080/upload`

## Deploy (Cloud Functions Gen 2)

```bash
cd cloud-function
npm install
npm run build

gcloud functions deploy chatrag-upload \
  --gen2 \
  --runtime=nodejs20 \
  --region=us-central1 \
  --source=. \
  --entry-point=uploadProxy \
  --trigger-http \
  --allow-unauthenticated \
  --set-env-vars=UPSTREAM_UPLOAD_URL=https://chatrag.app/api/upload,PUBLIC_APP_BASE_URL=https://chatrag.app,ALLOWED_ORIGINS=https://chatrag.app,https://www.chatrag.app
```

After deploy, use the function URL in `ui` as `VITE_CLOUD_FUNCTION_UPLOAD_URL`.
