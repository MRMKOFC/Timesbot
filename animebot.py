import requests
import os
import json
import time
import logging
import hashlib
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("anime_news_bot.log"), logging.StreamHandler()]
)

# Configuration
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
POSTED_TWEETS_FILE = "posted_tweets.json"
POSTED_CONTENT_FILE = "posted_content.json"
HOURS_TO_CHECK = 24

SOURCES = [
    "@Anime", "@comic_natalie", "@MangaMoguraRE",
    "@AniNewsAndFacts", "@WSJ_manga", "@animetv_jp",
    "@animecornernews", "@animety_off", "@ItsAnimeJP",
    "@AIR_News01", "@AniTrendz", "@myanimelist"
]

def get_content_hash(text):
    return hashlib.md5(text.encode()).hexdigest()

def load_posted_data():
    try:
        posted_tweets = set()
        if os.path.exists(POSTED_TWEETS_FILE):
            with open(POSTED_TWEETS_FILE, "r") as f:
                posted_tweets = set(json.load(f))
        posted_content = set()
        if os.path.exists(POSTED_CONTENT_FILE):
            with open(POSTED_CONTENT_FILE, "r") as f:
                posted_content = set(json.load(f))
        return posted_tweets, posted_content
    except Exception as e:
        logging.error(f"Error loading posted data: {e}")
        return set(), set()

def save_posted_data(tweet_id, content_hash):
    try:
        posted_tweets, posted_content = load_posted_data()
        posted_tweets.add(tweet_id)
        posted_content.add(content_hash)
        with open(POSTED_TWEETS_FILE, "w") as f:
            json.dump(list(posted_tweets), f)
        with open(POSTED_CONTENT_FILE, "w") as f:
            json.dump(list(posted_content), f)
    except Exception as e:
        logging.error(f"Error saving posted data: {e}")

def is_recent(tweet_time):
    try:
        tweet_date = datetime.strptime(tweet_time, "%Y-%m-%dT%H:%M:%S.%fZ")
        return tweet_date > datetime.now() - timedelta(hours=HOURS_TO_CHECK)
    except:
        return True

def extract_title(text):
    sentences = text.split('.')
    if len(sentences) > 1:
        return sentences[0].strip()
    return ' '.join(text.split()[:7]).strip() + "..."

def scrape_twitter(source):
    try:
        url = f"https://twitter.com/{source.replace('@', '')}"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9"
        }
        response = requests.get(url, headers=headers, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        tweets = []

        for article in soup.find_all('article'):
            try:
                tweet_id = article['data-tweet-id']
                time_tag = article.find('time')
                if not time_tag or not is_recent(time_tag['datetime']):
                    continue

                text_div = article.find('div', {'data-testid': 'tweetText'})
                if not text_div:
                    continue

                text = ' '.join([p.get_text() for p in text_div.find_all('p')])
                content_hash = get_content_hash(text)

                media = []
                for img in article.find_all('img'):
                    if 'src' in img.attrs and ('media' in img['src'] or 'twimg' in img['src']):
                        img_url = img['src'].replace('&name=small', '&name=large')
                        media.append(img_url)

                if text and media:
                    tweets.append({
                        'id': tweet_id,
                        'text': text,
                        'media': list(set(media)),
                        'content_hash': content_hash
                    })
            except Exception as e:
                logging.warning(f"Skipping tweet - parsing error: {e}")
                continue

        return tweets
    except Exception as e:
        logging.error(f"Error scraping {source}: {e}")
        return []

def format_message(tweet):
    title = extract_title(tweet['text'])
    message = f"<b>⚡ {title}</b>\n"
    message += "﹏﹏﹏﹏﹏﹏﹏﹏﹏﹏﹏﹏﹏﹏﹏﹏﹏\n\n"
    message += tweet['text'] + "\n\n"
    message += "﹋﹋﹋﹋﹋﹋﹋﹋﹋﹋﹋﹋﹋﹋﹋﹋﹋\n"
    message += "🍁 | @TheAnimeTimes_acn"

    if len(message) > 1000:
        message = message[:950] + "...\n\n[CONTINUED]"

    return {
        'text': message,
        'media': tweet['media'][0]
    }

def send_to_telegram(content):
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            data={
                'chat_id': CHANNEL_ID,
                'photo': content['media'],
                'caption': content['text'],
                'parse_mode': 'HTML'
            },
            timeout=15
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Failed to send to Telegram: {e}")
        return False

def main():
    posted_tweets, posted_content = load_posted_data()
    logging.info(f"Starting scan (checking last {HOURS_TO_CHECK} hours)...")

    for source in SOURCES:
        logging.info(f"Checking {source}...")
        try:
            tweets = scrape_twitter(source)
            for tweet in tweets:
                if tweet['id'] in posted_tweets or tweet['content_hash'] in posted_content:
                    continue

                formatted = format_message(tweet)
                if send_to_telegram(formatted):
                    save_posted_data(tweet['id'], tweet['content_hash'])
                    logging.info(f"Posted new content from {source}")
                    time.sleep(10)
        except Exception as e:
            logging.error(f"Error processing {source}: {e}")

if __name__ == "__main__":
    main()