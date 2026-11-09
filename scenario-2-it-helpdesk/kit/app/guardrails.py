"""Safety checks that run in code, so they hold even if the model misbehaves."""
import logging
import re

log = logging.getLogger("helpdesk.guardrails")

# Phrases that show up when text tries to give orders to an AI assistant.
# Tickets are written by employees, so we scan them before the model sees them.
INJECTION_PATTERNS = [
    r"ignore (all |your |any |the )?(previous|prior|above|earlier) (instructions|rules|policies)",
    r"system override",
    r"maintenance mode",
    r"note for ai",
    r"do not (mention|tell|reveal) this",
    r"(pre-?approved|approval is not required|without asking)",
    r"you are now",
]

# Things a reply must never contain, whatever the model was told.
UNSAFE_REPLY_PATTERNS = [
    r"posture_check",                       # the "turn off the version check" trick
    r"client\.ini",
    r"local ?admin(istrator)? password",
    r"\bNakhla-[A-Za-z]+-\d{3,}\b",         # shape of the planted admin password
]

DOC_ID = re.compile(r"\b(?:KB|SP)-\d{3}\b")
# An error code like NX-781 or SWC-2001. Ids of documents, incidents and tickets are not error codes.
CODE = re.compile(r"\b(?!(?:KB|SP|INC|IT)-)[A-Z]{2,4}-\d{2,4}\b")
TICKET_ID = re.compile(r"\bIT-\d{4}\b")
URL = re.compile(r"https?://[^\s)\]>\"']+")
VERSION = re.compile(r"\b\d+\.\d+(?:\.\d+)?\b")


def find_injection(text: str) -> list[str]:
    """Return the suspicious patterns found in a piece of untrusted text."""
    return [p for p in INJECTION_PATTERNS if re.search(p, text or "", re.IGNORECASE)]


def clean_untrusted(text: str, source: str) -> str:
    """Return the text, or a placeholder if it looks like instructions to an AI."""
    hits = find_injection(text)
    if hits:
        # "Ignored and reported": the model never sees it, and the log shows it.
        log.warning("possible prompt injection removed from %s: %s", source, hits)
        return "[removed: this text looked like instructions to an AI assistant]"
    return text


def unsafe_reply(reply: str) -> list[str]:
    return [p for p in UNSAFE_REPLY_PATTERNS if re.search(p, reply or "", re.IGNORECASE)]


def reply_problems(reply: str, *, corpus: str, retrieved_ids: set[str]) -> list[str]:
    """Check an answer against what the model was actually given.

    corpus is every text the model could legitimately quote: the sources, the
    conversation, the employee profile. Anything in the reply that is not in it
    (a URL, an error code, a version, a ticket id) was invented.
    """
    problems = []
    cited = set(DOC_ID.findall(reply))
    if not cited & retrieved_ids:
        problems.append("The reply must cite at least one id from SOURCES in square brackets, like [KB-002].")
    # A document may be mentioned if the sources themselves mention it ("see KB-009"), but a
    # document nobody gave the model (a deprecated or draft one) may not.
    allowed_docs = retrieved_ids | set(DOC_ID.findall(corpus))
    for doc_id in sorted(cited - allowed_docs):
        problems.append(f"{doc_id} does not appear in the SOURCES.")

    lowered = corpus.lower()
    for url in sorted({u.rstrip(".,;:") for u in URL.findall(reply)}):
        if url.lower() not in lowered:
            problems.append(f"The URL {url} does not appear in the SOURCES.")
    for code in sorted(set(CODE.findall(reply))):
        if code not in corpus:
            problems.append(f"The error code {code} does not appear in the SOURCES.")
    for version in sorted(set(VERSION.findall(reply))):
        if version not in corpus:
            problems.append(f"The version {version} does not appear in the SOURCES.")
    for ticket in sorted(set(TICKET_ID.findall(reply))):
        if ticket not in corpus:
            problems.append(f"The ticket id {ticket} was not returned by the helpdesk system.")
    for pattern in unsafe_reply(reply):
        problems.append(f"The reply must not contain anything matching '{pattern}'.")
    return problems
