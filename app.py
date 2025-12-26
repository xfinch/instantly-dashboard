#!/usr/bin/env python3
"""
Instantly.ai Campaign Dashboard
Web UI for managing email campaigns
"""

import os
import sys
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


def get_client():
    """Get Instantly client"""
    return InstantlyClient()


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
        client = get_client()

        # Get campaign details
        campaign = None
        try:
            campaign = client._make_request("GET", f"campaigns/{CAMPAIGN_ID}", {})
        except:
            campaign = {
                'name': 'WA Integrative Medicine',
                'status': 0,
                'daily_limit': 50
            }

        # Get all leads
        all_leads = get_all_campaign_leads(client, CAMPAIGN_ID)
        clinic_leads = filter_clinic_leads(all_leads)

        # Get leads with different statuses
        active_leads = [l for l in clinic_leads if l.get('status') == 1]
        pending_leads = [l for l in clinic_leads if l.get('status') == 0]

        return jsonify({
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
        })
    except Exception as e:
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

        # Try to start campaign
        try:
            response = client._make_request("POST", f"campaigns/{CAMPAIGN_ID}/launch", {})
            return jsonify({'success': True, 'message': 'Campaign started'})
        except:
            # Try alternative - update status
            try:
                response = client._make_request("PUT", f"campaigns/{CAMPAIGN_ID}", {
                    "status": 1
                })
                return jsonify({'success': True, 'message': 'Campaign activated'})
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': 'Could not start via API. Please start manually in Instantly.ai dashboard.',
                    'error': str(e)
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
            response = client._make_request("PUT", f"campaigns/{CAMPAIGN_ID}", {
                "status": 0
            })
            return jsonify({'success': True, 'message': 'Campaign paused'})
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Could not pause via API',
                'error': str(e)
            }), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
