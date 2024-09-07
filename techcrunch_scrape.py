import requests
from bs4 import BeautifulSoup
import csv
from datetime import datetime, timedelta
import re
import json
import os
import time
import random

# TechCrunch base URL
base_url = "https://techcrunch.com/category/startups/page/"

# Function to load existing articles database
def load_articles_database():
    if os.path.exists("articles_database.json"):
        with open("articles_database.json", 'r') as f:
            return json.load(f)
    return []

# Function to save updated articles database
def save_articles_database(articles):
    with open("articles_database.json", 'w') as f:
        json.dump(articles, f)

# Load existing articles
existing_articles = load_articles_database()
existing_links = set(article['Link'] for article in existing_articles)

# Modify the keywords to include more variations
funding_keywords = ["funding", "raises", "raised", "raising", "series", "seed", "investment", "invested", "investing", "valuation", "round", "capital", "venture", "equity", "financing"]
currency_symbols = ["€", "$", "£", "¥"]  # Add more currency symbols if needed

# List to hold new articles
new_articles = []

# Get the date one month ago
one_month_ago = datetime.now() - timedelta(days=30)

# Set a maximum number of pages to scrape
MAX_PAGES = 15

# Function to implement exponential backoff
def exponential_backoff(attempt):
    return min(30, 2 ** attempt + random.uniform(0, 1))

# Function to make a request with rate limiting
def make_request(url, session, attempt=0):
    try:
        response = session.get(url)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        if attempt < 5:  # Max 5 retries
            wait_time = exponential_backoff(attempt)
            print(f"Error occurred: {e}. Retrying in {wait_time:.2f} seconds...")
            time.sleep(wait_time)
            return make_request(url, session, attempt + 1)
        else:
            print(f"Failed to retrieve {url} after 5 attempts.")
            return None

# Create a session for persistent connections
session = requests.Session()

page = 1
stop_scraping = False
while page <= MAX_PAGES and not stop_scraping:
    url = f"{base_url}{page}/"
    print(f"Scraping page {page}: {url}")
    
    response = make_request(url, session)
    if not response:
        print(f"Failed to retrieve page {page}. Moving to next page.")
        page += 1
        continue
    
    soup = BeautifulSoup(response.content, 'html.parser')
    articles = soup.find_all('div', class_='post-block')
    
    print(f"Found {len(articles)} articles on page {page}")
    
    if not articles:
        print(f"No articles found on page {page}. Moving to next page.")
        page += 1
        continue  # Move to the next page instead of breaking the loop
    
    for article in articles:
        title = title_element.text.strip()
        link = title_element.find('a')['href']
        date_string = article.select_one('time')['datetime'].split('T')[0]
        summary = article.select_one('p.wp-block-post-excerpt__excerpt').text.strip()
        published_date = datetime.strptime(date_string, '%Y-%m-%d')
        
        print(f"\nProcessing article: {title} (Published: {published_date.strftime('%Y-%m-%d')})")
        
        if published_date < one_month_ago:
            print(f"Reached articles older than one month on page {page}. Stopping.")
            stop_scraping = True
            break  # We've reached articles older than one month, stop processing this page
        
        if link in existing_links:
            print("Article already in database. Skipping.")
            continue  # Skip if this article is already in the database
        
        # Fetch full article content
        article_response = make_request(link, session)
        if not article_response:
            continue
        
        article_soup = BeautifulSoup(article_response.content, 'html.parser')
        content_element = article_soup.find('div', class_='article-content')
        
        if not content_element:
            print("Couldn't find article content. Trying alternative method.")
            content_element = article_soup.find('div', class_='article-container')
        
        content = content_element.text if content_element else ""
        
        # Print the first 200 characters of content for debugging
        print(f"Content preview: {content[:200]}...")
        
        # Search for keywords and currency symbols
        found_keywords = [keyword for keyword in funding_keywords if re.search(r'\b' + re.escape(keyword) + r'\b', content, re.IGNORECASE)]
        found_currency = any(symbol in content for symbol in currency_symbols)
        
        print(f"Found keywords: {found_keywords}")
        print(f"Found currency symbols: {found_currency}")
        
        if found_keywords or found_currency:  # Changed from 'and' to 'or' to loosen criteria
            # Extract company name from title
            company_name = ""
            funding_verbs = ["raises", "secures", "lands", "gets", "closes", "announces", "completes"]
            verb_match = re.search(r'\b(' + '|'.join(funding_verbs) + r')\b', title, re.IGNORECASE)
            if verb_match:
                verb_position = verb_match.start()
                name_match = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', title[:verb_position])
                if name_match:
                    company_name = name_match[-1]  # Take the last match, closest to the verb

            new_article = {
                "Title": title,
                "Company Name": company_name,
                "Published Date": published_date.strftime("%Y-%m-%d"),
                "Link": link,
                "Summary": summary,
                "Found Keywords": ", ".join(found_keywords)
            }
            new_articles.append(new_article)
            existing_articles.append(new_article)
            existing_links.add(link)
            
            print(f"New matched article: {title}")
            print(f"Company Name: {company_name}")
            print(f"Keywords found: {', '.join(found_keywords)}")
            print("---")
        else:
            print("Article does not match criteria. Skipping.")
        
        time.sleep(random.uniform(1, 3))  # Random delay between article requests
    
    page += 1  # Move to the next page
    
    if page > MAX_PAGES:
        print(f"Reached maximum number of pages ({MAX_PAGES}). Stopping.")
    
    time.sleep(random.uniform(3, 7))  # Random delay between page requests

print(f"Total new articles found: {len(new_articles)}")

# Save updated database
save_articles_database(existing_articles)

# Write new articles to CSV
if new_articles:
    csv_file = f"new_funding_articles_{datetime.now().strftime('%Y-%m-%d')}.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["Title", "Company Name", "Published Date", "Link", "Summary", "Found Keywords"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(new_articles)
    print(f"New articles have been written to {csv_file}")
else:
    print("No new articles found matching the keywords.")

print(f"Total articles in database: {len(existing_articles)}")