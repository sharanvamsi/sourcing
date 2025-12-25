import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

CACHE_FILE = "domain_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=4)

def find_company_domain(company_name):
    # Normalize key to lower case for consistent caching
    cache_key = company_name.strip().lower()
    
    # 1. Check Cache
    cache = load_cache()
    if cache_key in cache:
        print(f"Cache Hit: '{company_name}' -> {cache[cache_key]}")
        return cache[cache_key]
        
    print(f"Searching for domain of company: '{company_name}'...")
    
    # Use the same key as search/enrich, assuming it has permissions
    # Or fallback to APOLLO_API_KEY if defined
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
                
                # 2. Update Cache
                if domain:
                    cache[cache_key] = domain
                    save_cache(cache)
                    
                return domain
            else:
                print("No organizations found.")
                return None
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            return None
            
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

if __name__ == "__main__":
    # Test Cases
    print("--- Run 1 (API Calls expected if empty cache) ---")
    find_company_domain("Stripe")
    find_company_domain("OpenAI")
    
    print("\n--- Run 2 (Cache Hits expected) ---")
    find_company_domain("Stripe")
    find_company_domain("OpenAI")
    
    print("\n--- New Query ---")
    find_company_domain("Airbnb")
