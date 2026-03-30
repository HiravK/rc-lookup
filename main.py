import os
import re
import json
import asyncio
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from mca_scraper import get_director_details_by_din

app = FastAPI(title="RC Lookup API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

IDFY_ACCOUNT_ID = os.environ.get("IDFY_ACCOUNT_ID", "")
IDFY_API_KEY = os.environ.get("IDFY_API_KEY", "")
IDFY_URL = "https://apicentral.idfy.com/verify_with_source/ind_rc_basic"


class RCRequest(BaseModel):
    registration_number: str


def is_company_owner(owner_name: str) -> bool:
    """Heuristic: if owner name contains company-like keywords, treat as company."""
    if not owner_name:
        return False
    company_keywords = [
        "pvt", "private", "ltd", "limited", "llp", "llc", "inc", "corp",
        "corporation", "enterprises", "solutions", "services", "technologies",
        "industries", "company", "co.", "holdings", "ventures", "group",
        "associates", "consultants", "trading", "leasing", "finance",
    ]
    name_lower = owner_name.lower()
    return any(kw in name_lower for kw in company_keywords)


def extract_cin_from_name(owner_name: str) -> Optional[str]:
    """Try to extract CIN pattern from owner name if present."""
    cin_pattern = r'[A-Z]{1}[0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}'
    match = re.search(cin_pattern, owner_name.upper())
    return match.group(0) if match else None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/lookup")
async def lookup_rc(req: RCRequest):
    reg_no = req.registration_number.strip().upper().replace(" ", "")

    if not reg_no:
        raise HTTPException(status_code=400, detail="Registration number is required")

    headers = {
        "account_id": IDFY_ACCOUNT_ID,
        "api_key": IDFY_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "id": "rc_lookup_001",
        "task": {
            "registration_number": reg_no
        }
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(IDFY_URL, headers=headers, json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"iDfy API error: {e.response.text}"
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Network error: {str(e)}")

    data = resp.json()

    # Extract vehicle info
    result = data.get("result", {})
    vehicle_info = {
        "registration_number": reg_no,
        "owner_name": result.get("owner_name", ""),
        "vehicle_class": result.get("vehicle_class", ""),
        "maker_model": result.get("maker_model", ""),
        "maker_description": result.get("maker_description", ""),
        "fuel_type": result.get("fuel_type", ""),
        "color": result.get("color", ""),
        "chassis_number": result.get("chassis_number", ""),
        "engine_number": result.get("engine_number", ""),
        "registration_date": result.get("registration_date", ""),
        "registration_validity": result.get("registration_validity", ""),
        "fitness_upto": result.get("fitness_upto", ""),
        "insurance_validity": result.get("insurance_validity", ""),
        "insurance_company": result.get("insurance_company", ""),
        "pucc_validity": result.get("pucc_validity", ""),
        "financer": result.get("financer", ""),
        "state": result.get("state", ""),
        "rto_code": result.get("rto_code", ""),
        "raw": result,
    }

    owner_name = vehicle_info["owner_name"]
    is_company = is_company_owner(owner_name)
    directors = []

    if is_company:
        cin = extract_cin_from_name(owner_name)
        directors = await get_director_details_by_din(owner_name, cin)

    return {
        "success": True,
        "vehicle": vehicle_info,
        "is_company_vehicle": is_company,
        "directors": directors,
    }
