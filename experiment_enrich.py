import os
import requests
import json
import sentry_sdk
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from experiment_search import search_people

load_dotenv()

def _enrich_batch(batch, api_key, batch_index):
    """
    Enriches a single batch of people using Apollo's bulk_match endpoint.
    Returns a list of enriched people from this batch.
    """
    url = "https://api.apollo.io/v1/people/bulk_match"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key
    }
    
    payload = {
        "details": batch,
        "reveal_personal_emails": True 
    }

    try:
        # Manually serialize to handle datetime objects from DB
        json_payload = json.dumps(payload, default=str)
        response = requests.post(url, headers=headers, data=json_payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            matches = data.get('matches', [])
            
            batch_results = []
            for idx, match_item in enumerate(matches):
                if match_item and match_item.get('email'):
                    original_person = batch[idx].copy()
                    # Update with revealed data
                    original_person.update(match_item)
                    batch_results.append(original_person)
            return batch_index, batch_results, None
        else:
            error = Exception(f"Apollo API Error {response.status_code}: {response.text}")
            return batch_index, [], error
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return batch_index, [], e

def enrich_people(people_list, max_workers=5):
    """
    Enriches a list of people using Apollo's bulk_match endpoint.
    Batches in groups of 10 and processes batches in parallel.
    
    Args:
        people_list: List of people dictionaries to enrich
        max_workers: Maximum number of parallel API calls (default: 5)
    
    Returns:
        List of enriched people with emails revealed
    """
    api_key = os.getenv("BULK_MATCH_API_KEY") or os.getenv("MIXED_PEOPLE_API_KEY")
    if not api_key:
        error_msg = "Error: No API Key found for enrichment."
        print(error_msg)
        sentry_sdk.capture_message(error_msg, level="error")
        raise ValueError(error_msg)

    if not people_list:
        return []

    batch_size = 10
    batches = []
    
    # Create batches
    for i in range(0, len(people_list), batch_size):
        batch = people_list[i:i + batch_size]
        batches.append((i // batch_size, batch))
    
    enriched_results = []
    errors = []
    
    # Process batches in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all batch processing tasks
        future_to_batch = {
            executor.submit(_enrich_batch, batch, api_key, batch_index): batch_index 
            for batch_index, batch in batches
        }
        
        # Collect results as they complete
        batch_results = {}
        for future in as_completed(future_to_batch):
            batch_index, results, error = future.result()
            batch_results[batch_index] = (results, error)
            if error:
                errors.append(error)
    
    # Combine results in order
    for batch_index in sorted(batch_results.keys()):
        results, error = batch_results[batch_index]
        enriched_results.extend(results)
    
    # If any batch failed, raise the first error
    if errors:
        raise errors[0]




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
