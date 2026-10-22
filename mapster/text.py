import re


def clean(text: str) -> str:
    """Hard guarantee: no dashes or exclamation marks survive."""
    text = text.replace("—", ", ").replace("–", ", ")
    text = re.sub(r"\s+-+\s+", ", ", text)
    text = re.sub(r"(?<=\w)-(?=\w)", " ", text)
    text = re.sub(r" +,", ",", text).replace(",,", ",")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.replace("!", ".").strip()


def first_name(full: str | None) -> str:
    return full.strip().split(" ")[0] if full and full.strip() else "there"
