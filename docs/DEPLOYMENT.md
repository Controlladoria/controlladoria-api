# Deployment Guide

Complete guide for deploying the full ControlladorIA platform to production.

---

## Architecture

```
                         ┌──────────────────────────┐
                         │  controlladoria-website   │
                         │  Next.js 16.2 (static)    │
                         │  Vercel                   │
                         │  controlladoria.com.br    │
                         └──────────────────────────┘

┌──────────────────────┐  HTTPS  ┌─────────────────────────────┐
│  controlladoria-ui   │ ──────> │     controlladoria-api      │
│  Next.js 16.1        │         │     FastAPI / Python 3.12   │
│  AWS Amplify         │         │     Railway                 │
│  app.controlladoria  │         │     api.controlladoria.com  │
└──────────────────────┘         └──────────────┬──────────────┘
                                                │
┌──────────────────────┐  HTTPS  ┌──────────────┘
│  controlladoria-     │ ──────> │  ┌────────────────────┐
│  sysadmin-ui         │         │  │  PostgreSQL 16      │
│  Next.js 14.2        │         │  │  Railway           │
│  AWS Amplify         │         │  └────────────────────┘
│  admin.controlladoria│         │
└──────────────────────┘         │  ┌────────────────────┐
                                 │  │  Redis             │
                                 │  │  (Cache/Celery)    │
                                 │  └────────────────────┘
                                 │
                                 │  S3 ──────────────────────────────┐
                                 │  (file storage)                   │
                                 │                                   ▼
                                 │  SQS ──> controlladoria-jobs <── EventBridge
                                 │          AWS Lambda (us-east-2)   (schedules)
                                 │
                                 │  ┌────────────────────┐
                                 └> │  Stripe (billing)  │
                                    │  Resend (email)     │
                                    │  Gemini / Nova / GPT│
                                    └────────────────────┘

┌──────────────────────┐
│  controlladoria-app  │  ←── EAS Build (cloud)
│  Expo SDK 54         │
│  iOS + Android       │
└──────────────────────┘
```

---

## Prerequisites

Accounts and access required:

| Service | Purpose | URL |
|---------|---------|-----|
| Railway | API + database hosting | railway.app |
| AWS | S3, SQS, Lambda, ECR, SSM | aws.amazon.com |
| GitHub | CI/CD via Actions | github.com |
| AWS Amplify | Frontend hosting (UI + sysadmin) | console.aws.amazon.com/amplify |
| Vercel | Marketing website | vercel.com |
| Stripe | Billing | dashboard.stripe.com |
| Resend | Transactional email | resend.com |
| Google AI Studio | Gemini API keys | aistudio.google.com |
| OpenAI | Fallback AI | platform.openai.com |
| Expo (EAS) | Mobile builds | expo.dev |
| Apple Developer | iOS distribution | developer.apple.com |
| Google Play Console | Android distribution | play.google.com/console |

---

## Deployment Order

Follow this order — each step depends on the previous.

```
1. AWS infrastructure (S3, SQS, IAM, SSM)
2. Railway PostgreSQL + API
3. AWS Lambda jobs
4. AWS Amplify — customer UI
5. AWS Amplify — sysadmin UI
6. Vercel — marketing website
7. Stripe webhooks
8. Mobile (EAS Build)
```

---

## Step 1 — AWS Infrastructure

### 1.1 S3 Bucket

```bash
aws s3api create-bucket \
  --bucket controlladoria-prod \
  --region us-east-2 \
  --create-bucket-configuration LocationConstraint=us-east-2

# Block public access
aws s3api put-public-access-block \
  --bucket controlladoria-prod \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

### 1.2 SQS Queue

```bash
# Create queue with DLQ
aws sqs create-queue \
  --queue-name controlladoria-document-processing-prod-dlq \
  --region us-east-2

DLQ_ARN=$(aws sqs get-queue-attributes \
  --queue-url <dlq-url> \
  --attribute-names QueueArn \
  --query Attributes.QueueArn --output text)

aws sqs create-queue \
  --queue-name controlladoria-document-processing-prod \
  --region us-east-2 \
  --attributes VisibilityTimeout=900,MessageRetentionPeriod=86400,RedrivePolicy="{\"deadLetterTargetArn\":\"$DLQ_ARN\",\"maxReceiveCount\":3}"
```

### 1.3 IAM Role for Lambda

Create a role `controlladoria-lambda-prod` with trust policy for Lambda, and attach a custom policy with:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["s3:GetObject","s3:PutObject","s3:DeleteObject"], "Resource": "arn:aws:s3:::controlladoria-prod/*" },
    { "Effect": "Allow", "Action": ["sqs:ReceiveMessage","sqs:DeleteMessage","sqs:GetQueueAttributes"], "Resource": "arn:aws:sqs:us-east-2:*:controlladoria-document-processing-prod" },
    { "Effect": "Allow", "Action": ["ssm:GetParameter","ssm:GetParameters","ssm:GetParametersByPath"], "Resource": "arn:aws:ssm:us-east-2:*:parameter/controlladoria/prod/*" },
    { "Effect": "Allow", "Action": ["bedrock:InvokeModel"], "Resource": "*" },
    { "Effect": "Allow", "Action": ["ecr:GetDownloadUrlForLayer","ecr:BatchGetImage","ecr:GetAuthorizationToken"], "Resource": "*" },
    { "Effect": "Allow", "Action": ["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"], "Resource": "*" }
  ]
}
```

### 1.4 SSM Parameter Store

Populate all Lambda config. Use SecureString for sensitive values:

```bash
PREFIX="/controlladoria/prod/worker"

aws ssm put-parameter --name "$PREFIX/ENVIRONMENT"      --value "production"     --type String
aws ssm put-parameter --name "$PREFIX/DATABASE_URL"     --value "postgresql://..."  --type SecureString
aws ssm put-parameter --name "$PREFIX/JWT_SECRET_KEY"   --value "$(openssl rand -hex 32)"  --type SecureString
aws ssm put-parameter --name "$PREFIX/ENCRYPTION_KEY"   --value "<fernet-key>"   --type SecureString
aws ssm put-parameter --name "$PREFIX/AI_PROVIDER"      --value "gemini"         --type String
aws ssm put-parameter --name "$PREFIX/GEMINI_API_KEYS"  --value "key1,key2"      --type SecureString
aws ssm put-parameter --name "$PREFIX/GEMINI_MODEL"     --value "gemini-flash-lite-latest" --type String
aws ssm put-parameter --name "$PREFIX/NOVA_MODEL"       --value "us.amazon.nova-2-lite-v1:0" --type String
aws ssm put-parameter --name "$PREFIX/NOVA_REGION"      --value "us-east-2"      --type String
aws ssm put-parameter --name "$PREFIX/OPENAI_API_KEYS"  --value "sk-..."         --type SecureString
aws ssm put-parameter --name "$PREFIX/OPENAI_MODEL"     --value "gpt-5.4-nano"   --type String
aws ssm put-parameter --name "$PREFIX/AI_FAILOVER_ENABLED" --value "true"        --type String
aws ssm put-parameter --name "$PREFIX/S3_BUCKET_NAME"   --value "controlladoria-prod" --type String
aws ssm put-parameter --name "$PREFIX/USE_S3"           --value "true"           --type String
aws ssm put-parameter --name "$PREFIX/SQS_DOCUMENT_QUEUE_URL" --value "https://sqs.us-east-2..." --type String
aws ssm put-parameter --name "$PREFIX/STRIPE_API_KEY"   --value "sk_live_..."    --type SecureString
aws ssm put-parameter --name "$PREFIX/RESEND_API_KEY"   --value "re_..."         --type SecureString
aws ssm put-parameter --name "$PREFIX/FRONTEND_URL"     --value "https://app.controlladoria.com.br" --type String
```

---

## Step 2 — Railway (API + PostgreSQL)

### 2.1 Create Services

1. New project on Railway
2. Add **PostgreSQL** service — copy `DATABASE_URL` from connection tab
3. Add **Web Service** → Deploy from GitHub → select `controlladoria-api` repo, branch `main`

### 2.2 Configure Environment Variables

Set all variables in Railway dashboard → Variables tab:

```bash
ENVIRONMENT=production
DATABASE_URL=<railway-postgres-url>
JWT_SECRET_KEY=<openssl rand -hex 32>
ENCRYPTION_KEY=<fernet-key>

AI_PROVIDER=gemini
GEMINI_API_KEYS=key1,key2
GEMINI_MODEL=gemini-flash-lite-latest
NOVA_MODEL=us.amazon.nova-2-lite-v1:0
NOVA_REGION=us-east-2
OPENAI_API_KEYS=sk-...
AI_FAILOVER_ENABLED=true

AWS_ACCESS_KEY_ID=<key>
AWS_SECRET_ACCESS_KEY=<secret>
AWS_REGION=us-east-2
S3_BUCKET_NAME=controlladoria-prod
USE_S3=true
SQS_DOCUMENT_QUEUE_URL=https://sqs.us-east-2...

STRIPE_API_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...        # Set after step 7
STRIPE_PRICE_ID_BASIC=price_...
STRIPE_PRICE_ID_PRO=price_...
STRIPE_PRICE_ID_MAX=price_...
STRIPE_TRIAL_DAYS=15
STRIPE_SUCCESS_URL=https://app.controlladoria.com.br/dashboard
STRIPE_CANCEL_URL=https://app.controlladoria.com.br/pricing

RESEND_API_KEY=re_...
FROM_EMAIL=ControlladorIA <noreply@controlladoria.com.br>
ADMIN_EMAIL=admin@controlladoria.com.br
SUPPORT_EMAIL=suporte@controlladoria.com.br
FRONTEND_URL=https://app.controlladoria.com.br

CORS_ORIGINS=https://app.controlladoria.com.br,https://admin.controlladoria.com.br,https://controlladoria.com.br

REDIS_URL=<redis-url-if-using-celery>
FREE_DEMO_MODE=false

LOG_LEVEL=INFO
RATE_LIMIT_ENABLED=true
```

### 2.3 Add GitHub Secret

```
Repository Settings → Secrets → Actions
RAILWAY_TOKEN_PROD = <token from Railway account settings>
```

### 2.4 Deploy

The `railway.json` start command runs migrations automatically:
```
python create_database.py && alembic upgrade head && uvicorn api:app --host 0.0.0.0 --port $PORT
```

Trigger first deploy by pushing to `main` (dev) or dispatching `deploy-prod.yml`.

### 2.5 Create First Sysadmin Account

After the API is up, run once:
```bash
# Via Railway CLI
railway run python create_sysadmin.py

# Or SSH into the service and run directly
```

### 2.6 Configure Custom Domain

Railway dashboard → Settings → Domains → Add `api.controlladoria.com.br`

---

## Step 3 — Lambda Jobs

### 3.1 Add GitHub Secrets

```
AWS_ACCESS_KEY_ID         ← same IAM user as step 1
AWS_SECRET_ACCESS_KEY
LAMBDA_EXECUTION_ROLE_ARN ← ARN of role created in step 1.3
PROD_SQS_DOCUMENT_PROCESSING_ARN ← ARN of SQS queue from step 1.2
```

### 3.2 Deploy

Dispatch `deploy-prod.yml` in `controlladoria-jobs` repo (type "deploy" to confirm).

The workflow automatically:
- Builds Docker image, pushes to ECR
- Creates/updates 4 Lambda functions
- Wires SQS trigger (batch 1, concurrency 50)
- Creates EventBridge schedules for cleanup/retry jobs
- Cleans up old ECR images (keeps 5)

---

## Step 4 — AWS Amplify (Customer UI)

1. Open Amplify Console → **New app** → **Host web app** → GitHub
2. Select `controlladoria-ui` repo, branch `main`
3. Framework: Next.js (auto-detected)
4. Environment variables:
   ```
   NEXT_PUBLIC_API_URL=https://api.controlladoria.com.br
   ```
5. Deploy
6. Add custom domain: `app.controlladoria.com.br`

---

## Step 5 — AWS Amplify (Sysadmin UI)

1. Amplify Console → **New app** → same flow
2. Select `controlladoria-sysadmin-ui` repo, branch `main`
3. Environment variables:
   ```
   NEXT_PUBLIC_API_URL=https://api.controlladoria.com.br
   NEXT_PUBLIC_CUSTOMER_URL=https://app.controlladoria.com.br
   ```
4. Deploy
5. Add custom domain: `admin.controlladoria.com.br`
6. Consider enabling **Amplify access control** (password protection) for extra security

---

## Step 6 — Vercel (Marketing Website)

1. vercel.com → **Add New Project** → Import `controlladoria-website`
2. Framework: Next.js (auto-detected)
3. No environment variables needed
4. Deploy
5. Add custom domain: `controlladoria.com.br`

---

## Step 7 — Stripe Webhooks

1. Stripe Dashboard → **Developers** → **Webhooks** → **Add endpoint**
2. URL: `https://api.controlladoria.com.br/stripe/webhook`
3. Events to listen for:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
4. Copy signing secret → set `STRIPE_WEBHOOK_SECRET` in Railway env vars → redeploy

---

## Step 8 — Mobile App (EAS Build)

```bash
cd controlladoria-app
npm install -g eas-cli
eas login                   # Expo account

# Configure API URL for production builds (in eas.json or as EAS secret)
eas secret:create --scope project --name EXPO_PUBLIC_API_URL \
  --value https://api.controlladoria.com.br

# Build
npm run build:android       # eas build --platform android
npm run build:ios            # eas build --platform ios (builds on Expo servers)

# Submit to stores
eas submit --platform android
eas submit --platform ios
```

**Requirements:**
- Apple Developer Program membership ($99/yr) — for iOS App Store
- Google Play Console account ($25 one-time) — for Android
- App bundle IDs configured in `app.json`

---

## CI/CD Summary

| Repo | Trigger (Dev) | Trigger (Prod) | Target |
|------|--------------|----------------|--------|
| `controlladoria-api` | Push to `main` | `workflow_dispatch` ("deploy") | Railway |
| `controlladoria-jobs` | Push to `main` | `workflow_dispatch` ("deploy") | Lambda via ECR |
| `controlladoria-ui` | Push to `main` | Push to `main` | Amplify (auto) |
| `controlladoria-sysadmin-ui` | Push to `main` | Push to `main` | Amplify (auto) |
| `controlladoria-website` | Push to `main` | Push to `main` | Vercel (auto) |
| `controlladoria-app` | Manual `eas build` | Manual `eas build` + `eas submit` | EAS cloud |

---

## Post-Deployment Verification

```bash
# 1. API health
curl https://api.controlladoria.com.br/health

# 2. Auth flow
curl -X POST https://api.controlladoria.com.br/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test"}'

# 3. Docs
open https://api.controlladoria.com.br/docs

# 4. Customer UI
open https://app.controlladoria.com.br

# 5. Sysadmin
open https://admin.controlladoria.com.br

# 6. Marketing site
open https://controlladoria.com.br
```

Test paths:
1. Register new user → receive verification email → verify
2. Upload a PDF document → wait for PENDING_VALIDATION status → validate rows
3. View DRE report → export as PDF
4. Start Stripe checkout with test card `4242 4242 4242 4242`
5. Check Stripe webhook was received (Dashboard → Webhooks → Recent deliveries)

---

## Rollback

### API (Railway)
Railway Dashboard → Deployments → select previous deploy → **Redeploy**

### Jobs (Lambda)
```bash
# Previous image tag is stored in ECR — update Lambda to previous image:
aws lambda update-function-code \
  --function-name controlladoria-worker-document-processing-prod \
  --image-uri <previous-ecr-image-uri>
```

### Frontends (Amplify / Vercel)
Both platforms show deployment history — click any previous build to promote it to production.

### Database Migration Rollback
```bash
alembic downgrade -1    # rolls back one migration
```
Always take a manual backup before running migrations on production.

---

## Monitoring

| What | Where |
|------|-------|
| API errors | Sysadmin UI → Errors page |
| API logs | Railway dashboard → Logs tab |
| Lambda logs | CloudWatch Logs → `/aws/lambda/controlladoria-worker-*` |
| Lambda metrics | CloudWatch Metrics (invocations, errors, duration) |
| Queue depth | SQS Console → `controlladoria-document-processing-prod` |
| Billing | Stripe Dashboard |
| Email delivery | Resend Dashboard |
| Frontend build | Amplify Console → Build logs |

---

## Security Checklist

Before going live:

- [ ] `ENVIRONMENT=production` in Railway
- [ ] `FREE_DEMO_MODE=false`
- [ ] Stripe LIVE keys (not test `sk_test_...`)
- [ ] JWT_SECRET_KEY is unique and ≥ 64 chars
- [ ] CORS_ORIGINS lists only production domains (no `*`)
- [ ] `.env` files are in `.gitignore`
- [ ] No hardcoded secrets in code
- [ ] Stripe webhook signature verification active
- [ ] Rate limiting enabled
- [ ] Sysadmin UI on separate subdomain with access control
- [ ] First sysadmin account created and MFA enabled

---

## Known Issues to Fix Before Production

> These are code bugs that must be patched before the first prod deploy.

1. **`controlladoria-api/config.py` lines 122-124, 215-217** — domain names contain a space (`"controllad oria.com.br"`). Fix: remove the space.
2. **`controlladoria-api/api.py` lines 174-179** — CORS origins are hardcoded in a `if environment == "production"` block (with the broken domain names) instead of reading from `settings.cors_origins`. Fix: remove the hardcoded block and rely on `CORS_ORIGINS` env var.
3. **`controlladoria-sysadmin-ui/.env.example` line 5** — same space typo in commented prod URL.
