# Cloud Run deployment notes

Recommended fast path:
- build backend image
- optionally build frontend and serve its static files from the backend
- deploy backend image to Cloud Run
- use Cloud SQL for PostgreSQL
- use Cloud Storage when you switch away from disk
- keep Chroma on a VM or container service if you want Chroma HTTP mode

Cloud Run supports mapping a custom domain after domain verification. citeturn966466search2turn966466search14

## Example flow

1. Buy domain, for example on GoDaddy.
2. Deploy backend to Cloud Run.
3. In Google Cloud, verify `mychatbot.com`.
4. Add the DNS records Google gives you at your registrar.
5. Point `mychatbot.com` to the frontend entry and `api.mychatbot.com` if you choose separate backend hostnames.

## Notes
- Cloud Run is simple for demos and shareable links.
- Root route `/` can serve the upload page.
- Dynamic routes like `/c/:conversationId` work well behind one frontend app.
