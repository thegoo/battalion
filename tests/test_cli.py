import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from battalion.assurance import assure
from battalion.cli import main
from battalion.mission_analyst import generate_mission_contract
from battalion.models import AssuranceResult
from battalion.storage import read_yaml, write_yaml


class BattalionCliTests(unittest.TestCase):
    CONSTRAINT_PROMPT = (
        "Build a TypeScript Node REST API running in Docker with a health endpoint. "
        "Allow GET requests only. Follow OWASP guidance. "
        "Create happy-path, negative-path, and malicious-request tests."
    )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    @property
    def workspace(self):
        return self.cwd / ".battalion"

    @property
    def ledger_path(self):
        return self.workspace / "ledger.yaml"

    def run_cli(self, *args):
        output = StringIO()
        with redirect_stdout(output):
            main(list(args), self.cwd)
        return output.getvalue()

    def initialize(self):
        self.run_cli(
            "init",
            "--title", "JWT Auth",
            "--objective", "Add secure JWT auth",
            "--prompt", "Build JWT authentication.",
        )

    def initialize_with_prompt(self, prompt):
        self.run_cli("init", "--title", "Constraint Mission", "--prompt", prompt)

    def plan_contract(self, acceptance=True, reviews=True):
        args = ["plan", "--requirement", "Validate JWT issuer"]
        if acceptance:
            args.extend(["--acceptance", "Unknown issuers are rejected"])
        if reviews:
            args.extend(["--review", "architect", "--review", "secops", "--review", "tester"])
        self.run_cli(*args)

    def satisfy_requirement(self):
        evidence = self.cwd / "evidence" / "jwt-tests.txt"
        evidence.parent.mkdir()
        evidence.write_text("test_rejects_unknown_issuer: passed\n", encoding="utf-8")
        ledger = read_yaml(self.ledger_path)
        requirement = ledger["requirements"][0]
        requirement["status"] = "completed"
        requirement["evidence"] = ["evidence/jwt-tests.txt"]
        for review in requirement["required_reviews"]:
            review["status"] = "completed"
        write_yaml(self.ledger_path, ledger)

    def result(self):
        return assure(self.workspace)

    def test_init_creates_workspace_and_original_prompt(self):
        self.initialize()
        for name in ("mission.yaml", "agents.yaml", "ledger.yaml", "events.jsonl", "reports"):
            self.assertTrue((self.workspace / name).exists())
        self.assertEqual(read_yaml(self.workspace / "mission.yaml")["original_prompt"], "Build JWT authentication.")
        self.assertEqual(len(read_yaml(self.workspace / "agents.yaml")["agents"]), 9)

    def test_console_entry_point_is_registered(self):
        repository = Path(__file__).resolve().parents[1]
        pyproject = (repository / "pyproject.toml").read_text(encoding="utf-8")
        setup_compatibility = (repository / "setup.py").read_text(encoding="utf-8")
        self.assertIn('battalion = "battalion.cli:main"', pyproject)
        self.assertIn('"battalion=battalion.cli:main"', setup_compatibility)

    def test_cli_help_executes_successfully(self):
        output = StringIO()
        with self.assertRaises(SystemExit) as raised, redirect_stdout(output):
            main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("Battalion v0.1.4", output.getvalue())

    def test_interactive_init_captures_and_stores_mission_prompt(self):
        mission_prompt = "Build a hello world REST API."
        with patch("battalion.cli.sys.stdin.isatty", return_value=True), patch("builtins.input", return_value=mission_prompt):
            self.run_cli("init")
        mission = read_yaml(self.workspace / "mission.yaml")
        ledger = read_yaml(self.ledger_path)
        self.assertEqual(mission["mission_prompt"], mission_prompt)
        self.assertEqual(mission["objective"], mission_prompt)
        self.assertEqual(ledger["mission_prompt"], mission_prompt)

    def test_mission_analyst_generates_requirements(self):
        self.initialize()
        output = self.run_cli("plan")
        ledger = read_yaml(self.ledger_path)
        self.assertEqual(ledger["generated_by"], "mission_analyst")
        self.assertGreaterEqual(len(ledger["requirements"]), 4)
        self.assertEqual(
            [requirement["id"] for requirement in ledger["requirements"]],
            [f"R-{index:03d}" for index in range(1, len(ledger["requirements"]) + 1)],
        )
        self.assertIn("Mission Analyst generated the mission contract", output)

    def test_mission_analyst_generation_is_deterministic(self):
        prompt = "Build a hello world REST API."
        self.assertEqual(
            generate_mission_contract("M-001", prompt),
            generate_mission_contract("M-001", prompt),
        )

    def test_generated_requirements_have_acceptance_criteria(self):
        self.initialize()
        self.run_cli("plan")
        requirements = read_yaml(self.ledger_path)["requirements"]
        self.assertTrue(all(requirement["acceptance"] for requirement in requirements))
        self.assertTrue(all(all(criterion.strip() for criterion in requirement["acceptance"]) for requirement in requirements))

    def test_mission_analyst_generates_assumptions_and_risks(self):
        self.initialize()
        self.run_cli("plan")
        ledger = read_yaml(self.ledger_path)
        self.assertEqual([item["id"] for item in ledger["assumptions"]], ["A-001"])
        self.assertTrue(ledger["risks"])
        self.assertEqual([item["id"] for item in ledger["risks"]], [f"RISK-{index:03d}" for index in range(1, len(ledger["risks"]) + 1)])
        self.assertTrue(all(item["statement"] for item in ledger["assumptions"] + ledger["risks"]))

    def test_technology_constraints_are_extracted(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("plan")
        ledger = read_yaml(self.ledger_path)
        statements = [item["statement"] for item in ledger["constraints"]["technical"]]
        self.assertEqual(statements, ["TypeScript is required.", "Node.js is required.", "Docker packaging is required."])
        requirement_statements = [item["statement"] for item in ledger["requirements"]]
        self.assertIn("Create TypeScript Node application", requirement_statements)
        self.assertIn("Containerize application with Docker", requirement_statements)

    def test_security_constraints_are_extracted(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("plan")
        ledger = read_yaml(self.ledger_path)
        security = [item["statement"] for item in ledger["constraints"]["security"]]
        self.assertIn("Only GET requests are permitted.", security)
        self.assertIn("Error handling must follow OWASP guidance.", security)
        requirements = {item["statement"]: item for item in ledger["requirements"]}
        self.assertIn("Enforce GET-only endpoint behavior", requirements)
        self.assertIn("Implement secure error handling", requirements)
        self.assertIn("POST requests are rejected", requirements["Enforce GET-only endpoint behavior"]["acceptance"])

    def test_explicit_testing_constraints_generate_test_acceptance(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("plan")
        ledger = read_yaml(self.ledger_path)
        testing = [item["statement"] for item in ledger["constraints"]["testing"]]
        self.assertEqual(testing, [
            "Happy-path tests are required.",
            "Negative-path tests are required.",
            "Malicious-request tests are required.",
        ])
        test_requirement = next(item for item in ledger["requirements"] if item["statement"] == "Create automated tests")
        self.assertTrue(any("Happy-path" in criterion for criterion in test_requirement["acceptance"]))
        self.assertTrue(any("Negative-path" in criterion for criterion in test_requirement["acceptance"]))
        self.assertTrue(any("Malicious-request" in criterion for criterion in test_requirement["acceptance"]))

    def test_prompt_traceability_is_generated_for_every_requirement(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("plan")
        ledger = read_yaml(self.ledger_path)
        constraint_ids = {
            item["id"]
            for values in ledger["constraints"].values()
            for item in values
        }
        for requirement in ledger["requirements"]:
            trace = requirement["traceability"]
            self.assertEqual(trace["source"], "mission_prompt")
            self.assertIn(trace["prompt_excerpt"], self.CONSTRAINT_PROMPT)
            self.assertTrue(trace["rationale"])
            self.assertTrue(set(trace["constraint_ids"]).issubset(constraint_ids))

    def test_missing_information_generates_clarifications_not_framework_assumptions(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("plan")
        ledger = read_yaml(self.ledger_path)
        questions = [item["question"] for item in ledger["clarifications"]]
        self.assertIn("What endpoint path should be used?", questions)
        self.assertIn("What application framework should be used?", questions)
        self.assertIn("What timestamp format should be returned?", questions)
        self.assertTrue(all(item["status"] == "open" for item in ledger["clarifications"]))
        self.assertFalse(any("Express" in item["statement"] for item in ledger["assumptions"]))

    def test_mission_prompt_remains_immutable_during_contract_generation(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        before = (self.workspace / "mission.yaml").read_bytes()
        self.run_cli("plan")
        self.run_cli("dispatch")
        self.run_cli("report")
        after = (self.workspace / "mission.yaml").read_bytes()
        self.assertEqual(before, after)
        self.assertEqual(read_yaml(self.ledger_path)["mission_prompt"], self.CONSTRAINT_PROMPT)

    def test_assurance_validates_trace_links_and_reports_open_clarifications(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("plan")
        result = self.result()
        self.assertEqual((result.status, result.recommendation), ("AMBER", "NO-GO"))
        self.assertTrue(any("Q-001 remains open" in finding for finding in result.findings))
        ledger = read_yaml(self.ledger_path)
        ledger["requirements"][0]["traceability"]["prompt_excerpt"] = "Text not present in the mission prompt"
        write_yaml(self.ledger_path, ledger)
        result = self.result()
        self.assertEqual(result.status, "RED")
        self.assertTrue(any("does not occur in the authoritative mission prompt" in finding for finding in result.findings))

    def test_completed_traceable_generated_contract_can_reach_green(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("plan")
        evidence = self.cwd / "evidence" / "mission-validation.txt"
        evidence.parent.mkdir()
        evidence.write_text("All prompt-derived requirements validated.\n", encoding="utf-8")
        ledger = read_yaml(self.ledger_path)
        for requirement in ledger["requirements"]:
            requirement["status"] = "completed"
            requirement["evidence"] = ["evidence/mission-validation.txt"]
            for review in requirement["required_reviews"]:
                review["status"] = "completed"
        for clarification in ledger["clarifications"]:
            clarification["status"] = "resolved"
        write_yaml(self.ledger_path, ledger)
        result = self.result()
        self.assertEqual((result.status, result.recommendation, result.confidence), ("GREEN", "GO", 100))

    def test_mission_analyst_generates_explainable_review_assignments(self):
        self.initialize()
        self.run_cli("plan")
        requirements = read_yaml(self.ledger_path)["requirements"]
        for requirement in requirements:
            self.assertTrue(requirement["required_reviews"])
            for review in requirement["required_reviews"]:
                self.assertEqual(review["status"], "pending")
                self.assertTrue(review["reason"])

    def test_generated_mission_contract_is_traceable_to_prompt(self):
        self.initialize()
        self.run_cli("plan")
        mission = read_yaml(self.workspace / "mission.yaml")
        ledger = read_yaml(self.ledger_path)
        self.assertEqual(ledger["mission_id"], mission["id"])
        self.assertEqual(ledger["mission_prompt"], mission["mission_prompt"])
        event_types = [json.loads(line)["type"] for line in (self.workspace / "events.jsonl").read_text().splitlines()]
        self.assertIn("mission_contract_generated", event_types)

    def test_generated_contract_is_visible_in_mission_report(self):
        self.initialize()
        self.run_cli("plan")
        self.run_cli("report")
        report = (self.workspace / "reports" / "mission-report.md").read_text(encoding="utf-8")
        self.assertIn("**Generated by:** mission_analyst", report)
        self.assertIn("A-001:", report)
        self.assertIn("RISK-001:", report)
        self.assertIn("## Extracted Constraints", report)
        self.assertIn("## Clarifications", report)
        self.assertIn("## Prompt Traceability", report)
        self.assertIn("Required Reviews", report)
        self.assertIn("Required review is pending", report)

    def test_assurance_consumes_generated_contract_as_incomplete_not_malformed(self):
        self.initialize()
        self.run_cli("plan")
        self.run_cli("dispatch")
        result = self.result()
        self.assertEqual((result.status, result.recommendation), ("AMBER", "NO-GO"))
        self.assertTrue(any("Mission work remains open" in finding for finding in result.findings))
        self.assertTrue(any("Required review is pending" in finding for finding in result.findings))
        self.assertFalse(any("Missing" in finding or "invalid" in finding.lower() for finding in result.findings))

    def test_missing_mission_has_friendly_error_for_every_mission_command(self):
        expected = (
            "Current directory does not contain a Battalion mission.\n\n"
            "Run:\n\n  battalion init\n\n"
            "or navigate to a directory containing .battalion"
        )
        commands = (
            ["plan", "--requirement", "Example"],
            ["dispatch"],
            ["assure"],
            ["report"],
        )
        for command in commands:
            with self.subTest(command=command[0]), self.assertRaises(SystemExit) as raised:
                main(command, self.cwd)
            self.assertEqual(str(raised.exception), expected)
            self.assertNotIn("Traceback", str(raised.exception))

    def test_commands_discover_mission_from_process_current_directory(self):
        original_directory = Path.cwd()
        outside_repository = self.cwd / "arbitrary" / "hello-world"
        outside_repository.mkdir(parents=True)
        try:
            os.chdir(outside_repository)
            assurance_output = StringIO()
            with redirect_stdout(assurance_output):
                main(["init", "--objective", "Portable mission", "--prompt", "Portable mission"])
                main([
                    "plan", "--requirement", "Run anywhere",
                    "--acceptance", "CLI uses the current directory",
                    "--review", "architect",
                ])
                main(["dispatch"])
                main(["assure"])
                main(["report"])
        finally:
            os.chdir(original_directory)
        self.assertTrue((outside_repository / ".battalion" / "mission.yaml").is_file())
        self.assertTrue((outside_repository / ".battalion" / "reports" / "mission-report.md").is_file())
        self.assertIn("Status: AMBER", assurance_output.getvalue())

    def test_plan_creates_contract_and_dispatch_updates_audit(self):
        self.initialize()
        self.plan_contract()
        self.run_cli("dispatch")
        requirement = read_yaml(self.ledger_path)["requirements"][0]
        self.assertEqual((requirement["id"], requirement["status"]), ("R-001", "planned"))
        self.assertEqual(requirement["acceptance"], ["Unknown issuers are rejected"])
        self.assertEqual([review["status"] for review in requirement["required_reviews"]], ["pending"] * 3)
        events = [json.loads(line)["type"] for line in (self.workspace / "events.jsonl").read_text().splitlines()]
        self.assertIn("requirement_added", events)
        self.assertIn("plan_created", events)
        self.assertIn("dispatch_simulated", events)

    def test_open_valid_contract_is_amber_no_go(self):
        self.initialize()
        self.plan_contract()
        result = self.result()
        self.assertEqual((result.status, result.recommendation), ("AMBER", "NO-GO"))
        self.assertTrue(any("Mission work remains open" in finding for finding in result.findings))
        self.assertTrue(any("Required review is pending" in finding for finding in result.findings))

    def test_green_cannot_occur_without_evidence(self):
        self.initialize()
        self.plan_contract()
        self.satisfy_requirement()
        ledger = read_yaml(self.ledger_path)
        ledger["requirements"][0]["evidence"] = []
        write_yaml(self.ledger_path, ledger)
        result = self.result()
        self.assertEqual((result.status, result.recommendation), ("RED", "NO-GO"))
        self.assertIn("R-001: Completed without evidence", result.findings)

    def test_green_cannot_occur_without_acceptance_criteria(self):
        self.initialize()
        self.plan_contract(acceptance=False)
        self.satisfy_requirement()
        result = self.result()
        self.assertEqual((result.status, result.recommendation), ("RED", "NO-GO"))
        self.assertTrue(any("acceptance criteria" in finding.lower() for finding in result.findings))

    def test_green_cannot_occur_without_required_reviews(self):
        self.initialize()
        self.plan_contract(reviews=False)
        evidence = self.cwd / "evidence.txt"
        evidence.write_text("passed\n", encoding="utf-8")
        ledger = read_yaml(self.ledger_path)
        ledger["requirements"][0].update(status="completed", evidence=["evidence.txt"])
        write_yaml(self.ledger_path, ledger)
        result = self.result()
        self.assertEqual((result.status, result.recommendation), ("RED", "NO-GO"))
        self.assertIn("R-001: Missing required reviews", result.findings)

    def test_pending_review_prevents_green(self):
        self.initialize()
        self.plan_contract()
        self.satisfy_requirement()
        ledger = read_yaml(self.ledger_path)
        ledger["requirements"][0]["required_reviews"][1]["status"] = "pending"
        write_yaml(self.ledger_path, ledger)
        result = self.result()
        self.assertEqual((result.status, result.recommendation), ("AMBER", "NO-GO"))
        self.assertIn("R-001: Required review is pending: secops", result.findings)

    def test_nonexistent_evidence_is_red(self):
        self.initialize()
        self.plan_contract()
        self.satisfy_requirement()
        ledger = read_yaml(self.ledger_path)
        ledger["requirements"][0]["evidence"] = ["evidence/not-there.txt"]
        write_yaml(self.ledger_path, ledger)
        result = self.result()
        self.assertEqual(result.status, "RED")
        self.assertIn("R-001: Evidence file does not exist: evidence/not-there.txt", result.findings)

    def test_invalid_audit_json_is_red(self):
        self.initialize()
        self.plan_contract()
        self.satisfy_requirement()
        (self.workspace / "events.jsonl").write_text("not-json\n", encoding="utf-8")
        result = self.result()
        self.assertEqual((result.status, result.recommendation), ("RED", "NO-GO"))
        self.assertTrue(any("line 1 is invalid JSON" in finding for finding in result.findings))
        self.assertIn("Mission: Audit trail is missing mission_initialized event", result.findings)

    def test_audit_without_matching_initialization_is_red(self):
        self.initialize()
        event = {
            "timestamp": "2026-06-23T00:00:00Z",
            "type": "mission_initialized",
            "actor": "battalion_cli",
            "details": {"mission_id": "M-999"},
        }
        (self.workspace / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
        result = self.result()
        self.assertEqual(result.status, "RED")
        self.assertTrue(any("wrong mission_id" in finding for finding in result.findings))
        self.assertIn("Mission: Audit trail is missing mission_initialized event", result.findings)

    def test_green_succeeds_for_complete_contract(self):
        self.initialize()
        self.plan_contract()
        self.satisfy_requirement()
        result = self.result()
        self.assertEqual((result.status, result.recommendation), ("GREEN", "GO"))

    def test_assurance_is_deterministic_for_identical_inputs(self):
        self.initialize()
        self.plan_contract()
        self.satisfy_requirement()
        first = self.result().to_dict()
        second = self.result().to_dict()
        self.assertEqual(first, second)

    def test_go_is_impossible_without_green(self):
        with self.assertRaisesRegex(ValueError, "GO is only valid"):
            AssuranceResult("AMBER", "GO", 100, [])
        self.initialize()
        scenarios = [self.result()]
        self.plan_contract()
        scenarios.append(self.result())
        for result in scenarios:
            self.assertFalse(result.recommendation == "GO" and result.status != "GREEN")

    def test_all_contract_failures_are_reported_together(self):
        self.initialize()
        self.plan_contract(acceptance=False, reviews=False)
        ledger = read_yaml(self.ledger_path)
        ledger["requirements"][0]["status"] = "completed"
        write_yaml(self.ledger_path, ledger)
        (self.workspace / "events.jsonl").write_text("broken\n", encoding="utf-8")
        findings = self.result().findings
        self.assertTrue(any("acceptance criteria" in finding.lower() for finding in findings))
        self.assertIn("R-001: Completed without evidence", findings)
        self.assertIn("R-001: Missing required reviews", findings)
        self.assertTrue(any("invalid JSON" in finding for finding in findings))
        self.assertIn("Mission: Audit trail is missing mission_initialized event", findings)

    def test_malformed_requirement_is_not_silently_ignored(self):
        self.initialize()
        write_yaml(self.ledger_path, {"requirements": [{"id": "R-001"}]})
        result = self.result()
        self.assertEqual(result.status, "RED")
        for field in ("statement", "status", "acceptance", "evidence", "required_reviews"):
            self.assertIn(f"R-001: Missing required field: {field}", result.findings)

    def test_accepted_risk_requires_risk_entry(self):
        self.initialize()
        self.plan_contract()
        ledger = read_yaml(self.ledger_path)
        requirement = ledger["requirements"][0]
        requirement["status"] = "accepted_risk"
        for review in requirement["required_reviews"]:
            review["status"] = "completed"
        write_yaml(self.ledger_path, ledger)
        result = self.result()
        self.assertEqual(result.status, "RED")
        self.assertIn("R-001: Accepted risk has no risk entry", result.findings)

    def test_missing_workspace_files_are_all_reported(self):
        result = self.result()
        self.assertEqual((result.status, result.recommendation), ("RED", "NO-GO"))
        self.assertEqual(len([finding for finding in result.findings if "Missing required file" in finding]), 4)

    def test_report_contains_contract_and_assurance_sections(self):
        self.initialize()
        self.plan_contract()
        self.satisfy_requirement()
        self.run_cli("report")
        report = (self.workspace / "reports" / "mission-report.md").read_text()
        for heading in (
            "## Mission", "## Mission Contract", "## Extracted Constraints", "## Clarifications",
            "## Prompt Traceability", "## Doctrine", "## Standing Agent Team", "## Requirements",
            "## Acceptance Criteria", "## Evidence Summary", "## Review Summary",
            "## Assumptions", "## Risks", "## Assurance Result", "## Human Approval",
        ):
            self.assertIn(heading, report)
        self.assertIn("Unknown issuers are rejected", report)
        self.assertIn("architect=completed", report)
        self.assertIn("**Status:** GREEN", report)
        self.assertIn("Decision: PENDING", report)


if __name__ == "__main__":
    unittest.main()
