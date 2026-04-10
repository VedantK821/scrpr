import pytest
from app.workers.scrape_worker import render_prompt


class TestRenderPrompt:
    def test_replaces_single_variable(self):
        prompt = "Find email for /Name/"
        row_data = {"Name": "Alice Smith"}
        assert render_prompt(prompt, row_data) == "Find email for Alice Smith"

    def test_replaces_multiple_variables(self):
        prompt = "Find /Key Contact/ at /Company/"
        row_data = {"Key Contact": "Bob Jones", "Company": "TCS"}
        assert render_prompt(prompt, row_data) == "Find Bob Jones at TCS"

    def test_missing_variable_left_as_is(self):
        prompt = "Find /Unknown Column/"
        row_data = {"Name": "Alice"}
        assert render_prompt(prompt, row_data) == "Find /Unknown Column/"

    def test_empty_row_data_leaves_prompt_unchanged(self):
        prompt = "Find /Name/ at /Company/"
        assert render_prompt(prompt, {}) == "Find /Name/ at /Company/"

    def test_no_variables_returns_prompt_unchanged(self):
        prompt = "Just a plain prompt with no variables"
        row_data = {"Name": "Alice"}
        assert render_prompt(prompt, row_data) == "Just a plain prompt with no variables"

    def test_case_sensitive_matching(self):
        prompt = "Find /company/"
        row_data = {"Company": "TCS", "company": "infosys"}
        assert render_prompt(prompt, row_data) == "Find infosys"
