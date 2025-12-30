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
    delete_user_session, get_user
)

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

if __name__ == '__main__':
    # Install: pip install flask flask-cors
    app.run(host='127.0.0.1', port=8502, debug=False)

