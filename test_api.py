import os
from dotenv import load_dotenv

load_dotenv()

def test_connection():
    print("Apollo API Connection Test")
    print("--------------------------")
    
    # Securely get API key
    api_key = os.getenv("APOLLO_API_KEY")
    
    if not api_key:
        print("Error: API Key cannot be empty.")
        return

    url = "https://api.apollo.io/v1/organizations/search"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key
    }
    params = {
        "q": "google.com"
    }

    try:
        print("\nTesting connection...")
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            print("\nSUCCESS: Connection works!")
            print(f"Status Code: {response.status_code}")
            # print("Response sample:", response.json()) # Optional: print data
        else:
            print(f"\nFAILURE: API returned status code {response.status_code}")
            print("Response:", response.text)
            
    except Exception as e:
        print(f"\nERROR: Could not connect. Details: {e}")

if __name__ == "__main__":
    test_connection()
