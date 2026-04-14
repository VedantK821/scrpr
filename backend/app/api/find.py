import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.table import Table
from app.models.column import Column, ColumnType
from app.models.row import Row
from app.models.cell import Cell, CellStatus
from app.services.list_builder import ListBuilder
from app.services.people_finder import find_people
from app.services.email_verifier_v2 import verify_email, find_and_verify
from app.services.domain_resolver import resolve_domain

router = APIRouter()


class FindRequest(BaseModel):
    criteria: str  # "Top 100 MNCs in India that hire from campus"
    target_count: int = 25
    entity_type: str = "companies"  # "companies" or "people"
    country: str = ""  # "India", "USA", etc. — filters results
    table_name: str | None = None  # Optional — auto-generates if not provided


class FindResponse(BaseModel):
    table_id: str
    table_name: str
    entities_found: int
    fields: list[str]
    stages_completed: list[str] = []


@router.post("/find-stream")
async def find_stream(body: FindRequest):
    """Stream progress stages while building the list."""
    from fastapi.responses import StreamingResponse
    import json as _json

    async def generate():
        builder = ListBuilder()

        yield _json.dumps({"stage": "thinking", "message": "Analyzing your criteria..."}) + "\n"

        entities = await builder._generate_initial_list(body.criteria, body.target_count, body.entity_type)
        yield _json.dumps({"stage": "initial_list", "message": f"Generated initial list of {len(entities)} {body.entity_type}", "count": len(entities)}) + "\n"

        if len(entities) < body.target_count:
            yield _json.dumps({"stage": "searching", "message": "Searching the web for more results..."}) + "\n"
            queries = await builder._generate_search_queries(body.criteria, body.entity_type)
            yield _json.dumps({"stage": "scraping", "message": f"Scraping {len(queries)} search result pages..."}) + "\n"
            web_results = await builder._search_and_scrape(queries)
            if web_results:
                yield _json.dumps({"stage": "expanding", "message": "Cross-referencing web data to expand list..."}) + "\n"
                entities = await builder._expand_list(body.criteria, entities, web_results, body.target_count, body.entity_type)

        yield _json.dumps({"stage": "deduplicating", "message": f"Deduplicating {len(entities)} entries..."}) + "\n"

        # Dedup
        seen = set()
        deduped = []
        for entity in entities:
            name = (entity.get("name") or entity.get("company") or "").lower().strip()
            if name and name not in seen:
                seen.add(name)
                deduped.append(entity)
        entities = deduped[:body.target_count]

        yield _json.dumps({"stage": "done", "message": f"Found {len(entities)} {body.entity_type}", "count": len(entities), "entities": entities}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.post("/find", response_model=FindResponse)
async def find_and_create_table(body: FindRequest, db: AsyncSession = Depends(get_db)):
    """AI-powered list building. Describe what you want, get a populated table."""

    builder = ListBuilder()

    # Build the list — append country to criteria if provided
    criteria = body.criteria
    if body.country:
        criteria = f"{criteria}. COUNTRY FILTER: Only include {body.entity_type} based in or operating in {body.country}."

    result = await builder.build_list(
        criteria=criteria,
        target_count=body.target_count,
        entity_type=body.entity_type,
    )

    entities = result["entities"]
    if not entities:
        raise HTTPException(status_code=404, detail="Could not find any matching entities. Try different criteria.")

    fields = result["fields"]

    # Create table
    table_name = body.table_name or f"{body.entity_type.title()}: {body.criteria[:50]}"
    table = Table(name=table_name)
    db.add(table)
    await db.flush()

    # Create columns from the entity fields
    columns = {}
    for i, field_name in enumerate(fields):
        col = Column(
            table_id=table.id,
            name=field_name.replace("_", " ").title(),
            type=ColumnType.TEXT,
            position=i,
        )
        db.add(col)
        await db.flush()
        columns[field_name] = col

    # Create rows from entities
    for entity in entities:
        row = Row(table_id=table.id)
        db.add(row)
        await db.flush()

        for field_name, col in columns.items():
            value = entity.get(field_name)
            if value:
                cell = Cell(
                    row_id=row.id,
                    column_id=col.id,
                    value=str(value),
                    status=CellStatus.FOUND,
                )
                db.add(cell)

    # Auto-create enrichment columns based on entity type
    # These are the columns the user will "Run" to find people and emails
    next_pos = len(fields)

    if body.entity_type == "companies":
        # For companies: add "Key Contact" (agent) + "Email" (waterfall)
        company_col_name = "Company" if "company" not in fields else "Name" if "name" not in fields else fields[0]

        contact_col = Column(
            table_id=table.id,
            name="Key Contact",
            type=ColumnType.AGENT,
            position=next_pos,
            config={
                "prompt": f"Find the most relevant hiring contact at /{company_col_name.replace('_', ' ').title()}/. "
                          f"Context: {body.criteria[:200]}. "
                          f"Return their full name, title, and LinkedIn URL."
            },
        )
        db.add(contact_col)
        await db.flush()
        next_pos += 1

        email_col = Column(
            table_id=table.id,
            name="Email",
            type=ColumnType.WATERFALL,
            position=next_pos,
            config={
                "prompt": f"Find email for /Key Contact/ at /{company_col_name.replace('_', ' ').title()}/",
                "sources": ["email_pattern", "ai_agent"],
            },
        )
        db.add(email_col)
        await db.flush()

    elif body.entity_type == "people":
        # For people: add "Email" (waterfall) + "Company Info" (agent)
        name_col_name = "Name" if "name" not in fields else "Full Name" if "full_name" not in fields else fields[0]

        email_col = Column(
            table_id=table.id,
            name="Email",
            type=ColumnType.WATERFALL,
            position=next_pos,
            config={
                "prompt": f"Find email for /{name_col_name.replace('_', ' ').title()}/",
                "sources": ["email_pattern", "ai_agent"],
            },
        )
        db.add(email_col)
        await db.flush()

    await db.commit()

    return FindResponse(
        table_id=str(table.id),
        table_name=table_name,
        entities_found=len(entities),
        fields=fields,
    )


# ── Find People at a Company ────────────────────────────────────────


class FindPeopleRequest(BaseModel):
    company: str
    roles: list[str] | None = None
    department: str = ""
    location: str = ""
    count: int = 10
    verify_emails: bool = False


class PersonFound(BaseModel):
    name: str
    title: str = ""
    company: str = ""
    linkedin_url: str = ""
    source: str = ""
    email: str = ""
    email_verified: bool = False
    email_confidence: float = 0.0


class FindPeopleResponse(BaseModel):
    company: str
    domain: str = ""
    people: list[PersonFound]
    total_found: int
    emails_verified: int = 0


@router.post("/find-people", response_model=FindPeopleResponse)
async def find_people_at_company(body: FindPeopleRequest):
    """Find people at a company by role/seniority, optionally verify their emails.

    1. Discovers people via LinkedIn dorks, company websites, web search
    2. Resolves company email domain
    3. Optionally verifies emails using multi-oracle engine
    """
    # Step 1: Find people
    people_raw = await find_people(
        company=body.company,
        roles=body.roles,
        department=body.department,
        location=body.location,
        count=body.count,
    )

    if not people_raw:
        raise HTTPException(status_code=404, detail=f"No people found at {body.company}")

    # Step 2: Resolve domain
    domain = await resolve_domain(body.company)

    # Step 3: Optionally verify emails
    people_out = []
    emails_verified = 0

    for p in people_raw:
        person = PersonFound(
            name=p["name"],
            title=p.get("title", ""),
            company=body.company,
            linkedin_url=p.get("linkedin_url", ""),
            source=p.get("source", ""),
        )

        if body.verify_emails and domain and person.name:
            result = await find_and_verify(
                name=person.name,
                company=body.company,
                domain=domain,
            )
            if result.get("exists"):
                person.email = result["email"]
                person.email_verified = True
                person.email_confidence = result.get("confidence", 0.0)
                emails_verified += 1
            elif result.get("email"):
                person.email = result["email"]
                person.email_confidence = result.get("confidence", 0.0)

        people_out.append(person)

    return FindPeopleResponse(
        company=body.company,
        domain=domain or "",
        people=people_out,
        total_found=len(people_out),
        emails_verified=emails_verified,
    )
