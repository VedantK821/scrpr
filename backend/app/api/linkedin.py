from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.scraper.linkedin_session import LinkedInSession
from app.scraper.linkedin_scraper import LinkedInScraper

router = APIRouter()
session = LinkedInSession()


class LinkedInCookieRequest(BaseModel):
    li_at: str


@router.get("/linkedin/status")
async def linkedin_status():
    """Check if LinkedIn session is configured."""
    return {
        "connected": session.has_session(),
        "has_cookie": session.get_li_at_cookie() is not None,
    }


@router.post("/linkedin/connect-cookie")
async def connect_with_cookie(body: LinkedInCookieRequest):
    """Connect LinkedIn by providing the li_at cookie directly."""
    if not body.li_at or len(body.li_at) < 10:
        raise HTTPException(status_code=400, detail="Invalid li_at cookie value")
    await session.set_cookie_direct(body.li_at)
    return {"success": True, "message": "LinkedIn connected via cookie"}


@router.post("/linkedin/connect-browser")
async def connect_with_browser():
    """Open a browser window for interactive LinkedIn login."""
    success = await session.login_interactive()
    if success:
        return {"success": True, "message": "LinkedIn connected via browser login"}
    raise HTTPException(status_code=400, detail="LinkedIn login failed or timed out")


@router.post("/linkedin/disconnect")
async def disconnect():
    """Clear LinkedIn session."""
    session.clear_session()
    return {"success": True, "message": "LinkedIn disconnected"}


@router.post("/linkedin/search")
async def search_linkedin(body: dict):
    """Search LinkedIn for people."""
    query = body.get("query", "")
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")
    scraper = LinkedInScraper()
    results = await scraper.search_people(query, max_results=body.get("max_results", 5))
    return {"results": results}
