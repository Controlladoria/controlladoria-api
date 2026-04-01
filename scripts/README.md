# Admin Scripts

Utility scripts for ControlladorIA administration.

## Make Admin Script

Create or promote users to admin role.

### Usage

**Promote existing user to admin:**
```bash
python scripts/make_admin.py user@example.com
```

**Create new admin user (if doesn't exist):**
```bash
python scripts/make_admin.py admin@controlladoria.com.br --create
```

You'll be prompted for:
- Password (min 8 characters)
- Full name (optional)
- Company name (optional)

**List all admin users:**
```bash
python scripts/make_admin.py --list
```

### Examples

```bash
# Promote existing user
$ python scripts/make_admin.py steve@company.com
Promoting 'steve@company.com' to admin...
✅ User promoted to admin successfully!
   Email: steve@company.com
   Name: Steve Jobs
   Admin: True

# Create new admin
$ python scripts/make_admin.py admin@controlladoria.com.br --create
User 'admin@controlladoria.com.br' not found. Creating new admin user...
Enter password for new admin user: ********
Confirm password: ********
Enter full name (optional): System Administrator
Enter company name (optional): ControlladorIA
✅ Admin user created successfully!
   Email: admin@controlladoria.com.br
   Name: System Administrator
   Admin: True

# List admins
$ python scripts/make_admin.py --list

📋 Admin Users (2):
--------------------------------------------------------------------------------
  Email: admin@controlladoria.com.br
  Name: System Administrator
  Active: Yes
  Created: 2026-01-24
--------------------------------------------------------------------------------
  Email: steve@company.com
  Name: Steve Jobs
  Active: Yes
  Created: 2026-01-15
--------------------------------------------------------------------------------
```

### Requirements

- Database must be accessible (check DATABASE_URL in .env)
- Run from project root directory

### Security Notes

- Passwords are hashed with bcrypt before storage
- Admin users have full access to `/admin` dashboard
- Admin role cannot be self-assigned via UI (must use this script)
- Only users with `is_admin=True` can access admin endpoints
