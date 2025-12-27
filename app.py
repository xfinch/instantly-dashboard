#!/usr/bin/env python3
"""
Instantly.ai Campaign Dashboard
Web UI for managing email campaigns
"""

import os
import sys
import json
from flask import Flask, render_template, jsonify, request
from functools import wraps

from instantly_client import InstantlyClient

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# HTTP Basic Auth
def check_auth(username, password):
    """Check if username/password combination is valid"""
    AUTH_USERNAME = os.environ.get('DASHBOARD_USERNAME', 'admin')
    AUTH_PASSWORD = os.environ.get('DASHBOARD_PASSWORD', 'changeme')
    return username == AUTH_USERNAME and password == AUTH_PASSWORD

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return ('Unauthorized', 401, {
        'WWW-Authenticate': 'Basic realm="Login Required"'
    })

def requires_auth(f):
    """Decorator to require HTTP Basic Auth"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


# Campaign constants
CAMPAIGN_ID = "bfe30fd9-3417-410f-800b-7b8e7151a965"
CLINIC_KEYWORDS = ['clinic', 'medicine', 'wellness', 'health', 'naturopathic',
                   'integrative', 'holistic', 'doctor', 'dr.', 'medical']

# Load enriched data
ENRICHED_DATA = {}
def load_enriched_data():
    """Load enriched lead data from JSON file"""
    global ENRICHED_DATA

    # Try multiple paths for the enriched data file
    possible_paths = [
        os.path.join(os.path.dirname(__file__), 'all_wa_leads_enriched.json'),  # Same directory (for Railway)
        os.path.join(os.path.dirname(__file__), '..', '.tmp', 'all_wa_leads_enriched.json'),  # Local dev
    ]

    for enriched_path in possible_paths:
        try:
            if os.path.exists(enriched_path):
                with open(enriched_path, 'r') as f:
                    leads = json.load(f)
                    # Index by email for quick lookup
                    for lead in leads:
                        if lead.get('email'):
                            ENRICHED_DATA[lead['email'].lower()] = lead
                print(f"✓ Loaded {len(ENRICHED_DATA)} enriched leads from {enriched_path}")
                return
        except Exception as e:
            print(f"Error loading from {enriched_path}: {e}")
            continue

    print("⚠ Warning: No enriched data file found. Lead details and personalization will not be available.")

# Load enriched data on startup
load_enriched_data()


def get_client():
    """Get Instantly client"""
    try:
        return InstantlyClient()
    except Exception as e:
        print(f"ERROR: Failed to initialize Instantly client: {e}")
        print(f"INSTANTLY_API_KEY is {'set' if os.environ.get('INSTANTLY_API_KEY') else 'NOT SET'}")
        raise


def get_all_campaign_leads(client, campaign_id):
    """Get all leads from campaign with pagination"""
    all_leads = []
    skip = 0

    while True:
        try:
            response = client._make_request('POST', 'leads/list', {
                'campaign_id': campaign_id,
                'skip': skip,
                'limit': 100
            })

            if 'items' in response and response['items']:
                all_leads.extend(response['items'])
                skip += 100
                if len(response['items']) < 100:
                    break
            else:
                break
        except Exception as e:
            print(f"Error fetching leads: {e}")
            break

    return all_leads


def filter_clinic_leads(leads):
    """Filter for clinic-related leads with emails"""
    return [
        l for l in leads
        if l.get('email') and
        l.get('email') != 'No email' and
        any(kw in l.get('company_name', '').lower() for kw in CLINIC_KEYWORDS)
    ]


@app.route('/')
@requires_auth
def dashboard():
    """Main dashboard view"""
    return render_template('dashboard.html')


@app.route('/api/campaign/stats')
@requires_auth
def campaign_stats():
    """Get campaign statistics"""
    try:
        print("Starting campaign_stats endpoint")
        client = get_client()
        print("Client initialized successfully")

        # Get campaign details
        campaign = None
        try:
            campaign = client._make_request("GET", f"campaigns/{CAMPAIGN_ID}", {})
            print(f"Campaign fetched: {campaign.get('name')}")
        except Exception as e:
            print(f"Campaign fetch failed: {e}, using defaults")
            campaign = {
                'name': 'WA Integrative Medicine',
                'status': 0,
                'daily_limit': 50
            }

        # Get all leads
        print("Fetching leads...")
        all_leads = get_all_campaign_leads(client, CAMPAIGN_ID)
        print(f"Fetched {len(all_leads)} total leads")

        clinic_leads = filter_clinic_leads(all_leads)
        print(f"Filtered to {len(clinic_leads)} clinic leads")

        # Get leads with different statuses
        active_leads = [l for l in clinic_leads if l.get('status') == 1]
        pending_leads = [l for l in clinic_leads if l.get('status') == 0]

        result = {
            'campaign': {
                'name': campaign.get('name', 'WA Integrative Medicine'),
                'id': CAMPAIGN_ID,
                'status': 'Active' if campaign.get('status') == 1 else 'Paused',
                'daily_limit': campaign.get('daily_limit', 50)
            },
            'stats': {
                'total_leads': len(all_leads),
                'clinic_leads': len(clinic_leads),
                'other_leads': len(all_leads) - len(clinic_leads),
                'active_leads': len(active_leads),
                'pending_leads': len(pending_leads)
            }
        }
        print(f"Returning stats: {result}")
        return jsonify(result)
    except Exception as e:
        print(f"ERROR in campaign_stats: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/campaign/leads')
@requires_auth
def campaign_leads():
    """Get campaign leads"""
    try:
        client = get_client()

        # Get pagination params
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        filter_type = request.args.get('filter', 'clinics')  # clinics, all, other

        # Get all leads
        all_leads = get_all_campaign_leads(client, CAMPAIGN_ID)

        # Filter based on type
        if filter_type == 'clinics':
            leads = filter_clinic_leads(all_leads)
        elif filter_type == 'other':
            clinic_leads = filter_clinic_leads(all_leads)
            clinic_emails = {l.get('email') for l in clinic_leads}
            leads = [l for l in all_leads if l.get('email') not in clinic_emails]
        else:
            leads = all_leads

        # Paginate
        total = len(leads)
        start = (page - 1) * per_page
        end = start + per_page
        page_leads = leads[start:end]

        return jsonify({
            'leads': [
                {
                    'email': l.get('email', 'No email'),
                    'company': l.get('company_name', 'No company'),
                    'status': 'Active' if l.get('status') == 1 else 'Pending',
                    'custom_fields': {
                        'website': l.get('website', ''),
                        'phone': l.get('phone', '')
                    }
                }
                for l in page_leads
            ],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/campaign/start', methods=['POST'])
@requires_auth
def start_campaign():
    """Start the campaign"""
    try:
        client = get_client()

        # Update campaign status to active (paused: false)
        try:
            response = client._make_request("PATCH", f"campaigns/{CAMPAIGN_ID}", {
                "paused": False
            })
            return jsonify({'success': True, 'message': 'Campaign started successfully'})
        except Exception as e:
            print(f"Error starting campaign: {e}")
            return jsonify({
                'success': False,
                'message': f'Could not start campaign via API: {str(e)}',
                'note': 'You may need to start the campaign manually in the Instantly.ai dashboard.'
            }), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/campaign/pause', methods=['POST'])
@requires_auth
def pause_campaign():
    """Pause the campaign"""
    try:
        client = get_client()

        try:
            response = client._make_request("PATCH", f"campaigns/{CAMPAIGN_ID}", {
                "paused": True
            })
            return jsonify({'success': True, 'message': 'Campaign paused successfully'})
        except Exception as e:
            print(f"Error pausing campaign: {e}")
            return jsonify({
                'success': False,
                'message': f'Could not pause campaign via API: {str(e)}',
                'note': 'You may need to pause the campaign manually in the Instantly.ai dashboard.'
            }), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/lead/details/<email>')
@requires_auth
def lead_details(email):
    """Get enriched details for a specific lead"""
    try:
        email_lower = email.lower()
        enriched = ENRICHED_DATA.get(email_lower)

        if not enriched:
            return jsonify({'error': 'Lead not found in enriched data'}), 404

        # Return relevant enriched information
        details = {
            'company_name': enriched.get('title', 'Unknown'),
            'category': enriched.get('categoryName', 'N/A'),
            'address': enriched.get('address', 'N/A'),
            'city': enriched.get('city', 'N/A'),
            'state': enriched.get('state', 'N/A'),
            'website': enriched.get('website', 'N/A'),
            'phone': enriched.get('phone', 'N/A'),
            'rating': enriched.get('totalScore'),
            'review_count': enriched.get('reviewsCount', 0),
            'hours': enriched.get('openingHours', []),
            'accessibility': enriched.get('additionalInfo', {}).get('Accessibility', []),
            'amenities': enriched.get('additionalInfo', {}).get('Amenities', []),
            'payments': enriched.get('additionalInfo', {}).get('Payments', []),
        }

        return jsonify(details)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/campaign/message-preview')
@requires_auth
def message_preview():
    """Get message preview with personalization"""
    try:
        client = get_client()
        email = request.args.get('email', '')

        # Get campaign details to retrieve email template
        campaign = client._make_request("GET", f"campaigns/{CAMPAIGN_ID}", {})

        # Get enriched data for personalization
        enriched = ENRICHED_DATA.get(email.lower()) if email else None

        # Extract email sequences from campaign
        sequences = campaign.get('sequences', [])

        if not sequences:
            return jsonify({'error': 'No email sequences found'}), 404

        # Get first email in sequence
        first_email = sequences[0] if sequences else {}

        # Personalize the message if we have enriched data
        subject = first_email.get('subject', '')
        body = first_email.get('body', '')

        if enriched:
            # Replace common variables
            company_name = enriched.get('title', 'your practice')
            city = enriched.get('city', '')
            category = enriched.get('categoryName', 'healthcare provider')

            personalization = {
                'company_name': company_name,
                'city': city,
                'category': category,
                'rating': enriched.get('totalScore'),
                'review_count': enriched.get('reviewsCount', 0)
            }
        else:
            personalization = {
                'company_name': '{{company_name}}',
                'city': '{{city}}',
                'category': '{{category}}',
                'rating': '{{rating}}',
                'review_count': '{{review_count}}'
            }

        return jsonify({
            'subject': subject,
            'body': body,
            'personalization': personalization,
            'sequence_position': 1,
            'total_sequences': len(sequences)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
