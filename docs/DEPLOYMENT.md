# Deployment Guide

Complete guide for deploying ControlladorIA to production.

## Table of Contents
- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Backend Deployment](#backend-deployment)
- [Frontend Deployment](#frontend-deployment)
- [Database Setup](#database-setup)
- [Environment Variables](#environment-variables)
- [Post-Deployment](#post-deployment)
- [Monitoring & Maintenance](#monitoring--maintenance)

---

## Architecture Overview

ControlladorIA consists of three main components:

```
┌─────────────┐      ┌─────────────┐      ┌──────────────┐
│   Frontend  │ ───> │   Backend   │ ───> │  PostgreSQL  │
│  (Next.js)  │      │  (FastAPI)  │      │   Database   │
│   Vercel    │      │  Render.com │      │  Render.com  │
└─────────────┘      └─────────────┘      └──────────────┘
       │                    │
       │                    ↓
       │             ┌─────────────┐
       │             │   Stripe    │
       │             │   Webhooks  │
       └────────────>└─────────────┘
```

**Recommended Stack:**
- **Frontend:** Vercel (Next.js optimized)
- **Backend:** Render.com or Railway
- **Database:** Render.com PostgreSQL or Neon
- **Payments:** Stripe
- **Email:** Resend

---

## Prerequisites

Before deploying, ensure you have:

- [ ] GitHub account
- [ ] Vercel account (free tier OK)
- [ ] Render.com or Railway account
- [ ] Stripe account (configured - see [STRIPE_SETUP.md](./STRIPE_SETUP.md))
- [ ] Domain name (optional but recommended)
- [ ] SSL certificate (automatic with Vercel/Render)

---

## Backend Deployment

### Option 1: Render.com (Recommended)

#### Step 1: Prepare Repository

Ensure your repo has:
- `requirements.txt` with all dependencies
- `api.py` as main application file
- `alembic/` directory with migrations

#### Step 2: Create Web Service

1. Go to [render.com](https://render.com)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Configure:
   - **Name:** `controlladoria-api`
   - **Region:** Choose closest to users
   - **Branch:** `main`
   - **Root Directory:** (leave blank or set to root)
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn api:app --host 0.0.0.0 --port $PORT`

#### Step 3: Add Environment Variables

Click **"Advanced"** → Add environment variables:

```bash
# AI Provider
AI_PROVIDER=openai  # or anthropic
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...

# Database (will be set after creating PostgreSQL instance)
DATABASE_URL=postgresql://...

# JWT
JWT_SECRET_KEY=<generate-with-openssl-rand-hex-32>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Stripe (LIVE KEYS for production)
STRIPE_API_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
STRIPE_TRIAL_DAYS=15
STRIPE_SUCCESS_URL=https://yourdomain.com/
STRIPE_CANCEL_URL=https://yourdomain.com/pricing

# Email (Resend)
RESEND_API_KEY=re_...
FROM_EMAIL=noreply@yourdomain.com

# Frontend URL
FRONTEND_URL=https://yourdomain.com

# CORS
CORS_ORIGINS=https://yourdomain.com

# Environment
ENVIRONMENT=production

# File Storage
MAX_UPLOAD_SIZE=52428800  # 50MB

# Rate Limiting
RATE_LIMIT_ENABLED=true
```

#### Step 4: Deploy

1. Click **"Create Web Service"**
2. Render will:
   - Clone your repo
   - Install dependencies
   - Start the server
   - Provide a URL: `https://controlladoria-api.onrender.com`

#### Step 5: Run Migrations

After first deploy:
```bash
# Using Render Shell
# Go to dashboard → Your service → Shell tab
alembic upgrade head
```

### Option 2: Railway

1. Go to [railway.app](https://railway.app)
2. **New Project** → **Deploy from GitHub**
3. Select repository
4. Railway auto-detects Python
5. Add environment variables (same as Render)
6. Deploy
7. Run migrations via Railway CLI:
   ```bash
   railway run alembic upgrade head
   ```

---

## Frontend Deployment

### Vercel (Recommended for Next.js)

#### Step 1: Prepare Repository

Ensure `frontend/` directory has:
- `package.json`
- `next.config.ts`
- `.env.local.example` (but NOT `.env.local` - don't commit secrets!)

#### Step 2: Connect to Vercel

1. Go to [vercel.com](https://vercel.com)
2. Click **"Add New Project"**
3. Import your GitHub repository
4. Vercel will auto-detect Next.js

#### Step 3: Configure Build Settings

- **Framework Preset:** Next.js
- **Root Directory:** `frontend`
- **Build Command:** `npm run build` (auto-detected)
- **Output Directory:** `.next` (auto-detected)
- **Install Command:** `npm install` (auto-detected)

#### Step 4: Environment Variables

Add to Vercel project settings:

```bash
NEXT_PUBLIC_API_URL=https://controlladoria-api.onrender.com  # Your backend URL
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_live_...  # Stripe LIVE publishable key
```

⚠️ **Important:** Only `NEXT_PUBLIC_` variables are exposed to browser. Keep secrets in backend!

#### Step 5: Deploy

1. Click **"Deploy"**
2. Vercel will:
   - Build Next.js app
   - Deploy to CDN
   - Provide URL: `https://controlladoria.vercel.app`

#### Step 6: Custom Domain (Optional)

1. In Vercel project settings → **"Domains"**
2. Add your domain: `yourdomain.com`
3. Follow DNS configuration instructions
4. Vercel provides automatic SSL

---

## Database Setup

### Render PostgreSQL (Recommended)

#### Step 1: Create Database

1. In Render dashboard, click **"New +"** → **"PostgreSQL"**
2. Configure:
   - **Name:** `controlladoria-db`
   - **Database:** `controlladoria`
   - **User:** `controlladoria`
   - **Region:** Same as backend
   - **Plan:** Starter ($7/month minimum for production)

#### Step 2: Get Connection String

1. Click on created database
2. Copy **"External Database URL"**
3. Format: `postgresql://user:password@host:port/database`

#### Step 3: Add to Backend

1. Go to backend web service
2. **Environment** → Edit `DATABASE_URL`
3. Paste connection string
4. Save
5. Service will auto-redeploy

#### Step 4: Run Migrations

```bash
# In Render Shell (backend service → Shell tab)
alembic upgrade head
```

### Alternative: Neon (Serverless)

1. Go to [neon.tech](https://neon.tech)
2. Create project
3. Copy connection string
4. Add to backend environment variables
5. Run migrations

See [DATABASE_SETUP.md](./DATABASE_SETUP.md) for more options.

---

## Environment Variables

### Backend Environment Variables (Complete Reference)

```bash
# ===== AI Provider =====
AI_PROVIDER=openai
OPENAI_API_KEY=sk-proj-...
# ANTHROPIC_API_KEY=sk-ant-...

# ===== Database =====
DATABASE_URL=postgresql://user:password@host:port/database

# ===== Authentication =====
JWT_SECRET_KEY=your-secret-key-generate-with-openssl-rand-hex-32
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# ===== Stripe =====
STRIPE_API_KEY=sk_live_51...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
STRIPE_TRIAL_DAYS=15
STRIPE_SUCCESS_URL=https://yourdomain.com/
STRIPE_CANCEL_URL=https://yourdomain.com/pricing

# ===== Email (Resend) =====
RESEND_API_KEY=re_...
FROM_EMAIL=noreply@yourdomain.com

# ===== URLs =====
FRONTEND_URL=https://yourdomain.com
CORS_ORIGINS=https://yourdomain.com

# ===== Application =====
ENVIRONMENT=production
API_TITLE=ControlladorIA API
API_VERSION=1.0.0

# ===== File Upload =====
MAX_UPLOAD_SIZE=52428800  # 50MB in bytes

# ===== Rate Limiting =====
RATE_LIMIT_ENABLED=true
UPLOAD_RATE_LIMIT=10/minute
CONTACT_RATE_LIMIT=5/hour

# ===== File Cleanup =====
FILE_CLEANUP_ENABLED=true
FILE_RETENTION_DAYS=365
CLEANUP_ORPHANED_FILES=true
CLEANUP_SCHEDULE_HOUR=2

# ===== Logging =====
LOG_LEVEL=INFO
```

### Frontend Environment Variables

```bash
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_live_51...
```

---

## Post-Deployment

### 1. Configure Stripe Webhooks

Update webhook URL to production:

1. Stripe Dashboard → **Developers** → **Webhooks**
2. Add endpoint: `https://controlladoria-api.onrender.com/stripe/webhook`
3. Select events:
   - checkout.session.completed
   - customer.subscription.created
   - customer.subscription.updated
   - customer.subscription.deleted
   - invoice.payment_succeeded
   - invoice.payment_failed
4. Copy webhook signing secret
5. Update backend environment: `STRIPE_WEBHOOK_SECRET`

### 2. Test Production Flow

**Critical test paths:**

1. **User Registration:**
   - Go to https://yourdomain.com/register
   - Create account
   - Verify email in logs (Resend dashboard)

2. **Subscription Flow:**
   - Login
   - Go to /pricing
   - Start trial with real card (you can cancel immediately)
   - Check Stripe dashboard for subscription
   - Check database for subscription record

3. **Document Upload:**
   - Upload test PDF
   - Verify processing
   - Check file storage

4. **Webhook Verification:**
   - In Stripe, send test webhook
   - Check backend logs for webhook received
   - Verify database updated

### 3. Health Check

Test all endpoints:

```bash
# Health check
curl https://controlladoria-api.onrender.com/health

# Should return:
# {"status":"healthy","timestamp":"...","checks":{...}}
```

### 4. Setup Monitoring

#### Render Monitoring

- Automatic in Render dashboard
- View logs, CPU, memory
- Set up email alerts

#### Sentry (Error Tracking)

```bash
# Install
pip install sentry-sdk[fastapi]

# In api.py (top of file)
import sentry_sdk
sentry_sdk.init(
    dsn="https://...@sentry.io/...",
    environment="production"
)
```

Add to Vercel:
```bash
npm install @sentry/nextjs
npx @sentry/wizard@latest -i nextjs
```

---

## Monitoring & Maintenance

### Daily Checks

- [ ] Check error logs (Render dashboard)
- [ ] Monitor Stripe dashboard for failed payments
- [ ] Check database size (stay under plan limits)

### Weekly Checks

- [ ] Review Sentry errors (if configured)
- [ ] Check failed payment retries
- [ ] Monitor API response times

### Monthly Checks

- [ ] Review hosting costs
- [ ] Check database backups
- [ ] Test restore process
- [ ] Update dependencies:
  ```bash
  pip list --outdated
  npm outdated
  ```

### Backup Strategy

**Automated (via Render):**
- Daily automatic backups (included in Starter plan+)
- Retention: 7 days (Starter), 30 days (Standard)

**Manual Backups:**
```bash
# Download database backup
# Render Dashboard → Database → Backups → Download

# Or via pg_dump
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql
```

**Backup Schedule:**
- Daily: Automated (via Render)
- Weekly: Manual download to local storage
- Before migrations: Always backup first

### Scaling Considerations

**When to upgrade:**

| Metric | Free/Starter Limit | Action |
|--------|-------------------|--------|
| Users | 100-500 | Upgrade to Standard plan |
| Database | >1GB | Upgrade Render DB plan or migrate to AWS RDS |
| API requests | >100/min sustained | Add load balancer, multiple instances |
| Storage | >10GB files | Move to S3/CloudFlare R2 |

---

## Troubleshooting

### Build Fails

**Frontend build error:**
```bash
# Check Vercel build logs
# Common issues:
# - Missing environment variables
# - TypeScript errors
# - Import errors

# Test locally first:
cd frontend
npm run build
```

**Backend build error:**
```bash
# Check Render logs
# Common issues:
# - Missing dependencies in requirements.txt
# - Python version mismatch
```

### 500 Internal Server Error

**Check backend logs:**
1. Render Dashboard → Your service → Logs
2. Look for Python errors
3. Common issues:
   - Missing environment variable
   - Database connection failed
   - AI API key invalid

### Webhook Not Working

```bash
# Test webhook manually
curl -X POST https://controlladoria-api.onrender.com/stripe/webhook \
  -H "Content-Type: application/json" \
  -d '{}'

# Should return 400 (invalid payload) but proves endpoint is accessible

# Check Stripe webhook status
# Stripe Dashboard → Webhooks → Your endpoint → Recent events
```

### Database Connection Issues

```bash
# Test connection
psql $DATABASE_URL

# Check connection pool settings
# In database.py, ensure pool_size is reasonable for your plan
```

---

## Security Checklist

Before going live:

- [ ] All API keys in environment variables (not code)
- [ ] `.env` files in `.gitignore`
- [ ] HTTPS enabled (automatic with Vercel/Render)
- [ ] CORS configured correctly (only your domain)
- [ ] Stripe webhook signature verification enabled
- [ ] Rate limiting enabled
- [ ] SQL injection protection (using SQLAlchemy ORM)
- [ ] XSS protection (React auto-escaping)
- [ ] JWT tokens expire (30 minutes)
- [ ] Database backups enabled
- [ ] Error messages don't leak sensitive info

---

## Rollback Procedure

If deployment fails:

### Frontend Rollback (Vercel)
1. Vercel Dashboard → Deployments
2. Find previous working deployment
3. Click "..." → "Promote to Production"

### Backend Rollback (Render)
1. Render Dashboard → Your service
2. Manual Deploy → Select previous commit
3. Deploy

### Database Rollback
```bash
# Rollback migration
alembic downgrade -1

# Restore from backup
psql $DATABASE_URL < backup_YYYYMMDD.sql
```

---

## Performance Optimization

### Frontend (Vercel)

- ✅ Automatic CDN
- ✅ Edge caching
- ✅ Image optimization (use Next.js Image)
- ✅ Code splitting (automatic)

### Backend (Render)

**Caching:**
```python
# Add Redis for session caching (optional)
# Render Dashboard → New Redis instance
# Update api.py with Redis caching
```

**Database Optimization:**
```sql
-- Add indexes for frequently queried fields
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_user_upload ON documents(user_id, upload_date DESC);
```

---

## Cost Estimation

**Minimum Production Setup:**

| Service | Plan | Cost/Month |
|---------|------|------------|
| Render Backend | Starter | $7 |
| Render PostgreSQL | Starter | $7 |
| Vercel Frontend | Free | $0 |
| Stripe | Transaction fees | 2.9% + $0.30 |
| Domain | Namecheap | ~$1 |
| **Total** | | **~$15/month** |

**With Growth (100 users):**

| Service | Plan | Cost/Month |
|---------|------|------------|
| Render Backend | Standard | $25 |
| PostgreSQL | Standard | $20 |
| Vercel Frontend | Pro (optional) | $0-20 |
| AI API Costs | Pay-per-use | $10-50 |
| **Total** | | **~$55-115/month** |

---

## Next Steps

1. ✅ Deploy backend to Render
2. ✅ Deploy frontend to Vercel
3. ✅ Set up production database
4. ✅ Configure all environment variables
5. ✅ Run database migrations
6. ✅ Configure Stripe webhooks
7. ✅ Test complete user flow
8. ✅ Set up monitoring
9. ✅ Configure custom domain
10. ✅ Go live!

---

## Support Resources

- **Render Docs:** https://render.com/docs
- **Vercel Docs:** https://vercel.com/docs
- **Next.js Docs:** https://nextjs.org/docs
- **FastAPI Docs:** https://fastapi.tiangolo.com
- **Stripe Docs:** https://stripe.com/docs

For ControlladorIA-specific issues, check:
- [DATABASE_SETUP.md](./DATABASE_SETUP.md)
- [STRIPE_SETUP.md](./STRIPE_SETUP.md)
- [GitHub Issues](https://github.com/yourusername/ControlladorIA/issues)
