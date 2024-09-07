import feedparser
import requests
import re
import csv
import sqlite3
from bs4 import BeautifulSoup
from waybackpy import WaybackMachineAvailabilityAPI
from datetime import datetime, timedelta
import time

# TechCrunch RSS feed URL
rss_url = "https://techcrunch.com/category/startups/feed/"

# Database setup
def setup_database():
    conn = sqlite3.connect('articles_database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS articles
                 (title TEXT, company_name TEXT, published_date TEXT, 
                  link TEXT PRIMARY KEY, summary TEXT, found_keywords TEXT)''')
    conn.commit()
    return conn

# Function to parse feed and extract articles
def parse_feed(feed_content):
    articles = []
    feed = feedparser.parse(feed_content)

    print(f"Total entries in feed: {len(feed.entries)}")

    funding_keywords = [
    r"raised [$€£¥]?[0-9,.]+(?:[MB]| million| billion)? in a Series [A-Z] round", 
    r"raised [$€£¥]?[0-9,.]+(?:[MB]| million| billion)? in a seed round", 
    r"closed a [$€£¥]?[0-9,.]+(?:[MB]| million| billion)? Series [A-Z] round", 
    r"closed a [$€£¥]?[0-9,.]+(?:[MB]| million| billion)? funding round",
    r"secured [$€£¥]?[0-9,.]+(?:[MB]| million| billion)? in venture funding", 
    r"completed a [$€£¥]?[0-9,.]+(?:[MB]| million| billion)? raise", 
    r"led the [$€£¥]?[0-9,.]+(?:[MB]| million| billion)? Series [A-Z] round", 
    r"participated in a [$€£¥]?[0-9,.]+(?:[MB]| million| billion)? Series [A-Z] round",
    r"announced a [$€£¥]?[0-9,.]+(?:[MB]| million| billion)? funding round", 
    r"post-money valuation of [$€£¥]?[0-9,.]+(?:[MB]| million| billion)?", 
    r"closed a [$€£¥]?[0-9,.]+(?:[MB]| million| billion)? investment", 
    r"valuation jumped to [$€£¥]?[0-9,.]+(?:[MB]| million| billion)? after Series [A-Z]",
    r"secured [$€£¥]?[0-9,.]+(?:[MB]| million| billion)? in funding led by", 
    r"raised over [$€£¥]?[0-9,.]+(?:[MB]| million| billion)? in Series [A-Z]", 
    r"received a [$€£¥]?[0-9,.]+(?:[MB]| million| billion)? investment from"]

    currency_symbols = ["€", "$", "£", "¥"]  # Add more currency symbols if needed

    for entry in feed.entries:
        title = entry.title
        summary = entry.get('summary', '')
        link = entry.link
        published_date = entry.published

        summary = BeautifulSoup(summary, "html.parser").get_text()

        found_keywords = [keyword for keyword in funding_keywords if re.search(r'\b' + re.escape(keyword) + r'\b', summary + title, re.IGNORECASE)]
        found_currency = any(symbol in summary + title for symbol in currency_symbols)

        if found_keywords or found_currency:
            company_name = ""
            funding_verbs = ["raises", "secures", "lands", "gets", "closes", "announces", "completes"]
            
            verb_match = re.search(r'\b(' + '|'.join(funding_verbs) + r')\b', title, re.IGNORECASE)
            if verb_match:
                verb_position = verb_match.start()
                name_match = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', title[:verb_position])
                if name_match:
                    company_name = name_match[-1]  # Take the last match, closest to the verb

            articles.append({
                "Title": title,
                "Company Name": company_name,
                "Published Date": published_date,
                "Link": link,
                "Summary": summary[:200],  # Truncate summary for brevity
                "Found Keywords": ", ".join(found_keywords)
            })

    return articles

# Function to get historical RSS feeds
def get_historical_feeds(start_date, end_date, conn):
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    availability_api = WaybackMachineAvailabilityAPI(rss_url, user_agent)

    new_articles = 0
    current_date = start_date

    while current_date <= end_date:
        print(f"Fetching RSS feed for {current_date.strftime('%Y-%m-%d')}...")
        try:
            snapshot = availability_api.near(current_date.strftime("%Y%m%d"))
            if snapshot:
                print(f"Found snapshot: {snapshot.archive_url}")
                response = requests.get(snapshot.archive_url)
                if response.status_code == 200:
                    articles = parse_feed(response.content)
                    new_articles += add_articles_to_db(articles, conn)
                    print(f"Found {len(articles)} articles, {new_articles} new.")
                else:
                    print(f"Failed to retrieve RSS feed. Status code: {response.status_code}")
            else:
                print("No snapshots found for this date.")
        except Exception as e:
            print(f"Error occurred: {str(e)}")

        current_date += timedelta(days=1)
        time.sleep(1)  # Be respectful to the Wayback Machine servers

    return new_articles

# Function to add articles to the database
def add_articles_to_db(articles, conn):
    c = conn.cursor()
    new_articles = 0
    for article in articles:
        c.execute("SELECT * FROM articles WHERE link=?", (article['Link'],))
        if c.fetchone() is None:
            c.execute("INSERT INTO articles VALUES (?, ?, ?, ?, ?, ?)",
                      (article['Title'], article['Company Name'], article['Published Date'],
                       article['Link'], article['Summary'], article['Found Keywords']))
            new_articles += 1
    conn.commit()
    return new_articles

# Main execution
start_date = datetime(2024, 9, 1)  # Adjust this to your desired start date
end_date = datetime(2024, 9, 5)  # Adjust this to your desired end date

conn = setup_database()
new_articles = get_historical_feeds(start_date, end_date, conn)

c = conn.cursor()
c.execute("SELECT COUNT(*) FROM articles")
total_articles = c.fetchone()[0]

print(f"New articles added: {new_articles}")
print(f"Total articles in database: {total_articles}")

# Export to CSV
csv_file = "historical_funding_articles.csv"
c.execute("SELECT * FROM articles")
articles = c.fetchall()

with open(csv_file, "w", newline="", encoding="utf-8") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["Title", "Company Name", "Published Date", "Link", "Summary", "Found Keywords"])
    writer.writerows(articles)

print(f"Data has been successfully written to {csv_file}")

conn.close()