import os
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import base64
from bs4 import BeautifulSoup
from datetime import datetime
import csv

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Define the pattern at the module level
investor_pattern = re.compile(r'([^.]+?)\s*led the round and (?:were|was) joined by\s*(.*?)(?:\.|\s*$)', re.IGNORECASE)

def get_gmail_service():
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def get_recent_emails_from_sender(service, sender_email, max_results=10):
    results = service.users().messages().list(userId='me', q=f'from:{sender_email}', maxResults=max_results).execute()
    messages = results.get('messages', [])

    emails = []
    for message in messages:
        msg = service.users().messages().get(userId='me', id=message['id'], format='full').execute()
        
        # Get email subject and date
        subject = ''
        date = ''
        for header in msg['payload']['headers']:
            if header['name'] == 'Subject':
                subject = header['value']
            elif header['name'] == 'Date':
                date = header['value']
            if subject and date:
                break

        # Get email body
        body = ''
        if 'parts' in msg['payload']:
            for part in msg['payload']['parts']:
                if part['mimeType'] == 'text/plain':
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    break
        else:
            if 'data' in msg['payload']['body']:
                body = base64.urlsafe_b64decode(msg['payload']['body']['data']).decode('utf-8')

        if not body:
            print(f"Warning: Could not extract body for email with subject: {subject}")
        
        emails.append({
            'subject': subject,
            'body': body,
            'date': date
        })

    return emails

def extract_venture_deals(email_content, deal_date):
    venture_deals = []
    
    if not email_content:
        print("Email content is empty.")
        return venture_deals

    # Split the content by newlines
    lines = email_content.split('\n')
    start_index = next((i for i, line in enumerate(lines) if 'VENTURE DEALS' in line), -1)
    if start_index == -1:
        print("No 'VENTURE DEALS' section found in the email.")
        return venture_deals

    print("Found 'VENTURE DEALS' section.")
    deals_text = lines[start_index+1:]

    # Process each deal
    current_deal = ""
    for line in deals_text:
        line = line.strip()
        if 'PRIVATE EQUITY' in line:
            print("Reached 'PRIVATE EQUITY' section. Stopping processing for this email.")
            break
        if line.startswith('-'):
            if current_deal:
                venture_deals.append(parse_deal(current_deal, deal_date))
            current_deal = line
        elif line:
            current_deal += " " + line
    
    # Add the last deal if we haven't reached PRIVATE EQUITY
    if current_deal and 'PRIVATE EQUITY' not in current_deal:
        venture_deals.append(parse_deal(current_deal, deal_date))

    return venture_deals

def parse_deal(deal_text, deal_date):
    # Extract company name and URL
    company_match = re.search(r'-\s*(.*?)\s*<(https?://[^>]+)>', deal_text)
    if company_match:
        company_name = company_match.group(1).strip()
        company_url = company_match.group(2)
        company_info = deal_text.split('>')[1].strip()  # Get the text after the URL
    else:
        company_name = "No company name found"
        company_url = "No URL found"
        company_info = deal_text

    # Extract funding amount
    funding_match = re.search(r'([$€£¥]?[0-9,.]+\s?(?:million|billion))', company_info)
    funding_amount = funding_match.group(1) if funding_match else "No funding amount found"

    # Extract investors
    investor_match = investor_pattern.search(company_info)
    if investor_match:
        lead_investors = investor_match.group(1).strip()
        joined_investors = investor_match.group(2).strip()
        investors = f"{lead_investors}, {joined_investors}"
    else:
        # Try to find investors after "funding from" anywhere in the company_info
        funding_from_match = re.search(r'funding from\s*(.*?)(?=\.\s*[A-Z]|\s*$)', company_info, re.IGNORECASE | re.DOTALL)
        if funding_from_match:
            investors = funding_from_match.group(1).strip()
        else:
            investors = "No investors found"

    # Process investors
    if investors != "No investors found":
        # Remove "and others" and replace "existing investors" with a comma
        investors = re.sub(r'\s*,?\s*and\s+others?\s*', '', investors, flags=re.IGNORECASE)
        investors = re.sub(r'\s*,?\s*existing\s+investors?\s*', ',', investors, flags=re.IGNORECASE)
        # Remove any trailing comma and whitespace
        investors = investors.rstrip(',').strip()
        # Split by comma and 'and', then rejoin with commas
        investors = [inv.strip() for inv in re.split(r',\s*|\s+and\s+', investors) if inv.strip()]
        
        # Remove trailing period from the last investor, if present
        if investors and investors[-1].endswith('.'):
            investors[-1] = investors[-1].rstrip('.')
        
        investors = ', '.join(investors)
        
        # Additional step to remove any remaining 'and' and handle commas
        def replace_and(match):
            parts = match.group(0).split('and')
            if len(parts) == 2:
                before, after = parts
                before = before.strip().rstrip(',')
                after = after.strip().lstrip(',')
                if before and after:
                    return f"{before}, {after}"
                elif before:
                    return before
                elif after:
                    return after
            return match.group(0)  # If we can't split it, return the original string

        investors = re.sub(r'(^|,\s*)and(\s*,|$)', r'\1\2', investors, flags=re.IGNORECASE)  # Remove 'and' at start or end of list
        investors = re.sub(r'\w*\s*\band\b\s*\w*', replace_and, investors, flags=re.IGNORECASE)
        
        # Remove any duplicate commas and leading/trailing commas
        investors = re.sub(r',\s*,', ',', investors).strip(',').strip()

        # Final check to remove any remaining 'and's
        def remove_and(investor):
            # Remove 'and' when it's preceded by a space and followed by a capital letter
            return re.sub(r'\s+and(?=[A-Z])', ', ', investor)

        investor_list = re.split(r',\s*', investors)
        investor_list = [remove_and(inv.strip()) for inv in investor_list]
        investors = ', '.join(filter(None, investor_list))  # filter(None, ...) removes any empty strings
    
    return {
        'company_name': company_name,
        'url': company_url,
        'funding': funding_amount,
        'investors': investors,
        'deal_date': deal_date
    }

def export_to_csv(venture_deals, filename='venture_deals.csv'):
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['company_name', 'company_URL', 'funding', 'investors', 'deal_date']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for deal in venture_deals:
            # Rename the 'url' key to 'Company URL' for the CSV output
            deal_copy = deal.copy()
            deal_copy['company_URL'] = deal_copy.pop('url')
            writer.writerow(deal_copy)

def main():
    service = get_gmail_service()
    sender_email = 'fortune@newsletter.fortune.com'
    num_emails = 30  # Set to 1 for the most recent email
    emails = get_recent_emails_from_sender(service, sender_email, max_results=num_emails)

    print(f"Fetched {len(emails)} most recent emails from {sender_email}")
    all_venture_deals = []
    for i, email in enumerate(emails, 1):
        print(f"\nProcessing Email {i}:")
        print(f"Subject: {email['subject']}")
        print(f"Date: {email['date']}")
        
        # Parse the email date
        email_date = datetime.strptime(email['date'], "%a, %d %b %Y %H:%M:%S %z")
        deal_date = email_date.strftime("%Y-%m-%d")
        
        if email['body']:
            venture_deals = extract_venture_deals(email['body'], deal_date)
            all_venture_deals.extend(venture_deals)
            print(f"Venture Deals found: {len(venture_deals)}")
            for deal in venture_deals:
                print(f"  - Company: {deal['company_name']}")
                print(f"    URL: {deal['url']}")
                print(f"    Funding: {deal['funding']}")
                print(f"    Investors: {deal['investors']}")
                print(f"    Deal Date: {deal['deal_date']}")
                print()
        else:
            print("Email body is empty. Skipping venture deals extraction.")

    if all_venture_deals:
        export_to_csv(all_venture_deals)
        print(f"\nExported {len(all_venture_deals)} venture deals to CSV.")
    else:
        print("\nNo venture deals found to export.")

if __name__ == '__main__':
    main()
