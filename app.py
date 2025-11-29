import requests
import time
from datetime import datetime
import feedparser
import gspread
from google.oauth2.service_account import Credentials
from urllib.parse import quote
import csv
import re
import os
from dotenv import load_dotenv

load_dotenv()
NEWS_DATA_API=os.getenv("NEWS_DATA_API")
SEARCH_QUERY=os.getenv("SEARCH_QUERY","AI Automations")
LANGUAGE=os.getenv("LANGUAGE","")
SPREADSHEET_ID=os.getenv("SPREADSHEET_ID")
SHEET_NAME=os.getenv("SHEET_NAME","sheet1")
CREDENTIAL_FILE=os.getenv("CREDENTIAL_FILE","credentials.json")
REQUEST_DELAY=2

def fetch_google_news(query, language="en",max_results=100):
    print(f"\n Fetching news from Google news")
    articles = []
    try:
        encoded_query=quote(query)
        rss_url=f"https://news.google.com/rss/search?q={encoded_query}&hl={language}&gl=US&ceid=US:{language}"
        feed=feedparser.parse(rss_url)
        for entry in feed.entries[:max_results]:
            title=entry.title
            source="Google News"
            if " - " in title:
                parts=title.rsplit(" - ",1)
                title=parts[0]
                source=parts[1] if len(parts)>1 else "Google News"
            summary=entry.get("summary","")
            if summary:
                import re
                summary=re.sub('<[^<]+?>','',summary)
                summary=summary.strip()
            if not summary or len(summary)<10:
                summary=f"Article from {source}"
            articles.append({
                "Source":source,
                "Title":title,
                "Link":entry.link,
                "Date":entry.get("published", ""),
                "Summary":summary
            })
        
        print(f" Fetched {len(articles)} from Google News")
    except Exception as e:
        print(f" Error fetching news from Google News: {e}")
    
    return articles
def news_data_articles(query, language, max_page=50):
    print(f"fetching News from NewsData.io")
    articles=[]
    next_page=None
    page_count=0
    base_url="https://newsdata.io/api/1/news"
    while page_count<max_page:
        params={
            "apikey": NEWS_DATA_API,
            "q": query,
            "language": language
        }
        if next_page:
            params["page"]=next_page
        try:
            response=requests.get(base_url,params=params)
            response.raise_for_status()
            data=response.json()
            if data.get("status")=="success":
                results=data.get("results",[])
                for article in results:
                    articles.append({
                        "Source":article.get("source_id","NewsData.io"),
                        "Title":article.get("title",""),                  
                        "Link":article.get("link",""),                     
                        "Date":article.get("pubDate",""),                  
                        "Summary":article.get("description","")           
                    })
                page_count+=1
                print(f"page {page_count}: {len(results)} articles (Total: {len(articles)})")
                next_page = data.get("nextPage")
                if not next_page:
                    print(f"No more pages available")
                    break
                time.sleep(REQUEST_DELAY)
            else:
                print(f"API ERROR: {data.get('message', 'Unknown error')}")
                break
        except requests.exceptions.HTTPError as e:
            if "429" in str(e):
                print(f"\n Rate limit exceeded! You've used your daily quota.")
                print(f"  Wait 24 hours or reduce max_page parameter.")
                break
            else:
                print(f"Error: {e}")
                break
        except Exception as e:
            print(f"Error: {e}")
            break
    return articles

def clean_title(title):
    if not title:
        return ""
    cleaned=re.sub(r'[^\w\s]','',title.lower())
    cleaned=' '.join(cleaned.split())
    return cleaned

def deduplicate_article(articles):
    print(f"removing duplicate articles")
    seen_titles=set()
    seen_links=set()
    unique_articles=[]
    for article in articles:
        title=clean_title(article.get("Title",""))
        link=article.get("Link","").strip()
        if not title or not link:
            continue
        if link not in seen_links and title not in seen_titles:
            seen_titles.add(title)
            seen_links.add(link)
            unique_articles.append(article)
    duplicates=len(articles)-len(unique_articles)
    print(f"removed {duplicates} duplicates")
    print(f"{len(unique_articles)} unique articles remaining")
    return unique_articles

def setup_google_sheets(credentials_file):
    try:
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds=Credentials.from_service_account_file(credentials_file,scopes=scopes)
        client=gspread.authorize(creds)
        return client
    except Exception as e:
        print(f"Google sheet failed to update: {e}")
        return None
    
def write_to_sheets(client,spreadsheet_Id,sheet_name,articles):
    try:
        print(f"Writing to Google Sheets.......")
        sheets=client.open_by_key(spreadsheet_Id).worksheet(sheet_name)
        rows=[]
        for article in articles:
            rows.append([
                article.get("Source",""),
                article.get("Date",""),
                article.get("Link",""),
                article.get("Title",""),
                article.get("Summary","")
            ])
        if rows:
            sheets.append_rows(rows,value_input_option="USER_ENTERED")
            print(f"Successfully wrote {len(rows)} articles to sheets")
            return True
        else:
            print(f"No article to written")
            return False
    except Exception as e:
        print(f"Fialed to write on sheets : {e}")
        return False
    
def save_to_csv(articles,filename):
    try:
        with open(filename,'w',newline='',encoding='utf-8')as f:
            if articles:
                fieldnames=["Source","Date","Link","Title","Summary"]
                writer=csv.DictWriter(f,fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(articles)
                print(f"Saved to {filename}")
                return True
    except Exception as e:
        print(f" CSV saving failed : {e}")
        return False
    
def main():
    if not SPREADSHEET_ID:
        print(f"ERROR: Spreadsheet Id required in .env file")
        return
    print("="*70)
    print("AI AUTOMATION NEWS FETCHER")
    print("="*70)
    print(f"Search Query: {SEARCH_QUERY}")
    print(f"Language: {LANGUAGE}")
    print(f"started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    all_articles=[]
    google_articles=fetch_google_news(SEARCH_QUERY,LANGUAGE,max_results=100)
    all_articles.extend(google_articles)
    if NEWS_DATA_API:
        newsdata_article=news_data_articles(SEARCH_QUERY,LANGUAGE,max_page=50)
        all_articles.extend(newsdata_article)
    else:
        newsdata_article=[]
        print("\n Skipping NewsData.io (API key not configured)")
    unique_articles=deduplicate_article(all_articles)
    print("\n"+"="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Google News: {len(google_articles)} articles")
    print(f"NewsData.io: {len(newsdata_article)} articles")
    print(f"---")
    print(f"Total Raw: {len(all_articles)} items")
    print(f"After Dedup: {len(unique_articles)} unique items")
    print("="*70)
    if len(unique_articles)==0:
        print("\n  No articles found. Try a different search query")
        return
    timestamp=datetime.now().strftime('%Y%mp%d_%H%M%S')
    csv_filename=f"news_backup_{timestamp}.csv"
    print(f"\n Saving CSV backup...")
    save_to_csv(unique_articles,csv_filename)
    try:
        client=setup_google_sheets(CREDENTIAL_FILE)
        if client:
            write_to_sheets(client,SPREADSHEET_ID,SHEET_NAME,unique_articles)
        else:
            print(f"\n Skipping Google Sheets upload")
            print(f"Check that {CREDENTIAL_FILE} exists and is valid")
    except FileNotFoundError:
        print(f"\n {CREDENTIAL_FILE} not found")
        print(f"Articles saved to CSV: {csv_filename}")
    except Exception as e:
        print(f"\n  Error uploading to Google Sheets: {e}")
        print(f"Articles saved to CSV: {csv_filename}")

    print("\n"+"="*70)
    print("COMPLETED")
    print("="*70)
    print(f"Total articles: {len(unique_articles)}")
    print(f"CSV backup: {csv_filename}")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)


if __name__ =="__main__":
    main()