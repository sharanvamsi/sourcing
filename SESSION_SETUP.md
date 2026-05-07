# Session Management Setup Guide

This app supports secure HTTP-only cookie sessions via a reverse proxy (nginx) and session middleware service.

## Architecture

```
User Browser
    ↓
Nginx (Reverse Proxy) - Sets HTTP-only cookies
    ↓
Session Middleware (Flask) - Manages session tokens
    ↓
Streamlit App - Uses sessions for authentication
```

## Setup Options

### Option 1: Production Setup with Nginx (Recommended)

1. **Install nginx** (if not already installed)
   ```bash
   # Ubuntu/Debian
   sudo apt-get install nginx
   
   # macOS
   brew install nginx
   ```

2. **Start the session middleware service**
   ```bash
   python session_middleware.py
   ```
   This runs on port 8502 by default.

3. **Configure nginx**
   - Copy `nginx.conf.example` to your nginx sites directory
   - Update the configuration with your domain and SSL certificates
   - Enable the site: `sudo ln -s /etc/nginx/sites-available/your-app /etc/nginx/sites-enabled/`
   - Test: `sudo nginx -t`
   - Reload: `sudo systemctl reload nginx`

4. **Set environment variable** (optional)
   ```bash
   export SESSION_MIDDLEWARE_URL="http://127.0.0.1:8502"
   ```

### Option 2: Development Setup (JavaScript Cookies)

For local development without nginx:

1. The app will automatically use JavaScript-accessible cookies
2. Less secure but works for development
3. Cookies are set via JavaScript (not HTTP-only)

### Option 3: Simple URL-based (Current Fallback)

If neither middleware nor cookies work, the app falls back to URL query parameters (least secure).

## Security Features

- **HTTP-only cookies**: Cannot be accessed by JavaScript (XSS protection)
- **Secure flag**: Only sent over HTTPS
- **SameSite=Lax**: CSRF protection
- **Session expiration**: 24 hours by default
- **Automatic cleanup**: Expired sessions are removed

## Testing

1. Start the session middleware:
   ```bash
   python session_middleware.py
   ```

2. Start Streamlit:
   ```bash
   streamlit run app.py
   ```

3. Login and verify:
   - Session token should be in HTTP-only cookie (check browser DevTools)
   - Reload page - should stay logged in
   - Logout - cookie should be deleted

## Troubleshooting

- **Middleware not connecting**: Check if `session_middleware.py` is running on port 8502
- **Cookies not setting**: Verify nginx configuration and SSL certificates
- **Sessions expiring too quickly**: Adjust `expires_in_hours` in `create_user_session()`



