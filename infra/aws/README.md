# Deploy to AWS App Runner

## Quickstart (fastest path to live demo)

```bash
# 1. Set your secrets
export OPENAI_API_KEY=sk-...
export CHROMA_API_KEY=ck-...
export AWS_REGION=us-east-1  # optional, default us-east-1

# 2. Run the deploy script
./infra/aws/deploy-aws.sh
```

The script will:
1. Install AWS CLI + Docker if missing
2. Create an ECR repository and push the Docker image
3. Create an RDS PostgreSQL instance (db.t4g.micro)
4. Apply the database schema
5. Deploy to App Runner (auto-scaling)
6. Print the live URL

## Files

| File | Purpose |
|------|---------|
| `deploy-aws.sh` | One-command deploy script for macOS |
| `cloudformation.json` | Full CloudFormation stack (VPC, RDS, App Runner) |

## Approximate monthly cost (low traffic demo)

| Service | Cost |
|---------|------|
| App Runner (auto-pause) | ~$5/mo minimum |
| RDS db.t4g.micro | ~$13/mo |
| ChromaDB Cloud | Free tier |
| **Total** | **~$18/mo** |

## Map domain: chatrag.app

1. Open **AWS Console → App Runner → mychatbot → Custom domains**
2. Click **Link domain** → enter `chatrag.app`
3. AWS will show CNAME validation records
4. Go to **GoDaddy → DNS Management** for chatrag.app:
   - Add CNAME records for validation (shown by AWS)
   - Add CNAME: `@` → `<apprunner-url>` (or use A record with alias)
5. Wait for DNS propagation and certificate validation (~10-30 min)

App Runner provides free managed SSL.

## Alternative: CloudFormation

```bash
aws cloudformation deploy \
  --template-file infra/aws/cloudformation.json \
  --stack-name mychatbot \
  --parameter-overrides \
    DatabasePassword=YOUR_DB_PASSWORD \
    OpenAiApiKey=sk-... \
    ChromaApiKey=ck-... \
    ImageUri=123456789.dkr.ecr.us-east-1.amazonaws.com/mychatbot:latest \
  --capabilities CAPABILITY_NAMED_IAM
```

## Conversation URLs

After deployment, conversations work at:
```
https://chatrag.app/c/742a8554-5660-4418-b8bd-d0b4ef089180
```
- S3 once you move beyond local disk
- Route 53 or registrar DNS for custom domain

Route 53 can route traffic to AWS resources, and alias records can point a root domain to supported AWS targets. citeturn966466search11turn966466search15

## Example flow

1. Buy `mychatbot.com`.
2. Deploy backend and frontend.
3. Get the target hostname or load balancer DNS name.
4. Add DNS records at GoDaddy, or move DNS into Route 53.
5. Point root and `www` or `api` records to the deployed service.

## Notes
- For a very fast demo, one backend service can also serve the built frontend.
- Later you can separate frontend and backend into different services.
