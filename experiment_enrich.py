import os
import requests
import json
import sentry_sdk
import math
from dotenv import load_dotenv
from experiment_search import search_people

load_dotenv()

def enrich_people(people_list):
    """
    Enriches a list of people using Apollo's bulk_match endpoint.
    Batches in groups of 10.
    """
    api_key = os.getenv("BULK_MATCH_API_KEY") or os.getenv("MIXED_PEOPLE_API_KEY")
    if not api_key:
        print("Error: No API Key found for enrichment.")
        return people_list

    url = "https://api.apollo.io/v1/people/bulk_match"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key
    }

    enriched_results = []
    batch_size = 10
    
    for i in range(0, len(people_list), batch_size):
        batch = people_list[i:i + batch_size]
        
        payload = {
            "details": batch,
            "reveal_personal_emails": True 
        }

        try:
            # Manually serialize to handle datetime objects from DB
            json_payload = json.dumps(payload, default=str)
            response = requests.post(url, headers=headers, data=json_payload)
            if response.status_code == 200:
                data = response.json()
                matches = data.get('matches', [])
                
                for idx, match_item in enumerate(matches):
                    if match_item and match_item.get('email'):
                        original_person = batch[idx].copy()
                        # Update with revealed data
                        original_person.update(match_item)
                        enriched_results.append(original_person)
            else:
                # RAISE instead of print, so UI can catch it
                raise Exception(f"Apollo API Error {response.status_code}: {response.text}")
        except Exception as e:
            sentry_sdk.capture_exception(e)
            # Re-raise so the UI knows enrichment failed
            raise e




    return enriched_results

if __name__ == "__main__":
    # Test script same as before...
    print("STEP 1: SEARCHING...")
    results = search_people(domain="apple.com", job_titles=["Engineering"], max_results=5)
    if results:
        print("STEP 2: ENRICHING...")
        enriched = enrich_people(results)
        if enriched:
            for p in enriched:
                print(f"{p.get('first_name')} {p.get('last_name')} -> {p.get('email')}")
        else:
            print("No enriched results found.")
    else:
        print("No results found.")
