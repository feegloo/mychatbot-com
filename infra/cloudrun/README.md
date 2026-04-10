# Deploy to Google Cloud Run

## Quickstart (fastest path to live demo)

```bash
# 1. Set your secrets
export GCP_PROJECT_ID=your-gcp-project-id
export OPENAI_API_KEY=sk-...
export CHROMA_API_KEY=ck-...

# 2. Run the deploy script
./infra/cloudrun/deploy-gcp.sh
```

The script will:
1. Install `gcloud` CLI + Docker if missing
2. Enable required GCP APIs
3. Create a Cloud SQL PostgreSQL instance (db-f1-micro, ~$7/mo)
4. Build & push the Docker image to GCR
5. Deploy to Cloud Run (auto-scales 0→3 instances)
6. Print the live URL

## Files

| File | Purpose |
|------|---------|
| `deploy-gcp.sh` | One-command deploy script for macOS |
| `cloudbuild.yaml` | Cloud Build CI/CD pipeline (optional) |
| `service.yaml` | Cloud Run service definition (for `gcloud run services replace`) |

## Approximate monthly cost (low traffic demo)

| Service | Cost |
|---------|------|
| Cloud Run (0 min instances) | ~$0 idle, ~$0.50/1M requests |
| Cloud SQL (db-f1-micro) | ~$7/mo |
| ChromaDB Cloud | Free tier |
| **Total** | **~$7/mo idle** |

## Map domain: chatrag.app

```bash
# 1. Create domain mapping in Cloud Run
gcloud run domain-mappings create \
  --service=mychatbot \
  --region=europe-west1 \
  --domain=chatrag.app

# 2. It will show DNS records needed. Go to GoDaddy → DNS Management for chatrag.app

# 3. Add the records:
#    Type: A     Name: @    Value: <IP from gcloud output>
#    Type: AAAA  Name: @    Value: <IPv6 from gcloud output>
#    Type: CNAME Name: www  Value: ghs.googlehosted.com.

# 4. Wait for DNS propagation (5-30 min), then verify:
gcloud run domain-mappings describe --domain=chatrag.app --region=europe-west1
```

Cloud Run provides free managed SSL for custom domains.

## Conversation URLs

After deployment, conversations work at:
```
https://chatrag.app/c/742a8554-5660-4418-b8bd-d0b4ef089180
```
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
