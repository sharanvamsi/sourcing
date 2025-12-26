import os
import requests
import sentry_sdk
from dotenv import load_dotenv

load_dotenv()

from db_manager import get_cached_domain, update_domain_cache

def find_company_domain(company_name):
    # Normalize key to lower case for consistent caching
    cache_key = company_name.strip().lower()
    
    # 1. Check DB Cache
    cached_domain = get_cached_domain(cache_key)
    if cached_domain:
        print(f"DB Cache Hit: '{company_name}' -> {cached_domain}")
        return cached_domain
        
    print(f"Searching for domain of company: '{company_name}'...")
    
    # Use the same key as search/enrich, assuming it has permissions
    api_key = os.getenv("ORG_SEARCH_API_KEY")
    if not api_key:
        print("Error: ORG_SEARCH_API_KEY not found in environment variables.")
        return None

    url = "https://api.apollo.io/v1/organizations/search"
    
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key
    }
    
    payload = {
        "q_organization_name": company_name,
        "page": 1,
        "per_page": 1
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            organizations = data.get('organizations', [])
            
            if organizations:
                # Get the first match
                org = organizations[0]
                name = org.get('name')
                domain = org.get('primary_domain')
                
                print(f"Found: {name} -> {domain}")
                
                # 2. Update DB Cache
                if domain:
                    update_domain_cache(cache_key, domain)
                    
                return domain
            else:
                print("No organizations found.")
                return None
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            return None
            
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"An error occurred: {e}")
        return None

if __name__ == "__main__":
    companies_to_test = [
        "gatesfoundation.org",      # User's specific case
    ]

    print("\n--- STARTING RIGOROUS DOMAIN RESOLUTION TEST ---\n")
    
    for company in companies_to_test:
        print(f"Testing: '{company}'")
        domain = find_company_domain(company)
        print(f"Result : {domain}")
        print("-" * 30)

    print("\n--- CACHE VERIFICATION (Re-running 'Google') ---")
    find_company_domain("Google") # Should hit cache
