"""
Email Service for SendGrid Integration

Handles email sending, template personalization, and campaign orchestration.
"""
import os
import re
import sentry_sdk
from datetime import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, TrackingSettings, OpenTracking, ClickTracking

from db_manager import (
    get_sendgrid_key, get_lead_by_id, get_email_template,
    get_campaign, get_campaign_emails, update_sent_email,
    update_campaign_status, update_campaign_sent_count,
    mark_lead_contacted
)


def get_sendgrid_client(user_email):
    """
    Gets a configured SendGrid client for the user.

    Args:
        user_email: User's email to retrieve their SendGrid API key

    Returns:
        SendGridAPIClient instance or None if no key configured
    """
    api_key = get_sendgrid_key(user_email)
    if not api_key:
        return None
    return SendGridAPIClient(api_key=api_key)


def personalize_template(template_str, lead):
    """
    Replaces template variables with lead data.

    Supported variables:
        {{first_name}} - Lead's first name
        {{last_name}} - Lead's last name
        {{company}} - Organization name
        {{title}} - Job title
        {{email}} - Lead's email address

    Args:
        template_str: Template string with {{variable}} placeholders
        lead: Lead dictionary with data

    Returns:
        Personalized string with variables replaced
    """
    if not template_str:
        return template_str

    # Extract values from lead, handling nested organization
    first_name = lead.get('first_name', '')
    last_name = lead.get('last_name', '')
    title = lead.get('title', '')
    email = lead.get('email', '')

    # Handle organization which might be nested or flat
    company = ''
    if isinstance(lead.get('organization'), dict):
        company = lead.get('organization', {}).get('name', '')
    elif lead.get('organization_name'):
        company = lead.get('organization_name', '')
    elif lead.get('company'):
        company = lead.get('company', '')

    # Replace all variables
    replacements = {
        '{{first_name}}': first_name or '',
        '{{last_name}}': last_name or '',
        '{{company}}': company or '',
        '{{title}}': title or '',
        '{{email}}': email or '',
    }

    result = template_str
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, str(value))

    return result


def send_campaign_email(sg_client, sender_email, sender_name, recipient_email, subject, body_html, body_text=None):
    """
    Sends a single email via SendGrid with open/click tracking enabled.

    Args:
        sg_client: SendGrid client instance
        sender_email: From email address
        sender_name: From display name
        recipient_email: To email address
        subject: Email subject
        body_html: HTML body content
        body_text: Plain text body (optional)

    Returns:
        dict with 'success', 'message_id', 'error' keys
    """
    try:
        # Build the message
        from_email = (sender_email, sender_name) if sender_name else sender_email

        message = Mail(
            from_email=from_email,
            to_emails=recipient_email,
            subject=subject,
            html_content=body_html
        )

        if body_text:
            message.plain_text_content = body_text

        # Enable open and click tracking
        tracking_settings = TrackingSettings()
        tracking_settings.open_tracking = OpenTracking(enable=True)
        tracking_settings.click_tracking = ClickTracking(enable=True, enable_text=True)
        message.tracking_settings = tracking_settings

        # Send the email
        response = sg_client.send(message)

        # Extract message ID from headers
        message_id = None
        if hasattr(response, 'headers') and 'X-Message-Id' in response.headers:
            message_id = response.headers['X-Message-Id']

        if response.status_code in (200, 201, 202):
            return {
                'success': True,
                'message_id': message_id,
                'error': None
            }
        else:
            return {
                'success': False,
                'message_id': None,
                'error': f"SendGrid returned status {response.status_code}"
            }

    except Exception as e:
        sentry_sdk.capture_exception(e)
        return {
            'success': False,
            'message_id': None,
            'error': str(e)
        }


def send_campaign(campaign_id, user_email):
    """
    Sends all pending emails in a campaign.

    Args:
        campaign_id: ID of the campaign to send
        user_email: Email of the PM sending (to get their SendGrid key)

    Returns:
        dict with 'success', 'sent_count', 'failed_count', 'errors' keys
    """
    # Get SendGrid client
    sg_client = get_sendgrid_client(user_email)
    if not sg_client:
        return {
            'success': False,
            'sent_count': 0,
            'failed_count': 0,
            'errors': ['SendGrid API key not configured. Please add your SendGrid key in settings.']
        }

    # Get campaign details
    campaign = get_campaign(campaign_id)
    if not campaign:
        return {
            'success': False,
            'sent_count': 0,
            'failed_count': 0,
            'errors': ['Campaign not found']
        }

    # Get template
    template = get_email_template(campaign['template_id'])
    if not template:
        return {
            'success': False,
            'sent_count': 0,
            'failed_count': 0,
            'errors': ['Email template not found']
        }

    # Update campaign status to sending
    update_campaign_status(campaign_id, 'sending')

    # Get all pending emails
    campaign_emails = get_campaign_emails(campaign_id)
    pending_emails = [e for e in campaign_emails if e['status'] == 'pending']

    sent_count = 0
    failed_count = 0
    errors = []

    for sent_email in pending_emails:
        lead_id = sent_email['lead_id']
        lead = get_lead_by_id(lead_id)

        if not lead or not lead.get('email'):
            failed_count += 1
            errors.append(f"Lead {lead_id}: No email address")
            update_sent_email(sent_email['id'], status='failed')
            continue

        # Personalize template
        personalized_subject = personalize_template(template['subject'], lead)
        personalized_html = personalize_template(template['body_html'], lead)
        personalized_text = personalize_template(template.get('body_text', ''), lead) if template.get('body_text') else None

        # Send the email
        result = send_campaign_email(
            sg_client=sg_client,
            sender_email=campaign['sender_email'],
            sender_name=campaign.get('sender_name'),
            recipient_email=lead['email'],
            subject=personalized_subject,
            body_html=personalized_html,
            body_text=personalized_text
        )

        if result['success']:
            sent_count += 1
            update_sent_email(
                sent_email['id'],
                status='sent',
                sendgrid_message_id=result['message_id'],
                sent_at=datetime.now()
            )
            # Mark lead as contacted in team basket
            mark_lead_contacted(campaign['team_name'], lead_id, user_email)
        else:
            failed_count += 1
            errors.append(f"Lead {lead_id}: {result['error']}")
            update_sent_email(sent_email['id'], status='failed')

    # Update campaign status and counts
    final_status = 'sent' if failed_count == 0 else 'sent'  # Mark as sent even with some failures
    if sent_count == 0 and failed_count > 0:
        final_status = 'failed'

    update_campaign_status(campaign_id, final_status)
    update_campaign_sent_count(campaign_id, sent_count)

    return {
        'success': failed_count == 0,
        'sent_count': sent_count,
        'failed_count': failed_count,
        'errors': errors
    }


def preview_email(template_id, lead_id):
    """
    Generates a preview of an email for a specific lead.

    Args:
        template_id: ID of the template
        lead_id: ID of the lead

    Returns:
        dict with 'subject', 'body_html', 'body_text' keys or None if error
    """
    template = get_email_template(template_id)
    if not template:
        return None

    lead = get_lead_by_id(lead_id)
    if not lead:
        return None

    return {
        'subject': personalize_template(template['subject'], lead),
        'body_html': personalize_template(template['body_html'], lead),
        'body_text': personalize_template(template.get('body_text', ''), lead) if template.get('body_text') else None
    }
