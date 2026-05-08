import streamlit as st
import json
import pandas as pd
import os
import math
import sentry_sdk
from experiment_search import search_people, find_company_domain
from experiment_enrich import enrich_people
from db_manager import (
    init_db, sync_roster, get_basket_leads, add_lead_to_basket,
    clear_basket, update_lead_enrichment, log_credit_usage,
    save_user_keys, get_user_keys, delete_user_keys, query, log_audit_event,
    get_user, get_all_users, add_user, migrate_roster_to_db,
    get_blacklist, add_to_blacklist, remove_from_blacklist,
    get_cached_domain, update_domain_cache, check_environment, ALLOWED_TEAMS,
    get_user_credit_total, get_team_credit_total, get_team_members, get_team_info,
    check_team_credit_limit, create_user_session, get_user_from_session,
    delete_user_session, cleanup_expired_sessions,
    # Team basket functions
    get_or_create_team_basket, get_team_basket_leads, is_lead_in_team_basket,
    check_team_basket_duplicates, add_leads_to_team_basket, mark_lead_contacted,
    get_team_basket_stats, is_pm,
    # Email functions
    get_email_templates, get_email_template, save_email_template, delete_email_template,
    create_campaign, get_team_campaigns, get_campaign_stats,
    save_sendgrid_key, get_sendgrid_key
)
import db_manager
from local_error_logger import log_error
from export_manager import export_to_clipboard
from email_service import send_campaign, preview_email

# --- SENTRY INITIALIZATION ---
SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        enable_logs=True,
        send_default_pii=True, # Helps map errors to specific user emails
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

# --- CONFIGURATION ---
st.set_page_config(
    page_title="ABA Sourcing    ",
    layout="wide"
)

# Premium CSS
st.markdown("""
    <style>
    .stMetric {
        background-color: rgba(255,255,255,0.05);
        padding: 15px;
        border-radius: 10px;
        border: 1px solid rgba(255,255,255,0.1);
    }
    [data-testid="stMetricValue"] {
        color: #ffffff;
    }
    [data-testid="stMetricLabel"] {
        color: rgba(255,255,255,0.7);
    }
    [data-testid="stSidebar"] {
        background-image: linear-gradient(#2e3b4e, #1a2431);
        color: white;
    }
    [data-testid="stSidebar"] * {
        color: white !important;
    }
    .main h1 {
        font-weight: 800;
        color: #1e293b;
    }
    .stButton>button {
        border-radius: 8px;
    }
    </style>
    
    <script>
    // Cookie management functions
    function setCookie(name, value, days) {
        var expires = "";
        if (days) {
            var date = new Date();
            date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
            expires = "; expires=" + date.toUTCString();
        }
        // Set secure cookie (requires HTTPS in production)
        var secure = window.location.protocol === 'https:' ? '; Secure' : '';
        document.cookie = name + "=" + (value || "") + expires + "; path=/" + secure + "; SameSite=Lax";
    }
    
    function getCookie(name) {
        var nameEQ = name + "=";
        var ca = document.cookie.split(';');
        for(var i = 0; i < ca.length; i++) {
            var c = ca[i];
            while (c.charAt(0) === ' ') c = c.substring(1, c.length);
            if (c.indexOf(nameEQ) === 0) return c.substring(nameEQ.length, c.length);
        }
        return null;
    }
    
    function deleteCookie(name) {
        document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
    }
    </script>
""", unsafe_allow_html=True)

# --- STARTUP CHECK ---
if not check_environment():
    st.error("### 🛑 Configuration Error")
    st.warning("Critical environment variables are missing. The application may not function correctly. Please check your **Sentry** dashboard or server logs for details.")

# --- HELPER FUNCTIONS ---
def check_blacklist(domain, blacklist):
    if not domain:
        return False
    domain_lower = domain.lower()
    for blocked in blacklist:
        if blocked.lower() in domain_lower:
            return True
    return False

# --- STATE INITIALIZATION ---
if "user" not in st.session_state:
    st.session_state.user = None
if "api_keys" not in st.session_state:
    st.session_state.api_keys = None
if "basket" not in st.session_state:
    st.session_state.basket = []
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "selected_ids" not in st.session_state:
    st.session_state.selected_ids = set()
if "enriched" not in st.session_state:
    st.session_state.enriched = False

# --- MAIN APP ---
def main():
    # 1. INITIALIZE DB
    init_db()
    
    # Cleanup expired sessions (only run occasionally, not every load)
    # Use a flag to only run cleanup every N page loads
    if "last_cleanup" not in st.session_state:
        st.session_state.last_cleanup = 0
    import time
    if time.time() - st.session_state.last_cleanup > 3600:  # Run cleanup max once per hour
        cleanup_expired_sessions()
        st.session_state.last_cleanup = time.time()
    
    # Fetch active profiles and settings from DB
    # (Note: For local-to-cloud migration, use the cloud_sync.py utility)
    blacklist = get_blacklist()

    # 2. CHECK FOR EXISTING SESSION (persistent login)
    if not st.session_state.user:
        session_token = None
        
        # Method 1: Check URL params first (fastest method)
        query_params = st.query_params
        session_token = query_params.get("session", None)
        
        # Method 2: Try middleware API with SHORTER timeout (only if no token in URL)
        # This avoids waiting if we already have a token
        if not session_token:
            try:
                import requests
                middleware_url = os.getenv("SESSION_MIDDLEWARE_URL", "http://127.0.0.1:8502")
                # Quick check with very short timeout (0.1s instead of 1s)
                response = requests.get(f"{middleware_url}/api/session/validate", timeout=0.1)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('valid') and data.get('user'):
                        user_data = data['user']
                        user = get_user(user_data['email'])
                        if user:
                            st.session_state.user = user
                            st.session_state.basket = get_basket_leads(user['email'])
                            saved_key = get_user_keys(user['email'])
                            if saved_key:
                                st.session_state.api_keys = saved_key
                            st.rerun()
            except:
                # Middleware not available - skip it quickly
                pass
        
        # Method 3: Read from JavaScript-accessible cookie (only if no token yet)
        # Only try once per page load to avoid reload loops
        if not session_token:
            # Check if URL already has session param to avoid reload loop
            if "session" not in query_params:
                cookie_read_script = """
                <script>
                (function() {
                    function getCookie(name) {
                        var nameEQ = name + "=";
                        var ca = document.cookie.split(';');
                        for(var i = 0; i < ca.length; i++) {
                            var c = ca[i];
                            while (c.charAt(0) === ' ') c = c.substring(1, c.length);
                            if (c.indexOf(nameEQ) === 0) {
                                return c.substring(nameEQ.length, c.length);
                            }
                        }
                        return null;
                    }
                    var token = getCookie("session_token");
                    if (token && !window.location.search.includes("session=")) {
                        var url = new URL(window.location);
                        url.searchParams.set("session", token);
                        window.history.replaceState({}, '', url);
                        // Small delay to avoid immediate reload
                        setTimeout(function() {
                            window.location.reload();
                        }, 100);
                    }
                })();
                </script>
                """
                st.markdown(cookie_read_script, unsafe_allow_html=True)
                # Re-check query params after potential cookie read
                query_params = st.query_params
                session_token = query_params.get("session", None)
        
        if session_token:
            user = get_user_from_session(session_token)
            if user:
                st.session_state.user = user
                st.session_state.basket = get_basket_leads(user['email'])
                saved_key = get_user_keys(user['email'])
                if saved_key:
                    st.session_state.api_keys = saved_key
                st.rerun()

    # 3. LOGIN SCREEN
    if not st.session_state.user:
        st.header("Login")
        st.write("Welcome back! Please enter your email to continue.")
        
        login_email = st.text_input("Enter your Email", placeholder="user@example.com")
        login_pass = st.text_input("Enter Club Password", type="password")
        
        if st.button("Sign In", type="primary"):
            if not login_email or not login_pass:
                st.warning("Please enter your email and password.")
            else:
                # Get password from environment variable, fallback to default for backward compatibility
                expected_password = os.getenv("CLUB_PASSWORD", "club2025")
                if login_pass != expected_password:
                    log_audit_event(login_email, "LOGIN_FAILED", "Invalid club password")
                    st.error("Invalid password. Please check the club handbook.")
                else:
                    # Password is correct, now check if user exists
                    try:
                        user_obj = get_user(login_email)
                        
                        if user_obj:
                            st.session_state.user = user_obj
                            log_audit_event(login_email, "LOGIN_SUCCESS")
                            # Persistence: Load basket from DB on login
                            st.session_state.basket = get_basket_leads(user_obj['email'])
                            
                            # Create session token for persistent login
                            session_token = create_user_session(login_email)
                            
                            # Method 1: Try to set HTTP-only cookie via session middleware API
                            # (Preferred method - requires session_middleware.py running)
                            try:
                                import requests
                                middleware_url = os.getenv("SESSION_MIDDLEWARE_URL", "http://127.0.0.1:8502")
                                response = requests.post(
                                    f"{middleware_url}/api/session/create",
                                    json={"email": login_email},
                                    timeout=2
                                )
                                if response.status_code == 200:
                                    # Cookie set by middleware, redirect will include it
                                    st.rerun()
                                    return
                            except:
                                # Middleware not available, use JavaScript cookie fallback
                                pass
                            
                            # Method 2: Set JavaScript-accessible cookie (fallback)
                            # Note: Less secure but works without middleware
                            cookie_script = f"""
                            <script>
                            function setCookie(name, value, days) {{
                                var expires = "";
                                if (days) {{
                                    var date = new Date();
                                    date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
                                    expires = "; expires=" + date.toUTCString();
                                }}
                                var secure = window.location.protocol === 'https:' ? '; Secure' : '';
                                document.cookie = name + "=" + (value || "") + expires + "; path=/" + secure + "; SameSite=Lax";
                            }}
                            setCookie("session_token", "{session_token}", 1);
                            </script>
                            """
                            st.markdown(cookie_script, unsafe_allow_html=True)
                            
                            # Also add to URL as fallback (will be removed once cookie is read)
                            st.query_params["session"] = session_token
                            
                            st.rerun()
                        else:
                            # User not found in database
                            error_msg = f"Login attempt failed: Email '{login_email}' not found in database"
                            log_error(Exception(error_msg), context=f"Login failure - email: {login_email}")
                            log_audit_event(login_email, "LOGIN_FAILED", "Email not in database")
                            st.error("Email not found in the roster.")
                            
                            # Helpful hint for first-time production setup
                            if not get_all_users():
                                st.divider()
                                st.info("💡 **First Time Setup?** It looks like your production database is currently empty. "
                                        "To bootstrap your account, please ensure the `ADMIN_EMAIL` environment variable "
                                        "is set in Railway, or run `python migrate_json_to_db.py` from your local terminal.")
                    except Exception as e:
                        # Database error during login
                        log_error(e, context=f"Login error for email: {login_email}")
                        log_audit_event(login_email, "LOGIN_FAILED", f"Database error: {str(e)}")
                        st.error("An error occurred while checking your credentials. Please try again.")
                        sentry_sdk.capture_exception(e)
        return

    # 3. API CONFIGURATION SCREEN
    user_email = st.session_state.user.get('email')
    
    if not st.session_state.api_keys:
        # Check if we have saved key for this user (Now Decrypted from DB)
        saved_key = get_user_keys(user_email)
        if saved_key:
            st.session_state.api_keys = saved_key
            st.rerun()
        
        st.header("API Configuration")
        st.info(f"Welcome, {st.session_state.user['name']}. Please provide your Apollo API key to continue.")
        st.caption("Your API key will be encrypted and stored securely. It will be used for all Apollo API operations (search, enrichment, and organization lookup).")
        
        # Logout button
        if st.button("Logout", type="secondary"):
            # Get session token from cookie or URL
            session_token = None
            query_params = st.query_params
            session_token = query_params.get("session", None)
            
            # Also try to get from cookie via JavaScript
            cookie_delete_script = """
            <script>
            function deleteCookie(name) {
                document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
            }
            deleteCookie("session_token");
            </script>
            """
            st.markdown(cookie_delete_script, unsafe_allow_html=True)
            
            if session_token:
                delete_user_session(session_token)
            
            # Clear session state
            st.session_state.user = None
            st.session_state.api_keys = None
            st.session_state.basket = []
            st.session_state.search_results = []
            
            # Remove session token from URL if present
            if "session" in st.query_params:
                del st.query_params["session"]
            
            st.rerun()
        
        with st.form("keys_form"):
            api_key = st.text_input("Apollo API Key", type="password", help="Enter your Apollo.io API key. This single key will be used for all operations.")
            
            if st.form_submit_button("Save & Continue"):
                if not api_key:
                    st.error("API key is required.")
                else:
                    # Persist Encrypted in DB
                    save_user_keys(user_email, api_key)
                    st.session_state.api_keys = api_key
                    st.rerun()
        return

    # Set Environment Variable for scripts to pick up
    os.environ["APOLLO_API_KEY"] = st.session_state.api_keys

    # 4. DASHBOARD
    
    # Sidebar
    with st.sidebar:
        st.subheader("User Profile")
        st.write(f"**Name:** {st.session_state.user['name']}")
        user_membership = (st.session_state.user.get("membership") or "aba").lower()
        if user_membership == "aba":
            st.write(f"**Team:** {st.session_state.user['team_name']}")
        st.write(f"**Basket:** {len(st.session_state.basket)} leads")
        
        # Display user's credit usage
        user_email = st.session_state.user['email']
        total_credits = get_user_credit_total(user_email)
        st.write(f"**Credits Used:** {total_credits}")
        
        if st.button("Logout"):
            # Get session token from cookie or URL
            session_token = None
            query_params = st.query_params
            session_token = query_params.get("session", None)
            
            # Also delete cookie via JavaScript
            cookie_delete_script = """
            <script>
            function deleteCookie(name) {
                document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
            }
            deleteCookie("session_token");
            </script>
            """
            st.markdown(cookie_delete_script, unsafe_allow_html=True)
            
            if session_token:
                delete_user_session(session_token)
            
            # Clear session state
            st.session_state.user = None
            st.session_state.api_keys = None
            st.session_state.basket = []
            st.session_state.search_results = []
            
            # Remove session token from URL if present
            if "session" in st.query_params:
                del st.query_params["session"]
            
            st.rerun()
            
        st.divider()
        if st.button("Reset API Keys"):
            user_email = st.session_state.user.get('email')
            # Delete from database
            delete_user_keys(user_email)
            # Clear session state
            st.session_state.api_keys = None
            # Log the action
            log_audit_event(user_email, "API_KEYS_RESET", "User reset their API keys")
            st.success("API keys have been reset. Please enter a new API key to continue.")
            st.rerun()

    # Tabs
    tabs = ["🔍 Search", "🛒 Basket", "👥 Team Leads"]
    # Check if user is PM - use session state user object (loaded at login with role)
    user_role = st.session_state.user.get('role', 'consultant')
    user_is_pm = user_role == 'pm'
    if user_is_pm:
        tabs.append("📧 Email Outreach")
    # Admin Check: Add Admin tab if DB record says so
    is_admin = bool(st.session_state.user.get('is_admin', False))
    if is_admin:
        tabs.append("📊 Admin")

    tab_list = st.tabs(tabs)
    tab_search = tab_list[0]
    tab_basket = tab_list[1]
    tab_team_leads = tab_list[2]
    tab_idx = 3
    if user_is_pm:
        tab_email = tab_list[tab_idx]
        tab_idx += 1
    if is_admin:
        tab_admin = tab_list[tab_idx]

    # --- SEARCH TAB ---
    with tab_search:
        col1, col2 = st.columns([3, 1])
        with col1:
            domain_query = st.text_input("Company Domain / Name")
        with col2:
            max_results_input = st.number_input("Max Results", min_value=1, max_value=150, value=25)

        col3, col4, col5 = st.columns(3)
        with col3:
            titles_input = st.text_input("Job Titles (comma separated)")
        with col4:
            locations_input = st.text_input("Locations (comma separated)")
        with col5:
            seniority_options = ['senior', 'manager', 'director', 'head', 'vp', 'c_level', 'partner', 'owner']
            seniority_input = st.multiselect("Seniority", seniority_options)

        if st.button("Search Leads", type="primary"):
            if not domain_query:
                st.warning("Please enter a Company Name or Domain.")
                st.stop()

            user_membership = (st.session_state.user.get("membership") or "aba").lower()
            apply_blacklist = (user_membership == "aba") and (not bool(st.session_state.user.get("blacklist_exempt")))
            if apply_blacklist and check_blacklist(domain_query, blacklist):
                st.error(f"🛑 Access Denied: '{domain_query}' is on the Global Blacklist.")
                st.stop()

            # Check team credit limit before allowing search
            user_team = st.session_state.user['team_name']
            is_allowed, remaining, current = check_team_credit_limit(user_team, credits_to_add=0)
                
            if not is_allowed:
                st.error("🚫 Credit Limit Reached: Your team has used all 4,500 credits. Please contact your PMs.")
                st.stop()
                
            # Clear old checkbox states and results
            st.session_state.search_results = [] 
            st.session_state.selected_ids = set()
            for k in list(st.session_state.keys()):
                if k.startswith("chk_"):
                    del st.session_state[k]
                
            with st.spinner(f"Searching for candidates at {domain_query}..."):
                target_domain = domain_query
                if "." not in domain_query:
                     found_domain = find_company_domain(domain_query)
                     if found_domain:
                         target_domain = found_domain
                         st.success(f"Resolved '{domain_query}' to '{target_domain}'")
                     else:
                         st.error(f"Could not find a domain for organization '{domain_query}'. Please try entering the domain directly.")
                         st.stop()
                    
                titles = [t.strip() for t in titles_input.split(",")] if titles_input else []
                locations = [l.strip() for l in locations_input.split(",")] if locations_input else []
                
                results = search_people(
                    domain=target_domain,
                    job_titles=titles,
                    locations=locations,
                    seniority=seniority_input,
                    max_results=max_results_input
                )
                
                if not results:
                    st.info("No results found.")
                else:
                    st.session_state.search_results = results
                    # DEFAULT: Select ALL found results
                    st.session_state.selected_ids = set(p['id'] for p in results)
                    for p in results:
                        st.session_state[f"chk_{p['id']}"] = True

        # --- RESULTS DISPLAY (Pagination) ---
        if st.session_state.search_results:
            results = st.session_state.search_results
            total_results = len(results)
            
            st.divider()
            st.subheader(f"Found {total_results} matches")
            
            PAGE_SIZE = 25
            total_pages = math.ceil(total_results / PAGE_SIZE)
            
            if total_pages > 1:
                page_num = st.radio("Page", range(1, total_pages + 1), horizontal=True)
            else:
                page_num = 1
                
            start_idx = (page_num - 1) * PAGE_SIZE
            end_idx = start_idx + PAGE_SIZE
            current_page_results = results[start_idx:end_idx]
            
            c_h1, c_h2 = st.columns(2)
            if c_h1.button("Select All on Page"):
                for p in current_page_results:
                    st.session_state.selected_ids.add(p['id'])
                    st.session_state[f"chk_{p['id']}"] = True
                st.rerun()
            if c_h2.button("Deselect All on Page"):
                for p in current_page_results:
                    st.session_state.selected_ids.discard(p['id'])
                    st.session_state[f"chk_{p['id']}"] = False
                st.rerun()

            for person in current_page_results:
                checkbox_key = f"chk_{person['id']}"
                is_selected = person['id'] in st.session_state.selected_ids
                
                # Initialize checkbox state if not exists
                if checkbox_key not in st.session_state:
                    st.session_state[checkbox_key] = is_selected
                
                col_mark, col_details = st.columns([1, 10])
                with col_mark:
                    checkbox_value = st.checkbox("Select", key=checkbox_key, label_visibility="hidden")
                    
                    if checkbox_value:
                        st.session_state.selected_ids.add(person['id'])
                    else:
                        st.session_state.selected_ids.discard(person['id'])
                
                with col_details:
                     st.markdown(f"**{person.get('first_name')} {person.get('last_name_obfuscated', '')}** — {person.get('title')}")
                     st.caption(f"{person.get('organization', {}).get('name', 'N/A')} | {person.get('email', 'Email Hidden')}")

            st.divider()
            num_selected = len(st.session_state.selected_ids)
            if st.button(f"Add {num_selected} Selected Leads to Basket", type="primary", disabled=num_selected==0):
                selected_objects = [p for p in st.session_state.search_results if p['id'] in st.session_state.selected_ids]
                
                user_email = st.session_state.user['email']
                added_count = 0
                for p in selected_objects:
                    # DB Persistence: Add to DB basket
                    add_lead_to_basket(user_email, p)
                    added_count += 1
                
                # Refresh local session basket from DB
                st.session_state.basket = get_basket_leads(user_email)
                st.success(f"Added {added_count} leads to basket!")
                st.session_state.search_results = []
                st.session_state.selected_ids = set()
                st.rerun()

    # --- BASKET TAB ---
    with tab_basket:
        st.subheader("Your Basket")
        if not st.session_state.basket:
            st.info("Basket is empty.")
        else:
            df = pd.DataFrame(st.session_state.basket)
            
            # Flatten Org to 'company'
            if 'organization' in df.columns:
                df['company'] = df['organization'].apply(lambda x: x.get('name') if isinstance(x, dict) else str(x))
            elif 'company' not in df.columns:
                df['company'] = "N/A"
            
            # Ensure 'last_name' exists (fallback to obfuscated if needed)
            if 'last_name' not in df.columns:
                df['last_name'] = df['last_name_obfuscated'] if 'last_name_obfuscated' in df.columns else ""
            else:
                # Fill missing last_names with obfuscated ones if available
                if 'last_name_obfuscated' in df.columns:
                    df['last_name'] = df['last_name'].fillna(df['last_name_obfuscated'])

            # Display Filter: first name, last name, title, and company
            display_cols = ['first_name', 'last_name', 'title', 'company']
            # Only keep columns that actually exist
            available_display = [c for c in display_cols if c in df.columns]
            st.dataframe(df[available_display], width='stretch')

            col_b1, col_b2 = st.columns([1, 4])
            if col_b1.button("Clear Basket"):
                clear_basket(st.session_state.user['email'])
                st.session_state.basket = []
                st.session_state.enriched = False
                st.rerun()
                
            if col_b2.button("✨ Enrich & Add to Team", type="primary"):
                # Check team credit limit before enrichment
                user_email = st.session_state.user['email']
                user_team = st.session_state.user['team_name']

                # Step 1: Check for duplicates in team basket before spending credits
                duplicates, non_duplicates = check_team_basket_duplicates(user_team, st.session_state.basket)

                if duplicates:
                    st.warning(f"⚠️ {len(duplicates)} leads already in team basket (will be skipped, saving credits)")

                if not non_duplicates:
                    st.info("All leads in your basket are already in the team basket. No enrichment needed.")
                    # Clear personal basket since all are duplicates
                    clear_basket(user_email)
                    st.session_state.basket = []
                    st.rerun()

                credits_needed = len(non_duplicates)

                is_allowed, remaining, current = check_team_credit_limit(user_team, credits_to_add=credits_needed)

                if not is_allowed:
                    if remaining is not None and remaining == 0:
                        st.error("🚫 Credit Limit Reached: Your team has used all 4,500 credits. Please contact your PMs.")
                    else:
                        st.error(f"🚫 Credit Limit Exceeded: This enrichment would use {credits_needed} credits, but your team only has {remaining} credits remaining out of 4,500. Please reduce your basket size.")
                    st.stop()

                with st.spinner(f"Enriching {len(non_duplicates)} contacts (this uses credits)..."):
                    try:
                        # Only enrich non-duplicates
                        results = enrich_people(non_duplicates)

                        if not results:
                             st.warning("No emails could be revealed for these contacts. They were filtered from the export.")
                        else:
                             # DB Persistence: Update leads with emails & full names
                             for p in results:
                                 update_lead_enrichment(p['id'], p)

                             # Add enriched leads to team basket
                             added_count = add_leads_to_team_basket(user_team, results, user_email)

                             # Log usage
                             log_credit_usage(user_email, "Enrichment", len(results))
                             st.success(f"Enrichment Complete! {len(results)} emails revealed and added to team basket.")

                        # Clear personal basket after successful enrichment
                        clear_basket(user_email)
                        st.session_state.basket = []
                        st.session_state.enriched = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Enrichment Failed: {e}")
                        st.info("Your basket has been preserved. Please check your **Bulk Match API Key** in settings.")
                        # Log error locally for development
                        log_error(e, context="Enrichment process failed")
                        sentry_sdk.capture_exception(e)

            if st.session_state.get('enriched', False):
                st.divider()
                st.subheader("Export Enriched Contacts")
                
                # Keep existing CSV download button
                csv_cols = ['first_name', 'last_name', 'company', 'title', 'email']
                export_df = pd.DataFrame(st.session_state.basket)
                if 'organization' in export_df.columns:
                    export_df['company'] = export_df['organization'].apply(lambda x: x.get('name') if isinstance(x, dict) else str(x))
                
                available_csv = [c for c in csv_cols if c in export_df.columns]
                csv_data = export_df[available_csv].to_csv(index=False).encode('utf-8')
                
                col_download, col_clipboard = st.columns(2)
                
                with col_download:
                    st.download_button(
                        label="📥 Download CSV", 
                        data=csv_data, 
                        file_name="apollo_enriched_leads.csv", 
                        mime="text/csv"
                    )
                
                with col_clipboard:
                    # Copy to clipboard functionality (tab-separated, no headers)
                    tsv_string = export_to_clipboard(st.session_state.basket)
                    if tsv_string:
                        st.code(tsv_string, language=None)
                        st.caption("Copy the data above and paste into Google Sheets (tab-separated, no headers)")

    # --- TEAM LEADS TAB ---
    with tab_team_leads:
        st.header("Team Leads")
        user_team = st.session_state.user['team_name']
        user_email = st.session_state.user['email']

        # Get team basket stats
        basket_stats = get_team_basket_stats(user_team)

        # Display stats
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        col_stat1.metric("Total Leads", basket_stats['total'])
        col_stat2.metric("Available", basket_stats['available'])
        col_stat3.metric("Contacted", basket_stats['contacted'])

        st.divider()

        # Filter options
        filter_option = st.radio(
            "Filter",
            ["All", "Available", "Contacted"],
            horizontal=True
        )

        # Get filtered leads
        if filter_option == "Available":
            team_leads = get_team_basket_leads(user_team, filter_contacted=False)
        elif filter_option == "Contacted":
            team_leads = get_team_basket_leads(user_team, filter_contacted=True)
        else:
            team_leads = get_team_basket_leads(user_team)

        if not team_leads:
            st.info("No leads in team basket yet. Search and enrich contacts to add them here.")
        else:
            # Create DataFrame for display
            display_data = []
            for lead in team_leads:
                company = ''
                if isinstance(lead.get('organization'), dict):
                    company = lead.get('organization', {}).get('name', '')
                elif lead.get('organization_name'):
                    company = lead.get('organization_name', '')
                elif lead.get('company'):
                    company = lead.get('company', '')

                display_data.append({
                    'Name': f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip(),
                    'Company': company,
                    'Title': lead.get('title', ''),
                    'Email': lead.get('email', ''),
                    'Added By': lead.get('added_by', ''),
                    'Status': 'Contacted' if lead.get('is_contacted') else 'Available'
                })

            df_team_leads = pd.DataFrame(display_data)
            st.dataframe(df_team_leads, use_container_width=True)

            # Export option
            if st.button("📥 Export Team Leads to CSV"):
                csv_data = df_team_leads.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download CSV",
                    data=csv_data,
                    file_name=f"team_{user_team}_leads.csv",
                    mime="text/csv"
                )

        if not user_is_pm:
            st.divider()
            st.info("💡 Contact your PM to send outreach emails to these leads.")

    # --- EMAIL OUTREACH TAB (PM Only) ---
    if user_is_pm:
        with tab_email:
            st.header("Email Outreach")
            user_team = st.session_state.user['team_name']
            user_email = st.session_state.user['email']

            # Check if SendGrid key is configured
            sendgrid_key = get_sendgrid_key(user_email)

            # Sub-navigation
            email_section = st.radio(
                "Section",
                ["📝 Templates", "📤 Send Campaign", "📋 Campaigns", "📊 Analytics", "⚙️ Settings"],
                horizontal=True
            )

            st.divider()

            # --- TEMPLATES SECTION ---
            if email_section == "📝 Templates":
                st.subheader("Email Templates")

                col_new, col_list = st.columns([1, 2])

                with col_new:
                    with st.expander("➕ Create New Template", expanded=False):
                        with st.form("new_template_form"):
                            tmpl_name = st.text_input("Template Name")
                            tmpl_subject = st.text_input("Subject Line", help="Use {{first_name}}, {{company}}, etc.")
                            tmpl_html = st.text_area("Email Body (HTML)", height=200, help="Use {{first_name}}, {{last_name}}, {{company}}, {{title}}, {{email}}")
                            tmpl_text = st.text_area("Plain Text Version (optional)", height=100)

                            st.caption("**Available Variables:** {{first_name}}, {{last_name}}, {{company}}, {{title}}, {{email}}")

                            if st.form_submit_button("Save Template"):
                                if tmpl_name and tmpl_subject and tmpl_html:
                                    save_email_template(tmpl_name, tmpl_subject, tmpl_html, tmpl_text, user_email)
                                    st.success(f"Template '{tmpl_name}' created!")
                                    st.rerun()
                                else:
                                    st.error("Name, Subject, and Body are required.")

                with col_list:
                    templates = get_email_templates()
                    if templates:
                        for tmpl in templates:
                            with st.expander(f"📄 {tmpl['name']}"):
                                st.write(f"**Subject:** {tmpl['subject']}")
                                st.write(f"**Created:** {tmpl['created_at']}")
                                st.code(tmpl['body_html'][:200] + "..." if len(tmpl['body_html']) > 200 else tmpl['body_html'])
                                if st.button("🗑️ Delete", key=f"del_tmpl_{tmpl['id']}"):
                                    delete_email_template(tmpl['id'])
                                    st.rerun()
                    else:
                        st.info("No templates yet. Create one to get started.")

            # --- SEND CAMPAIGN SECTION ---
            elif email_section == "📤 Send Campaign":
                st.subheader("Send Campaign")

                if not sendgrid_key:
                    st.error("⚠️ SendGrid API key not configured. Go to Settings to add your key.")
                else:
                    # Get available (non-contacted) leads
                    available_leads = get_team_basket_leads(user_team, filter_contacted=False)

                    if not available_leads:
                        st.info("No available leads to contact. All leads in your team basket have been contacted.")
                    else:
                        st.write(f"**{len(available_leads)} leads available** for outreach")

                        # Select leads
                        lead_options = {
                            f"{l.get('first_name', '')} {l.get('last_name', '')} - {l.get('email', '')}": l.get('apollo_id') or l.get('id')
                            for l in available_leads if l.get('email')
                        }

                        selected_lead_names = st.multiselect(
                            "Select Leads",
                            options=list(lead_options.keys()),
                            default=list(lead_options.keys())[:10] if len(lead_options) > 10 else list(lead_options.keys())
                        )

                        selected_lead_ids = [lead_options[name] for name in selected_lead_names]

                        st.write(f"**{len(selected_lead_ids)} leads selected**")

                        # Select template
                        templates = get_email_templates()
                        if not templates:
                            st.warning("No templates available. Create a template first.")
                        else:
                            template_options = {t['name']: t['id'] for t in templates}
                            selected_template_name = st.selectbox("Select Template", options=list(template_options.keys()))
                            selected_template_id = template_options[selected_template_name] if selected_template_name else None

                            # Sender info
                            col_sender1, col_sender2 = st.columns(2)
                            with col_sender1:
                                sender_email = st.text_input("From Email", value=user_email)
                            with col_sender2:
                                sender_name = st.text_input("From Name", value=st.session_state.user.get('name', ''))

                            # Campaign name
                            campaign_name = st.text_input("Campaign Name", value=f"Campaign {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")

                            # Preview
                            if selected_lead_ids and selected_template_id:
                                with st.expander("👁️ Preview Email"):
                                    preview = preview_email(selected_template_id, selected_lead_ids[0])
                                    if preview:
                                        st.write(f"**Subject:** {preview['subject']}")
                                        st.markdown(preview['body_html'], unsafe_allow_html=True)

                            # Send button
                            if st.button("🚀 Send Campaign", type="primary", disabled=not selected_lead_ids or not selected_template_id):
                                if not campaign_name:
                                    st.error("Campaign name is required.")
                                else:
                                    with st.spinner(f"Creating campaign and sending {len(selected_lead_ids)} emails..."):
                                        try:
                                            # Create campaign
                                            campaign_id = create_campaign(
                                                name=campaign_name,
                                                team_name=user_team,
                                                template_id=selected_template_id,
                                                sender_email=sender_email,
                                                sender_name=sender_name,
                                                created_by=user_email,
                                                lead_ids=selected_lead_ids
                                            )

                                            # Send campaign
                                            result = send_campaign(campaign_id, user_email)

                                            if result['success']:
                                                st.success(f"Campaign sent successfully! {result['sent_count']} emails delivered.")
                                            else:
                                                st.warning(f"Campaign completed with issues. Sent: {result['sent_count']}, Failed: {result['failed_count']}")
                                                if result['errors']:
                                                    with st.expander("View Errors"):
                                                        for err in result['errors'][:10]:
                                                            st.write(f"- {err}")

                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Failed to send campaign: {e}")
                                            sentry_sdk.capture_exception(e)

            # --- CAMPAIGNS SECTION ---
            elif email_section == "📋 Campaigns":
                st.subheader("Campaign History")

                campaigns = get_team_campaigns(user_team)

                if not campaigns:
                    st.info("No campaigns yet. Send your first campaign to see it here.")
                else:
                    campaign_data = []
                    for c in campaigns:
                        campaign_data.append({
                            'Name': c['name'],
                            'Status': c['status'],
                            'Recipients': c['total_recipients'],
                            'Sent': c['sent_count'],
                            'Created': c['created_at']
                        })

                    df_campaigns = pd.DataFrame(campaign_data)
                    st.dataframe(df_campaigns, use_container_width=True)

            # --- ANALYTICS SECTION ---
            elif email_section == "📊 Analytics":
                st.subheader("Email Analytics")

                stats = get_campaign_stats(user_team)

                col_a1, col_a2, col_a3, col_a4 = st.columns(4)
                col_a1.metric("Total Campaigns", stats.get('total_campaigns', 0))
                col_a2.metric("Emails Sent", stats.get('total_sent', 0))
                col_a3.metric("Opened", stats.get('total_opened', 0))
                col_a4.metric("Clicked", stats.get('total_clicked', 0))

                # Calculate rates
                total_sent = stats.get('total_sent', 0)
                if total_sent > 0:
                    open_rate = (stats.get('total_opened', 0) / total_sent) * 100
                    click_rate = (stats.get('total_clicked', 0) / total_sent) * 100

                    st.divider()
                    col_r1, col_r2 = st.columns(2)
                    col_r1.metric("Open Rate", f"{open_rate:.1f}%")
                    col_r2.metric("Click Rate", f"{click_rate:.1f}%")

            # --- SETTINGS SECTION ---
            elif email_section == "⚙️ Settings":
                st.subheader("Email Settings")

                with st.form("sendgrid_settings"):
                    st.write("**SendGrid API Configuration**")
                    st.caption("Your SendGrid API key is stored encrypted and used to send emails.")

                    current_status = "✅ Configured" if sendgrid_key else "❌ Not configured"
                    st.write(f"Current Status: {current_status}")

                    new_sendgrid_key = st.text_input(
                        "SendGrid API Key",
                        type="password",
                        placeholder="SG.xxxxx..."
                    )

                    if st.form_submit_button("Save SendGrid Key"):
                        if new_sendgrid_key:
                            save_sendgrid_key(user_email, new_sendgrid_key)
                            st.success("SendGrid API key saved successfully!")
                            st.rerun()
                        else:
                            st.error("Please enter a valid API key.")

    # --- ADMIN TAB ---
    if is_admin:
        with tab_admin:
            st.header("Admin Analytics")
            st.write("Club-wide usage and tracking.")
            
            c1, c2, c3 = st.columns(3)
            
            # Total Credits
            total_stats = query("SELECT SUM(credit_spent) as total FROM credit_logs")
            total_credits = total_stats[0]['total'] if total_stats and total_stats[0]['total'] else 0
            
            # Total Leads in DB
            total_leads = query("SELECT COUNT(*) as count FROM leads")
            
            # Total Enriched (use TRUE for PostgreSQL, 1 for SQLite)
            enriched_condition = "TRUE" if db_manager.DATABASE_URL else "1"
            total_enriched = query(f"SELECT COUNT(*) as count FROM leads WHERE is_enriched = {enriched_condition}")
            
            c1.metric("Credits Consumed", f"{total_credits}")
            c2.metric("Leads Stored", f"{total_leads[0]['count']}")
            c3.metric("Emails Revealed", f"{total_enriched[0]['count']}")
            
            st.divider()
            st.subheader("User Credit Usage")
            users_with_credits = query('''
                SELECT email, name, team_name, total_credits_used
                FROM users
                ORDER BY total_credits_used DESC
            ''')
            if users_with_credits:
                df_users = pd.DataFrame(users_with_credits)
                df_users.columns = ['Email', 'Name', 'Team', 'Credits Used']
                st.dataframe(df_users, width='stretch')
            else:
                st.info("No user credit data available.")
            
            st.divider()
            st.subheader("Team Credit Usage")
            teams_with_credits = []
            for team_name in ALLOWED_TEAMS:
                team_info = get_team_info(team_name)
                teams_with_credits.append({
                    'Team': team_info['name'],
                    'Total Credits': team_info['total_credits_used'],
                    'Members': team_info['member_count']
                })
            
            if teams_with_credits:
                df_teams = pd.DataFrame(teams_with_credits)
                df_teams = df_teams.sort_values('Total Credits', ascending=False)
                st.dataframe(df_teams, width='stretch')
            else:
                st.info("No team credit data available.")
            
            st.divider()
            st.subheader("Leaderboard (Credit Usage)")
            usage_data = query('''
                SELECT u.name, u.team_name, u.total_credits_used as credits
                FROM users u
                ORDER BY u.total_credits_used DESC
            ''')
            if usage_data:
                df_leaderboard = pd.DataFrame(usage_data)
                df_leaderboard.columns = ['Name', 'Team', 'Credits']
                st.table(df_leaderboard)
            else:
                st.info("No usage data recorded yet.")
            
            st.divider()
            st.subheader("Blacklist Management")
            with st.expander("Manage Blocked Domains"):
                new_blocked = st.text_input("Add Domain to Blacklist (e.g., google.com)")
                if st.button("Add to Blacklist"):
                    if new_blocked:
                        add_to_blacklist(new_blocked)
                        st.success(f"Added {new_blocked} to blacklist!")
                        st.rerun()
                
                st.write("**Current Blacklist:**")
                for b_domain in blacklist:
                    col_b, col_r = st.columns([3, 1])
                    col_b.write(f"- {b_domain}")
                    if col_r.button("Remove", key=f"rm_{b_domain}"):
                        remove_from_blacklist(b_domain)
                        st.rerun()

            st.divider()
            st.subheader("User Management")
            with st.expander("Add/Update Member"):
                with st.form("add_user_form"):
                    nu_email = st.text_input("Member Email")
                    nu_name = st.text_input("Full Name")
                    nu_team = st.selectbox("Team", options=ALLOWED_TEAMS, index=None, placeholder="Select a team")
                    nu_role = st.selectbox("Role", options=["consultant", "pm"], index=0, help="PMs can send email campaigns")
                    nu_membership = st.selectbox("Membership", options=["aba", "external"], index=0, help="ABA users are subject to the global blacklist; external users are not.")
                    nu_admin = st.checkbox("Is Administrator?")
                    nu_blacklist_exempt = st.checkbox("Blacklist Exempt?", help="If enabled, this user can search domains that are on the global blacklist.")
                    if st.form_submit_button("Save Member"):
                        if nu_email and nu_name and nu_team:
                            try:
                                add_user(
                                    nu_email,
                                    nu_name,
                                    nu_team,
                                    nu_admin,
                                    role=nu_role,
                                    blacklist_exempt=nu_blacklist_exempt,
                                    membership=nu_membership,
                                )
                                st.success(f"User {nu_name} updated in database!")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                        else:
                            st.error("Email, Name, and Team are required.")
            
            users = get_all_users()
            st.dataframe(pd.DataFrame(users), width='stretch')

            st.divider()
            st.subheader("Security Feed (Audit Logs)")
            audit_data = query("SELECT timestamp, user_email, event_type, details FROM audit_logs ORDER BY timestamp DESC LIMIT 20")
            if audit_data:
                st.dataframe(pd.DataFrame(audit_data), width='stretch')
            else:
                st.info("No security events recorded.")
            
            if SENTRY_DSN:
                st.info("🚀 Sentry Observability is active. Full error tracebacks are available in the Sentry Dashboard.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Hide raw tracebacks for a professional experience
        st.error("### 🏗️ Something went wrong")
        st.write("The application encountered an unexpected error. Please try again later.")
        
        # Log error locally for development
        log_error(e, context="Main application error")
        
        # We don't need to manually capture here since Sentry's SDK 
        # usually handles unhandled exceptions, but just in case:
        sentry_sdk.capture_exception(e)
