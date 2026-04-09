import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_table(client: AsyncClient, name: str = "EmailTest") -> str:
    resp = await client.post("/api/tables", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_column(client: AsyncClient, table_id: str, name: str = "Email", col_type: str = "text") -> str:
    resp = await client.post(f"/api/tables/{table_id}/columns", json={"name": name, "type": col_type, "position": 0})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_row(client: AsyncClient, table_id: str, col_id: str, value: str) -> tuple[str, str]:
    resp = await client.post(f"/api/tables/{table_id}/rows", json={"cells": {col_id: value}})
    assert resp.status_code == 201
    data = resp.json()
    return data["id"], data["cells"][0]["id"]


# ---------------------------------------------------------------------------
# POST /emails/compose
# ---------------------------------------------------------------------------

class TestComposeEmails:
    @pytest.mark.asyncio
    async def test_compose_creates_draft_for_row_with_email(self, client: AsyncClient):
        """compose endpoint creates a draft when a row has a cell with an email address."""
        table_id = await _create_table(client, "ComposeBasic")
        col_id = await _create_column(client, table_id, "Email")
        await _create_row(client, table_id, col_id, "alice@example.com")

        resp = await client.post("/api/emails/compose", json={
            "table_id": table_id,
            "subject_template": "Hi there",
            "body_template": "Hello from Scrpr.",
            "personalization_level": "light",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["to_email"] == "alice@example.com"
        assert data[0]["status"] == "personalized"
        assert data[0]["subject"] == "Hi there"

    @pytest.mark.asyncio
    async def test_compose_skips_rows_without_email(self, client: AsyncClient):
        """Rows that have no cell value containing '@' are skipped."""
        table_id = await _create_table(client, "ComposeSkipNoEmail")
        col_id = await _create_column(client, table_id, "Name")
        await _create_row(client, table_id, col_id, "John Doe")  # no email

        resp = await client.post("/api/emails/compose", json={
            "table_id": table_id,
            "subject_template": "Hi /Name/",
            "body_template": "Hello /Name/.",
            "personalization_level": "light",
        })

        # No drafts created — but endpoint returns 200 with empty list
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_compose_returns_404_when_no_rows(self, client: AsyncClient):
        """404 when table exists but has no rows."""
        table_id = await _create_table(client, "ComposeNoRows")

        resp = await client.post("/api/emails/compose", json={
            "table_id": table_id,
            "subject_template": "Hi",
            "body_template": "Body",
            "personalization_level": "light",
        })

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_compose_substitutes_variables(self, client: AsyncClient):
        """Subject and body variables /ColName/ are replaced with cell values."""
        table_id = await _create_table(client, "ComposeVars")
        name_col = await _create_column(client, table_id, "Name")
        email_col = await _create_column(client, table_id, "Email")

        # Create a row with both Name and Email cells
        resp = await client.post(f"/api/tables/{table_id}/rows", json={
            "cells": {name_col: "Bob", email_col: "bob@example.com"}
        })
        assert resp.status_code == 201

        resp = await client.post("/api/emails/compose", json={
            "table_id": table_id,
            "subject_template": "Hi /Name/",
            "body_template": "Dear /Name/, we'd love to connect.",
            "personalization_level": "light",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["subject"] == "Hi Bob"
        assert "Bob" in data[0]["body"]

    @pytest.mark.asyncio
    async def test_compose_with_row_ids_filter(self, client: AsyncClient):
        """When row_ids is provided, only those rows are composed."""
        table_id = await _create_table(client, "ComposeFilter")
        col_id = await _create_column(client, table_id, "Email")
        row1_id, _ = await _create_row(client, table_id, col_id, "a@example.com")
        row2_id, _ = await _create_row(client, table_id, col_id, "b@example.com")

        resp = await client.post("/api/emails/compose", json={
            "table_id": table_id,
            "subject_template": "Hi",
            "body_template": "Body",
            "personalization_level": "light",
            "row_ids": [row1_id],
        })

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["to_email"] == "a@example.com"

    @pytest.mark.asyncio
    async def test_compose_max_level_calls_ai(self, client: AsyncClient):
        """personalization_level=max triggers AI personalization."""
        table_id = await _create_table(client, "ComposeMax")
        col_id = await _create_column(client, table_id, "Email")
        await _create_row(client, table_id, col_id, "carol@example.com")

        with patch("app.services.email_composer.LLMRouter") as MockLLM:
            instance = MockLLM.return_value
            instance.complete = AsyncMock(return_value="AI-crafted body text")

            resp = await client.post("/api/emails/compose", json={
                "table_id": table_id,
                "subject_template": "Hi there",
                "body_template": "Default body",
                "personalization_level": "max",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["body"] == "AI-crafted body text"
        assert data[0]["confidence"] == 0.85


# ---------------------------------------------------------------------------
# GET /emails/drafts/{table_id}
# ---------------------------------------------------------------------------

class TestListDrafts:
    @pytest.mark.asyncio
    async def test_list_drafts_returns_created_drafts(self, client: AsyncClient):
        """GET /emails/drafts/{table_id} returns the drafts created by compose."""
        table_id = await _create_table(client, "ListDrafts")
        col_id = await _create_column(client, table_id, "Email")
        await _create_row(client, table_id, col_id, "dave@example.com")

        await client.post("/api/emails/compose", json={
            "table_id": table_id,
            "subject_template": "Hello",
            "body_template": "Hi there.",
            "personalization_level": "light",
        })

        resp = await client.get(f"/api/emails/drafts/{table_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["to_email"] == "dave@example.com"

    @pytest.mark.asyncio
    async def test_list_drafts_empty_for_new_table(self, client: AsyncClient):
        """GET drafts for a table with no drafts returns empty list."""
        table_id = await _create_table(client, "EmptyDrafts")
        resp = await client.get(f"/api/emails/drafts/{table_id}")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_drafts_only_returns_table_drafts(self, client: AsyncClient):
        """Drafts from one table don't appear in another table's list."""
        table1_id = await _create_table(client, "TableDrafts1")
        table2_id = await _create_table(client, "TableDrafts2")
        col1_id = await _create_column(client, table1_id, "Email")
        await _create_row(client, table1_id, col1_id, "e@example.com")

        await client.post("/api/emails/compose", json={
            "table_id": table1_id,
            "subject_template": "Hi",
            "body_template": "Body",
            "personalization_level": "light",
        })

        resp = await client.get(f"/api/emails/drafts/{table2_id}")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# PATCH /emails/drafts/{draft_id}
# ---------------------------------------------------------------------------

class TestUpdateDraft:
    @pytest.mark.asyncio
    async def test_update_subject_and_body(self, client: AsyncClient):
        """PATCH can update subject and body of a draft."""
        table_id = await _create_table(client, "UpdateDraft")
        col_id = await _create_column(client, table_id, "Email")
        await _create_row(client, table_id, col_id, "frank@example.com")

        compose_resp = await client.post("/api/emails/compose", json={
            "table_id": table_id,
            "subject_template": "Original Subject",
            "body_template": "Original Body",
            "personalization_level": "light",
        })
        draft_id = compose_resp.json()[0]["id"]

        patch_resp = await client.patch(f"/api/emails/drafts/{draft_id}", json={
            "subject": "Updated Subject",
            "body": "Updated Body",
        })
        assert patch_resp.status_code == 200
        assert patch_resp.json() == {"ok": True}

        # Verify via list
        drafts = await client.get(f"/api/emails/drafts/{table_id}")
        draft = drafts.json()[0]
        assert draft["subject"] == "Updated Subject"
        assert draft["body"] == "Updated Body"

    @pytest.mark.asyncio
    async def test_update_status_to_skipped(self, client: AsyncClient):
        """PATCH can update status to 'skipped'."""
        table_id = await _create_table(client, "SkipDraft")
        col_id = await _create_column(client, table_id, "Email")
        await _create_row(client, table_id, col_id, "grace@example.com")

        compose_resp = await client.post("/api/emails/compose", json={
            "table_id": table_id,
            "subject_template": "Hi",
            "body_template": "Body",
            "personalization_level": "light",
        })
        draft_id = compose_resp.json()[0]["id"]

        patch_resp = await client.patch(f"/api/emails/drafts/{draft_id}", json={"status": "skipped"})
        assert patch_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_draft_not_found_returns_404(self, client: AsyncClient):
        """PATCH on non-existent draft returns 404."""
        resp = await client.patch(
            "/api/emails/drafts/00000000-0000-0000-0000-000000000000",
            json={"subject": "x"}
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /emails/send
# ---------------------------------------------------------------------------

class TestSendEmails:
    @pytest.mark.asyncio
    async def test_send_marks_draft_as_sent(self, client: AsyncClient):
        """POST /emails/send with mocked EmailSender marks drafts sent."""
        table_id = await _create_table(client, "SendTest")
        col_id = await _create_column(client, table_id, "Email")
        await _create_row(client, table_id, col_id, "henry@example.com")

        compose_resp = await client.post("/api/emails/compose", json={
            "table_id": table_id,
            "subject_template": "Hi",
            "body_template": "Body",
            "personalization_level": "light",
        })
        draft_id = compose_resp.json()[0]["id"]

        from app.services.email_sender import SendResult
        with patch("app.api.emails.EmailSender") as MockSender:
            instance = MockSender.return_value
            instance.send = AsyncMock(return_value=SendResult(success=True))

            resp = await client.post("/api/emails/send", json={
                "draft_ids": [draft_id],
                "delay_seconds": 0.0,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["sent"] == 1
        assert data["failed"] == 0

    @pytest.mark.asyncio
    async def test_send_marks_draft_as_failed_on_error(self, client: AsyncClient):
        """POST /emails/send marks draft as failed when sender returns error."""
        table_id = await _create_table(client, "SendFail")
        col_id = await _create_column(client, table_id, "Email")
        await _create_row(client, table_id, col_id, "irene@example.com")

        compose_resp = await client.post("/api/emails/compose", json={
            "table_id": table_id,
            "subject_template": "Hi",
            "body_template": "Body",
            "personalization_level": "light",
        })
        draft_id = compose_resp.json()[0]["id"]

        from app.services.email_sender import SendResult
        with patch("app.api.emails.EmailSender") as MockSender:
            instance = MockSender.return_value
            instance.send = AsyncMock(return_value=SendResult(success=False, error="SMTP not configured"))

            resp = await client.post("/api/emails/send", json={
                "draft_ids": [draft_id],
                "delay_seconds": 0.0,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["sent"] == 0
        assert data["failed"] == 1
        assert data["results"][0]["error"] == "SMTP not configured"

    @pytest.mark.asyncio
    async def test_send_skips_skipped_drafts(self, client: AsyncClient):
        """Drafts with status=skipped are not sent."""
        table_id = await _create_table(client, "SendSkipped")
        col_id = await _create_column(client, table_id, "Email")
        await _create_row(client, table_id, col_id, "jake@example.com")

        compose_resp = await client.post("/api/emails/compose", json={
            "table_id": table_id,
            "subject_template": "Hi",
            "body_template": "Body",
            "personalization_level": "light",
        })
        draft_id = compose_resp.json()[0]["id"]

        # Mark as skipped
        await client.patch(f"/api/emails/drafts/{draft_id}", json={"status": "skipped"})

        from app.services.email_sender import SendResult
        with patch("app.api.emails.EmailSender") as MockSender:
            instance = MockSender.return_value
            instance.send = AsyncMock(return_value=SendResult(success=True))

            resp = await client.post("/api/emails/send", json={
                "draft_ids": [draft_id],
                "delay_seconds": 0.0,
            })

        data = resp.json()
        assert data["sent"] == 0
        assert data["failed"] == 0
        # send was never called since the draft was skipped
        instance.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_marks_bounced_on_bounce_error(self, client: AsyncClient):
        """If error contains 'bounced', status is set to BOUNCED."""
        table_id = await _create_table(client, "SendBounced")
        col_id = await _create_column(client, table_id, "Email")
        await _create_row(client, table_id, col_id, "kate@example.com")

        compose_resp = await client.post("/api/emails/compose", json={
            "table_id": table_id,
            "subject_template": "Hi",
            "body_template": "Body",
            "personalization_level": "light",
        })
        draft_id = compose_resp.json()[0]["id"]

        from app.services.email_sender import SendResult
        with patch("app.api.emails.EmailSender") as MockSender:
            instance = MockSender.return_value
            instance.send = AsyncMock(return_value=SendResult(success=False, error="Recipient refused (bounced)"))

            resp = await client.post("/api/emails/send", json={
                "draft_ids": [draft_id],
                "delay_seconds": 0.0,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["failed"] == 1
        assert "bounced" in data["results"][0]["error"].lower()
