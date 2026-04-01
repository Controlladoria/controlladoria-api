# Database Setup Guide

This guide covers database setup for both development and production environments.

## Table of Contents
- [Development Setup (SQLite)](#development-setup-sqlite)
- [Production Setup (PostgreSQL)](#production-setup-postgresql)
- [Hosting Providers Comparison](#hosting-providers-comparison)
- [Migration Workflow](#migration-workflow)
- [Backup Strategy](#backup-strategy)

---

## Development Setup (SQLite)

SQLite is used for local development. No installation required!

### Quick Start

1. **Environment variables** - Already configured in `.env`:
```bash
DATABASE_URL=sqlite:///./controlladoria.db
```

2. **Initialize database**:
```bash
# Create tables
alembic upgrade head
```

3. **Database location**:
- File: `controlladoria.db` (in project root)
- Automatically created on first run

### SQLite Limitations

⚠️ **Do NOT use SQLite in production:**
- Limited concurrent writes
- No built-in replication
- File-based (not suitable for cloud)
- Max database size: ~281 TB (but performance degrades earlier)

---

## Production Setup (PostgreSQL)

PostgreSQL is **required** for production deployment.

### Why PostgreSQL?

✅ **Advantages:**
- Full ACID compliance
- Excellent concurrent write performance
- Advanced indexing and query optimization
- JSON/JSONB support for extracted_data_json
- Built-in full-text search
- Robust replication and backup tools
- Industry standard for production SaaS

### Local PostgreSQL Setup

#### Option 1: Docker (Recommended)

```bash
# Run PostgreSQL in Docker
docker run -d \
  --name controlladoria-postgres \
  -e POSTGRES_USER=controlladoria \
  -e POSTGRES_PASSWORD=your_secure_password \
  -e POSTGRES_DB=controlladoria \
  -p 5432:5432 \
  postgres:16-alpine

# Connection string
DATABASE_URL=postgresql://controlladoria:your_secure_password@localhost:5432/controlladoria
```

#### Option 2: Native Installation

**Windows:**
```bash
# Download installer from postgresql.org
# Or use Chocolatey:
choco install postgresql

# Create database
psql -U postgres
CREATE DATABASE controlladoria;
CREATE USER controlladoria WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE controlladoria TO controlladoria;
```

**Linux/Mac:**
```bash
# Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib

# macOS (Homebrew)
brew install postgresql@16

# Create database
createdb controlladoria
```

### Update Environment Variables

Update `.env`:
```bash
# Replace SQLite URL with PostgreSQL
DATABASE_URL=postgresql://controlladoria:your_secure_password@localhost:5432/controlladoria
```

### Run Migrations

```bash
# Apply all migrations
alembic upgrade head

# Verify tables created
psql -U controlladoria -d controlladoria -c "\dt"
```

---

## Hosting Providers Comparison

### 1. Render.com ⭐ **RECOMMENDED FOR MVP/STARTUP**

**Pros:**
- ✅ Free tier available (good for POC)
- ✅ Extremely easy setup (1-click)
- ✅ Automatic backups
- ✅ Built-in SSL
- ✅ No credit card for free tier
- ✅ Great for small teams

**Cons:**
- ❌ Free tier expires data after 90 days
- ❌ Limited storage (1GB free)
- ❌ Slower performance than AWS

**Pricing:**
- Free: 1GB storage, 90-day data retention
- Starter: $7/month - 10GB storage, daily backups
- Standard: $20/month - 50GB storage, hourly backups

**Setup Time:** 5 minutes

**Best For:** MVP, proof of concept, early-stage startups

**How to Set Up:**
1. Go to [render.com](https://render.com)
2. New → PostgreSQL
3. Name: `controlladoria-db`
4. Region: Choose closest to users
5. Instance Type: Free or Starter
6. Copy "External Database URL"
7. Add to your `.env` as `DATABASE_URL`

---

### 2. Railway.app 🚀 **BEST FOR DEVELOPERS**

**Pros:**
- ✅ Developer-friendly UI
- ✅ $5 free credit monthly
- ✅ Pay-as-you-go pricing
- ✅ Easy GitHub integration
- ✅ Automatic deployments
- ✅ Fast provisioning

**Cons:**
- ❌ No free tier (uses free credits)
- ❌ Credits run out quickly with heavy usage

**Pricing:**
- $0.000231/GB-hour (~$5-10/month typical usage)
- Includes backups, SSL

**Setup Time:** 3 minutes

**Best For:** Developer productivity, rapid iteration

**How to Set Up:**
1. Go to [railway.app](https://railway.app)
2. New Project → Add PostgreSQL
3. Variables tab → Copy `DATABASE_URL`
4. Add to your `.env`

---

### 3. Heroku Postgres 🏢 **CLASSIC CHOICE**

**Pros:**
- ✅ Mature, reliable platform
- ✅ Excellent CLI tools
- ✅ Strong ecosystem
- ✅ Well-documented

**Cons:**
- ❌ No free tier (since Nov 2022)
- ❌ More expensive than alternatives
- ❌ Slower than specialized DB hosts

**Pricing:**
- Mini: $5/month - 1GB storage
- Basic: $9/month - 10GB storage
- Standard: $50/month - 64GB storage

**Setup Time:** 10 minutes

**Best For:** Teams already on Heroku ecosystem

**How to Set Up:**
```bash
# Install Heroku CLI
npm install -g heroku

# Login
heroku login

# Create database
heroku addons:create heroku-postgresql:mini -a your-app-name

# Get connection string
heroku config:get DATABASE_URL -a your-app-name
```

---

### 4. AWS RDS 🏆 **ENTERPRISE PRODUCTION**

**Pros:**
- ✅ Enterprise-grade reliability (99.95% SLA)
- ✅ Advanced features (read replicas, multi-AZ)
- ✅ Excellent performance
- ✅ Scales to massive workloads
- ✅ Integration with AWS ecosystem

**Cons:**
- ❌ Complex setup
- ❌ Higher cost
- ❌ Requires AWS knowledge
- ❌ No free tier for production

**Pricing:**
- db.t3.micro: ~$15-20/month (20GB storage)
- db.t3.small: ~$30-40/month (100GB storage)
- Additional costs: backups, data transfer

**Setup Time:** 30-60 minutes

**Best For:** Established businesses, high-traffic applications

**How to Set Up:**
1. AWS Console → RDS → Create Database
2. Engine: PostgreSQL 16
3. Template: Free tier (dev) or Production
4. Instance: db.t3.micro
5. Storage: 20GB (auto-scaling enabled)
6. Connectivity: Public access (for now)
7. Create database
8. Copy endpoint from RDS console
9. Connection string: `postgresql://username:password@endpoint:5432/controlladoria`

---

### 5. DigitalOcean Managed Databases 💧 **PREDICTABLE PRICING**

**Pros:**
- ✅ Transparent, predictable pricing
- ✅ Good performance/cost ratio
- ✅ Simple interface
- ✅ Reliable infrastructure

**Cons:**
- ❌ No free tier
- ❌ Less feature-rich than AWS

**Pricing:**
- Basic: $15/month - 1GB RAM, 10GB storage
- Standard: $60/month - 4GB RAM, 38GB storage

**Setup Time:** 15 minutes

**Best For:** Stable, predictable workloads

---

### 6. Neon.tech ⚡ **SERVERLESS POSTGRES**

**Pros:**
- ✅ Serverless (scales to zero)
- ✅ Free tier with generous limits
- ✅ Branching for dev environments
- ✅ Fast cold starts
- ✅ Modern, developer-friendly

**Cons:**
- ❌ Newer platform (less proven)
- ❌ Limited regions

**Pricing:**
- Free: 0.5GB storage, 100 hours compute/month
- Pro: $19/month - Unlimited compute

**Setup Time:** 2 minutes

**Best For:** Side projects, startups with variable traffic

**How to Set Up:**
1. Go to [neon.tech](https://neon.tech)
2. Create Project
3. Copy connection string
4. Add to `.env`

---

## Provider Recommendation Matrix

| Use Case | Recommended Provider | Alternative |
|----------|---------------------|-------------|
| **Just testing/POC** | Render (Free) | Neon (Free) |
| **MVP/Early Startup** | Render (Starter $7) | Railway ($5-10) |
| **Growing Startup** | Railway or DigitalOcean | AWS RDS (t3.micro) |
| **Established Business** | AWS RDS (t3.small+) | DigitalOcean (Standard) |
| **Enterprise** | AWS RDS (Multi-AZ) | GCP Cloud SQL |
| **Variable Traffic** | Neon (Serverless) | Railway |

### Our Recommendation for ControlladorIA:

**Phase 1 (Now):** Render.com Starter ($7/month)
- Easy to set up
- Affordable
- Sufficient for first 100-1000 users
- Daily backups included

**Phase 2 (Growth):** Railway or DigitalOcean ($15-20/month)
- Better performance
- More storage
- When you hit 1000+ users

**Phase 3 (Scale):** AWS RDS ($30-50/month)
- When you need enterprise features
- 10,000+ users
- Multi-AZ, read replicas

---

## Migration Workflow

### Creating Migrations

```bash
# After modifying database.py models
alembic revision --autogenerate -m "description of changes"

# Review generated migration in alembic/versions/
# Edit if necessary (especially for data migrations)

# Apply migration
alembic upgrade head
```

### Rollback

```bash
# Rollback one migration
alembic downgrade -1

# Rollback to specific version
alembic downgrade <revision_id>

# Rollback all
alembic downgrade base
```

### Production Migration Process

**IMPORTANT:** Always test migrations on a staging database first!

```bash
# 1. Backup production database
pg_dump -U controlladoria -d controlladoria > backup_$(date +%Y%m%d).sql

# 2. Test migration on staging
alembic upgrade head

# 3. If successful, apply to production
# (Use your production DATABASE_URL)
alembic upgrade head

# 4. Verify
psql $DATABASE_URL -c "SELECT version_num FROM alembic_version;"
```

---

## Backup Strategy

### Automated Backups (Provider-Managed)

Most providers offer automatic backups:
- **Render:** Daily backups (Starter+)
- **Railway:** Included with all plans
- **AWS RDS:** Automated daily backups (configurable retention)
- **DigitalOcean:** Daily backups included

### Manual Backups

```bash
# Full database dump
pg_dump -U controlladoria -d controlladoria -F c -f controlladoria_backup.dump

# Restore from dump
pg_restore -U controlladoria -d controlladoria -c controlladoria_backup.dump

# SQL format (human-readable)
pg_dump -U controlladoria -d controlladoria > controlladoria_backup.sql
psql -U controlladoria -d controlladoria < controlladoria_backup.sql
```

### Backup Schedule Recommendation

- **Daily:** Automated backups via provider
- **Weekly:** Manual export for off-site storage
- **Before migrations:** Always backup before running migrations
- **Monthly:** Test restore process (verify backups work!)

---

## Performance Optimization

### Indexing Strategy

Already implemented in `database.py`:
- User email (unique index)
- Document user_id (foreign key index)
- Document status (filter index)

### Connection Pooling

For production, use connection pooling:

```bash
# Install
pip install psycopg2-pool

# Or use SQLAlchemy's pooling (already configured)
# In database.py, the engine uses:
# pool_size=5, max_overflow=10
```

### Monitoring Queries

```sql
-- Show slow queries
SELECT pid, query, state, query_start
FROM pg_stat_activity
WHERE state = 'active'
AND query_start < NOW() - INTERVAL '5 seconds';

-- Show table sizes
SELECT
  tablename,
  pg_size_pretty(pg_total_relation_size(tablename::regclass)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(tablename::regclass) DESC;
```

---

## Troubleshooting

### Connection Refused

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check port
netstat -an | grep 5432

# Verify connection string format
# postgresql://username:password@host:port/database
```

### Permission Errors

```sql
-- Grant all permissions
GRANT ALL PRIVILEGES ON DATABASE controlladoria TO controlladoria;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO controlladoria;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO controlladoria;
```

### Migration Conflicts

```bash
# If migrations conflict, stamp current state
alembic stamp head

# Then create new migration
alembic revision --autogenerate -m "fix conflicts"
```

---

## Next Steps

1. ✅ Choose a provider based on your stage
2. ✅ Set up database
3. ✅ Update `DATABASE_URL` in `.env`
4. ✅ Run migrations: `alembic upgrade head`
5. ✅ Test connection
6. ✅ Set up automated backups
7. ✅ Configure monitoring (optional)

For production deployment, see [DEPLOYMENT.md](./DEPLOYMENT.md)
