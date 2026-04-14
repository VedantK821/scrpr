import os
import re
import logging
from app.sources.base import EnrichmentSource, SourceResult
from app.scraper.email_verifier import EmailVerifier, EmailVerifyStatus
from app.services.email_cache import EmailCacheService

logger = logging.getLogger(__name__)

# Self-contained enrichment logger — writes to file regardless of main.py
_LOG_DIR = os.path.expanduser("~/.scrpr/logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_elog = logging.getLogger("enrichment")
if not _elog.handlers:
    _elog.setLevel(logging.DEBUG)
    _efh = logging.FileHandler(os.path.join(_LOG_DIR, "enrichment.log"), encoding="utf-8")
    _efh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s", datefmt="%H:%M:%S"))
    _elog.addHandler(_efh)
    _esh = logging.StreamHandler()
    _esh.setFormatter(logging.Formatter("[ENRICH] %(message)s"))
    _elog.addHandler(_esh)

# Ordered by frequency in the real world (first.last is ~48% of companies)
ALL_PATTERNS = [
    "{first}.{last}@{domain}",
    "{first}{last}@{domain}",
    "{f}{last}@{domain}",
    "{f}.{last}@{domain}",
    "{first}_{last}@{domain}",
    "{first}-{last}@{domain}",
    "{last}.{first}@{domain}",
    "{last}{first}@{domain}",
    "{last}{f}@{domain}",
    "{last}_{first}@{domain}",
    "{first}@{domain}",
    "{last}@{domain}",
    "{f}{l}@{domain}",
    "{first}.{l}@{domain}",
    "{first}{middle}.{last}@{domain}",
    "{f}{middle}{last}@{domain}",
]

# Common company name → actual domain mappings (Indian companies + global MNCs)
KNOWN_DOMAINS = {
    "tcs": "tcs.com",
    "tata consultancy services": "tcs.com",
    "infosys": "infosys.com",
    "wipro": "wipro.com",
    "hcl": "hcltech.com",
    "hcl technologies": "hcltech.com",
    "reliance": "ril.com",
    "reliance industries": "ril.com",
    "mahindra": "mahindra.com",
    "tech mahindra": "techmahindra.com",
    "larsen & toubro": "larsentoubro.com",
    "l&t": "larsentoubro.com",
    "bajaj": "bajaj.com",
    "hdfc bank": "hdfcbank.com",
    "icici bank": "icicibank.com",
    "axis bank": "axisbank.com",
    "kotak mahindra": "kotak.com",
    "state bank of india": "sbi.co.in",
    "sbi": "sbi.co.in",
    "hindustan unilever": "hul.co.in",
    "itc": "itcportal.com",
    "asian paints": "asianpaints.com",
    "mckinsey": "mckinsey.com",
    "bcg": "bcg.com",
    "bain": "bain.com",
    "deloitte": "deloitte.com",
    "pwc": "pwc.com",
    "ey": "ey.com",
    "ernst & young": "ey.com",
    "kpmg": "kpmg.com",
    "accenture": "accenture.com",
    "capgemini": "capgemini.com",
    "cognizant": "cognizant.com",
    "ibm": "ibm.com",
    "google": "google.com",
    "microsoft": "microsoft.com",
    "amazon": "amazon.com",
    "meta": "meta.com",
    "apple": "apple.com",
    "oracle": "oracle.com",
    "salesforce": "salesforce.com",
    "adobe": "adobe.com",
    "dell": "dell.com",
    "hp": "hp.com",
    "samsung": "samsung.com",
    "sony": "sony.com",
    "goldman sachs": "gs.com",
    "jp morgan": "jpmorgan.com",
    "morgan stanley": "morganstanley.com",
    "deutsche bank": "db.com",
    "barclays": "barclays.com",
    "hsbc": "hsbc.com",
    "unilever": "unilever.com",
    "nestle": "nestle.com",
    "procter & gamble": "pg.com",
    "p&g": "pg.com",
}


def _looks_like_domain(s: str) -> bool:
    """Check if a string looks like a real domain (has a valid TLD)."""
    s = s.strip().lower()
    return bool(re.match(r'^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z]{2,})+$', s))


def _resolve_domain(company: str, raw_domain: str) -> str:
    """Resolve company name to actual email domain."""
    if raw_domain:
        d = raw_domain.lower().replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0].strip()
        if d and _looks_like_domain(d):
            return d
        logger.debug(f"Ignoring invalid domain value: '{raw_domain}' for {company}")

    if not company:
        return ""

    # Check known domains first
    company_lower = company.lower().strip()
    for key, domain in KNOWN_DOMAINS.items():
        if key in company_lower or company_lower in key:
            return domain

    # Fallback: clean and guess
    # Try removing common suffixes, but keep at least the core name
    clean = re.sub(r'\b(ltd|limited|inc|incorporated|pvt|private|corporation|llp|llc)\b', '', company_lower, flags=re.IGNORECASE)
    clean = re.sub(r'[^a-z0-9\s]', '', clean).strip()
    clean = re.sub(r'\s+', '', clean)
    if clean:
        return f"{clean}.com"
    # If everything was stripped, just use the raw company name
    fallback = re.sub(r'[^a-z0-9]', '', company_lower)
    return f"{fallback}.com" if fallback else ""


def _parse_name(full_name: str) -> dict:
    """Parse a full name into first, middle, last, and initial components."""
    parts = full_name.strip().lower().split()
    # Remove common titles/suffixes
    skip = {"mr", "mrs", "ms", "dr", "prof", "sir", "shri", "smt", "jr", "sr", "ii", "iii"}
    parts = [p for p in parts if p.rstrip(".") not in skip]

    if not parts:
        return {}

    first = re.sub(r'[^a-z]', '', parts[0])

    if len(parts) == 1:
        return {"first": first, "last": "", "middle": "", "f": first[0] if first else "", "l": ""}

    last = re.sub(r'[^a-z]', '', parts[-1])
    middle = re.sub(r'[^a-z]', '', parts[1]) if len(parts) > 2 else ""

    return {
        "first": first,
        "last": last,
        "middle": middle,
        "f": first[0] if first else "",
        "l": last[0] if last else "",
        "m": middle[0] if middle else "",
    }


def _generate_candidates(name_parts: dict, domain: str) -> list[str]:
    """Generate email candidates, ordered by likelihood."""
    if not name_parts.get("first") or not domain:
        return []

    candidates = []
    for pattern in ALL_PATTERNS:
        try:
            # Skip patterns requiring middle name if we don't have one
            if "{middle}" in pattern and not name_parts.get("middle"):
                continue
            email = pattern.format(domain=domain, **name_parts)
            if email and email not in candidates:
                candidates.append(email)
        except KeyError:
            continue
    return candidates


class EmailPatternSource(EnrichmentSource):
    name = "email_pattern"
    rate_limit_per_minute = 10

    def __init__(self):
        self.verifier = EmailVerifier()
        self.cache = EmailCacheService()

    async def enrich(self, row_data: dict[str, str], prompt: str) -> SourceResult:
        from app.services.contact_parser import extract_name
        elog = logging.getLogger("enrichment")

        raw_name = (
            row_data.get("Key Contact")
            or row_data.get("Contact")
            or row_data.get("name") or row_data.get("full_name")
            or row_data.get("Recruiter") or row_data.get("Hiring Contact")
            or ""
        )
        full_name = extract_name(raw_name) if raw_name else ""
        raw_domain = row_data.get("domain") or row_data.get("Domain") or row_data.get("website") or ""
        company = row_data.get("company") or row_data.get("Company") or row_data.get("Name") or ""

        elog.info(f"EMAIL_PATTERN: name='{full_name}' company='{company}' raw_domain='{raw_domain}'")
        elog.debug(f"  row_data keys: {list(row_data.keys())}")

        if not full_name:
            elog.warning(f"  SKIP: no name (raw='{raw_name}')")
            return SourceResult(found=False, source_name=self.name, error="No name provided")
        if not raw_domain and not company:
            elog.warning(f"  SKIP: no domain or company")
            return SourceResult(found=False, source_name=self.name, error="No domain or company provided")

        # Smart domain resolution — search-based, not guessing
        if raw_domain:
            domain = _resolve_domain(company, raw_domain)
        else:
            from app.services.domain_resolver import resolve_domain
            domain = await resolve_domain(company)
            if not domain:
                domain = _resolve_domain(company, "")  # fallback to old guesser
        if not domain:
            elog.error(f"  FAIL: could not resolve domain for '{company}'")
            return SourceResult(found=False, source_name=self.name, error=f"Could not resolve domain for '{company}'")
        elog.info(f"  DOMAIN: {domain} (from raw='{raw_domain}', company='{company}')")

        # Parse name (handles titles, middle names, Indian names)
        name_parts = _parse_name(full_name)
        if not name_parts.get("first") or not name_parts.get("last"):
            return SourceResult(found=False, source_name=self.name, error="Need at least first and last name")

        # ── Step 1: OSINT pattern discovery (PGP + GitHub — learn BEFORE guessing)
        discovered_pattern = None
        direct_hit = None

        # 1a: GitHub commit mining
        try:
            from app.services.github_email_miner import mine_github_emails
            mine_result = await mine_github_emails(company, domain)
            if mine_result.emails:
                for mined_email in mine_result.emails:
                    local = mined_email.split("@")[0].lower()
                    if name_parts["first"] in local and name_parts.get("last", "") in local:
                        direct_hit = mined_email
                        break
                if direct_hit:
                    elog.info(f"  GITHUB HIT: {direct_hit}")
                    return SourceResult(
                        found=True, value=direct_hit,
                        data={"method": "github_commit", "verified": True},
                        confidence=0.95, source_name=self.name,
                    )
                discovered_pattern = mine_result.pattern
                elog.info(f"  GITHUB: pattern={discovered_pattern} ({len(mine_result.emails)} emails)")
        except Exception as e:
            elog.debug(f"  GITHUB: failed ({e})")

        # 1b: Ghost OSINT (PGP keyservers, CT logs, search engines)
        try:
            from app.services.ghost_osint import gather_domain_intel
            intel = await gather_domain_intel(domain)
            if intel.all_emails:
                elog.info(f"  OSINT: {len(intel.all_emails)} emails, pattern={intel.detected_pattern}")
                for osint_email in intel.all_emails:
                    local = osint_email.split("@")[0].lower()
                    if name_parts["first"] in local and name_parts.get("last", "") in local:
                        elog.info(f"  OSINT HIT: {osint_email}")
                        return SourceResult(
                            found=True, value=osint_email,
                            data={"method": "osint_direct", "verified": True},
                            confidence=0.90, source_name=self.name,
                        )
                if not discovered_pattern and intel.detected_pattern:
                    discovered_pattern = intel.detected_pattern
        except Exception as e:
            elog.debug(f"  OSINT: failed ({e})")

        # 1c: Cache pattern learning
        cached_pattern = await self._learn_pattern_from_cache(domain)
        if cached_pattern:
            elog.info(f"  CACHE: learned pattern={cached_pattern}")

        # ── Step 2: Generate candidates (pattern-first ordering)
        candidates = _generate_candidates(name_parts, domain)
        if not candidates:
            elog.error(f"  FAIL: no candidates generated")
            return SourceResult(found=False, source_name=self.name, error="Could not generate email candidates")

        # Reorder: put discovered/cached pattern candidates first
        best_pattern = discovered_pattern or cached_pattern
        if best_pattern:
            first = name_parts["first"]
            last = name_parts["last"]
            f = name_parts.get("f", "")
            middle = name_parts.get("middle", "")
            pattern_target = None
            if best_pattern == "first.last":
                pattern_target = f"{first}.{last}@{domain}"
            elif best_pattern == "f.last":
                pattern_target = f"{f}.{last}@{domain}"
            elif best_pattern == "first.middle.last" and middle:
                pattern_target = f"{first}.{middle}.{last}@{domain}"
            if pattern_target and pattern_target in candidates:
                candidates.remove(pattern_target)
                candidates.insert(0, pattern_target)
                elog.info(f"  PATTERN-FIRST: {pattern_target}")

        elog.info(f"  CANDIDATES: {candidates[:5]}")

        # ── Step 3: Verify via email_verifier_v2 (all 7 oracles)
        from app.services.email_verifier_v2 import verify_batch

        results = await verify_batch(candidates[:10])
        verified = [r for r in results if r.get("exists") is True]

        if verified:
            best = verified[0]
            elog.info(f"  VERIFIED: {best['email']} ({best['method']}, conf={best['confidence']})")
            return SourceResult(
                found=True, value=best["email"],
                data={
                    "candidates": candidates[:5],
                    "method": best["method"],
                    "verified": True,
                    "provider": best.get("provider", ""),
                },
                confidence=best["confidence"], source_name=self.name,
            )

        # No oracle confirmed any candidate
        best_guess = candidates[0]
        elog.warning(f"  NO VERIFICATION: returning best guess {best_guess}")
        return SourceResult(
            found=True, value=best_guess,
            data={"candidates": candidates[:5], "method": "pattern_guess", "verified": False},
            confidence=0.15, source_name=self.name,
        )

    async def _learn_pattern_from_cache(self, domain: str) -> str | None:
        """Check the email cache for known emails at this domain to learn the pattern."""
        try:
            cached_emails = await self.cache.lookup_by_domain(domain)
            if not cached_emails:
                return None

            # Find the most common pattern from cached emails
            patterns_seen = {}
            for entry in cached_emails:
                email = entry.email
                name = entry.person_name.lower().split()
                if len(name) < 2:
                    continue
                first = re.sub(r'[^a-z]', '', name[0])
                last = re.sub(r'[^a-z]', '', name[-1])
                local = email.split("@")[0]

                # Detect which pattern this email matches
                if local == f"{first}.{last}":
                    patterns_seen["first.last"] = patterns_seen.get("first.last", 0) + 1
                elif local == f"{first}{last}":
                    patterns_seen["firstlast"] = patterns_seen.get("firstlast", 0) + 1
                elif local == f"{first[0]}{last}":
                    patterns_seen["flast"] = patterns_seen.get("flast", 0) + 1
                elif local == f"{first[0]}.{last}":
                    patterns_seen["f.last"] = patterns_seen.get("f.last", 0) + 1
                elif local == first:
                    patterns_seen["first"] = patterns_seen.get("first", 0) + 1

            if not patterns_seen:
                return None

            # Return the most common pattern
            best_pattern = max(patterns_seen, key=patterns_seen.get)
            logger.info(f"Learned domain pattern for {domain}: {best_pattern} (from {sum(patterns_seen.values())} cached emails)")
            return best_pattern  # This is the pattern name, not the email — caller maps it

        except Exception:
            return None
