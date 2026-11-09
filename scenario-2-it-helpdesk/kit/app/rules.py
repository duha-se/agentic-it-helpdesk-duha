"""Decisions that must not depend on a model's mood: priority, category, department rules, incidents.

Every rule here comes from a knowledge-base document (KB-002, KB-015, KB-016, SP-002).
"""
import re

CATEGORIES = ("network_access", "identity_access", "hardware", "software", "email_collab",
              "security", "onboarding", "other")

# KB-015 section 3: who handles each category (shown in the draft; the API sets the real value).
TEAM_BY_CATEGORY = {
    "network_access": "Network Operations",
    "identity_access": "Identity & Access Management",
    "hardware": "Endpoint Engineering",
    "software": "Endpoint Engineering",
    "email_collab": "Collaboration Services",
    "security": "Security Operations",
    "onboarding": "IT Service Desk",
    "other": "IT Service Desk",
}

# Which services can have an outage on the status page, and their id there.
STATUS_SERVICE_ID = {"vpn": "vpn", "wifi": "wifi", "identity": "nakhlaid", "mail": "mail",
                     "print": "print", "software": "software", "hardware": "mdm", "vdi": "vdi"}

PRIORITY_ORDER = ["P1", "P2", "P3", "P4"]          # most urgent first
IMPACT_TO_PRIORITY = {"blocked": "P2", "workaround": "P3", "request": "P4"}   # KB-015 section 2


def more_urgent(a: str, b: str) -> str:
    return a if PRIORITY_ORDER.index(a) <= PRIORITY_ORDER.index(b) else b


def department_route(employee: dict | None, service: str) -> str | None:
    """Department exceptions that change what the agent may do (KB-016, KB-002, SP-002)."""
    if not employee or service != "vpn":
        return None
    if employee.get("contractor") or employee.get("department") == "Contractors":
        return "contractor_vpn"      # no VPN for contractors, and no ticket for asking
    if employee.get("department") == "Finance":
        return "finance_vpn"         # straight to Security Operations, no client troubleshooting
    return None


def matching_incident(status: dict | None, service: str, codes: list[str], employee: dict | None) -> dict | None:
    """An ACTIVE incident for the same service and the same error code (KB-015 section 1)."""
    service_id = STATUS_SERVICE_ID.get(service)
    if not status or not service_id or not codes:
        return None
    for incident in status.get("incidents", []):
        if incident.get("status") != "active" or incident.get("service") != service_id:
            continue
        if not set(codes) & set(incident.get("error_codes", [])):
            continue
        # An incident that names gateways only hurts people on those gateways.
        # Finance is on GW-3, so an incident about GW-2 is not theirs.
        text = f"{incident.get('title', '')} {incident.get('affected', '')}"
        gateways = set(re.findall(r"GW-\d", text))
        mine = (employee or {}).get("vpn_gateway")
        if gateways and mine and mine not in gateways:
            continue
        return incident
    return None


def final_category(suggested: str, route: str | None, security_incident: bool) -> str:
    if route == "finance_vpn" or security_incident:
        return "security"
    return suggested if suggested in CATEGORIES else "other"


def final_priority(employee: dict, base: str, affected_users: int, security_incident: bool,
                   route: str | None) -> tuple[str, list[str]]:
    """Start from the base priority and only ever raise it. Returns (priority, reasons)."""
    priority, reasons = base, []
    if affected_users > 3:                                   # KB-015 v3.0: more than 3 users
        priority = "P1"
        reasons.append(f"{affected_users} people are affected, which is more than 3 (KB-015).")
    if security_incident:
        priority = "P1"
        reasons.append("This is a security incident (KB-015).")
    if employee.get("vip") or employee.get("department") == "Executive Office":
        priority = "P1"
        reasons.append("Executive Office requests are always P1 (KB-016).")
    if route == "finance_vpn":
        priority = more_urgent(priority, "P2")
        reasons.append("Finance VPN problems are at least P2 and go straight to Security Operations (KB-016).")
    return priority, reasons


def validate_payload(p: dict) -> list[str]:
    """The same rules as dataset/schemas/ticket.schema.json, so a draft is valid before the human sees it."""
    errors = []
    if not 5 <= len(p.get("subject", "")) <= 120:
        errors.append("subject must be 5-120 characters")
    if not 10 <= len(p.get("description", "")) <= 4000:
        errors.append("description must be 10-4000 characters")
    if p.get("category") not in CATEGORIES:
        errors.append("unknown category")
    if p.get("priority") not in PRIORITY_ORDER:
        errors.append("unknown priority")
    if not re.fullmatch(r"[a-z0-9._-]+@nakhla\.example", p.get("requester_email", "")):
        errors.append("bad requester_email")
    steps = p.get("attempted_steps") or []
    if not 1 <= len(steps) <= 20 or any(not 3 <= len(s) <= 300 for s in steps):
        errors.append("attempted_steps needs 1-20 steps of 3-300 characters")
    if any(not re.fullmatch(r"(KB|SP)-\d{3}", r) for r in p.get("kb_refs", [])):
        errors.append("bad kb_refs")
    if not 1 <= int(p.get("affected_users", 1)) <= 1000:
        errors.append("affected_users must be 1-1000")
    return errors
