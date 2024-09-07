import feedparser
import requests
import re
import csv
from bs4 import BeautifulSoup

# URL of TechCrunch RSS feed
rss_url = "https://techcrunch.com/feed/"

# parse feed
feed = feedparser.parse(rss_url)

#list to hold articles
articles = []

# Defining key word search
funding_keywords = ["funding", "raises", "series", "seed", "investment", "raised", "valuation", "round"]
currency_symbols = ["€", "$"]

# Loop through each entry in the feed
for entry in feed.entries:
    title = entry.title
    summary = entry.get('summary', '')
    link = entry.link
    published_date = entry.published
 
    
    # Remove HTML tags
    summary = BeautifulSoup(summary, "html.parser").get_text()

# Search for keywords
    found_keywords = [keyword for keyword in funding_keywords if re.search(r'\b' + re.escape(keyword) + r'\b', summary, re.IGNORECASE)]
    found_currency = any(symbol in summary for symbol in currency_symbols)

# Print and export articles
    if found_keywords and found_currency:
        # Extract company name from title
        company_name = ""
        funding_verbs = ["raises", "secures", "lands", "gets", "closes"]
        
        # Find the first funding verb in the title
        verb_match = re.search(r'\b(' + '|'.join(funding_verbs) + r')\b', title, re.IGNORECASE)
        if verb_match:
            verb_position = verb_match.start()
            # Look for capitalized words before the verb
            name_match = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', title[:verb_position])
            if name_match:
                company_name = name_match[-1]  # Take the last match, closest to the verb

        if not company_name:
            print(f"Could not extract company name from title: {title}")

        articles.append({
            "Title": title,
            "Company Name": company_name,
            "Published Date": entry.published,
            "Link": entry.link,
            "Summary": summary,
            "Found Keywords": ", ".join(found_keywords)
        })
        print(f"Matched article: {title}")
        print(f"Company Name: {company_name}")
        print(f"Keywords found: {', '.join(found_keywords)}")
        print("---")

print(f"Total articles found: {len(articles)}")

if articles:  # Check if any articles were found
    csv_file = "funding_articles.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["Title", "Company Name", "Published Date", "Link", "Summary", "Found Keywords"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerows(articles)

    print(f"Data has been successfully written to {csv_file}")
else:
    print("No articles found matching the keywords.")