import os
import requests
import json
from dotenv import load_dotenv
from experiment_search import search_people

load_dotenv()

def enrich_people(people):
    
    api_key = os.getenv("BULK_MATCH_API_KEY")
    if not api_key:
        print("Error: BULK_MATCH_API_KEY not found in environment variables.")
        return

    url = "https://api.apollo.io/v1/people/bulk_match"
    
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key
    }
    
    enriched_results = []
    total_credits = 0
    BATCH_SIZE = 10
    
    # Process in batches
    for i in range(0, len(people), BATCH_SIZE):
        batch = people[i:i + BATCH_SIZE]
        print(f"Processing batch {i//BATCH_SIZE + 1} ({len(batch)} people)...")
        
        payload = {
            "details": batch,
            "reveal_personal_emails": True 
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                credits = data.get('credits_consumed', 0)
                total_credits += credits
                
                matches = data.get('matches', [])
                
                for match in matches:
                    first = match.get('first_name') or ""
                    last = match.get('last_name') or ""
                    email = match.get('email') or "N/A"
                    company = match.get('organization', {}).get('name') or "N/A"
                    title = match.get('title') or "N/A"
                    
                    person_data = {
                        "first_name": first,
                        "last_name": last,
                        "company": company,
                        "title": title,
                        "email": email
                    }
                    enriched_results.append(person_data)
            else:
                print(f"Batch Error: {response.status_code}")
                print(response.text)
                
        except Exception as e:
            print(f"An error occurred in batch processing: {e}")
    
    print(f"Total Credits Consumed: {total_credits}")
    return enriched_results

if __name__ == "__main__":
    # Integration Test
    # 1. Search
    print("STEP 1: SEARCHING...")
    search_results = search_people(
        domain="openai",
        job_titles=["Software Engineer"],
        locations=["San Francisco"],
        max_results=25 # Keep small to save credits
    )
    
    print(f"search_results: {search_results}")
    if search_results:
        # 2. Enrich
        print("\nSTEP 2: ENRICHING...")
        final_data = enrich_people(search_results)
        
        print("\nFINAL ENRICHED DATA:")
        for p in final_data:
            print(p)
    else:
        print("No search results to enrich.")
