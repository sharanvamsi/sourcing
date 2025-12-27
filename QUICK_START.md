# Quick Start: Launching abasourcing.com

## Immediate Next Steps

### 1. Fix Security Issue (CRITICAL - Do This First!)
The app currently has a hardcoded password. Before sharing with users:

**Option A: Use Environment Variable (Recommended)**
```bash
# In your deployment platform (Railway/Render/etc), add:
CLUB_PASSWORD=your-secure-password-here
```

**Option B: Update Password in Code**
- Edit `app.py` line 110
- Change `"club2025"` to your new password
- Commit and push

### 2. Set Up Domain

**If using Railway:**
1. Go to Railway → Your Project → Settings → Networking
2. Click "Add Custom Domain"
3. Enter: `abasourcing.com`
4. Railway will show you a CNAME record
5. Go to your domain registrar (where you bought abasourcing.com)
6. Add CNAME record:
   - Name: `@` or `abasourcing.com`
   - Value: `[railway-provided-hostname].railway.app`
   - TTL: 3600
7. Wait 5-60 minutes for DNS propagation

**If using Render:**
1. Go to Render → Your Service → Settings → Custom Domain
2. Add domain: `abasourcing.com`
3. Follow Render's DNS instructions
4. Add A record pointing to Render's IP

### 3. Verify Environment Variables

Make sure these are set in your deployment platform:

```bash
# Required
DATABASE_URL=postgresql://...
MASTER_ENCRYPTION_SECRET=your-strong-secret-key

# Recommended
CLUB_PASSWORD=your-secure-password
SENTRY_DSN=https://...
ADMIN_EMAIL=admin@abasourcing.com
```

### 4. Sync User Roster

If you have users in `roster.json`:
```bash
python cloud_sync.py
```

Or add users via Admin panel once deployed.

### 5. Test Before Sharing

1. Visit https://abasourcing.com
2. Test login with a test user
3. Test search functionality
4. Test enrichment
5. Test CSV export
6. Check Sentry for any errors

### 6. Share with Users

Send an email with:
- **URL**: https://abasourcing.com
- **Password**: [Share securely]
- **Instructions**: How to get Apollo API keys and configure them

---

## Common Issues

**Domain not working?**
- Check DNS propagation: https://www.whatsmydns.net/#CNAME/abasourcing.com
- Verify CNAME/A records are correct
- Wait up to 48 hours for full propagation

**SSL certificate issues?**
- Most platforms auto-provision SSL
- Ensure DNS is configured first
- Wait 10-60 minutes after DNS is correct

**Can't login?**
- Verify user exists in database
- Check password matches CLUB_PASSWORD env var
- Check Sentry for error logs

**API errors?**
- Verify users have configured their Apollo API keys
- Check API key permissions
- Review Sentry error logs

---

## Support

For issues, check:
1. Sentry dashboard for errors
2. Deployment platform logs
3. Database connection status

---

## Launch Checklist

- [ ] Password is secure (not hardcoded)
- [ ] Domain is configured (abasourcing.com)
- [ ] SSL certificate is active
- [ ] Environment variables are set
- [ ] Database is connected
- [ ] Users are synced
- [ ] Test login works
- [ ] Test search works
- [ ] Test enrichment works
- [ ] Sentry monitoring is active
- [ ] User documentation is ready
- [ ] Support channel is set up

---

Ready to launch! 🚀

