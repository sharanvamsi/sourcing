import os
import requests
import json
import sentry_sdk
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from experiment_search import search_people
from db_manager import get_lead_by_id, is_lead_enriched, store_enriched_lead, check_team_basket_duplicates

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
        "reveal_personal_emails": False 
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

def enrich_people(people_list, max_workers=5, team_name=None):
    """
    Enriches a list of people using Apollo's bulk_match endpoint.
    Checks database first to avoid redundant API calls for already-enriched contacts.
    If team_name is provided, also checks team basket for duplicates (saves credits).
    Batches in groups of 10 and processes batches in parallel.

    Args:
        people_list: List of people dictionaries to enrich
        max_workers: Maximum number of parallel API calls (default: 5)
        team_name: Optional team name to check for duplicates in team basket

    Returns:
        dict with keys:
            - 'enriched': List of enriched people with emails revealed
            - 'skipped_duplicates': List of leads that were skipped (already in team basket)
            - 'credits_used': Number of credits actually used (excludes duplicates)
        If team_name is None, returns just the list for backward compatibility.
    """
    api_key = os.getenv("APOLLO_API_KEY")
    if not api_key:
        error_msg = "Error: APOLLO_API_KEY not found for enrichment."
        print(error_msg)
        sentry_sdk.capture_message(error_msg, level="error")
        raise ValueError(error_msg)

    if not people_list:
        if team_name:
            return {'enriched': [], 'skipped_duplicates': [], 'credits_used': 0}
        return []

    # Step 0: If team_name provided, check for duplicates in team basket first
    skipped_duplicates = []
    if team_name:
        duplicates, people_list = check_team_basket_duplicates(team_name, people_list)
        skipped_duplicates = duplicates

        if not people_list:
            # All leads are duplicates
            return {'enriched': [], 'skipped_duplicates': skipped_duplicates, 'credits_used': 0}

    # Step 1: Check database for already-enriched contacts
    already_enriched = []
    needs_enrichment = []
    enrichment_map = {}  # Maps original index to enriched data from DB

    for idx, person in enumerate(people_list):
        apollo_id = person.get('id')
        if not apollo_id:
            # If no ID, we need to enrich via API
            needs_enrichment.append((idx, person))
            continue

        # Check if already enriched in database
        if is_lead_enriched(apollo_id):
            # Get enriched data from database
            enriched_lead = get_lead_by_id(apollo_id)
            if enriched_lead and enriched_lead.get('email'):
                # Store mapping to maintain order
                enrichment_map[idx] = enriched_lead
                already_enriched.append(idx)
        else:
            # Needs enrichment via API
            needs_enrichment.append((idx, person))
    
    # Step 2: Enrich contacts that need API calls
    api_enriched_results = []
    if needs_enrichment:
        # Extract just the person objects for API calls
        people_to_enrich = [person for _, person in needs_enrichment]
        
        batch_size = 10
        batches = []
        
        # Create batches
        for i in range(0, len(people_to_enrich), batch_size):
            batch = people_to_enrich[i:i + batch_size]
            batches.append((i // batch_size, batch))
        
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
            if error:
                continue  # Skip failed batches
            api_enriched_results.extend(results)
        
        # If any batch failed, raise the first error
        if errors:
            raise errors[0]
        
        # Step 3: Store newly enriched contacts in database
        for enriched_person in api_enriched_results:
            apollo_id = enriched_person.get('id')
            if apollo_id:
                try:
                    # Store complete enrichment data
                    store_enriched_lead(apollo_id, enriched_person)
                except Exception as e:
                    # Log error but continue processing
                    sentry_sdk.capture_exception(e)
                    print(f"Warning: Failed to store enriched lead {apollo_id}: {e}")
        
        # Map API results back to original indices
        api_idx = 0
        for orig_idx, _ in needs_enrichment:
            if api_idx < len(api_enriched_results):
                enrichment_map[orig_idx] = api_enriched_results[api_idx]
                api_idx += 1
    
    # Step 4: Combine results maintaining original order
    final_results = []
    for idx in range(len(people_list)):
        if idx in enrichment_map:
            enriched_person = enrichment_map[idx]
            # Only include if email exists (filtered by API or DB)
            if enriched_person.get('email'):
                final_results.append(enriched_person)

    # Calculate credits used (only API calls cost credits, not DB lookups)
    credits_used = len([p for _, p in needs_enrichment])

    if team_name:
        return {
            'enriched': final_results,
            'skipped_duplicates': skipped_duplicates,
            'credits_used': credits_used
        }

    return final_results

if __name__ == "__main__":
    # Test script same as before...
    print("STEP 1: SEARCHING...")
    results = search_people(domain="apple.com", job_titles=["Engineering"], max_results=25)
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
