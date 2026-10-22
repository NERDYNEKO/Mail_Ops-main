"""Prompts and email drafting."""
import json
import re
import urllib.request
from functools import lru_cache

from . import llm
from .text import clean, first_name

SIGNATURE = ("Best regards,\n\nRudraksh Singh Bhadauria\nFounder, Mapster\n"
             "https://mapster.co.in/ | +91-7987543938")

CLIENT_FACTS = """About Mapster (only use what is true here):
- Indoor navigation and visitor engagement platform for large exhibitions, expos and trade shows.
- Turn by turn indoor wayfinding to any stall, hall or facility, accurate indoors where GPS fails.
- Searchable directory of every exhibitor, stall, workshop and zone.
- Gamified treasure hunt (points, streaks, leaderboard) so visitors explore every corner, not only booths near the entrance.
- Announcements and in app guidebook for live schedule changes and offers.
- Works in 7 Indian languages. One web app, no download, visitors scan a QR code at entry.
- Admin dashboard with live visitor and booth analytics to show sponsors and exhibitors.
- Fully built and working today.
- Pilot offer: first pilot exhibition partner. Mapster builds, deploys and supports everything free of cost, no long term commitment. In return, the event becomes their flagship case study.
- The proposal PDF is attached. Offer a quick call with a live demo."""

NETWORK_FACTS = """About Mapster (only use what is true here):
- Indoor navigation and exhibition engagement platform, fully built and working today. Founder: Rudraksh Singh Bhadauria.
- Problem: GPS fails indoors, visitors get lost in large events, malls, campuses, airports and metro stations, and static maps cannot update live.
- Product: turn by turn indoor wayfinding, searchable exhibitor directory, gamified treasure hunt that drives footfall to every stall, live announcements, 7 Indian languages, admin analytics dashboard. Web app, no download.
- Market context from the deck: global indoor positioning market about 10.9 billion USD in 2023 growing to over 43 billion USD by 2030 (Grand View Research, MarketsandMarkets).
- Stage: product is built, now looking for the first pilot exhibition partner and early guidance.
- The pitch deck is attached.
- The ask is a short conversation: advice, feedback, introductions to exhibition organizers or other relevant people, or investment interest if it fits them. Do not claim any revenue, customers or funding that is not listed here."""

STYLE = """Voice and style rules (important):
- Write the way a friendly founder talks to a smart acquaintance. Natural, relaxed, a little warm. Use contractions (I'm, we'd, it's, don't, you'll). It should read like it was typed in two minutes, not drafted by a team.
- Start with one specific, genuine observation about their event or work. Never flattery, never "I came across", never "I'm reaching out", never "I hope you're well".
- Explain Mapster in everyday words, like telling a friend. Paint one small real scene (a parent with a kid hunting for the robotics zone, an exhibitor tucked in a back hall nobody walks past) instead of listing features. Avoid jargon such as platform, solution, engagement, analytics, ecosystem, stakeholders. Say "you'd see which areas visitors actually spend time in" rather than "live analytics dashboard".
- Vary the rhythm: mix a short sentence with a longer one. It's fine to start a sentence with And, But or So once. No pattern of three matching sentences.
- Let each paragraph flow into the next with a natural link, not a feature list in disguise.
- End with a soft, easy ask, like "Would you be up for a quick call this week? Happy to show it live." Not "Please let me know your availability".
- NEVER use dashes of any kind: no em dash, no en dash, no hyphen as punctuation. Avoid hyphenated compound words too (write "turn by turn", "walk through"). Use commas and full stops.
- No bullet points, no bold, no headings, no emojis, no exclamation marks.
- Banned words and phrases: leverage, seamless, elevate, game changer, cutting edge, revolutionize, delve, unlock, streamline, robust, innovative, "take it to the next level", "I hope this email finds you well", "in today's fast paced world".
- Never invent facts about the recipient. Use only the details given. If details are thin, stay honest and general."""


@lru_cache(maxsize=256)
def fetch_site(url: str, limit: int = 3000) -> str:
    if not url:
        return ""
    try:
        if not url.startswith("http"):
            url = "https://" + url
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
        html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()[:limit]
    except Exception:
        return ""


def _ask(system: str, user: str) -> dict:
    raw = llm.complete(system, user)
    d = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    body = clean(d["body"])
    head, sep, rest = body.partition("\n")
    if sep and head.startswith("Hi ") and head.endswith(",") and not rest.startswith("\n"):
        body = head + "\n\n" + rest
    return {"subject": clean(d["subject"]), "body": body}


def _context(c: dict) -> str:
    return (f"Recipient name: {c.get('name', '')}\nOrganization: {c.get('org', '')}\n"
            f"Event: {c.get('event', '')}\n"
            f"What they do / details (from our notes): {c.get('about', '')}\n"
            f"Website text (may be empty or noisy):\n{fetch_site(c.get('website', ''))}")


def write_first(c: dict) -> dict:
    fn = first_name(c.get("name"))
    if c.get("category") == "network":
        system = f"You write short personal emails for Rudraksh, founder of Mapster, to people who could help with advice, network or investment.\n{NETWORK_FACTS}\n\n{STYLE}"
        task = f"""Write a first email of about 70 words (60 to 78, never more) in 3 short paragraphs:
1. "Hi {fn}," then one or two sentences showing you know who they are and why you picked them (use only the details given).
2. Two sentences on what Mapster is and why it matters, plus that it is built and now looking for its first pilot.
3. Ask for a short call to get their thoughts, introductions or interest, and say the pitch deck is attached."""
        subj = "Subject: plain, human, mentions Mapster and what you want (a quick conversation). Under 70 characters."
    else:
        system = f"You write short personal outreach emails for Rudraksh, founder of Mapster, to exhibition organizers.\n{CLIENT_FACTS}\n\n{STYLE}"
        task = f"""Write a first email of about 70 words (60 to 78, never more) in 3 short paragraphs:
1. "Hi {fn}," then one or two sentences showing you understand what their event is and who it serves (use only the details given).
2. Two sentences on how Mapster helps THEM specifically, picking the 2 or 3 features that fit their event.
3. The free pilot offer (no cost, no long term commitment), say the proposal is attached, and ask for a quick demo call."""
        subj = "Subject: specific to their event, plain and human, mentions the free pilot. Under 70 characters."
    user = f"""{_context(c)}

{task}
Do NOT include a sign off or signature, it is added automatically. Count the words of the body. Going over 78 words is a failure. Keep sentences short.
{subj}
Reply ONLY with JSON: {{"subject": "...", "body": "..."}}"""
    best = None
    for _ in range(4):  # retry if the draft runs long
        mail = _ask(system, user)
        n = len(mail["body"].split())
        if best is None or n < len(best["body"].split()):
            best = mail
        if n <= 79:
            break
        user += f"\n\nYour last attempt was {n} words. Rewrite it clearly under 78 words."
    return best
