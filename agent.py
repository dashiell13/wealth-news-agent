"""
Wealth Management News Agent
Fetches daily news, analyzes it with Claude, and sends a digest email via Gmail.
"""

import os
import smtplib
import requests
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import anthropic

# ── Configuration ────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
NEWS_API_KEY      = os.environ.get("NEWS_API_KEY", "")       # newsapi.org free key
GMAIL_ADDRESS     = os.environ.get("GMAIL_ADDRESS", "")      # your Gmail address
GMAIL_APP_PASSWORD= os.environ.get("GMAIL_APP_PASSWORD", "") # Gmail App Password (not your login password)
RECIPIENT_EMAIL   = os.environ.get("RECIPIENT_EMAIL", GMAIL_ADDRESS)  # who gets the email

# Search queries for NewsAPI
SEARCH_QUERIES = [
    "wealth management",
    "private banking asset management",
    "financial advisor fiduciary",
    "SEC FINRA wealth regulation",
    "hedge fund family office",
]

NEWSAPI_BASE = "https://newsapi.org/v2/everything"
# ─────────────────────────────────────────────────────────────────────────────


def fetch_articles() -> list[dict]:
    """Fetch recent articles from NewsAPI across all search queries."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    seen_urls = set()
    all_articles = []

    for query in SEARCH_QUERIES:
        params = {
            "q": query,
            "from": yesterday,
            "sortBy": "relevancy",
            "language": "en",
            "pageSize": 10,
            "apiKey": NEWS_API_KEY,
        }
        try:
            resp = requests.get(NEWSAPI_BASE, params=params, timeout=10)
            resp.raise_for_status()
            for article in resp.json().get("articles", []):
                url = article.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_articles.append({
                        "title":       article.get("title", ""),
                        "source":      article.get("source", {}).get("name", ""),
                        "url":         url,
                        "description": article.get("description", "") or "",
                        "published":   article.get("publishedAt", "")[:10],
                    })
        except Exception as e:
            print(f"[WARN] NewsAPI query '{query}' failed: {e}")

    print(f"[INFO] Fetched {len(all_articles)} unique articles.")
    return all_articles[:40]  # cap to avoid huge prompts


def analyze_with_claude(articles: list[dict]) -> dict:
    """Send articles to Claude and get structured analysis."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    articles_text = "\n\n".join(
        f"[{i+1}] {a['title']}\nSource: {a['source']} | {a['published']}\nURL: {a['url']}\nSummary: {a['description']}"
        for i, a in enumerate(articles)
    )

    prompt = f"""You are a senior analyst covering the wealth management industry.
Below are today's news articles. Produce a concise daily briefing with EXACTLY these four sections:

## 1. Top Headlines Summary
3–5 bullet points covering the most important stories of the day.

## 2. Key Trends & Analysis
2–3 paragraphs on macro themes, market sentiment, and strategic implications for wealth managers.

## 3. Notable Company & Market Moves
Bullet list of significant M&A, product launches, personnel changes, fund flows, or market data points.

## 4. Regulatory & Compliance Updates
Bullet list of any SEC, FINRA, DOL, or international regulatory developments relevant to wealth managers. Write "Nothing significant today." if none.

Keep each section tight and actionable. Cite article numbers like [3] where relevant.

--- ARTICLES ---
{articles_text}
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    analysis = message.content[0].text
    return {"analysis": analysis, "article_count": len(articles)}


def build_html_email(analysis: str, articles: list[dict], date_str: str) -> str:
    """Wrap the Claude analysis in a clean HTML email template."""
    # Convert markdown-ish bullets/headers to HTML
    lines = analysis.split("\n")
    html_body = ""
    for line in lines:
        line = line.strip()
        if not line:
            html_body += "<br>"
        elif line.startswith("## "):
            html_body += f'<h2 style="color:#1a3c5e;border-bottom:2px solid #c8a951;padding-bottom:4px">{line[3:]}</h2>'
        elif line.startswith("- ") or line.startswith("• "):
            html_body += f'<li style="margin-bottom:6px">{line[2:]}</li>'
        else:
            html_body += f'<p style="margin:4px 0">{line}</p>'

    source_links = "".join(
        f'<li><a href="{a["url"]}" style="color:#1a3c5e">{a["title"]}</a> <span style="color:#888">— {a["source"]}</span></li>'
        for a in articles[:15]
    )

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Georgia,serif;max-width:680px;margin:0 auto;color:#222;background:#fafaf8">
  <div style="background:#1a3c5e;padding:24px 32px;border-radius:8px 8px 0 0">
    <h1 style="color:#c8a951;margin:0;font-size:22px">⚖️ Wealth Management Daily Briefing</h1>
    <p style="color:#9ab5cf;margin:6px 0 0">{date_str}</p>
  </div>
  <div style="background:#fff;padding:28px 32px;border:1px solid #ddd;border-top:none">
    {html_body}
    <hr style="margin:32px 0;border:none;border-top:1px solid #eee">
    <h3 style="color:#1a3c5e">📰 Source Articles</h3>
    <ul style="padding-left:18px;line-height:1.8">{source_links}</ul>
  </div>
  <div style="background:#f0ede6;padding:12px 32px;font-size:12px;color:#888;border-radius:0 0 8px 8px">
    Generated by Wealth Management News Agent · Powered by Claude
  </div>
</body>
</html>
"""


def send_email(subject: str, html_content: str) -> None:
    """Send HTML email via Gmail SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())

    print(f"[INFO] Email sent to {RECIPIENT_EMAIL}")


def run():
    print(f"[INFO] Starting wealth management news agent — {datetime.now():%Y-%m-%d %H:%M}")

    # Validate config
    missing = [k for k, v in {
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "NEWS_API_KEY":      NEWS_API_KEY,
        "GMAIL_ADDRESS":     GMAIL_ADDRESS,
        "GMAIL_APP_PASSWORD":GMAIL_APP_PASSWORD,
    }.items() if not v]
    if missing:
        raise EnvironmentError(f"Missing environment variables: {', '.join(missing)}")

    articles  = fetch_articles()
    result    = analyze_with_claude(articles)
    date_str  = datetime.now().strftime("%A, %B %-d, %Y")
    html      = build_html_email(result["analysis"], articles, date_str)
    subject   = f"💼 Wealth Management Briefing — {date_str}"

    send_email(subject, html)
    print("[INFO] Done.")


if __name__ == "__main__":
    run()