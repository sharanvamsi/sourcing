"""
Session Middleware Service for HTTP-Only Cookie Management
Run this as a separate service alongside Streamlit to handle secure cookie setting.

Usage:
    python session_middleware.py

This service runs on port 8502 and handles:
- Setting HTTP-only cookies via Set-Cookie headers
- Reading session tokens from cookies
- Session validation

For production, run this behind nginx which will set HTTP-only cookies.
"""
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import os
import sys

# Add parent directory to path to import db_manager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_manager import (
    create_user_session, get_user_from_session,
    delete_user_session, get_user,
    get_sent_email_by_message_id, update_sent_email,
    record_email_event, mark_lead_contacted, get_campaign
)
from datetime import datetime

app = Flask(__name__)
CORS(app, supports_credentials=True)

@app.route('/api/session/create', methods=['POST'])
def create_session():
    """Create a new session and return token (nginx will set HTTP-only cookie)"""
    data = request.json
    user_email = data.get('email')
    
    if not user_email:
        return jsonify({'error': 'Email required'}), 400
    
    # Verify user exists
    user = get_user(user_email)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Create session
    session_token = create_user_session(user_email)
    
    # Create response with HTTP-only cookie
    response = make_response(jsonify({
        'success': True,
        'session_token': session_token,
        'user': {
            'email': user['email'],
            'name': user['name'],
            'team_name': user['team_name']
        }
    }))
    
    # Set HTTP-only, Secure cookie (nginx will handle this in production)
    response.set_cookie(
        'session_token',
        value=session_token,
        max_age=86400,  # 24 hours
        httponly=True,
        secure=True,  # HTTPS only
        samesite='Lax',
        path='/'
    )
    
    return response

@app.route('/api/session/validate', methods=['GET'])
def validate_session():
    """Validate existing session from cookie"""
    session_token = request.cookies.get('session_token')
    
    if not session_token:
        return jsonify({'valid': False}), 401
    
    user = get_user_from_session(session_token)
    if not user:
        return jsonify({'valid': False}), 401
    
    return jsonify({
        'valid': True,
        'user': {
            'email': user['email'],
            'name': user['name'],
            'team_name': user['team_name']
        }
    })

@app.route('/api/session/delete', methods=['POST'])
def delete_session():
    """Delete session and clear cookie"""
    session_token = request.cookies.get('session_token')

    if session_token:
        delete_user_session(session_token)

    response = make_response(jsonify({'success': True}))
    response.set_cookie('session_token', '', expires=0, path='/')

    return response


@app.route('/api/webhooks/sendgrid', methods=['POST'])
def sendgrid_webhook():
    """
    Handle SendGrid webhook events for email tracking.

    Events handled:
    - delivered: Email was delivered
    - open: Email was opened
    - click: Link in email was clicked
    - bounce: Email bounced

    SendGrid sends an array of event objects.
    """
    try:
        events = request.json

        if not events or not isinstance(events, list):
            return jsonify({'error': 'Invalid payload'}), 400

        processed = 0
        for event in events:
            event_type = event.get('event')
            sg_message_id = event.get('sg_message_id')
            timestamp = event.get('timestamp')

            if not sg_message_id:
                continue

            # Find the sent_email record
            sent_email = get_sent_email_by_message_id(sg_message_id)
            if not sent_email:
                # Try with different message ID formats
                # SendGrid sometimes sends just the first part
                if '.' in sg_message_id:
                    short_id = sg_message_id.split('.')[0]
                    sent_email = get_sent_email_by_message_id(short_id)

            if not sent_email:
                continue

            # Record the event
            record_email_event(
                sent_email_id=sent_email['id'],
                sendgrid_message_id=sg_message_id,
                event_type=event_type,
                event_data=event
            )

            # Update sent_email status based on event type
            if event_type == 'delivered':
                update_sent_email(sent_email['id'], status='delivered')

            elif event_type == 'open':
                # First open sets opened_at, subsequent opens increment count
                updates = {'open_count': sent_email.get('open_count', 0) + 1}
                if not sent_email.get('opened_at'):
                    updates['opened_at'] = datetime.now()
                    updates['status'] = 'opened'
                update_sent_email(sent_email['id'], **updates)

            elif event_type == 'click':
                # First click sets clicked_at, subsequent clicks increment count
                updates = {'click_count': sent_email.get('click_count', 0) + 1}
                if not sent_email.get('clicked_at'):
                    updates['clicked_at'] = datetime.now()
                    updates['status'] = 'clicked'
                update_sent_email(sent_email['id'], **updates)

            elif event_type == 'bounce':
                update_sent_email(sent_email['id'], status='bounced')

            processed += 1

        return jsonify({'success': True, 'processed': processed})

    except Exception as e:
        import sentry_sdk
        sentry_sdk.capture_exception(e)
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Install: pip install flask flask-cors
    app.run(host='127.0.0.1', port=8502, debug=False)



