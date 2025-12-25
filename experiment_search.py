import os
import requests
import json
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
    
    api_key = os.getenv("MIXED_PEOPLE_API_KEY")
    if not api_key:
        print("Error: MIXED_PEOPLE_API_KEY not found in environment variables.")
        return

    url = "https://api.apollo.io/v1/mixed_people/api_search"
    
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key
    }
    
    payload = {
        "q_organization_domains": domain,
        "person_titles": job_titles,
        "person_locations": locations,
        "person_seniorities": seniority,
        "per_page": max_results,
        "page": 1
    }
    
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        response = requests.post(url, headers=headers, json=payload)
        
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
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    print("\nXXX TEST 1: Standard Search (Company Name 'Google' -> should resolve to google.com) XXX")
    search_people(
        domain="Google", # Testing resolution
        job_titles=["Software Engineer"],
        locations=["San Francisco, CA"],
        max_results=3
    )

    print("\nXXX TEST 2: Invalid Domain (should find nothing or error gracefully) XXX")
    search_people(
        domain="thisdomaindoesnotexist12345.com",
        job_titles=["Software Engineer"],
        max_results=3
    )

    print("\nXXX TEST 3: Special Characters in Title XXX")
    search_people(
        domain="google.com",
        job_titles=["C++ Developer", ".NET Developer"], # Special chars
        max_results=3
    )

    print("\nXXX TEST 4: Empty Locations (should default to world/any) XXX")
    search_people(
        domain="google.com",
        job_titles=["CEO"],
        locations=None,
        max_results=1
    )
