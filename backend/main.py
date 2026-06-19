"""
FastAPI Backend for ABA Sourcing Platform
Provides REST API endpoints for the Next.js frontend
"""
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime, timedelta
import os
import sys
import jwt

# Add parent directory to path to import existing modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables from parent directory .env file
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from db_manager import (
    init_db, get_user, get_all_users, add_user, update_user, count_admins, query,
    get_basket_leads, add_lead_to_basket, clear_basket,
    get_user_credit_total, get_team_credit_total, get_team_info,
    check_team_credit_limit, log_credit_usage, log_audit_event,
    get_user_keys, save_user_keys, delete_user_keys,
    get_blacklist, add_to_blacklist, remove_from_blacklist,
    # Team basket functions
    get_team_basket_leads, check_team_basket_duplicates,
    add_leads_to_team_basket, get_team_basket_stats,
    # Email functions
    get_email_templates, get_email_template, save_email_template,
    delete_email_template, create_campaign, get_team_campaigns,
    get_campaign_stats, save_sendgrid_key, get_sendgrid_key,
    ALLOWED_TEAMS, DATABASE_URL
)
from experiment_search import search_people, find_company_domain
from experiment_enrich import enrich_people
from email_service import send_campaign, preview_email

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

app = FastAPI(
    title="ABA Sourcing API",
    description="Backend API for lead sourcing and email outreach",
    version="2.0.0"
)

# CORS for the Next.js frontend. The previous "https://*.vercel.app" entry never
# matched (Starlette does exact-string matching on allow_origins). Extra origins
# can be supplied via CORS_ORIGINS (comma-separated); any *.up.railway.app domain
# is allowed by regex so the Railway-hosted frontend works without hardcoding its
# generated subdomain.
_default_origins = "http://localhost:3000"
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", _default_origins).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.up\.railway\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# Initialize database on startup
@app.on_event("startup")
async def startup():
    init_db()

# ============== Pydantic Models ==============

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class SearchRequest(BaseModel):
    domain: str
    job_titles: List[str] = []
    locations: List[str] = []
    seniority: List[str] = []
    max_results: int = 25

class EnrichRequest(BaseModel):
    lead_ids: List[str]

class AddToBasketRequest(BaseModel):
    leads: List[dict]

class TemplateRequest(BaseModel):
    name: str
    subject: str
    body_html: str
    body_text: Optional[str] = None
    template_id: Optional[int] = None

class CampaignRequest(BaseModel):
    name: str
    template_id: int
    sender_email: str
    sender_name: str
    lead_ids: List[str]

class ApiKeyRequest(BaseModel):
    apollo_api_key: Optional[str] = None
    sendgrid_api_key: Optional[str] = None

class UserRequest(BaseModel):
    email: str
    name: str
    team_name: str = ""  # not required for external members; backend assigns placeholder
    role: Literal["consultant", "pm"] = "consultant"
    is_admin: bool = False
    blacklist_exempt: bool = False
    membership: Literal["aba", "external"] = "aba"

# ============== Auth Helpers ==============

def create_token(email: str) -> str:
    expiration = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "sub": email,
        "exp": expiration,
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = get_user(email)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return dict(user)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def require_pm(user: dict = Depends(verify_token)) -> dict:
    if user.get("role") != "pm":
        raise HTTPException(status_code=403, detail="PM access required")
    return user

def require_admin(user: dict = Depends(verify_token)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# ============== Auth Routes ==============

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    expected_password = os.getenv("CLUB_PASSWORD", "club2025")
    if request.password != expected_password:
        log_audit_event(request.email, "LOGIN_FAILED", "Invalid password")
        raise HTTPException(status_code=401, detail="Invalid password")

    user = get_user(request.email)
    if not user:
        log_audit_event(request.email, "LOGIN_FAILED", "User not found")
        raise HTTPException(status_code=401, detail="User not found")

    log_audit_event(request.email, "LOGIN_SUCCESS")
    token = create_token(request.email)

    return TokenResponse(
        access_token=token,
        user=dict(user)
    )

@app.get("/api/auth/me")
async def get_current_user(user: dict = Depends(verify_token)):
    return {
        "user": user,
        "credits_used": get_user_credit_total(user["email"]),
        "team_credits": get_team_credit_total(user["team_name"]),
        "basket_count": len(get_basket_leads(user["email"]))
    }

# ============== Search Routes ==============

@app.post("/api/search")
async def search_leads(request: SearchRequest, user: dict = Depends(verify_token)):
    # Check team credit limit
    is_allowed, remaining, current = check_team_credit_limit(user["team_name"])
    if not is_allowed:
        raise HTTPException(status_code=403, detail="Team credit limit reached")

    # Check blacklist
    user_membership = (user.get("membership") or "aba").lower()
    apply_blacklist = (user_membership == "aba") and (not bool(user.get("blacklist_exempt")))
    if apply_blacklist:
        blacklist = get_blacklist()
        domain_lower = request.domain.lower()
        for blocked in blacklist:
            if blocked.lower() in domain_lower:
                raise HTTPException(status_code=403, detail=f"Domain {request.domain} is blacklisted")

    # Resolve domain if needed
    target_domain = request.domain
    if "." not in request.domain:
        found_domain = find_company_domain(request.domain)
        if found_domain:
            target_domain = found_domain
        else:
            raise HTTPException(status_code=404, detail=f"Could not find domain for {request.domain}")

    # Set API key from user's saved key
    api_key = get_user_keys(user["email"])
    if api_key:
        os.environ["APOLLO_API_KEY"] = api_key

    results = search_people(
        domain=target_domain,
        job_titles=request.job_titles,
        locations=request.locations,
        seniority=request.seniority,
        max_results=request.max_results
    )

    return {
        "results": results or [],
        "count": len(results) if results else 0,
        "resolved_domain": target_domain
    }

# ============== Basket Routes ==============

@app.get("/api/basket")
async def get_basket(user: dict = Depends(verify_token)):
    leads = get_basket_leads(user["email"])
    return {"leads": leads, "count": len(leads)}

@app.post("/api/basket/add")
async def add_to_basket(request: AddToBasketRequest, user: dict = Depends(verify_token)):
    added = 0
    for lead in request.leads:
        add_lead_to_basket(user["email"], lead)
        added += 1
    return {"added": added, "total": len(get_basket_leads(user["email"]))}

@app.delete("/api/basket/clear")
async def clear_user_basket(user: dict = Depends(verify_token)):
    clear_basket(user["email"])
    return {"success": True}

@app.post("/api/basket/enrich")
async def enrich_basket(user: dict = Depends(verify_token)):
    basket = get_basket_leads(user["email"])
    if not basket:
        raise HTTPException(status_code=400, detail="Basket is empty")

    team_name = user["team_name"]

    # Check for duplicates in team basket
    duplicates, non_duplicates = check_team_basket_duplicates(team_name, basket)

    if not non_duplicates:
        clear_basket(user["email"])
        return {
            "enriched": [],
            "skipped_duplicates": len(duplicates),
            "credits_used": 0,
            "message": "All leads already in team basket"
        }

    # Check credit limit
    credits_needed = len(non_duplicates)
    is_allowed, remaining, current = check_team_credit_limit(team_name, credits_needed)
    if not is_allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Credit limit exceeded. Need {credits_needed}, have {remaining} remaining"
        )

    # Set API key
    api_key = get_user_keys(user["email"])
    if api_key:
        os.environ["APOLLO_API_KEY"] = api_key

    # Enrich
    results = enrich_people(non_duplicates)

    if results:
        # Add to team basket
        add_leads_to_team_basket(team_name, results, user["email"])
        # Log credits
        log_credit_usage(user["email"], "Enrichment", len(results))

    # Clear personal basket
    clear_basket(user["email"])

    return {
        "enriched": results,
        "enriched_count": len(results) if results else 0,
        "skipped_duplicates": len(duplicates),
        "credits_used": len(results) if results else 0
    }

# ============== Team Leads Routes ==============

@app.get("/api/team-leads")
async def get_team_leads(
    filter: Optional[str] = None,
    user: dict = Depends(verify_token)
):
    team_name = user["team_name"]

    filter_contacted = None
    if filter == "available":
        filter_contacted = False
    elif filter == "contacted":
        filter_contacted = True

    leads = get_team_basket_leads(team_name, filter_contacted=filter_contacted)
    stats = get_team_basket_stats(team_name)

    return {
        "leads": leads,
        "stats": stats
    }

# ============== Email Routes (PM Only) ==============

@app.get("/api/email/templates")
async def list_templates(user: dict = Depends(require_pm)):
    templates = get_email_templates()
    return {"templates": templates}

@app.post("/api/email/templates")
async def create_template(request: TemplateRequest, user: dict = Depends(require_pm)):
    template_id = save_email_template(
        name=request.name,
        subject=request.subject,
        body_html=request.body_html,
        body_text=request.body_text,
        created_by=user["email"],
        template_id=request.template_id
    )
    return {"template_id": template_id, "success": True}

@app.delete("/api/email/templates/{template_id}")
async def remove_template(template_id: int, user: dict = Depends(require_pm)):
    delete_email_template(template_id)
    return {"success": True}

@app.get("/api/email/campaigns")
async def list_campaigns(user: dict = Depends(require_pm)):
    campaigns = get_team_campaigns(user["team_name"])
    stats = get_campaign_stats(user["team_name"])
    return {"campaigns": campaigns, "stats": stats}

@app.post("/api/email/campaigns")
async def create_and_send_campaign(request: CampaignRequest, user: dict = Depends(require_pm)):
    # Create campaign
    campaign_id = create_campaign(
        name=request.name,
        team_name=user["team_name"],
        template_id=request.template_id,
        sender_email=request.sender_email,
        sender_name=request.sender_name,
        created_by=user["email"],
        lead_ids=request.lead_ids
    )

    # Send campaign
    result = send_campaign(campaign_id, user["email"])

    return {
        "campaign_id": campaign_id,
        "sent_count": result["sent_count"],
        "failed_count": result["failed_count"],
        "success": result["success"]
    }

@app.get("/api/email/preview/{template_id}/{lead_id}")
async def preview_template(template_id: int, lead_id: str, user: dict = Depends(require_pm)):
    preview = preview_email(template_id, lead_id)
    if not preview:
        raise HTTPException(status_code=404, detail="Template or lead not found")
    return {"subject": preview.get("subject", ""), "body": preview.get("body_html", "")}

@app.post("/api/email/send")
async def send_email_campaign(request: CampaignRequest, user: dict = Depends(require_pm)):
    """Create and send an email campaign"""
    # Create campaign
    campaign_id = create_campaign(
        name=request.name,
        team_name=user["team_name"],
        template_id=request.template_id,
        sender_email=request.sender_email,
        sender_name=request.sender_name,
        created_by=user["email"],
        lead_ids=request.lead_ids
    )

    # Send campaign
    result = send_campaign(campaign_id, user["email"])

    return {
        "campaign_id": campaign_id,
        "sent_count": result.get("sent_count", 0),
        "failed_count": result.get("failed_count", 0),
        "success": result.get("success", False)
    }

@app.get("/api/email/stats")
async def get_email_stats(user: dict = Depends(require_pm)):
    """Get email campaign statistics"""
    stats = get_campaign_stats(user["team_name"])
    campaigns = get_team_campaigns(user["team_name"])

    total_sent = sum(c.get("sent_count", 0) for c in campaigns)
    total_delivered = sum(c.get("delivered_count", 0) for c in campaigns)
    total_opened = sum(c.get("opened_count", 0) for c in campaigns)
    total_clicked = sum(c.get("clicked_count", 0) for c in campaigns)

    return {
        "total_sent": total_sent,
        "total_delivered": total_delivered,
        "open_rate": total_opened / total_sent if total_sent > 0 else 0,
        "click_rate": total_clicked / total_sent if total_sent > 0 else 0,
        "by_campaign": [
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "sent": c.get("sent_count", 0),
                "opened": c.get("opened_count", 0),
                "clicked": c.get("clicked_count", 0)
            }
            for c in campaigns
        ]
    }

# ============== Settings Routes ==============

@app.get("/api/settings")
async def get_settings(user: dict = Depends(verify_token)):
    """Get user settings including API key status"""
    apollo_key = get_user_keys(user["email"])
    sendgrid_key = get_sendgrid_key(user["email"])
    return {
        "has_apollo_key": bool(apollo_key),
        "has_sendgrid_key": bool(sendgrid_key)
    }

@app.get("/api/settings/keys")
async def get_api_keys_status(user: dict = Depends(verify_token)):
    apollo_key = get_user_keys(user["email"])
    sendgrid_key = get_sendgrid_key(user["email"])
    return {
        "apollo_configured": bool(apollo_key),
        "sendgrid_configured": bool(sendgrid_key)
    }

class SingleApiKeyRequest(BaseModel):
    api_key: str

@app.post("/api/settings/apollo-key")
async def save_apollo_key(request: SingleApiKeyRequest, user: dict = Depends(verify_token)):
    """Save Apollo API key"""
    save_user_keys(user["email"], request.api_key)
    return {"success": True}

@app.post("/api/settings/sendgrid-key")
async def save_sendgrid_api_key(request: SingleApiKeyRequest, user: dict = Depends(require_pm)):
    """Save SendGrid API key (PM only)"""
    save_sendgrid_key(user["email"], request.api_key)
    return {"success": True}

@app.post("/api/settings/keys")
async def save_api_keys(request: ApiKeyRequest, user: dict = Depends(verify_token)):
    if request.apollo_api_key:
        save_user_keys(user["email"], request.apollo_api_key)
    if request.sendgrid_api_key:
        save_sendgrid_key(user["email"], request.sendgrid_api_key)
    return {"success": True}

@app.delete("/api/settings/keys")
async def delete_api_keys(user: dict = Depends(verify_token)):
    delete_user_keys(user["email"])
    return {"success": True}

# ============== Admin Routes ==============

@app.get("/api/admin/stats")
async def get_admin_stats(user: dict = Depends(require_admin)):
    total_credits = query("SELECT SUM(credit_spent) as total FROM credit_logs")
    total_leads = query("SELECT COUNT(*) as count FROM leads")
    enriched_condition = "TRUE" if DATABASE_URL else "1"
    total_enriched = query(f"SELECT COUNT(*) as count FROM leads WHERE is_enriched = {enriched_condition}")

    return {
        "total_credits": total_credits[0]["total"] or 0 if total_credits else 0,
        "total_leads": total_leads[0]["count"] if total_leads else 0,
        "total_enriched": total_enriched[0]["count"] if total_enriched else 0
    }

@app.get("/api/admin/users")
async def get_users(user: dict = Depends(require_admin)):
    users = get_all_users()
    return {"users": [dict(u) for u in users]}

@app.post("/api/admin/users")
async def create_or_update_user(request: UserRequest, user: dict = Depends(require_admin)):
    try:
        add_user(
            email=request.email,
            name=request.name,
            team_name=request.team_name,
            is_admin=request.is_admin,
            role=request.role,
            blacklist_exempt=request.blacklist_exempt,
            membership=request.membership
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log_audit_event(user["email"], "USER_CREATED", f"Created/updated {request.email.strip().lower()}")
    return {"success": True}

class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    team_name: Optional[str] = None
    role: Optional[Literal["consultant", "pm"]] = None
    is_admin: Optional[bool] = None
    membership: Optional[Literal["aba", "external"]] = None
    blacklist_exempt: Optional[bool] = None

@app.put("/api/admin/users/{email}")
async def update_user_role(email: str, request: UpdateUserRequest, user: dict = Depends(require_admin)):
    """Update an existing user's profile, role, membership or flags.

    Routes through db_manager.update_user so edits get the same validation,
    membership/team syncing and audit logging as creation.
    """
    target = get_user(email)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent locking everyone out by demoting the last remaining admin.
    if request.is_admin is False and dict(target).get("is_admin") and count_admins() <= 1:
        raise HTTPException(status_code=400, detail="Cannot remove the last remaining admin")

    changes = {k: v for k, v in {
        "name": request.name,
        "team_name": request.team_name,
        "role": request.role,
        "is_admin": request.is_admin,
        "membership": request.membership,
        "blacklist_exempt": request.blacklist_exempt,
    }.items() if v is not None}

    try:
        update_user(email, **changes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    log_audit_event(user["email"], "USER_UPDATED", f"Updated {email.strip().lower()}: {changes}")
    return {"success": True}

@app.get("/api/admin/analytics")
async def get_admin_analytics(user: dict = Depends(require_admin)):
    """Get platform analytics for admin dashboard"""
    users = get_all_users()

    # Get totals
    total_users = len(users)
    total_teams = len(ALLOWED_TEAMS)

    # Get total leads
    leads_result = query("SELECT COUNT(*) as count FROM leads")
    total_leads = leads_result[0]["count"] if leads_result else 0

    # Get total credits used
    credits_result = query("SELECT SUM(credit_spent) as total FROM credit_logs")
    total_credits_used = credits_result[0]["total"] or 0 if credits_result else 0

    # Get top users by credits
    top_users_result = query("""
        SELECT u.email, u.name, u.team_name, COALESCE(SUM(c.credit_spent), 0) as credits_used
        FROM users u
        LEFT JOIN credit_logs c ON u.email = c.user_email
        GROUP BY u.email, u.name, u.team_name
        ORDER BY credits_used DESC
        LIMIT 10
    """)

    # Get top teams
    top_teams = []
    for team_name in ALLOWED_TEAMS:
        info = get_team_info(team_name)
        top_teams.append(info)
    top_teams.sort(key=lambda x: x.get("used_credits", 0), reverse=True)

    return {
        "total_users": total_users,
        "total_teams": total_teams,
        "total_leads": total_leads,
        "total_credits_used": total_credits_used,
        "top_users": [dict(u) for u in top_users_result] if top_users_result else [],
        "top_teams": top_teams[:10]
    }

@app.get("/api/admin/teams")
async def get_teams(user: dict = Depends(require_admin)):
    teams = []
    for team_name in ALLOWED_TEAMS:
        info = get_team_info(team_name)
        teams.append(info)
    return {"teams": teams}

class AddCreditsRequest(BaseModel):
    amount: int

@app.post("/api/admin/teams/{team_name}/credits")
async def add_team_credits(team_name: str, request: AddCreditsRequest, user: dict = Depends(require_admin)):
    """Add credits to a team"""
    if team_name not in ALLOWED_TEAMS:
        raise HTTPException(status_code=404, detail="Team not found")

    if DATABASE_URL:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "UPDATE teams SET total_credits = total_credits + %s WHERE name = %s RETURNING total_credits",
            (request.amount, team_name)
        )
        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        new_total = result["total_credits"] if result else 0
    else:
        import sqlite3
        conn = sqlite3.connect("sourcing.db")
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE teams SET total_credits = total_credits + ? WHERE name = ?",
            (request.amount, team_name)
        )
        conn.commit()
        cursor.execute("SELECT total_credits FROM teams WHERE name = ?", (team_name,))
        result = cursor.fetchone()
        new_total = result[0] if result else 0
        cursor.close()
        conn.close()

    log_audit_event(user["email"], "ADD_CREDITS", f"Added {request.amount} credits to {team_name}")

    return {"success": True, "new_total": new_total}

@app.get("/api/admin/blacklist")
async def get_blacklist_domains(user: dict = Depends(require_admin)):
    return {"domains": get_blacklist()}

@app.post("/api/admin/blacklist/{domain}")
async def add_blacklist_domain(domain: str, user: dict = Depends(require_admin)):
    add_to_blacklist(domain)
    return {"success": True}

@app.delete("/api/admin/blacklist/{domain}")
async def remove_blacklist_domain(domain: str, user: dict = Depends(require_admin)):
    remove_from_blacklist(domain)
    return {"success": True}

@app.get("/api/admin/audit-logs")
async def get_audit_logs(user: dict = Depends(require_admin)):
    logs = query("SELECT timestamp, user_email, event_type, details FROM audit_logs ORDER BY timestamp DESC LIMIT 50")
    return {"logs": [dict(l) for l in logs] if logs else []}

# Health check
@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
