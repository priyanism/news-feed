import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
from urllib.parse import urljoin

SOURCES = [
    ("Daily Star Bangla - Explainer",
     "https://bangla.thedailystar.net/explainer"),

    ("Daily Star Bangla - Analysis",
     "https://bangla.thedailystar.net/analysis"),

    ("Daily Star - Slow Reads",
     "https://www.thedailystar.net/slow-reads"),

    ("TBS - Analysis",
     "https://www.tbsnews.net/analysis"),

    ("BanglaStream - Explainer",
     "https://www.banglastream.net/explainer")
]


def get_articles(name, url):
    articles = []

    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        r = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(r.text, "lxml")

        links = soup.find_all("a", href=True)

        seen = set()

        for a in links:
            title = a.get_text(" ", strip=True)
            link = urljoin(url, a["href"])

            if (
                len(title) > 30
                and link not in seen
                and link.startswith("http")
            ):
                seen.add(link)

                articles.append({
                    "title": title,
                    "link": link,
                    "source": name
                })

            if len(articles) >= 10:
                break

    except Exception as e:
        print(name, e)

    return articles


def create_feed():

    fg = FeedGenerator()

    fg.title("My News Feed")
    fg.link(
        href="https://priyanism.github.io/news-feed/feed.xml"
    )

    fg.description(
        "Daily Star, TBS and BanglaStream curated feed"
    )

    all_articles = []

    for name, url in SOURCES:
        all_articles.extend(
            get_articles(name, url)
        )


    unique = {}

    for item in all_articles:
        unique[item["link"]] = item


    for item in list(unique.values())[:50]:

        fe = fg.add_entry()

        fe.title(item["title"])
        fe.link(
            href=item["link"]
        )

        fe.description(
            f"Source: {item['source']}"
        )

        fe.pubDate(datetime.now(timezone.utc))


    fg.rss_file(
        "feed.xml"
    )


if __name__ == "__main__":
    create_feed()
