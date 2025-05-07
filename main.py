import asyncio
import platform

# 🩹 Patch for Playwright on Windows (especially when using Streamlit)
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
import time
import streamlit as st
import pandas as pd
import json
from datetime import datetime
import subprocess
import math
import re
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import plotly.express as px
from playwright.sync_api import sync_playwright
# Adjust decay weight for "last month" to be treated as 30 days old
# Load symbols
with open(r"C:\Users\Daziel Brilliant\Desktop\CV builder\Sentiment news yahoo\allsymbols.txt", "r") as f:
    symbols = [line.strip() for line in f if line.strip()]

def estimate_days_ago(time_str):
    time_str = time_str.lower()
    if "minute" in time_str or "hour" in time_str:
        return 0
    elif "day" in time_str:
        match = re.search(r'\d+', time_str)
        if match:
            return int(match.group())
        else:
            return 0
    elif "last week" in time_str:
        return int(7)
    elif "week" in time_str:
        match = re.search(r'\d+', time_str)
        return int(match.group()) * 7 if match else 0
    elif "last month" in time_str:
        return int(30)
    elif "month" in time_str:
        match = re.search(r'\d+', time_str)
        return int(match.group()) * 30 if match else 0
    elif "year" in time_str:
        match = re.search(r'\d+', time_str)
        return int(match.group()) * 365 if match else 0
    else:
        return 180

def decay_weight(days_old, lambda_decay=0.05):
    return math.exp(-lambda_decay * days_old)

def scroll_to_load_all_articles(page, max_scrolls=30, pause=2):
    for _ in range(max_scrolls):
        page.mouse.wheel(0, 3000)
        time.sleep(pause)

# UI: Select a stock ticker
ticker = st.selectbox("Select a stock ticker:", sorted(symbols))

def fetch_yahoo_ticker_news(ticker="TSLA", max_articles=100):
    url = f"https://finance.yahoo.com/quote/{ticker}/news"
    articles = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=60000)

        # Accept cookies if prompted
        try:
            page.wait_for_selector('button[name="agree"]', timeout=5000)
            page.click('button[name="agree"]')
        except:
            pass

        # Scroll to load more
        scroll_to_load_all_articles(page, max_scrolls=15, pause=1.5)

        blocks = page.query_selector_all("div.content.yf-1y7058a")

        for block in blocks[:max_articles]:
            try:
                anchor = block.query_selector("a")
                title = anchor.query_selector("h3").inner_text().strip()
                paragraph_tag = anchor.query_selector("p")
                quote = paragraph_tag.inner_text().strip() if paragraph_tag else ""
                url = anchor.get_attribute("href")
                if not url.startswith("http"):
                    url = "https://finance.yahoo.com" + url
                footer = block.query_selector("div.footer")
                source_time_tag = footer.query_selector("div.publishing") if footer else None
                source_time = source_time_tag.inner_text().strip() if source_time_tag else ""

                articles.append({
                    "title": title,
                    "quote": quote,
                    "url": url,
                    "source_time": source_time
                })
            except Exception as e:
                print("⚠️ Error extracting article:", e)

        browser.close()

    # Save file
    today = datetime.now().strftime("%d%m%Y")
    file_name = f"{ticker.upper()}{today}.json"
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    return file_name, articles
    
if st.button("Analyze News Sentiment"):
    with st.spinner("Fetching news and analyzing sentiment..."):
        # Run news fetch function directly
        news_file, news = fetch_yahoo_ticker_news(ticker)

        if not news:
            st.error("❌ No news found.")
        else:
            try:
                # Initialize VADER
                analyzer = SentimentIntensityAnalyzer()
                analyzed = []
                weighted_counts = {"Positive": 0, "Neutral": 0, "Negative": 0}

                for item in news:
                    text = item['title'] + ". " + item.get('quote', '')
                    score = analyzer.polarity_scores(text)
                    compound = score['compound']
                    if compound >= 0.05:
                        sentiment = 'Positive'
                    elif compound <= -0.05:
                        sentiment = 'Negative'
                    else:
                        sentiment = 'Neutral'

                    days_old = estimate_days_ago(item['source_time'])
                    weight = decay_weight(days_old)
                    weighted_counts[sentiment] += weight

                    analyzed.append({
                        "Title": item['title'],
                        "Quote": item.get('quote', ''),
                        "URL": item['url'],
                        "Source/Time": item['source_time'],
                        "Sentiment": sentiment,
                        "Compound": compound,
                        "Days Old": days_old,
                        "Weight": round(weight, 4)
                    })

                df = pd.DataFrame(analyzed)

                st.success(f"✅ Analysis complete for {ticker}. {len(df)} articles analyzed.")
                st.dataframe(df)

                # Summary chart using Plotly
                st.subheader("📊 Weighted Sentiment Breakdown")
                chart_df = pd.DataFrame(list(weighted_counts.items()), columns=['Sentiment', 'Weighted Count'])
                fig = px.bar(chart_df, x='Sentiment', y='Weighted Count', color='Sentiment', title="Sentiment Distribution (Weighted by Recency)", text_auto=True)
                st.plotly_chart(fig)

                # Export CSV
                csv_name = f"{ticker}_sentiment.csv"
                df.to_csv(csv_name, index=False)
                with open(csv_name, "rb") as f:
                    st.download_button("📥 Download CSV", f, file_name=csv_name)

            except Exception as e:
                st.error(f"⚠️ Error processing sentiment: {e}")
