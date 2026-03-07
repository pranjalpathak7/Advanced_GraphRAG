import os
import requests
import json
import time
from typing import List, Dict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
REPO_OWNER = "langchain-ai"
REPO_NAME = "langchain"
LIMIT = 100 
OUTPUT_DIR = "data/raw_issues"

def fetch_github_issues(owner: str, repo: str, limit: int = 100) -> List[Dict]:
    """
    Fetches issues from GitHub API with authentication and rate limit handling.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    token = os.getenv("GITHUB_TOKEN")
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
    }
    
    if token:
        headers["Authorization"] = f"token {token}"
        print("🔐 Using GitHub Token for authentication (High Rate Limit)")
    else:
        print("⚠️ No GitHub Token found. Rate limits will be low (60/hr).")

    params = {
        "state": "all",  # Open and closed
        "per_page": 100, # Max per page
        "sort": "created",
        "direction": "desc"
    }
    
    all_issues = []
    page = 1
    
    print(f"🚀 Fetching issues from {owner}/{repo}...")
    
    while len(all_issues) < limit:
        params["page"] = page
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            batch = response.json()
            if not batch:
                break
            
            all_issues.extend(batch)
            print(f"   Fetched page {page} ({len(batch)} issues)...")
            page += 1
        elif response.status_code == 403:
            print("❌ Rate limit exceeded! Wait or check your token.")
            break
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            break
            
        time.sleep(0.5)

    return all_issues[:limit]

def save_issues_locally(issues: List[Dict]):
    """
    Saves issues as individual JSON files for idempotency.
    """
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"wm Created directory: {OUTPUT_DIR}")
        
    print(f"💾 Saving {len(issues)} issues to disk...")
    
    for issue in issues:
        issue_number = issue.get("number")
        file_path = os.path.join(OUTPUT_DIR, f"issue_{issue_number}.json")
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(issue, f, indent=2)
            
    print(f"✅ Success! Data saved to {OUTPUT_DIR}")

if __name__ == "__main__":
    try:
        data = fetch_github_issues(REPO_OWNER, REPO_NAME, LIMIT)
        save_issues_locally(data)
    except Exception as e:
        print(f"❌ Critical Error: {e}")