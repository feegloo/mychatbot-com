# GitHub Actions Deployment Setup

This guide explains how to set up GitHub Actions to automatically deploy to Google Cloud Run.

## Prerequisites

- GitHub repository with push access to `main` branch
- GCP project (`chatbotqa-app`)
- Service account with Cloud Run and Container Registry permissions

## Step 1: Create a Google Cloud Service Account

```bash
# Set your project ID
export GCP_PROJECT_ID="chatbotqa-app"

# Create service account
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions Deployment" \
  --project=$GCP_PROJECT_ID

# Get service account email
SA_EMAIL=$(gcloud iam service-accounts list \
  --filter="displayName=GitHub Actions Deployment" \
  --format='value(email)' \
  --project=$GCP_PROJECT_ID)

echo "Service Account: $SA_EMAIL"
```

## Step 2: Grant Required IAM Roles

```bash
# Container Registry push permissions
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member=serviceAccount:$SA_EMAIL \
  --role=roles/storage.admin

# Cloud Run deployment permissions
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member=serviceAccount:$SA_EMAIL \
  --role=roles/run.admin

# Service Account permissions
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member=serviceAccount:$SA_EMAIL \
  --role=roles/iam.serviceAccountUser
```

## Step 3: Set Up Workload Identity Federation (Recommended)

This allows GitHub to authenticate without storing long-lived keys.

```bash
# Enable required APIs
gcloud services enable iamcredentials.googleapis.com
gcloud services enable sts.googleapis.com
gcloud services enable cloudresourcemanager.googleapis.com
gcloud services enable serviceusage.googleapis.com

# Create Workload Identity Pool
POOL_ID="github-actions"
gcloud iam workload-identity-pools create $POOL_ID \
  --project=$GCP_PROJECT_ID \
  --location=global \
  --display-name="GitHub Actions"

# Get pool resource name
WORKLOAD_IDENTITY_POOL_ID=$(gcloud iam workload-identity-pools describe $POOL_ID \
  --project=$GCP_PROJECT_ID \
  --location=global \
  --format='value(name)')

# Create OIDC provider
PROVIDER_ID="github"
gcloud iam workload-identity-pools providers create-oidc $PROVIDER_ID \
  --project=$GCP_PROJECT_ID \
  --location=global \
  --workload-identity-pool=$POOL_ID \
  --display-name="GitHub" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.aud=assertion.aud,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Grant service account access
gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
  --project=$GCP_PROJECT_ID \
  --role=roles/iam.workloadIdentityUser \
  --principal=principalSet://iam.googleapis.com/projects/$GCP_PROJECT_ID/locations/global/workloadIdentityPools/$POOL_ID/attribute.repository/YOUR_GITHUB_USERNAME/chatrag-com
```

Replace `YOUR_GITHUB_USERNAME` with your actual GitHub username.

## Step 4: Get Workload Identity Provider

```bash
WIF_PROVIDER=$(gcloud iam workload-identity-pools providers describe $PROVIDER_ID \
  --project=$GCP_PROJECT_ID \
  --location=global \
  --workload-identity-pool=$POOL_ID \
  --format='value(name)')

echo "WIF_PROVIDER: $WIF_PROVIDER"
echo "SERVICE_ACCOUNT: $SA_EMAIL"
```

## Step 5: Add GitHub Secrets

Go to your GitHub repository:
1. Settings > Secrets and variables > Actions > New repository secret

Add these secrets:

- **WIF_PROVIDER**: (from Step 4 output)
- **WIF_SERVICE_ACCOUNT**: `$SA_EMAIL` (from Step 4 output)
- **GCP_PROJECT_ID**: `chatbotqa-app`

## Step 6: Test the Workflow

1. Push a commit to `main` branch:
   ```bash
   git add .
   git commit -m "Enable GitHub Actions deployment"
   git push origin main
   ```

2. Go to your GitHub repository's **Actions** tab to see the deployment workflow running

3. Once successful, your app will be deployed to Cloud Run automatically

## Troubleshooting

### Workflow fails with "Failed to authenticate"
- Verify `WIF_PROVIDER` and `WIF_SERVICE_ACCOUNT` are correct
- Check that the service account has the required IAM roles

### "Permission denied" during deployment
- Run Step 2 again to ensure all roles are granted
- Add `roles/servicemanagement.admin` if Cloud SQL connection issues occur

### Image push fails
- Verify Container Registry API is enabled: `gcloud services enable containerregistry.googleapis.com`
- Check service account has `roles/storage.admin` permission

## Deployment Status

Once set up:
- ✅ Every push to `main` triggers automatic deployment
- ✅ Docker image is built and pushed to GCR
- ✅ Cloud Run service is updated with the new image
- ✅ No manual deployment needed!

---

## Alternative: Deploy with Service Account Key (`deploy-gcp.yml`)

The `deploy-gcp.yml` workflow uses a **service account JSON key** (`GCP_SA_KEY`) instead of Workload Identity Federation. This is simpler to configure — no identity pool setup required.

### Step A: Create & Download a Service Account Key

Follow Steps 1–2 above to create the service account and grant IAM roles, then download a JSON key:

```bash
# Create and download the JSON key
gcloud iam service-accounts keys create ~/gcp-sa-key.json \
  --iam-account=$SA_EMAIL \
  --project=$GCP_PROJECT_ID
```

> **Reference:** [Creating service account keys — Google Cloud docs](https://cloud.google.com/iam/docs/keys-create-delete)

### Step B: Base64-encode the Key

GitHub secrets must be plain text, so encode the JSON file:

```bash
# macOS
base64 -i ~/gcp-sa-key.json | tr -d '\n'

# Linux
base64 -w 0 ~/gcp-sa-key.json
```

Copy the full base64 string — this is the value you will paste as `GCP_SA_KEY`.

### Step C: Add Secrets to GitHub

1. Open your repository on GitHub.
2. Go to **Settings → Secrets and variables → Actions**
   ([direct link](https://github.com/feegloo/chatrag-com/settings/secrets/actions))
3. Click **New repository secret** for each secret below:

| Secret name | Value |
|---|---|
| `GCP_SA_KEY` | Base64-encoded JSON key from Step B |
| `GCP_PROJECT_ID` | Your GCP project ID (e.g. `chatbotqa-app`) |

> **Reference:** [Using secrets in GitHub Actions — GitHub docs](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions#creating-secrets-for-a-repository)

### Step D: Verify

Push a commit to `main`. The **Deploy to GCP Cloud Run** workflow should appear in the [Actions tab](https://github.com/feegloo/chatrag-com/actions) and complete successfully.

> ⚠️ **Security note:** Service account keys are long-lived credentials. Store them only in GitHub Secrets, never commit them to source control. Rotate or delete the key if it is ever exposed. For production workloads, prefer the Workload Identity Federation approach (Steps 1–6 above).
>
> See also: [Best practices for managing service account keys](https://cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys)
