# Deployment Guide: Setting up abasourcing.com

## Overview
This guide will help you configure your ABA Sourcing application to use the custom domain `abasourcing.com` and prepare it for production use with all your users.

## Prerequisites Checklist

Before starting, ensure you have:
- [ ] Domain `abasourcing.com` purchased and accessible
- [ ] Deployment platform account (Railway, Render, Fly.io, etc.)
- [ ] PostgreSQL database configured
- [ ] All environment variables set
- [ ] Sentry account configured for error tracking

---

## Step 1: Domain Setup

### 1.1 Purchase/Verify Domain
- If not already purchased, buy `abasourcing.com` from a registrar (Namecheap, GoDaddy, Google Domains, etc.)
- Ensure you have access to DNS management

### 1.2 Choose Your Deployment Platform

**Option A: Railway (Recommended for Streamlit)**
- Railway.app supports custom domains with automatic SSL
- Easy Streamlit deployment
- Built-in PostgreSQL

**Option B: Render**
- Free tier available
- Custom domain support
- Automatic SSL

**Option C: Fly.io**
- Good for Docker deployments
- Custom domain support

---

## Step 2: Configure DNS Records

### For Railway:
1. Go to your Railway project → Settings → Networking
2. Add custom domain: `abasourcing.com`
3. Railway will provide you with a CNAME record like: `xxxxx.railway.app`
4. In your domain registrar's DNS settings, add:
   ```
   Type: CNAME
   Name: @ (or abasourcing.com)
   Value: xxxxx.railway.app
   TTL: 3600
   ```
5. For www subdomain (optional):
   ```
   Type: CNAME
   Name: www
   Value: xxxxx.railway.app
   TTL: 3600
   ```

### For Render:
1. Go to your Render service → Settings → Custom Domain
2. Add domain: `abasourcing.com`
3. Render will provide DNS records to add:
   ```
   Type: A
   Name: @
   Value: [IP address provided by Render]
   ```
   ```
   Type: CNAME
   Name: www
   Value: [hostname provided by Render]
   ```

### DNS Propagation
- DNS changes can take 5 minutes to 48 hours to propagate
- Check propagation: https://www.whatsmydns.net/#CNAME/abasourcing.com
- Use `dig abasourcing.com` or `nslookup abasourcing.com` to verify

---

## Step 3: SSL/HTTPS Configuration

### Automatic SSL (Recommended)
Most platforms (Railway, Render) provide automatic SSL via Let's Encrypt:
- Enable "Automatic SSL" in your platform settings
- SSL certificate will be issued automatically once DNS is configured
- Certificate renews automatically

### Manual SSL (if needed)
If you need to configure SSL manually:
1. Generate SSL certificate (Let's Encrypt recommended)
2. Upload certificate to your platform
3. Configure HTTPS redirect

---

## Step 4: Environment Variables Setup

Ensure these environment variables are set in your deployment platform:

### Required Variables:
```bash
# Database
DATABASE_URL=postgresql://user:password@host:port/database

# Encryption
MASTER_ENCRYPTION_SECRET=your-secret-key-here

# Sentry (Optional but recommended)
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
```

### Optional Variables:
```bash
# Admin Email (for first-time setup)
ADMIN_EMAIL=admin@abasourcing.com

# Streamlit Configuration
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0
```

---

## Step 5: Production Readiness Checklist

### Security
- [ ] Change hardcoded password `club2025` to environment variable
- [ ] Ensure `MASTER_ENCRYPTION_SECRET` is strong and secure
- [ ] Verify API keys are encrypted in database
- [ ] Enable HTTPS/SSL
- [ ] Review Sentry error tracking setup

### Database
- [ ] PostgreSQL database is production-ready
- [ ] Database backups are configured
- [ ] Connection pooling is working
- [ ] Database migrations are complete

### Application
- [ ] All critical bugs are fixed
- [ ] Error handling is robust
- [ ] Logging is configured (Sentry)
- [ ] Performance is acceptable (parallel enrichment working)

### User Management
- [ ] User roster is synced to database
- [ ] Admin users are configured
- [ ] User onboarding process is documented

---

## Step 6: Deploy Application

### Using Railway:
1. Connect your GitHub repository to Railway
2. Railway will auto-detect Dockerfile
3. Set environment variables in Railway dashboard
4. Deploy will happen automatically on git push
5. Add custom domain in Settings → Networking

### Using Docker:
```bash
# Build image
docker build -t abasourcing .

# Run locally to test
docker run -p 8501:8501 \
  -e DATABASE_URL=your_db_url \
  -e MASTER_ENCRYPTION_SECRET=your_secret \
  abasourcing
```

---

## Step 7: Pre-Launch Testing

### Test Checklist:
- [ ] Domain resolves correctly: `https://abasourcing.com`
- [ ] SSL certificate is valid (green lock icon)
- [ ] Login works with test user
- [ ] API key configuration works
- [ ] Search functionality works
- [ ] Enrichment functionality works
- [ ] Database operations work correctly
- [ ] Error handling displays properly
- [ ] Admin panel is accessible
- [ ] CSV export works

### Load Testing:
- Test with multiple concurrent users
- Verify database connection pooling handles load
- Check API rate limits are respected

---

## Step 8: User Onboarding Preparation

### Create User Documentation:
1. **Login Instructions**
   - URL: https://abasourcing.com
   - Password: [share securely]
   - Email format: user@example.com

2. **API Key Setup**
   - Where to get Apollo API keys
   - How to configure keys in the app
   - Key security best practices

3. **User Guide**
   - How to search for leads
   - How to add leads to basket
   - How to enrich contacts
   - How to export CSV

### Prepare User Roster:
- [ ] All users are in database (use `cloud_sync.py` if needed)
- [ ] Admin users are marked
- [ ] Team assignments are correct

---

## Step 9: Launch Day Checklist

### Before Launch:
- [ ] Domain is live and accessible
- [ ] SSL certificate is valid
- [ ] All environment variables are set
- [ ] Database is populated with users
- [ ] Test login works
- [ ] Monitoring is active (Sentry)

### Launch Steps:
1. Send announcement email with:
   - URL: https://abasourcing.com
   - Login credentials
   - Quick start guide
   - Support contact info

2. Monitor:
   - Sentry for errors
   - Database connections
   - API usage
   - User login attempts

3. Be available for support:
   - Answer user questions
   - Fix any immediate issues
   - Collect feedback

---

## Step 10: Post-Launch Monitoring

### Daily Checks:
- Review Sentry error logs
- Monitor database performance
- Check API usage/credits
- Review user feedback

### Weekly Tasks:
- Review audit logs
- Check for security issues
- Update documentation as needed
- Plan improvements

---

## Troubleshooting

### Domain Not Resolving:
- Check DNS records are correct
- Wait for DNS propagation (up to 48 hours)
- Verify CNAME/A records point to correct host

### SSL Certificate Issues:
- Ensure DNS is configured correctly first
- Wait for automatic SSL provisioning (can take up to 1 hour)
- Check platform SSL status page

### Application Errors:
- Check Sentry dashboard for error details
- Verify environment variables are set correctly
- Check database connectivity
- Review application logs

### Database Connection Issues:
- Verify DATABASE_URL is correct
- Check database is accessible from deployment platform
- Verify connection pool settings
- Check database resource limits

---

## Support Resources

- **Sentry Dashboard**: Monitor errors and performance
- **Platform Logs**: Check deployment platform logs
- **Database Logs**: Review PostgreSQL logs if needed
- **User Support**: Create support email or channel

---

## Next Steps After Launch

1. **Gather User Feedback**: Create feedback form or channel
2. **Monitor Usage**: Track user activity and feature usage
3. **Iterate**: Fix bugs and add features based on feedback
4. **Scale**: Plan for increased usage and database growth
5. **Documentation**: Keep user documentation updated

---

## Quick Reference

**Production URL**: https://abasourcing.com  
**Admin Panel**: https://abasourcing.com (Admin tab)  
**Sentry**: [Your Sentry Dashboard URL]  
**Database**: [Your Database Provider Dashboard]

**Emergency Contacts**:
- Support Email: [Your support email]
- Admin: [Admin email]

---

Good luck with your launch! 🚀

