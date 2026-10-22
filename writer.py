"""Writes outreach emails (Anthropic API if a key exists, otherwise the local `claude` CLI)
and serves the short follow up messages from an editable pool."""
import json
import os
import re
import shutil
import subprocess
import urllib.request

try:
    import anthropic
except ImportError:
    anthropic = None

MODEL = os.getenv("WRITER_MODEL", "claude-sonnet-5-5")
TEMPLATES = "followup_templates.json"

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


def first_name(full: str) -> str:
    return (full or "").strip().split(" ")[0] if full else "there"


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


def clean(text: str) -> str:
    """Hard guarantee: no dashes or exclamation marks survive."""
    text = text.replace("—", ", ").replace("–", ", ")
    text = re.sub(r"\s+-+\s+", ", ", text)
    text = re.sub(r"(?<=\w)-(?=\w)", " ", text)
    text = re.sub(r" +,", ",", text).replace(",,", ",")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.replace("!", ".").strip()


def _llm(system: str, user: str) -> str:
    if os.getenv("ANTHROPIC_API_KEY") and anthropic:
        msg = anthropic.Anthropic().messages.create(
            model=MODEL, max_tokens=1000, system=system,
            messages=[{"role": "user", "content": user}])
        return msg.content[0].text
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("No ANTHROPIC_API_KEY and the `claude` CLI was not found.")
    r = subprocess.run([exe, "-p", "--output-format", "text"], input=system + "\n\n" + user,
                       capture_output=True, text=True, encoding="utf-8", timeout=240)
    if r.returncode != 0:
        raise RuntimeError("claude CLI failed: " + (r.stderr or r.stdout)[:300])
    return r.stdout


def _ask(system: str, user: str) -> dict:
    raw = _llm(system, user)
    d = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    body = clean(d["body"])
    NL = chr(10)
    head, sep, rest = body.partition(NL)
    if sep and head.startswith("Hi ") and head.endswith(",") and not rest.startswith(NL):
        body = head + NL + NL + rest
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


DEFAULT_POOL = {
    "client": [
        "Hi {first}, just nudging my earlier note back up in case it got buried. I'd love to show you Mapster live for {event}, whenever suits you.",
        "Hi {first}, one more thought on {event}. The stalls tucked away from the entrance are usually the ones nobody finds, and our treasure hunt fixes that. Could we do a quick call this week?",
        "Hi {first}, the pilot for {event} is completely free and we do all the setup. Even ten minutes on a call would show you how it works.",
        "Hi {first}, all we need to start is your floor plan and exhibitor list. Want me to send a few screens first so you can see how it looks?",
        "Hi {first}, I know event teams are swamped. If someone else handles this, could you point me their way?",
        "Hi {first}, you'd also get real visitor data after {event}, which sponsors love to see. Worth a quick look?",
        "Hi {first}, I'm still keen to help with {event}. If the timing's off, just say so and I'll check back later.",
        "Hi {first}, a quick yes or no on a call would really help me plan, and either answer is completely fine.",
        "Hi {first}, picture a parent at {event} trying to find one particular stall in a huge hall. That's the exact problem Mapster solves, and I'd happily show you how in a few minutes.",
        "Hi {first}, no sales pitch, promise. I'd just like to show you a working demo and hear what you think for {event}.",
        "Hi {first}, wanted to check my email reached the right person. If you look after visitor experience for {event}, I'd love a short chat.",
        "Hi {first}, we're offering this first pilot at no cost, so there's really nothing to lose by taking a look. Does this week or next suit you for a short call?",
        "Hi {first}, the hardest part of a big event is often the stalls at the back getting missed. Mapster sends visitors there on purpose. Can I show you how?",
        "Hi {first}, if a call is too much right now, I can email a few screens of the app instead. Just tell me what works for you.",
    ],
    "network": [
        "Hi {first}, bringing my note back to your inbox. I'd really value 15 minutes of your thoughts on Mapster, even if it's only feedback.",
        "Hi {first}, we're close to our first live pilot at an exhibition, and early guidance from people like you would mean a lot. Could we talk this week?",
        "Hi {first}, happy to send a few screens of the app if that's easier than a call.",
        "Hi {first}, if this isn't your area, could you point me to someone who might be a better fit? Even a name would help.",
        "Hi {first}, I know your inbox must be full. A one line reply with a good time to talk is all I need.",
        "Hi {first}, Mapster is already built and working, so I'm not asking you to back just an idea. Would a quick walk through help?",
        "Hi {first}, a gentle nudge. Still keen to hear your views whenever you have a few minutes.",
        "Hi {first}, last check in from me for now. If the timing's off, tell me and I'll reach out again later.",
        "Hi {first}, no big ask here. Just a short chat to get your honest take on Mapster, and maybe an introduction or two if you see a fit.",
        "Hi {first}, I'm building Mapster so visitors never get lost at big events, and I'd love an experienced pair of eyes on it. Do you have 15 minutes?",
        "Hi {first}, wanted to make sure my first note didn't slip past you. Even a quick 'not now' helps me a lot.",
        "Hi {first}, we're lining up our first exhibition pilot soon, and your perspective could shape where we go next. Open to a short call?",
    ],
}

GREETINGS = ["Hi {first},", "Hey {first},", "Hello {first},", "{first},"]


def load_pool() -> dict:
    if not os.path.exists(TEMPLATES):
        save_pool(DEFAULT_POOL)
    return json.load(open(TEMPLATES, encoding="utf-8"))


def save_pool(pool: dict):
    json.dump(pool, open(TEMPLATES, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


class _D(dict):
    def __missing__(self, k):
        return ""


def followup_text(c: dict, n: int) -> str:
    """Follow up number n (1 based). Order and greeting differ per person, so two contacts
    never get the same sequence of messages."""
    import random
    import zlib
    pool = load_pool().get(c.get("category") or "client") or DEFAULT_POOL["client"]
    seed = zlib.crc32((c.get("email") or c.get("name") or "x").lower().encode())
    cat = c.get("category") or "client"
    closers = {i for i, t in enumerate(pool) if any(k in t for k in ("check back later", "check in from me", "yes or no", "reach out again"))}
    rng = random.Random(seed)
    early = rng.sample([i for i in range(len(pool)) if i not in closers], len(pool) - len(closers))
    order = early + rng.sample(sorted(closers), len(closers))
    t = pool[order[(n - 1) % len(pool)]]
    greet = random.Random(seed * 31 + n).choice(GREETINGS)
    if t.startswith("Hi {first},"):
        t = greet + t[len("Hi {first},"):]
    event = c.get("event") or c.get("org") or "your event"
    return clean(t.format_map(_D(first=first_name(c.get("name")), name=c.get("name", ""),
                                 event=event, org=c.get("org") or "your organization")))
