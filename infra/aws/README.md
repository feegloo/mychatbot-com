# AWS deployment notes

Recommended fast path:
- backend on ECS Fargate or App Runner
- RDS PostgreSQL
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
