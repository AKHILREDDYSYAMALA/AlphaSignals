import os
import json
import requests
import feedparser
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# --- 1. CONFIGURATION & SOURCES ---
# You can add as many RSS feeds here as you want
NEWS_SOURCES = [
    "https://economictimes.indiatimes.com/markets/rssfeeds/2146842.cms", # ET Markets
    "https://www.livemint.com/rss/markets", # Livemint Markets
]
MEMORY_FILE = "seen_news.txt"

class AlphaSignal(BaseModel):
    event: str = Field(description="The main macro event or news headline")
    trade_type: str = Field(description="Categorize as: 'Earnings Swing', 'Structural Trend', or 'Hidden Monopoly'")
    time_horizon: str = Field(description="E.g., '1-3 Months', '1-2 Years', or '3-5+ Years'")
    industries_affected: list[str] = Field(description="List of directly impacted industries")
    supply_chain_impact: list[str] = Field(description="Critical components or services required")
    beneficiary_companies: list[str] = Field(description="Specific listed ancillary or supplier companies in India")
    reasoning: str = Field(description="Explain the logic. If it is an Earnings Swing, explain how this news hits their next quarterly report.")
    confidence_level: str = Field(description="High, Medium, or Low")

client = genai.Client()

# --- 2. THE MEMORY SYSTEM ---
def load_seen_urls():
    if not os.path.exists(MEMORY_FILE):
        return set()
    with open(MEMORY_FILE, "r") as f:
        return set(line.strip() for line in f)

def mark_as_seen(url):
    with open(MEMORY_FILE, "a") as f:
        f.write(url + "\n")

# --- 3. THE DATA INTAKE ---
def fetch_live_news():
    print("📡 Scanning live news sources...")
    seen_urls = load_seen_urls()
    fresh_news = []

    for source in NEWS_SOURCES:
        feed = feedparser.parse(source)
        # Grab the top 5 latest articles from each feed
        for entry in feed.entries[:5]:
            if entry.link not in seen_urls:
                # Combine headline and the article summary/description
                full_text = f"Headline: {entry.title}\nDetails: {entry.description}"
                fresh_news.append({"url": entry.link, "text": full_text})
    
    print(f"✅ Found {len(fresh_news)} new articles to analyze.")
    return fresh_news

# --- 4. THE INFERENCE ENGINE ---
def analyze_news(news_text: str):
    prompt = f"""
    You are a forensic financial analyst specializing in the Indian stock market.
    Your edge is finding hidden supply-chain monopolies and ancillary plays.
    
    Analyze the following news. 
    1. If the news is generic noise, set confidence_level to "Low" and leave companies blank.
    2. If actionable, classify the 'trade_type' and 'time_horizon':
       - "Earnings Swing" (1-3 Months): A supplier who will see a revenue bump in the next quarter due to this news.
       - "Structural Trend" (1-2 Years): A company providing picks-and-shovels to a growing sector.
       - "Hidden Monopoly" (3-5+ Years): A micro/small-cap with a deep moat, patents, or sole-supplier status.
    
    News Context:
    {news_text}
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash', 
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AlphaSignal,
            temperature=0.2, 
        ),
    )
    return json.loads(response.text)

# --- 5. THE DELIVERY ---
def send_telegram_alert(data: dict):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    message = f"""
🚨 *Live Market Signal* 🚨

📰 *The Catalyst:* {data['event']}

⏱️ *Play Type:* {data['trade_type']} ({data['time_horizon']})

⚙️ *Supply Chain Impact:* {', '.join(data['supply_chain_impact'][:3])}

💎 *Hidden Beneficiaries:* *{', '.join(data['beneficiary_companies'])}*

🧠 *The Logic:* {data['reasoning']}

📊 *Confidence:* {data['confidence_level']}
    """

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    response = requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})
    
    if response.status_code != 200:
        print(f"❌ Failed to send Telegram alert: {response.text}")

# --- MAIN AUTOMATION LOOP ---
if __name__ == "__main__":
    live_articles = fetch_live_news()
    
    for article in live_articles:
        print(f"🧠 Analyzing: {article['text'][:60]}...")
        
        try:
            insight = analyze_news(article['text'])
            
            # Only alert on high/medium confidence setups. Ignore the noise.
            if insight.get("confidence_level") in ["High", "Medium"] and len(insight.get("beneficiary_companies", [])) > 0:
                print("💎 High-value signal found! Sending to Telegram...")
                send_telegram_alert(insight)
            else:
                print("⏭️ No actionable supply chain data in this article. Skipping.")
                
            # Mark as seen so we don't process it again next time
            mark_as_seen(article['url'])
            
        except Exception as e:
            print(f"❌ Error analyzing article: {e}")