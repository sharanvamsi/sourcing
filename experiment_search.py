import os
import math
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
    
    # Apollo API typically has a maximum per_page limit of 100
    MAX_PER_PAGE = 100
    per_page = min(max_results, MAX_PER_PAGE)
    
    # Base payload (without page-specific params)
    base_payload = {
        # Only use q_organization_domains if it looks like a domain
        "q_organization_domains": domain if domain and "." in domain else None,
        "person_titles": job_titles,
        "person_locations": locations,
        "person_seniorities": seniority,
        "contact_email_status": "verified",
        "per_page": per_page
    }
    
    base_payload = {k: v for k, v in base_payload.items() if v is not None}

    all_people = []
    current_page = 1
    
    try:
        # Pagination loop: fetch pages until we have enough results or run out of pages
        while len(all_people) < max_results:
            # Create payload for this page
            payload = base_payload.copy()
            payload["page"] = current_page
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code != 200:
                print(f"Error: {response.status_code}")
                print(response.text)
                # If we have some results, return what we have; otherwise return empty
                break
            
            data = response.json()
            page_people = data.get('people', [])
            
            # If no people returned, we've reached the end
            if not page_people:
                break
            
            # Filter to only people with emails and add to our collection
            for person in page_people:
                if person.get('has_email'):
                    all_people.append(person)
                    # Stop if we've reached max_results
                    if len(all_people) >= max_results:
                        break
            
            # Check if there are more pages available
            total_entries = data.get('total_entries', 0)
            pagination = data.get('pagination', {})
            total_pages = pagination.get('total_pages')
            
            # If pagination object doesn't have total_pages, calculate from total_entries
            if total_pages is None and total_entries > 0:
                total_pages = math.ceil(total_entries / per_page)
            elif total_pages is None:
                total_pages = 1
            
            # If we've fetched all available pages or reached max_results, stop
            if current_page >= total_pages or len(all_people) >= max_results:
                break
            
            current_page += 1
        
        # Return up to max_results people
        return all_people[:max_results]
            
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"An error occurred: {e}")
        # Return whatever we've collected so far, if any
        return all_people[:max_results] if all_people else []

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
