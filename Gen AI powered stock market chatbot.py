import os
import json
import time
import openai
import yfinance as yf
import requests
import pandas as pd
from bs4 import BeautifulSoup
from fuzzywuzzy import process
from flask import Flask, request, jsonify
from openai import OpenAI

# 🔑 OpenAI API Key
openai.api_key = os.getenv("OPENAI_API_KEY")

print("🚀 Starting Stock Market Chatbot...")


# ✅ Load NSE Stock Symbols Dynamically
def load_nse_stock_symbols():
    """Load all NSE stock symbols from NSE CSV."""
    print("📥 Loading NSE stock symbols...")
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    try:
        df = pd.read_csv(url)
        stock_dict = {}
        for index, row in df.iterrows():
            stock_dict[row["SYMBOL"].lower()] = row["SYMBOL"] + ".NS"
            stock_dict[row["NAME OF COMPANY"].lower()] = row["SYMBOL"] + ".NS"
        print("✅ NSE stock symbols loaded successfully!")
        return stock_dict
    except Exception as e:
        print(f"Error loading NSE stock symbols: {str(e)}")
        return {}


# Load NSE stock symbols dynamically
stock_symbols = load_nse_stock_symbols()


# ✅ Function to Extract Stock Name or Symbol from User Query
def extract_stock_from_text(user_input):
    """Uses OpenAI to extract stock name or symbol from user query."""
    print(f"🔍 Extracting stock symbol from: {user_input}")
    prompt = f"Identify the stock name or symbol from this user request: '{user_input}'. Return only the company name or symbol in lowercase, nothing else."

    response = openai.OpenAI().chat.completions.create(model="gpt-4",
                                                       messages=[{
                                                           "role":
                                                           "user",
                                                           "content":
                                                           prompt
                                                       }])

    stock_name = response.choices[0].message.content.strip().lower()

    # Fuzzy Matching for Better Accuracy
    best_match, score = process.extractOne(stock_name, stock_symbols.keys())

    if score > 80:  # Ensure a good match
        print(f"✅ Stock symbol extracted: {stock_symbols[best_match]}")
        return stock_symbols[best_match]
    elif stock_name.upper() in [
            symbol.split(".")[0] for symbol in stock_symbols.values()
    ]:  # Check for direct symbol match
        return stock_name.upper() + ".NS"
    else:
        return None  # No good match found


# ✅ Function to Get Stock Data from Yahoo Finance
def get_stock_data(ticker):
    """Fetch stock data from Yahoo Finance."""
    print(f"🔍 Fetching stock data for: {ticker}")
    try:
        stock = yf.Ticker(ticker)
        stock_info = stock.info
        if "longName" not in stock_info:
            print("❌ Stock data not found. Please check the ticker symbol.")
            return {
                "Error":
                "Stock data not found. Please check the ticker symbol."
            }
        print("✅ Stock data retrieved successfully!")
        return {
            "Name": stock_info.get("longName", "N/A"),
            "Current Price": stock_info.get("currentPrice", "N/A"),
            "Market Cap": stock_info.get("marketCap", "N/A"),
            "PE Ratio": stock_info.get("trailingPE", "N/A"),
            "Dividend Yield": stock_info.get("dividendYield", "N/A"),
            "52-Week High": stock_info.get("fiftyTwoWeekHigh", "N/A"),
            "52-Week Low": stock_info.get("fiftyTwoWeekLow", "N/A"),
            "EPS": stock_info.get("trailingEps", "N/A"),
            "Beta": stock_info.get("beta", "N/A"),
        }
    except Exception as e:
        print(f"❌ Error fetching stock data: {str(e)}")
        return {"Error": str(e)}


# ✅ Function to Scrape Latest Stock News
def get_stock_news(company_name):
    print(f"📰 Fetching latest news for: {company_name}")
    """Scrape stock-related news from Moneycontrol and Yahoo Finance."""
    news_list = []

    # Scrape from Moneycontrol
    moneycontrol_url = f"https://www.moneycontrol.com/news/tags/{company_name.replace(' ', '-')}.html"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(moneycontrol_url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")
        moneycontrol_headlines = [
            headline.text.strip() for headline in soup.find_all("h2")[:5]
        ]
        news_list.extend(moneycontrol_headlines)
        print("✅ Stock news retrieved successfully!")
    except Exception as e:
        print(f"❌ Error fetching news: {str(e)}")
        news_list.append(f"Error fetching news from Moneycontrol: {str(e)}")

    # Scrape from Yahoo Finance News
    yahoo_url = f"https://finance.yahoo.com/quote/{company_name}/news"
    try:
        response = requests.get(yahoo_url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")
        yahoo_headlines = [
            headline.text.strip() for headline in soup.find_all("h3")[:5]
        ]
        news_list.extend(yahoo_headlines)
    except Exception as e:
        news_list.append(f"Error fetching news from Yahoo Finance: {str(e)}")

    return news_list if news_list else ["No recent news found."]


# ✅ Load or Create Assistant
def create_assistant():
    print("🤖 Loading AI Assistant...")
    assistant_file_path = 'assistant.json'
    if os.path.exists(assistant_file_path):
        with open(assistant_file_path, 'r') as file:
            assistant_id = json.load(file)['assistant_id']
            print(f"✅ Assistant loaded: {assistant_id}")
            return assistant_id
    print("❌ No assistant found.")
    return None


assistant_id = create_assistant()

# ✅ Start Flask App
app = Flask(__name__)
client = OpenAI(default_headers={"OpenAI-Beta": "assistants=v2"})


# ✅ Add Homepage Route (Fix 404 Error)
@app.route('/')
def home():
    return "✅ Stock Market Chatbot is Running!"


@app.route('/start', methods=['GET'])
def start_conversation():
    print("📝 Starting a new conversation thread...")
    thread = client.beta.threads.create()
    print(f"✅ Thread started: {thread.id}")
    return jsonify({"thread_id": thread.id})


@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    thread_id = data.get('thread_id')
    user_input = data.get('message', '')

    print(f"Received data: {data}")  # Log received data

    if not thread_id:
        print("❌ Error: Missing thread_id")
        return jsonify({"error": "Missing thread_id"}), 400

    # Extract stock name or symbol
    ticker = extract_stock_from_text(user_input)
    print(f"Extracted ticker: {ticker}")  # Log extracted ticker

    if not ticker:
        print(
            "❌ Could not identify the stock. Please try again with a valid company name or symbol."
        )
        return jsonify({
            "response":
            "Could not identify the stock. Please try again with a valid company name or symbol."
        }), 400

    # Fetch stock data
    stock_data = get_stock_data(ticker)
    print(f"Fetched stock data: {stock_data}")  # Log fetched stock data

    if "Error" in stock_data:
        print("❌ Stock data not found! Try another company.")
        return jsonify(
            {"response": "Stock data not found! Try another company."}), 400

    # Fetch stock news
    news = get_stock_news(ticker.split(".")[0])
    print(f"Fetched news: {news}")  # Log fetched news

    # Combine stock data and news into the query
    full_query = f"""
    User Query: {user_input}
    Stock Data: {stock_data}
    Recent News: {news}
    """
    print(f"Full query: {full_query}")  # Log full query

    print("💬 Sending message to AI assistant...")
    client.beta.threads.messages.create(thread_id=thread_id,
                                        role="user",
                                        content=full_query)
    run = client.beta.threads.runs.create(thread_id=thread_id,
                                          assistant_id=assistant_id)

    while True:
        run_status = client.beta.threads.runs.retrieve(thread_id=thread_id,
                                                       run_id=run.id)
        if run_status.status == 'completed':
            print("✅ AI Assistant responded!")
            break
        time.sleep(1)

    messages = client.beta.threads.messages.list(thread_id=thread_id)
    response = messages.data[0].content[0].text.value
    print(f"🤖 AI Response: {response}")

    # Return the response in a format expected by Voiceflow
    return jsonify({"response": response})


if __name__ == '__main__':
    print("🔥 Chatbot is running on port 8080...")
    app.run(host='0.0.0.0', port=8080)
