import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from email.utils import parsedate_to_datetime
import re
import hashlib

# ============================================================
# CONFIG
# ============================================================

MAX_PER_SOURCE = 12
REQUEST_TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; PriyanismRSSBot/1.0; "
        "+https://github.com/priyanism/news-feed)"
    )
}

SOURCES = [
    {
        "name": "Daily Star Bangla - Explainer",
        "url": "https://bangla.thedailystar.net/explainer",
        "domain": "bangla.thedailystar.net",
        "include": ["/explainer/"],
        "exclude": ["/video/", "/photo/"],
    },
    {
        "name": "Daily Star - Views",
        "url": "https://www.thedailystar.net/opinion/views",
        "domain": "www.thedailystar.net",
        "include": ["/opinion/views/"],
        "exclude": ["/video/", "/photo/"],
    },
    {
        "name": "TBS - Analysis",
        "url": "https://www.tbsnews.net/analysis",
        "domain": "www.tbsnews.net",
        "include": ["/analysis/"],
        "exclude": ["/author/", "/tags/", "/category/"],
    },
    {
        "name": "Daily Star - Slow Reads",
        "url": "https://www.thedailystar.net/slow-reads",
        "domain": "www.thedailystar.net",
        "include": ["/slow-reads/"],
        "exclude": [
            "/slow-reads-classics/",
            "/video/",
            "/photo/",
        ],
    },
    {
        "name": "The Conversation",
        "url": "https://theconversation.com/",
        "domain": "theconversation.com",
        "include": ["/articles/"],
        "exclude": ["/au/", "/uk/", "/us/", "/africa/", "/ca/"],
    },
    {
        "name": "Carnegie Endowment - Research",
        "url": "https://carnegieendowment.org/research",
        "domain": "carnegieendowment.org",
        "include": [
            "/research/",
            "/articles/",
            "/papers/",
            "/publications/",
        ],
        "exclude": [
            "/experts/",
            "/events/",
            "/about/",
            "/programs/",
            "/collections/",
        ],
    },
]


# ============================================================
# BASIC HELPERS
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def normalize_url(url):
    """Remove tracking parameters and fragments."""
    if not url:
        return None

    url = url.strip()

    if url.startswith("//"):
        url = "https:" + url

    if not url.startswith("http"):
        return None

    parsed = urlparse(url)

    # Remove query string + fragment.
    clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    # Remove trailing slash except root.
    if clean.endswith("/") and parsed.path != "/":
        clean = clean[:-1]

    return clean


def make_id(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def valid_domain(url, domain):
    try:
        return urlparse(url).netloc.lower() == domain.lower()
    except Exception:
        return False


def matches_any(url, patterns):
    return any(pattern in url for pattern in patterns)


# ============================================================
# DATE EXTRACTION
# ============================================================

def parse_date_string(value):
    if not value:
        return None

    value = clean_text(value)

    # ISO dates
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    # RFC dates
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    return None


def extract_date(soup, card=None):
    """
    Try JSON-LD, <time>, and common meta fields.
    """

    # 1. JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        text = script.string or script.get_text()
        if not text:
            continue

        # Simple regex is safer than assuming valid JSON structure.
        matches = re.findall(
            r'"(?:datePublished|dateModified)"\s*:\s*"([^"]+)"',
            text
        )

        for value in matches:
            dt = parse_date_string(value)
            if dt:
                return dt

    # 2. <time>
    if card:
        time_tag = card.find("time")
        if time_tag:
            value = time_tag.get("datetime") or time_tag.get_text()
            dt = parse_date_string(value)
            if dt:
                return dt

    # 3. Page-level <time>
    time_tag = soup.find("time")
    if time_tag:
        value = time_tag.get("datetime") or time_tag.get_text()
        dt = parse_date_string(value)
        if dt:
            return dt

    # 4. Meta tags
    meta_names = [
        "article:published_time",
        "date",
        "pubdate",
        "publish-date",
    ]

    for name in meta_names:
        tag = soup.find("meta", attrs={"property": name})
        if not tag:
            tag = soup.find("meta", attrs={"name": name})

        if tag and tag.get("content"):
            dt = parse_date_string(tag["content"])
            if dt:
                return dt

    return None


# ============================================================
# ARTICLE DESCRIPTION
# ============================================================

def extract_description(card):
    if not card:
        return ""

    # Prefer paragraphs
    p = card.find("p")
    if p:
        text = clean_text(p.get_text(" ", strip=True))
        if len(text) >= 40:
            return text[:500]

    # Then aria-label / title
    for attr in ["aria-label", "title"]:
        value = card.get(attr)
        if value:
            return clean_text(value)[:500]

    return ""


# ============================================================
# LINK EXTRACTION
# ============================================================

def extract_links(source, soup):
    articles = []
    seen = set()

    domain = source["domain"]
    include = source["include"]
    exclude = source["exclude"]

    # Look through all links.
    for a in soup.find_all("a", href=True):

        raw_url = a.get("href")
        url = normalize_url(urljoin(source["url"], raw_url))

        if not url:
            continue

        if not valid_domain(url, domain):
            continue

        if not matches_any(url, include):
            continue

        if matches_any(url, exclude):
            continue

        title = clean_text(a.get_text(" ", strip=True))

        # Ignore tiny navigation links.
        if len(title) < 25:
            continue

        # Avoid obvious UI elements.
        bad_titles = {
            "read more",
            "more",
            "click here",
            "subscribe",
            "login",
            "sign in",
            "share",
        }

        if title.lower() in bad_titles:
            continue

        if url in seen:
            continue

        seen.add(url)

        # Find nearest useful container.
        card = (
            a.find_parent("article")
            or a.find_parent("div", class_=re.compile(
                r"(card|article|story|item|post)",
                re.I
            ))
            or a.parent
        )

        description = extract_description(card)

        articles.append({
            "title": title,
            "url": url,
            "description": description,
        })

    return articles


# ============================================================
# SOURCE-SPECIFIC CLEANING
# ============================================================

def filter_source_articles(source, articles):
    name = source["name"]

    cleaned = []

    for item in articles:
        title = item["title"].strip()
        url = item["url"]

        # ----------------------------------------------------
        # Daily Star Slow Reads
        # ----------------------------------------------------
        if name == "Daily Star - Slow Reads":

            # Remove obvious category/navigation pages.
            if any(x in url for x in [
                "/slow-reads-classics",
                "/slow-reads-special",
            ]):
                continue

            # Keep meaningful long-form pieces.
            if len(title) < 30:
                continue

        # ----------------------------------------------------
        # The Conversation
        # ----------------------------------------------------
        elif name == "The Conversation":

            if "/articles/" not in url:
                continue

            # Conversation article URLs normally contain
            # a substantial slug.
            slug = url.rstrip("/").split("/")[-1]

            if len(slug) < 15:
                continue

        # ----------------------------------------------------
        # Carnegie
        # ----------------------------------------------------
        elif name == "Carnegie Endowment - Research":

            # Avoid generic research/category pages.
            if url.rstrip("/") in [
                "https://carnegieendowment.org/research"
            ]:
                continue

        cleaned.append(item)

    return cleaned


# ============================================================
# SCRAPE ONE SOURCE
# ============================================================

def scrape_source(source):
    print(f"Scraping: {source['name']}")

    try:
        response = session.get(
            source["url"],
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "lxml"
        )

        articles = extract_links(source, soup)

        articles = filter_source_articles(
            source,
            articles
        )

        # ----------------------------------------------------
        # Visit article pages to obtain real publication dates
        # ----------------------------------------------------
        enriched = []

        for article in articles[:MAX_PER_SOURCE * 2]:

            date = None

            try:
                article_response = session.get(
                    article["url"],
                    timeout=REQUEST_TIMEOUT
                )

                article_response.raise_for_status()

                article_soup = BeautifulSoup(
                    article_response.text,
                    "lxml"
                )

                date = extract_date(article_soup)

                # Improve description from article meta.
                if not article["description"]:
                    meta = article_soup.find(
                        "meta",
                        attrs={"name": "description"}
                    )

                    if meta and meta.get("content"):
                        article["description"] = clean_text(
                            meta["content"]
                        )[:500]

            except Exception as e:
                print(
                    f"  Article metadata failed: "
                    f"{article['url']} | {e}"
                )

            article["date"] = date
            enriched.append(article)

        # ----------------------------------------------------
        # Sort newest first.
        # Articles without date go last.
        # ----------------------------------------------------
        enriched.sort(
            key=lambda x: x["date"] or datetime.min.replace(
                tzinfo=timezone.utc
            ),
            reverse=True
        )

        return enriched[:MAX_PER_SOURCE]

    except Exception as e:
        print(
            f"FAILED: {source['name']} | {e}"
        )
        return []


# ============================================================
# RSS GENERATION
# ============================================================

def build_feed(all_articles):

    fg = FeedGenerator()

    fg.id(
        "https://priyanism.github.io/news-feed/feed.xml"
    )

    fg.title(
        "Priyanism High-Value Reading Feed"
    )

    fg.link(
        href="https://priyanism.github.io/news-feed/feed.xml",
        rel="self"
    )

    fg.description(
        "Curated reading feed for BCS, Erasmus Mundus "
        "and advanced English/IELTS preparation."
    )

    fg.language("en")

    fg.lastBuildDate(
        datetime.now(timezone.utc)
    )

    # --------------------------------------------------------
    # Global deduplication
    # --------------------------------------------------------

    seen_urls = set()
    seen_titles = set()

    final_articles = []

    for article in all_articles:

        url = normalize_url(article["url"])

        if not url:
            continue

        title_key = clean_text(
            article["title"]
        ).lower()

        if url in seen_urls:
            continue

        if title_key in seen_titles:
            continue

        seen_urls.add(url)
        seen_titles.add(title_key)

        final_articles.append(article)

    # --------------------------------------------------------
    # Global chronological ordering
    # --------------------------------------------------------

    final_articles.sort(
        key=lambda x: x["date"] or datetime.min.replace(
            tzinfo=timezone.utc
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # RSS items
    # --------------------------------------------------------

    for article in final_articles:

        fe = fg.add_entry()

        fe.id(
            make_id(article["url"])
        )

        fe.title(
            article["title"]
        )

        fe.link(
            href=article["url"]
        )

        description = article["description"]

        if not description:
            description = (
                f"Source: {article['source']}"
            )

        fe.description(
            description
        )

        publication_date = article["date"]

        if not publication_date:
            publication_date = datetime.now(
                timezone.utc
            )

        fe.pubDate(
            publication_date
        )

        # Put source in category.
        fe.category(
            term=article["source"]
        )

    return fg


# ============================================================
# MAIN
# ============================================================

def main():

    all_articles = []

    successful_sources = 0

    for source in SOURCES:

        articles = scrape_source(source)

        if articles:
            successful_sources += 1

        for article in articles:
            article["source"] = source["name"]

        all_articles.extend(articles)

    print(
        f"\nSuccessful sources: "
        f"{successful_sources}/{len(SOURCES)}"
    )

    print(
        f"Articles collected before dedup: "
        f"{len(all_articles)}"
    )

    # Do not destroy feed if every source suddenly fails.
    if not all_articles:
        print(
            "ERROR: No articles collected. "
            "Keeping previous feed.xml."
        )
        return

    feed = build_feed(all_articles)

    feed.rss_file(
        "feed.xml",
        pretty=True
    )

    print(
        f"Feed generated successfully: "
        f"{len(all_articles)} raw articles"
    )


if __name__ == "__main__":
    main()
