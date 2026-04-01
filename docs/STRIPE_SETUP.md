# Stripe Setup Guide

Complete guide to configure Stripe for subscription billing in ControlladorIA.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Step 1: Create Stripe Account](#step-1-create-stripe-account)
- [Step 2: Get API Keys](#step-2-get-api-keys)
- [Step 3: Create Product & Pricing](#step-3-create-product--pricing)
- [Step 4: Configure Webhooks](#step-4-configure-webhooks)
- [Step 5: Set Up Customer Portal](#step-5-set-up-customer-portal)
- [Step 6: Testing](#step-6-testing)
- [Step 7: Go Live](#step-7-go-live)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

- ✅ ControlladorIA backend running (api.py)
- ✅ HTTPS domain for production webhooks
- ✅ Stripe account (free to create)

---

## Step 1: Create Stripe Account

### 1.1 Sign Up

1. Go to [stripe.com](https://stripe.com)
2. Click **"Start now"** or **"Sign up"**
3. Enter email and create password
4. Verify email

### 1.2 Business Information

Stripe will ask for:
- Business type (select "Individual" or "Company")
- Country (Brazil - stripe.com supports Brazil!)
- Business details

**Note:** You can start in **Test Mode** without completing business verification.

---

## Step 2: Get API Keys

### 2.1 Access API Keys

1. Log in to [Stripe Dashboard](https://dashboard.stripe.com)
2. Click **"Developers"** in left sidebar
3. Click **"API keys"**

### 2.2 Copy Keys

You'll see two sets of keys:

**Test Mode Keys** (use these first):
- **Publishable key:** `pk_test_...`
- **Secret key:** `sk_test_...`

**Live Mode Keys** (use after going live):
- **Publishable key:** `pk_live_...`
- **Secret key:** `sk_live_...`

### 2.3 Add to Environment Variables

**Backend (.env):**
```bash
# Stripe API Keys (TEST MODE - for development)
STRIPE_API_KEY=sk_test_YOUR_KEY_HERE
```

**Frontend (.env.local):**
```bash
# Stripe Publishable Key (TEST MODE)
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_51xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

⚠️ **Security Warning:**
- **NEVER** commit `sk_test_` or `sk_live_` keys to Git
- Add `.env` to `.gitignore`
- Only use `pk_` keys in frontend (they're safe to expose)

---

## Step 3: Create Product & Pricing

### 3.1 Create Product

1. In Stripe Dashboard, go to **"Products"** (or **"Product Catalog"**)
2. Click **"Add product"**
3. Fill in details:
   - **Name:** `ControlladorIA Monthly Subscription`
   - **Description:** `Acesso ilimitado ao ControlladorIA - processamento de documentos com IA`
   - **Image:** Upload logo (optional but recommended)

### 3.2 Create Price

Still on the product creation page:

**Pricing Model:**
- Select: **"Standard pricing"**

**Price:**
- Amount: **R$ 99.00** (or your chosen price)
- Billing period: **Monthly**
- Currency: **BRL** (Brazilian Real)

**Free Trial:**
- ✅ Check **"Offer a free trial"**
- Trial period: **15 days**

**Billing Type:**
- Select: **"Recurring"**

**Payment Behavior:**
- Select: **"Charge automatically"**

### 3.3 Save and Copy Price ID

1. Click **"Add product"** or **"Save product"**
2. The product page will show the **Price ID**: `price_xxxxxxxxxxxxxxxxxxxxxxxx`
3. Copy this Price ID

### 3.4 Add Price ID to Environment

**Backend (.env):**
```bash
# Stripe Price ID (Monthly Subscription)
STRIPE_PRICE_ID=price_1xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Trial Settings
STRIPE_TRIAL_DAYS=15
```

### 3.5 Configure Success/Cancel URLs

**Backend (.env):**
```bash
# Stripe Checkout URLs
STRIPE_SUCCESS_URL=http://localhost:3000/  # Development
STRIPE_CANCEL_URL=http://localhost:3000/pricing

# For production, use your domain:
# STRIPE_SUCCESS_URL=https://yourdomain.com/
# STRIPE_CANCEL_URL=https://yourdomain.com/pricing
```

---

## Step 4: Configure Webhooks

Webhooks keep your database synchronized with Stripe subscription events.

### 4.1 Why Webhooks Are Critical

Stripe webhooks notify your backend when:
- ✅ User completes checkout (start trial)
- ✅ Trial ends (charge customer)
- ✅ Payment succeeds (activate subscription)
- ✅ Payment fails (suspend access)
- ✅ User cancels subscription

**Without webhooks, your app won't know about subscription changes!**

### 4.2 Local Testing with Stripe CLI (Development)

For local development, use Stripe CLI to forward webhooks:

```bash
# Install Stripe CLI
# Windows (Scoop)
scoop install stripe

# macOS (Homebrew)
brew install stripe/stripe-cli/stripe

# Linux
wget https://github.com/stripe/stripe-cli/releases/download/vX.X.X/stripe_X.X.X_linux_x86_64.tar.gz
tar -xvf stripe_X.X.X_linux_x86_64.tar.gz

# Login to Stripe
stripe login

# Forward webhooks to local server
stripe listen --forward-to http://localhost:8000/stripe/webhook
```

You'll see output like:
```
> Ready! Your webhook signing secret is whsec_xxxxxxxxxxxxxxxxxxxxx (^C to quit)
```

**Copy the webhook secret** and add to `.env`:
```bash
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxx
```

### 4.3 Production Webhook Setup

1. In Stripe Dashboard, go to **"Developers"** → **"Webhooks"**
2. Click **"Add endpoint"**
3. Enter endpoint URL:
   ```
   https://yourdomain.com/stripe/webhook
   ```
4. Select events to listen to:
   - ✅ `checkout.session.completed`
   - ✅ `customer.subscription.created`
   - ✅ `customer.subscription.updated`
   - ✅ `customer.subscription.deleted`
   - ✅ `invoice.payment_succeeded`
   - ✅ `invoice.payment_failed`

5. Click **"Add endpoint"**
6. Click on the newly created endpoint
7. Click **"Reveal"** next to **"Signing secret"**
8. Copy the secret (starts with `whsec_`)
9. Add to production `.env`:
   ```bash
   STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxx
   ```

### 4.4 Verify Webhook Setup

**Test webhook:**
```bash
# In Stripe Dashboard, go to webhook endpoint
# Click "Send test webhook"
# Select event: "customer.subscription.created"
# Click "Send test webhook"

# Check your backend logs - you should see:
# INFO - Processing Stripe webhook: customer.subscription.created
```

---

## Step 5: Set Up Customer Portal

The Customer Portal allows users to manage their subscriptions self-service.

### 5.1 Enable Customer Portal

1. In Stripe Dashboard, go to **"Settings"** → **"Billing"** → **"Customer portal"**
2. Click **"Activate"**

### 5.2 Configure Portal Features

**Features to enable:**
- ✅ Update payment method
- ✅ View invoices
- ✅ Cancel subscription
- ✅ Update billing email

**Business Information:**
- Add your business name
- Add support email
- Add terms of service URL (optional)
- Add privacy policy URL (optional)

### 5.3 Cancellation Settings

**Cancellation behavior:**
- Select: **"Cancel at end of billing period"** (default)
- This lets users keep access until they've paid for

OR

- Select: **"Cancel immediately"** (more aggressive)

**Recommendation:** Use **"Cancel at end of billing period"** for better UX.

### 5.4 Save Configuration

Click **"Save changes"**

### 5.5 Add Frontend URL

**Backend (.env):**
```bash
# Frontend URL (for portal redirects)
FRONTEND_URL=http://localhost:3000  # Development

# For production:
# FRONTEND_URL=https://yourdomain.com
```

---

## Step 6: Testing

### 6.1 Test Credit Cards

Stripe provides test cards for testing. **DO NOT USE REAL CARDS IN TEST MODE!**

**Successful Payment:**
- Card number: `4242 4242 4242 4242`
- Expiry: Any future date (e.g., `12/34`)
- CVC: Any 3 digits (e.g., `123`)
- ZIP: Any 5 digits (e.g., `12345`)

**Payment Requires Authentication (3D Secure):**
- Card number: `4000 0025 0000 3155`

**Payment Fails:**
- Card number: `4000 0000 0000 0002`

**Full list:** [Stripe Test Cards](https://stripe.com/docs/testing)

### 6.2 Test Flow

**Complete Subscription Flow:**

1. **Start backend:**
   ```bash
   cd D:\Users\Steve\Code\ControlladorIA
   uvicorn api:app --reload
   ```

2. **Start webhook forwarding** (in another terminal):
   ```bash
   stripe listen --forward-to http://localhost:8000/stripe/webhook
   ```

3. **Start frontend:**
   ```bash
   cd frontend
   npm run dev
   ```

4. **Test user journey:**
   - Go to http://localhost:3000/register
   - Create account with test email: `test@example.com`
   - Go to http://localhost:3000/pricing
   - Click **"Começar Teste Grátis"**
   - Fill in test card: `4242 4242 4242 4242`
   - Complete checkout
   - You should be redirected back to app
   - Go to http://localhost:3000/account/subscription
   - Verify subscription shows as "Período de Teste"

5. **Check webhook logs:**
   ```bash
   # You should see in Stripe CLI:
   checkout.session.completed [evt_xxx] Succeeded
   customer.subscription.created [evt_xxx] Succeeded
   ```

6. **Check database:**
   ```bash
   sqlite3 controlladoria.db
   SELECT * FROM subscriptions;
   # Should show subscription with status='trialing'
   ```

### 6.3 Test Customer Portal

1. While logged in, go to `/account/subscription`
2. Click **"Gerenciar Assinatura"**
3. Should redirect to Stripe Customer Portal
4. Test:
   - Update payment method
   - View invoices
   - Cancel subscription
   - Resume subscription

---

## Step 7: Go Live

### 7.1 Complete Stripe Activation

Before going live, Stripe requires:
1. Business verification
2. Bank account for payouts
3. Tax information

**To activate:**
1. Go to Stripe Dashboard
2. You'll see a banner: **"Activate your account"**
3. Click and complete all required steps

This typically takes 1-2 business days for approval.

### 7.2 Switch to Live Mode

1. In Stripe Dashboard, toggle switch from **"Test mode"** to **"Live mode"** (top right)
2. Get new API keys:
   - Go to **"Developers"** → **"API keys"**
   - Copy **Live** keys

### 7.3 Update Environment Variables

**Production backend (.env):**
```bash
# Stripe Live Keys
STRIPE_API_KEY=sk_live_YOUR_KEY_HERE
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxx  # From live webhook endpoint
STRIPE_PRICE_ID=price_xxxxxxxxxxxxxxxxxxxxx  # Live price ID

# Production URLs
STRIPE_SUCCESS_URL=https://yourdomain.com/
STRIPE_CANCEL_URL=https://yourdomain.com/pricing
FRONTEND_URL=https://yourdomain.com
```

**Production frontend (.env.local):**
```bash
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_live_51xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 7.4 Create Live Product & Price

**IMPORTANT:** Products and prices created in Test Mode don't exist in Live Mode!

Repeat **Step 3** in **Live Mode**:
1. Switch to Live Mode
2. Create product again
3. Set price to R$ 99/month
4. Set 15-day trial
5. Copy the **new** Price ID
6. Update `STRIPE_PRICE_ID` with live price ID

### 7.5 Create Live Webhook

Repeat **Step 4.3** in **Live Mode**:
1. Switch to Live Mode
2. Create webhook endpoint
3. Add same events
4. Copy signing secret
5. Update `STRIPE_WEBHOOK_SECRET`

### 7.6 Pre-Launch Checklist

- [ ] Stripe account fully activated
- [ ] Live API keys configured
- [ ] Live product created with correct price
- [ ] Live webhook configured and tested
- [ ] Customer Portal enabled in live mode
- [ ] HTTPS enabled on domain
- [ ] Test complete flow with real card (your own card, then refund)
- [ ] Monitor first real transactions closely

---

## Troubleshooting

### Issue: "Invalid API Key"

**Solution:**
- Check you're using correct key for mode (test vs live)
- Verify no extra spaces in `.env`
- Restart backend after changing `.env`

### Issue: Webhooks not received

**Solution:**
```bash
# Check webhook endpoint is accessible
curl -X POST https://yourdomain.com/stripe/webhook

# Check webhook secret is correct
# In api.py logs, you should see:
# "Processing Stripe webhook: <event_type>"

# Verify webhook endpoint in Stripe Dashboard
# Go to Developers → Webhooks → Click endpoint → Check status
```

### Issue: "No such price"

**Solution:**
- Ensure you copied Price ID correctly
- If using Live Mode, create product in Live Mode (not Test Mode)
- Price ID should start with `price_`

### Issue: Subscription not created after checkout

**Solution:**
- Check webhook logs
- Verify webhook secret matches
- Check database for subscription record
- Look for errors in backend logs

### Issue: Customer Portal not working

**Solution:**
- Ensure Customer Portal is activated (Settings → Billing → Customer portal)
- Check user has subscription (subscription.stripe_customer_id exists)
- Verify frontend URL is correct in settings

### Issue: 3D Secure authentication fails

**Solution:**
- In test mode, use test cards that don't require auth: `4242 4242 4242 4242`
- For testing 3D Secure, use: `4000 0025 0000 3155` and follow prompts
- In live mode, this is handled by customer's bank

---

## Configuration Reference

### Complete .env Example

**Backend (.env):**
```bash
# === Stripe Configuration (TEST MODE) ===
STRIPE_API_KEY=sk_test_YOUR_KEY_HERE
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxx
STRIPE_PRICE_ID=price_xxxxxxxxxxxxxxxxxxxxx
STRIPE_TRIAL_DAYS=15
STRIPE_SUCCESS_URL=http://localhost:3000/
STRIPE_CANCEL_URL=http://localhost:3000/pricing
FRONTEND_URL=http://localhost:3000

# === For Production (Switch to Live Keys) ===
# STRIPE_API_KEY=sk_live_51xxxxxxxx
# STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxx
# STRIPE_PRICE_ID=price_xxxxxxxx
# STRIPE_SUCCESS_URL=https://yourdomain.com/
# STRIPE_CANCEL_URL=https://yourdomain.com/pricing
# FRONTEND_URL=https://yourdomain.com
```

**Frontend (.env.local):**
```bash
# === Stripe Configuration (TEST MODE) ===
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_51xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NEXT_PUBLIC_API_URL=http://localhost:8000

# === For Production ===
# NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_live_51xxxxxxxx
# NEXT_PUBLIC_API_URL=https://api.yourdomain.com
```

---

## Monitoring & Analytics

### Stripe Dashboard Metrics

Monitor these key metrics:
- **MRR (Monthly Recurring Revenue):** Total monthly revenue
- **Active Subscriptions:** Number of paying customers
- **Churn Rate:** Percentage of cancellations
- **Trial Conversion:** % of trials that convert to paid

### Useful Stripe Reports

1. **Revenue:** Dashboard → Home (shows MRR growth)
2. **Subscriptions:** Billing → Subscriptions (list all subscriptions)
3. **Customers:** Customers tab (view all customers)
4. **Failed Payments:** Billing → Failed payments

---

## Next Steps

1. ✅ Complete all 7 steps above
2. ✅ Test thoroughly in Test Mode
3. ✅ When ready, activate Stripe account
4. ✅ Switch to Live Mode
5. ✅ Create live products/webhooks
6. ✅ Update environment variables
7. ✅ Deploy to production
8. ✅ Monitor first transactions closely

For deployment instructions, see [DEPLOYMENT.md](./DEPLOYMENT.md)

---

## Additional Resources

- [Stripe Documentation](https://stripe.com/docs)
- [Stripe API Reference](https://stripe.com/docs/api)
- [Stripe Testing Guide](https://stripe.com/docs/testing)
- [Stripe Webhooks Guide](https://stripe.com/docs/webhooks)
- [Stripe Customer Portal Docs](https://stripe.com/docs/billing/subscriptions/integrating-customer-portal)
