import streamlit as st
import requests

st.set_page_config(page_title="Consulting Club Lead Sorter")

st.title("ABA Sourcing")

with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("Apollo API Key", type="password")

if st.button("Connection Test"):
    if not api_key:
        st.error("Please enter an API Key.")
    else:
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
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                st.success("Connection Successful! API Key is valid.")
            else:
                st.error(f"Connection Failed. Status Code: {response.status_code}")
                st.json(response.json())
        except Exception as e:
            st.error(f"An error occurred: {e}")
