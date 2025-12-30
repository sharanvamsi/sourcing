import os
import requests
import sentry_sdk
from dotenv import load_dotenv

load_dotenv()

def view_contact(contact_id):
    """
    Retrieves details for an existing contact in your team's Apollo database.
    
    Args:
        contact_id: The ID of the contact to retrieve
    
    Returns:
        Dictionary containing contact details, or None if error
    """
    api_key = os.getenv("MASTER_API_KEY")
    if not api_key:
        print("Error: MASTER_API_KEY not found in environment variables.")
        return None

    url = f"https://api.apollo.io/api/v1/contacts/{contact_id}"
    
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            contact = data.get('contact', {})
            return contact
        elif response.status_code == 403:
            print("Error: 403 Forbidden - This endpoint requires a master API key.")
            print("Please ensure you're using a master API key, not a restricted key.")
            return None
        elif response.status_code == 404:
            print(f"Error: 404 Not Found - Contact with ID '{contact_id}' not found.")
            return None
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            return None
            
    except Exception as e:
        sentry_sdk.capture_exception(e)
        print(f"An error occurred: {e}")
        return None

if __name__ == "__main__":
    # Test with a sample contact ID
    # Note: You'll need to replace this with an actual contact ID from your Apollo database
    test_contact_id = "57d94c6fa6da9872327af90e"  # Example ID from enrich_response_sample.json
    
    print(f"--- VIEWING CONTACT: {test_contact_id} ---\n")
    contact = view_contact(test_contact_id)
    
    if contact:
        print("Contact Details:")
        print(f"  ID: {contact.get('id', 'N/A')}")
        print(f"  Name: {contact.get('first_name', '')} {contact.get('last_name', '')}")
        print(f"  Title: {contact.get('title', 'N/A')}")
        print(f"  Email: {contact.get('email', 'N/A')}")
        print(f"  Organization: {contact.get('organization', {}).get('name', 'N/A') if contact.get('organization') else 'N/A'}")
        print(f"  LinkedIn: {contact.get('linkedin_url', 'N/A')}")
        print(f"  Email Status: {contact.get('email_status', 'N/A')}")
    else:
        print("Failed to retrieve contact details.")


