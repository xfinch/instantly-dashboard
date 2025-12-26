#!/usr/bin/env python3
"""
Instantly.ai API Client
Upload leads to Instantly.ai for cold email campaigns
"""

import os
import json
import requests
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()


class InstantlyClient:
    """Client for Instantly.ai API"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('INSTANTLY_API_KEY')
        if not self.api_key:
            raise ValueError("INSTANTLY_API_KEY not found in environment")

        # Try v2 API first
        self.base_url = "https://api.instantly.ai/api/v2"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make API request to Instantly"""
        url = f"{self.base_url}/{endpoint}"

        try:
            if method == "GET":
                response = requests.get(url, headers=self.headers, params=data)
            elif method == "POST":
                response = requests.post(url, headers=self.headers, json=data)
            elif method == "PUT":
                response = requests.put(url, headers=self.headers, json=data)
            elif method == "DELETE":
                response = requests.delete(url, headers=self.headers)

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"❌ API Error: {e}")
            if hasattr(e.response, 'text'):
                print(f"   Response: {e.response.text}")
            raise

    def get_campaigns(self) -> List[Dict]:
        """Get all campaigns"""
        response = self._make_request("GET", "campaigns")
        # V2 API returns paginated results
        return response.get('data', []) if isinstance(response, dict) else response

    def create_campaign(self, name: str) -> Dict:
        """Create a new campaign"""
        from datetime import datetime, timedelta

        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

        data = {
            "name": name,
            "campaign_schedule": {
                "start_date": today,
                "end_date": end_date,
                "schedules": [
                    {
                        "name": "Business Hours",
                        "timing": {
                            "from": "09:00",
                            "to": "17:00"
                        },
                        "days": {
                            "monday": True,
                            "tuesday": True,
                            "wednesday": True,
                            "thursday": True,
                            "friday": True
                        },
                        "timezone": "America/Chicago"
                    }
                ]
            },
            "sequences": [
                {
                    "steps": [
                        {
                            "type": "email",
                            "delay": 2,
                            "variants": [
                                {
                                    "subject": "Quick Question",
                                    "body": "Hi there,\n\nI wanted to reach out."
                                }
                            ]
                        }
                    ]
                }
            ],
            "daily_limit": 50,
            "email_gap": 30,
            "random_wait_max": 60,
            "stop_on_reply": True,
            "link_tracking": True,
            "open_tracking": True
        }
        return self._make_request("POST", "campaigns", data)

    def add_lead(self, lead_data: Dict) -> Dict:
        """
        Add a single lead

        Args:
            lead_data: Lead dict with required fields:
                - email (required)
                - campaign_id (required)
                - first_name (optional)
                - last_name (optional)
                - company_name (optional)
                - website (optional)
                - phone (optional)
                - custom variables (optional)
        """
        return self._make_request("POST", "leads", lead_data)

    def format_lead_for_instantly(self, lead: Dict) -> Dict:
        """
        Format a lead from our system for Instantly.ai

        Args:
            lead: Lead dict with our format (from Google Maps scraping)

        Returns:
            Formatted lead for Instantly.ai API
        """
        # Extract name from business title if available
        title = lead.get('title', '')

        # Basic mapping
        formatted = {
            "email": lead.get('primary_email', ''),
            "company_name": title,
            "website": lead.get('website', ''),
            "phone": lead.get('phone', ''),
        }

        # Add custom fields for additional data
        formatted.update({
            "custom_field_1": lead.get('address', ''),  # Full address
            "custom_field_2": lead.get('category', ''),  # Business category
            "custom_field_3": f"{lead.get('rating', '')} ({lead.get('reviewCount', '')} reviews)",  # Rating
            "custom_field_4": lead.get('city', ''),  # City
            "custom_field_5": lead.get('state', ''),  # State
        })

        # Remove empty fields
        return {k: v for k, v in formatted.items() if v}

    def upload_leads_from_json(self, json_file: str, campaign_name: str) -> Dict:
        """
        Upload leads from JSON file to Instantly.ai

        Args:
            json_file: Path to JSON file with enriched leads
            campaign_name: Name for the campaign

        Returns:
            Upload results
        """
        # Load leads
        with open(json_file, 'r') as f:
            leads = json.load(f)

        # Filter leads with emails
        leads_with_emails = [l for l in leads if l.get('primary_email')]

        print(f"\n📧 Uploading Leads to Instantly.ai")
        print(f"   Total leads: {len(leads)}")
        print(f"   Leads with emails: {len(leads_with_emails)}")

        if not leads_with_emails:
            print("❌ No leads with emails found")
            return {}

        # Get or create campaign
        campaigns = self.get_campaigns()
        campaign = None

        for c in campaigns:
            if c.get('name') == campaign_name:
                campaign = c
                print(f"✅ Using existing campaign: {campaign_name}")
                break

        if not campaign:
            print(f"📝 Creating new campaign: {campaign_name}")
            campaign = self.create_campaign(campaign_name)

        # Format leads for Instantly
        formatted_leads = [self.format_lead_for_instantly(l) for l in leads_with_emails]

        # Upload leads one by one (v2 API adds campaign_id per lead)
        total_uploaded = 0
        failed = 0

        for i, formatted_lead in enumerate(formatted_leads):
            # Add campaign_id to each lead
            formatted_lead['campaign_id'] = campaign['id']

            try:
                self.add_lead(formatted_lead)
                total_uploaded += 1
                if (i + 1) % 10 == 0:
                    print(f"📤 Uploaded {i + 1}/{len(formatted_leads)} leads...")
            except Exception as e:
                failed += 1
                if failed <= 3:  # Only show first 3 errors
                    print(f"❌ Failed to upload lead {i + 1}: {e}")

        print(f"\n✅ Upload complete!")
        print(f"   Total uploaded: {total_uploaded}/{len(leads_with_emails)}")
        print(f"   Campaign: {campaign_name}")
        print(f"   Campaign ID: {campaign['id']}")

        return {
            "campaign": campaign,
            "total_leads": len(leads),
            "uploaded": total_uploaded,
            "success_rate": f"{(total_uploaded/len(leads_with_emails)*100):.1f}%"
        }


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print("Usage: python3 instantly_client.py <leads_json_file> <campaign_name>")
        print("\nExample:")
        print("  python3 instantly_client.py .tmp/all_wa_leads_enriched.json 'WA Integrative Medicine'")
        sys.exit(1)

    json_file = sys.argv[1]
    campaign_name = sys.argv[2]

    client = InstantlyClient()
    result = client.upload_leads_from_json(json_file, campaign_name)
