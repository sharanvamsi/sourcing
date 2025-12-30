import os
from re import search
import requests
import sentry_sdk
from dotenv import load_dotenv
from experiment_org_search import find_company_domain

load_dotenv()

def search_people(domain=None, job_titles=None, locations=None, seniority=None, max_results=10):
    # Resolve company name to domain if necessary
    if domain and "." not in domain:
        print(f"Resolving domain for company: '{domain}'...")
        resolved = find_company_domain(domain)
        if resolved:
            domain = resolved
        else:
            print(f"Warning: Could not resolve domain for '{domain}'. Using as is.")
    
    api_key = os.getenv("APOLLO_API_KEY")
    if not api_key:
        print("Error: APOLLO_API_KEY not found in environment variables.")
        return []

    url = "https://api.apollo.io/v1/mixed_people/api_search"
    
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key
    }
    
    payload = {
        # Only use q_organization_domains if it looks like a domain
        "q_organization_domains": domain if domain and "." in domain else None,
        "person_titles": job_titles,
        "person_locations": locations,
        "person_seniorities": seniority,
        "contact_email_status": "verified",
        "per_page": max_results,
        "page": 1
    }
    
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            all_people = data.get('people', [])
            people = [p for p in all_people if p.get('has_email')]
            
            for person in people:
                id = person.get('id') or ""
                first = person.get('first_name') or ""
                last = person.get('last_name') or person.get('last_name_obfuscated') or ""
                name = f"{first} {last}".strip() or "N/A"
                
                title = person.get('title', "")
                org_name = 'N/A'
                if person.get('organization'):
                    org_name = person['organization'].get('name', 'N/A')
            return people
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            return []
            
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"An error occurred: {e}")
        return []

if __name__ == "__main__":
    print("\nTest: Standard Search (Company Name 'Google' -> should resolve to google.com)")
    results = search_people(
        domain="Google", # Testing resolution
        job_titles=["Software Engineer"],
        locations=["San Francisco, CA"],
        max_results=100
    )
    
    if results:
        print(f"\nFound {len(results)} people:\n")
        for person in results:
            first_name = person.get('first_name', 'N/A')
            last_name = person.get('last_name') or person.get('last_name_obfuscated', 'N/A')
            title = person.get('title', 'N/A')
            company = 'N/A'
            if person.get('organization'):
                company = person['organization'].get('name', 'N/A')
            
            print(f"{first_name} {last_name} | {company} | {title}")
    else:
        print("No results found.")
