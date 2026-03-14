"""
Workflow 2: Address Validation & Enrichment Agent
Validates addresses and standardises format.
"""

import json
import re
from demo_db import get_connection


# Simple demo validation rules (no external API needed in demo mode)
US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
}

# Approximate lat/lon for demo cities
CITY_COORDS = {
    "new york":    (40.7128, -74.0060),
    "london":      (51.5074, -0.1278),
    "chicago":     (41.8781, -87.6298),
    "los angeles": (34.0522, -118.2437),
    "detroit":     (42.3314, -83.0458),
    "houston":     (29.7604, -95.3698),
    "boston":      (42.3601, -71.0589),
    "dallas":      (32.7767, -96.7970),
    "cleveland":   (41.4993, -81.6944),
}


def _validate_us_address(row) -> tuple[bool, list]:
    issues = []
    if not row["state"] or row["state"].upper() not in US_STATES:
        issues.append(f"Invalid US state: '{row['state']}'")
    if not row["postal_code"] or not re.match(r"^\d{5}(-\d{4})?$", row["postal_code"]):
        issues.append(f"Invalid US ZIP: '{row['postal_code']}'")
    if not row["address_line1"] or len(row["address_line1"].strip()) < 5:
        issues.append("Address line too short")
    return len(issues) == 0, issues


def _validate_uk_address(row) -> tuple[bool, list]:
    issues = []
    uk_postcode = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$", re.I)
    if not row["postal_code"] or not uk_postcode.match(row["postal_code"]):
        issues.append(f"Invalid UK postcode: '{row['postal_code']}'")
    return len(issues) == 0, issues


def validate_address(party_site_id: int = None, party_id: int = None) -> dict:
    """
    Validate addresses for a party site or all sites of a party.
    Returns validation results with any issues and standardised fields.
    """
    conn = get_connection()
    c = conn.cursor()

    if party_site_id:
        sites = c.execute(
            "SELECT * FROM hz_party_sites WHERE party_site_id=?", (party_site_id,)
        ).fetchall()
    elif party_id:
        sites = c.execute(
            "SELECT * FROM hz_party_sites WHERE party_id=?", (party_id,)
        ).fetchall()
    else:
        sites = c.execute(
            "SELECT * FROM hz_party_sites WHERE validated=0"
        ).fetchall()

    results = []
    for site in sites:
        country = (site["country"] or "").upper()
        if country == "US":
            valid, issues = _validate_us_address(site)
        elif country == "UK":
            valid, issues = _validate_uk_address(site)
        else:
            valid, issues = True, []  # Pass-through for other countries

        # Enrich with lat/lon from demo lookup
        city_key = (site["city"] or "").lower()
        lat, lon = CITY_COORDS.get(city_key, (None, None))

        if valid:
            c.execute(
                "UPDATE hz_party_sites SET validated=1, lat=?, lon=?, updated_at=datetime('now') "
                "WHERE party_site_id=?",
                (lat, lon, site["party_site_id"])
            )
            c.execute(
                "INSERT INTO audit_log(workflow,entity_type,entity_id,action,details) VALUES (?,?,?,?,?)",
                ("ADDRESS_VALIDATION", "HZ_PARTY_SITES", site["party_site_id"],
                 "VALIDATED",
                 json.dumps({"address": site["address_line1"], "city": site["city"],
                             "lat": lat, "lon": lon}))
            )
        else:
            c.execute(
                "UPDATE hz_party_sites SET validated=0, updated_at=datetime('now') "
                "WHERE party_site_id=?",
                (site["party_site_id"],)
            )
            c.execute(
                "INSERT INTO audit_log(workflow,entity_type,entity_id,action,details) VALUES (?,?,?,?,?)",
                ("ADDRESS_VALIDATION", "HZ_PARTY_SITES", site["party_site_id"],
                 "VALIDATION_FAILED",
                 json.dumps({"address": site["address_line1"], "issues": issues}))
            )

        results.append({
            "party_site_id": site["party_site_id"],
            "party_id":      site["party_id"],
            "address":       f"{site['address_line1']}, {site['city']}, {site['state']} {site['postal_code']}, {site['country']}",
            "valid":         valid,
            "issues":        issues,
            "lat":           lat,
            "lon":           lon,
        })

    conn.commit()
    conn.close()

    return {
        "total_checked": len(results),
        "valid":         sum(1 for r in results if r["valid"]),
        "invalid":       sum(1 for r in results if not r["valid"]),
        "results":       results,
    }


def get_unvalidated_addresses() -> dict:
    """Return all unvalidated addresses."""
    conn = get_connection()
    c = conn.cursor()
    rows = c.execute(
        "SELECT ps.*, hp.party_name FROM hz_party_sites ps "
        "JOIN hz_parties hp ON hp.party_id = ps.party_id "
        "WHERE ps.validated = 0"
    ).fetchall()
    conn.close()
    return {
        "count": len(rows),
        "sites": [dict(r) for r in rows],
    }
