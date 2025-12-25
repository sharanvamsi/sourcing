import json
import os
from experiment_search import search_people
from experiment_enrich import enrich_people

LOG_FILE = "test_execution_log.txt"

def log_to_file(content):
    with open(LOG_FILE, "a") as f:
        f.write(content + "\n")

def run_test_case(test_name, domain, job_titles, locations, max_results=3):
    print(f"Running {test_name}...")
    
    log_to_file(f"==================================================")
    log_to_file(f"TEST CASE: {test_name}")
    log_to_file(f"Parameters: Domain={domain}, Titles={job_titles}, Locations={locations}")
    log_to_file(f"==================================================")

    # 1. Search
    log_to_file("\n--- STEP 1: KEYWORD SEARCH OUTPUT ---")
    try:
        search_results = search_people(domain, job_titles, locations, max_results)
        formatted_search = json.dumps(search_results, indent=4)
        log_to_file(formatted_search)
    except Exception as e:
        log_to_file(f"Search failed with error: {e}")
        search_results = []

    # 2. Enrich (if results found)
    enriched_data = []
    log_to_file("\n--- STEP 2: ENRICHMENT OUTPUT ---")
    if search_results:
        try:
            enriched_data = enrich_people(search_results)
            formatted_enrich = json.dumps(enriched_data, indent=4)
            log_to_file(formatted_enrich)
        except Exception as e:
            log_to_file(f"Enrichment failed with error: {e}")
    else:
        log_to_file("Skipping enrichment (no search results).")

    log_to_file("\n") # Spacing between tests

def main():
    # Clear log file
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    
    # Test Case 1: Standard Success (Google)
    run_test_case(
        "Standard Search (Google)",
        domain="google.com",
        job_titles=["Software Engineer"],
        locations=["San Francisco, CA"],
        max_results=3
    )

    # Test Case 2: Invalid Domain
    run_test_case(
        "Invalid Domain Search",
        domain="thisdomainsurelydoesnotexist12345.com",
        job_titles=["CEO"],
        locations=None,
        max_results=3
    )

    # Test Case 3: Special Characters in Title (should handle encoding/querying correctly)
    run_test_case(
        "Special Characters Title (C++)",
        domain="google.com",
        job_titles=["C++ Developer"],
        locations=None,
        max_results=2
    )
    
    # Test Case 4: Broad Search (No Location)
    run_test_case(
        "Broad Search (No Location)",
        domain="stripe.com",
        job_titles=["Engineer"],
        locations=None,
        max_results=2
    )

    # Test Case 5: International/Special Characters
    run_test_case(
        "International Characters (Desarrollador)",
        domain="spotify.com",
        job_titles=["Desarrollador"], # Spanish for Developer
        locations=None,
        max_results=2
    )

    # Test Case 6: Pagination/Limit Check
    # Apollo max per page is usually 100. Let's try a non-standard number to ensure 'per_page' param works.
    run_test_case(
        "Specific Limit (1 result)",
        domain="airbnb.com",
        job_titles=["Designer"],
        locations=["San Francisco"],
        max_results=1
    )

    # Test Case 7: Batching Check (>10 results)
    run_test_case(
        "Batching Check (12 results)",
        domain="google.com",
        job_titles=["Software Engineer"],
        locations=["San Francisco, CA"],
        max_results=12
    )

    print(f"\nTests completed. Check {LOG_FILE} for detailed output.")

if __name__ == "__main__":
    main()
