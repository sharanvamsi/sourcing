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
    check_team_credit_limit
)
from local_error_logger import log_error

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
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
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
    
    # Fetch active profiles and settings from DB
    # (Note: For local-to-cloud migration, use the cloud_sync.py utility)
    blacklist = get_blacklist()

    # 2. LOGIN SCREEN
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
            st.session_state.user = None
            st.session_state.api_keys = None
            st.session_state.basket = []
            st.session_state.search_results = []
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
        st.write(f"**Team:** {st.session_state.user['team_name']}")
        st.write(f"**Basket:** {len(st.session_state.basket)} leads")
        
        # Display user's credit usage
        user_email = st.session_state.user['email']
        total_credits = get_user_credit_total(user_email)
        st.write(f"**Credits Used:** {total_credits}")
        
        if st.button("Logout"):
            st.session_state.user = None
            st.session_state.api_keys = None
            st.session_state.basket = []
            st.session_state.search_results = []
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
    tabs = ["🔍 Search", "🛒 Basket"]
    # Admin Check: Add Admin tab if DB record says so
    is_admin = bool(st.session_state.user.get('is_admin', False))
    if is_admin:
        tabs.append("📊 Admin")
        
    tab_list = st.tabs(tabs)
    tab_search = tab_list[0]
    tab_basket = tab_list[1]
    if is_admin:
        tab_admin = tab_list[2]

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
            elif check_blacklist(domain_query, blacklist):
                st.error(f"🛑 Access Denied: '{domain_query}' is on the Global Blacklist.")
            else:
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
                is_selected = person['id'] in st.session_state.selected_ids
                
                col_mark, col_details = st.columns([1, 10])
                with col_mark:
                    st.checkbox("", key=f"chk_{person['id']}")
                    
                    if st.session_state[f"chk_{person['id']}"]:
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
            st.dataframe(df[available_display], use_container_width=True)

            col_b1, col_b2 = st.columns([1, 4])
            if col_b1.button("Clear Basket"):
                clear_basket(st.session_state.user['email'])
                st.session_state.basket = []
                st.session_state.enriched = False
                st.rerun()
                
            if col_b2.button("✨ Enrich & Checkout", type="primary"):
                # Check team credit limit before enrichment
                user_email = st.session_state.user['email']
                user_team = st.session_state.user['team_name']
                credits_needed = len(st.session_state.basket)
                
                is_allowed, remaining, current = check_team_credit_limit(user_team, credits_to_add=credits_needed)
                
                if not is_allowed:
                    if remaining is not None and remaining == 0:
                        st.error("🚫 Credit Limit Reached: Your team has used all 4,500 credits. Please contact your PMs.")
                    else:
                        st.error(f"🚫 Credit Limit Exceeded: This enrichment would use {credits_needed} credits, but your team only has {remaining} credits remaining out of 4,500. Please reduce your basket size.")
                    st.stop()
                
                with st.spinner("Enriching contacts (this uses credits)..."):
                    try:
                        results = enrich_people(st.session_state.basket)
                        
                        if not results:
                             st.warning("No emails could be revealed for these contacts. They were filtered from the export.")
                        else:
                             # DB Persistence: Update leads with emails & full names
                             for p in results:
                                 update_lead_enrichment(p['id'], p)
                             
                             # Log usage
                             log_credit_usage(user_email, "Enrichment", len(results))
                             st.success(f"Enrichment Complete! {len(results)} emails revealed.")
                        
                        # Refresh local session basket from DB
                        st.session_state.basket = get_basket_leads(user_email)
                        st.session_state.enriched = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Enrichment Failed: {e}")
                        st.info("Your basket has been preserved. Please check your **Bulk Match API Key** in settings.")
                        # Log error locally for development
                        log_error(e, context="Enrichment process failed")
                        sentry_sdk.capture_exception(e)

            if st.session_state.get('enriched', False):
                # CSV output: first name, last name, company, title and email
                csv_cols = ['first_name', 'last_name', 'company', 'title', 'email']
                # Create a fresh DF for export to ensure column order and presence
                export_df = pd.DataFrame(st.session_state.basket)
                # Ensure company and last name are prepared
                if 'organization' in export_df.columns:
                    export_df['company'] = export_df['organization'].apply(lambda x: x.get('name') if isinstance(x, dict) else str(x))
                
                available_csv = [c for c in csv_cols if c in export_df.columns]
                csv_data = export_df[available_csv].to_csv(index=False).encode('utf-8')
                
                st.download_button(
                    label="Download Enriched CSV", 
                    data=csv_data, 
                    file_name="apollo_enriched_leads.csv", 
                    mime="text/csv"
                )

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
            
            # Total Enriched
            total_enriched = query("SELECT COUNT(*) as count FROM leads WHERE is_enriched = 1")
            
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
                st.dataframe(df_users, use_container_width=True)
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
                st.dataframe(df_teams, use_container_width=True)
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
                    nu_admin = st.checkbox("Is Administrator?")
                    if st.form_submit_button("Save Member"):
                        if nu_email and nu_name and nu_team:
                            try:
                                add_user(nu_email, nu_name, nu_team, nu_admin)
                                st.success(f"User {nu_name} updated in database!")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                        else:
                            st.error("Email, Name, and Team are required.")
            
            users = get_all_users()
            st.dataframe(pd.DataFrame(users), use_container_width=True)

            st.divider()
            st.subheader("Security Feed (Audit Logs)")
            audit_data = query("SELECT timestamp, user_email, event_type, details FROM audit_logs ORDER BY timestamp DESC LIMIT 20")
            if audit_data:
                st.dataframe(pd.DataFrame(audit_data), use_container_width=True)
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
