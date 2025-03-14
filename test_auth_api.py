import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API endpoint
url = "http://localhost:8000/api/auth/google"

print(f"Sending request to {url}")

# Test with both JSON and form data approaches
def test_json_approach():
    print("\n=== Testing JSON approach ===")
    payload = {"idToken": "test-token"}
    headers = {"Content-Type": "application/json"}
    
    print(f"Payload: {json.dumps(payload)}")
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        
        print(f"Status code: {response.status_code}")
        print(f"Response headers: {response.headers}")
        
        try:
            print(f"Response body: {json.dumps(response.json(), indent=2)}")
        except:
            print(f"Response text: {response.text}")
            
        if response.status_code == 200:
            print("Authentication successful!")
        else:
            print("Authentication failed!")
    except Exception as e:
        print(f"Error: {str(e)}")

def test_form_approach():
    print("\n=== Testing form data approach ===")
    form_data = {"idToken": "test-token"}
    
    print(f"Form data: {form_data}")
    
    try:
        response = requests.post(url, data=form_data)
        
        print(f"Status code: {response.status_code}")
        print(f"Response headers: {response.headers}")
        
        try:
            print(f"Response body: {json.dumps(response.json(), indent=2)}")
        except:
            print(f"Response text: {response.text}")
            
        if response.status_code == 200:
            print("Authentication successful!")
        else:
            print("Authentication failed!")
    except Exception as e:
        print(f"Error: {str(e)}")

# Run both tests
test_json_approach()
test_form_approach() 
