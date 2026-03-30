"""
MCA21 portal scraper for director details.
Scrapes https://www.mca.gov.in/mcafoportal/companyLLPMasterData.do
and DIN-based director info pages.
"""

import re
import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import Optional
import logging

logger = logging.getLogger(__name__)

MCA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.mca.gov.in/",
}

MCA_COMPANY_SEARCH = "https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do"
MCA_DIN_SEARCH = "https://www.mca.gov.in/mcafoportal/viewDINStatus.do"


async def search_company_on_mca(company_name: str, cin: Optional[str], client: httpx.AsyncClient) -> list[dict]:
    """Search MCA for company and return list of directors with DINs."""
    directors = []

    try:
        # Try CIN-based search first if available
        if cin:
            params = {"companyID": cin}
        else:
            # Clean company name for search
            clean_name = re.sub(
                r'\b(pvt|private|ltd|limited|llp|llc|inc|corp)\b', '',
                company_name, flags=re.IGNORECASE
            ).strip()
            params = {"companyName": clean_name[:50]}

        resp = await client.get(
            MCA_COMPANY_SEARCH,
            params=params,
            headers=MCA_HEADERS,
            timeout=20.0,
            follow_redirects=True,
        )

        if resp.status_code != 200:
            logger.warning(f"MCA company search returned {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # Parse director table — MCA renders a table with DIN and name columns
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                # Look for rows that contain a DIN (8-digit number)
                row_text = " ".join(c.get_text(strip=True) for c in cols)
                din_match = re.search(r'\b(\d{8})\b', row_text)
                if din_match and len(cols) >= 2:
                    din = din_match.group(1)
                    # Try to identify name column (non-numeric, longer text)
                    name = ""
                    for col in cols:
                        txt = col.get_text(strip=True)
                        if txt and not txt.isdigit() and len(txt) > 3 and not re.match(r'^\d{8}$', txt):
                            name = txt
                            break
                    if din and name:
                        directors.append({"din": din, "name": name})

    except Exception as e:
        logger.error(f"MCA company search error: {e}")

    return directors


async def get_director_info_by_din(din: str, client: httpx.AsyncClient) -> dict:
    """Fetch director details from MCA DIN lookup."""
    info = {"din": din, "name": "", "email": "", "phone": "", "address": "", "status": ""}

    try:
        resp = await client.get(
            MCA_DIN_SEARCH,
            params={"dinNo": din},
            headers=MCA_HEADERS,
            timeout=20.0,
            follow_redirects=True,
        )

        if resp.status_code != 200:
            return info

        soup = BeautifulSoup(resp.text, "html.parser")

        # MCA renders key-value pairs in table rows
        rows = soup.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 2:
                label = cols[0].get_text(strip=True).lower()
                value = cols[1].get_text(strip=True)

                if "name" in label and not info["name"]:
                    info["name"] = value
                elif "email" in label:
                    info["email"] = value
                elif "phone" in label or "mobile" in label:
                    info["phone"] = value
                elif "address" in label and not info["address"]:
                    info["address"] = value
                elif "status" in label:
                    info["status"] = value

    except Exception as e:
        logger.error(f"DIN lookup error for {din}: {e}")

    return info


async def get_director_details_by_din(company_name: str, cin: Optional[str]) -> list[dict]:
    """
    Main entry: given a company name (and optional CIN),
    1. Search MCA for the company to get directors + DINs
    2. For each DIN, fetch director contact details
    Returns list of director dicts.
    """
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        verify=False,  # MCA portal has cert issues sometimes
    ) as client:
        # Step 1: get directors list
        directors = await search_company_on_mca(company_name, cin, client)

        if not directors:
            # Return a minimal entry indicating we found a company but couldn't get directors
            return [{
                "din": "N/A",
                "name": company_name,
                "email": "",
                "phone": "",
                "address": "",
                "status": "MCA lookup returned no results",
                "note": "Try searching manually at mca.gov.in",
            }]

        # Step 2: enrich each director with DIN details (parallel)
        tasks = [get_director_info_by_din(d["din"], client) for d in directors]
        enriched = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for i, director in enumerate(directors):
            base = {"din": director["din"], "name": director["name"], "email": "", "phone": "", "address": "", "status": ""}
            if isinstance(enriched[i], dict):
                base.update({k: v for k, v in enriched[i].items() if v})
            results.append(base)

        return results
