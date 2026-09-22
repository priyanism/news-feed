import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from urllib.parse import urljoin
from datetime import datetime, timezone


SOURCES = [
    {
        "name": "Daily Star Bangla - Explainer",
        "url": "https://bangla.thedailystar.net/explainer",
    },
    {
        "name": "Daily Star - Views",
        "url": "https://www.thedailystar.net/opinion/views",
    },
    {
        "name": "Daily Star - Slow Reads",
        "url": "https://www.thedailystar.net/slow-reads",
    },
    {
        "name": "TBS - Analysis",
        "url": "https://www.tbsnews.net/analysis",
    },
    {
        "name": "The Conversation",
        "url": "https://theconversation.com/",
    },
    {
        "name": "Carnegie Endowment - Research",
        "url": "https://carnegieendowment.org/research",
    },
]


HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def get_articles(source):
    try:
        r = requests.get(
            source["url"],
            headers=HEADERS,
            timeout=20
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        articles = []
        seen = set()

        for a in soup.find_all("a", href=True):
            title = a.get_text(" ", strip=True)
            link = urljoin(source["url"], a["href"])

            if not title:
                continue

            if link in seen:
                continue

            # Ignore obvious navigation links
            if len(title) < 20:
                continue

            if link.startswith("http"):
                seen.add(link)

                articles.append({
                    "title": title,
                    "link": link,
                    "source": source["name"]
                })

        return articles[:20]

    except Exception as e:
        print(f"ERROR: {source['name']} -> {e}")
        return []


all_articles = []

for source in SOURCES:
    articles = get_articles(source)

    print(
        f"{source['name']}: "
        f"{len(articles)} articles found"
    )

    all_articles.extend(articles)


# Remove duplicate links
unique = {}
for article in all_articles:
    unique[article["link"]] = article

all_articles = list(unique.values())


# Create RSS
fg = FeedGenerator()

fg.title("Priyanism High-Value Reading Feed")
fg.link(
    href="https://priyanism.github.io/news-feed/feed.xml",
    rel="self"
)
fg.description(
    "Curated reading feed for BCS, Erasmus Mundus and advanced English/IELTS preparation."
)
fg.language("en")


for article in all_articles:

    fe = fg.add_entry()

    fe.title(
        f"[{article['source']}] {article['title']}"
    )

    fe.link(
        href=article["link"]
    )

    fe.description(
        f"Source: {article['source']}"
    )


fg.rss_file("feed.xml")

print(
    f"\nDONE: {len(all_articles)} total articles added."
)
