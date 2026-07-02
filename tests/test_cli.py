import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from battalion.assurance import assure
from battalion.classification import ATTRIBUTE_SCHEMA_VERSION, AttributeCatalogLoader, MissionClassifier, default_attribute_catalog
from battalion.cli import main
from battalion.dispatcher import load_assignments
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
        for name in ("mission.yaml", "agents.yaml", "attributes.yml", "ledger.yaml", "events.jsonl", "reports"):
            self.assertTrue((self.workspace / name).exists())
        self.assertEqual(read_yaml(self.workspace / "mission.yaml")["original_prompt"], "Build JWT authentication.")
        self.assertEqual(len(read_yaml(self.workspace / "agents.yaml")["agents"]), 9)
        catalog = AttributeCatalogLoader(self.workspace / "attributes.yml").load()
        self.assertEqual(catalog["schema_version"], ATTRIBUTE_SCHEMA_VERSION)
        identifiers = [item["identifier"] for item in catalog["attributes"]]
        for identifier in ("REST_API", "HTTP_ENDPOINT", "USER_INTERFACE", "DATABASE", "SECURITY", "TESTING_REQUIRED", "NODE", "TYPESCRIPT", "DOTNET", "DOCKER"):
            self.assertIn(identifier, identifiers)

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
        self.assertIn("Battalion v0.4.0", output.getvalue())

    def classification_for_prompt(self, prompt):
        self.initialize_with_prompt(prompt)
        self.run_cli("assess")
        return json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))["mission_classification"]

    def detected_attributes_for_prompt(self, prompt):
        return set(self.classification_for_prompt(prompt)["detected_attributes"])

    def test_classifier_detects_rest_api_missions(self):
        attributes = self.detected_attributes_for_prompt("Build a REST API endpoint that returns JSON over HTTP.")
        self.assertIn("REST_API", attributes)

    def test_classifier_detects_react_user_interface_missions(self):
        attributes = self.detected_attributes_for_prompt("Build a React page with a form and submit button.")
        self.assertIn("USER_INTERFACE", attributes)

    def test_classifier_detects_sql_database_missions(self):
        attributes = self.detected_attributes_for_prompt("Create a SQL database migration that adds a schema table and index.")
        self.assertIn("DATABASE", attributes)

    def test_classifier_detects_docker_missions(self):
        attributes = self.detected_attributes_for_prompt("Package the service with Docker and a Dockerfile.")
        self.assertIn("DOCKER", attributes)

    def test_classifier_detects_security_missions(self):
        attributes = self.detected_attributes_for_prompt("Add JWT authentication and authorization following OWASP guidance.")
        self.assertIn("SECURITY", attributes)

    def test_classifier_detects_node_missions(self):
        attributes = self.detected_attributes_for_prompt("Build a Node Fastify API using npm scripts.")
        self.assertIn("NODE", attributes)

    def test_classifier_detects_dotnet_missions(self):
        attributes = self.detected_attributes_for_prompt("Build an ASP.NET minimal API in C# using Entity Framework.")
        self.assertIn("DOTNET", attributes)

    def test_classifier_records_classification_evidence_hit_counts_and_decisions(self):
        result = MissionClassifier(default_attribute_catalog()).classify(
            {"mission_prompt": "Build a REST API with OpenAPI over HTTP."},
            {"requirements": [], "clarifications": []},
        )
        rest = next(item for item in result["attributes"] if item["attribute"] == "REST_API")
        self.assertTrue(rest["classified"])
        self.assertEqual(rest["decision"], "classified")
        evidence = rest["classification_evidence"]
        indicators = {item["indicator"] for item in evidence}
        sources = {item["source"] for item in evidence}
        self.assertIn("rest", indicators)
        self.assertIn("http", indicators)
        self.assertIn("openapi", indicators)
        self.assertIn("mission_prompt", sources)
        self.assertEqual(rest["hit_count"], len(indicators))
        self.assertEqual(rest["threshold"], 2)
        database = next(item for item in result["attributes"] if item["attribute"] == "DATABASE")
        self.assertFalse(database["classified"])
        self.assertEqual(database["classification_evidence"], [])
        self.assertEqual(database["decision"], "not_classified")

    def test_classifier_tracks_evidence_sources(self):
        result = MissionClassifier(default_attribute_catalog()).classify(
            {"mission_prompt": "Build an API.", "objective": "Expose HTTP service."},
            {
                "requirements": [{"statement": "Document routes", "acceptance": ["OpenAPI document exists"]}],
                "clarifications": [{"status": "resolved", "answer": "Use REST conventions."}],
            },
        )
        rest = next(item for item in result["attributes"] if item["attribute"] == "REST_API")
        evidence = {(item["indicator"], item["source"]) for item in rest["classification_evidence"]}
        self.assertIn(("api", "mission_prompt"), evidence)
        self.assertIn(("http", "mission_objective"), evidence)
        self.assertIn(("openapi", "acceptance_criteria"), evidence)
        self.assertIn(("rest", "clarification_answer"), evidence)

    def test_rest_api_requires_threshold_hit_count(self):
        result = MissionClassifier(default_attribute_catalog()).classify(
            {"mission_prompt": "Return JSON from the worker."},
            {"requirements": [], "clarifications": []},
        )
        rest = next(item for item in result["attributes"] if item["attribute"] == "REST_API")
        self.assertFalse(rest["classified"])
        self.assertEqual(rest["hit_count"], 1)
        self.assertEqual(rest["threshold"], 2)

    def test_database_requires_threshold_hit_count(self):
        result = MissionClassifier(default_attribute_catalog()).classify(
            {"mission_prompt": "Create a SQL script."},
            {"requirements": [], "clarifications": []},
        )
        database = next(item for item in result["attributes"] if item["attribute"] == "DATABASE")
        self.assertFalse(database["classified"])
        self.assertEqual(database["hit_count"], 1)
        self.assertEqual(database["threshold"], 2)

    def test_classifier_uses_configurable_catalog_thresholds(self):
        result = MissionClassifier({
            "schema_version": ATTRIBUTE_SCHEMA_VERSION,
            "attributes": [{
                "identifier": "CUSTOM_RUNTIME",
                "description": "Custom runtime marker",
                "indicators": ["alpha", "beta"],
                "threshold": 2,
            }]
        }).classify({"mission_prompt": "Use alpha only."}, {"requirements": [], "clarifications": []})
        custom = result["attributes"][0]
        self.assertFalse(custom["classified"])
        self.assertEqual(custom["hit_count"], 1)
        result = MissionClassifier({
            "schema_version": ATTRIBUTE_SCHEMA_VERSION,
            "attributes": [{
                "identifier": "CUSTOM_RUNTIME",
                "description": "Custom runtime marker",
                "indicators": ["alpha", "beta"],
                "threshold": 2,
            }]
        }).classify({"mission_prompt": "Use alpha and beta."}, {"requirements": [], "clarifications": []})
        self.assertTrue(result["attributes"][0]["classified"])

    def test_attribute_catalog_loader_rejects_invalid_schema_version(self):
        self.initialize_with_prompt("Build a REST API.")
        (self.workspace / "attributes.yml").write_text("schema_version: wrong\nattributes: {}\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as raised:
            main(["assess"], self.cwd)
        self.assertIn("attribute catalog must be valid YAML conforming to battalion.attributes.v1", str(raised.exception))
        self.assertIn("unsupported attribute catalog schema_version", str(raised.exception))

    def test_attribute_catalog_loader_rejects_json_catalogs(self):
        self.initialize_with_prompt("Build a REST API.")
        (self.workspace / "attributes.yml").write_text('{"schema_version":"battalion.attributes.v1","attributes":{}}\n', encoding="utf-8")
        with self.assertRaises(SystemExit) as raised:
            main(["assess"], self.cwd)
        self.assertIn("attribute catalog must be valid YAML conforming to battalion.attributes.v1", str(raised.exception))
        self.assertIn("JSON/object-literal catalogs are not accepted", str(raised.exception))

    def test_mission_classifier_loads_attributes_from_yaml(self):
        self.initialize_with_prompt("Use acme runtime.")
        (self.workspace / "attributes.yml").write_text(
            "\n".join([
                f"schema_version: {ATTRIBUTE_SCHEMA_VERSION}",
                "attributes:",
                "  ACME_RUNTIME:",
                "    description: Custom ACME runtime.",
                "    threshold: 1",
                "    indicators:",
                "      - acme",
                "",
            ]),
            encoding="utf-8",
        )
        catalog = AttributeCatalogLoader(self.workspace / "attributes.yml").load()
        result = MissionClassifier(catalog).classify(
            {"mission_prompt": "Use acme runtime."},
            {"requirements": [], "clarifications": []},
        )
        self.assertEqual(result["detected_attributes"], ["ACME_RUNTIME"])

    def test_classifier_is_deterministic(self):
        mission = {"mission_prompt": "Build a REST API over HTTP with OpenAPI docs."}
        ledger = {"requirements": [{"statement": "Serve API route", "acceptance": ["OpenAPI document exists"]}], "clarifications": []}
        classifier = MissionClassifier(default_attribute_catalog())
        self.assertEqual(classifier.classify(mission, ledger), classifier.classify(mission, ledger))

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
        output = self.run_cli("assess")
        ledger = read_yaml(self.ledger_path)
        self.assertEqual(ledger["generated_by"], "mission_analyst")
        self.assertGreaterEqual(len(ledger["requirements"]), 4)
        self.assertEqual(
            [requirement["id"] for requirement in ledger["requirements"]],
            [f"R-{index:03d}" for index in range(1, len(ledger["requirements"]) + 1)],
        )
        self.assertIn("Readiness:", output)

    def test_mission_analyst_generation_is_deterministic(self):
        prompt = "Build a hello world REST API."
        created_at = "2026-06-23T00:00:00Z"
        self.assertEqual(
            generate_mission_contract("M-001", prompt, created_at),
            generate_mission_contract("M-001", prompt, created_at),
        )

    def test_generated_requirements_have_acceptance_criteria(self):
        self.initialize()
        self.run_cli("assess")
        requirements = read_yaml(self.ledger_path)["requirements"]
        self.assertTrue(all(requirement["acceptance"] for requirement in requirements))
        self.assertTrue(all(all(criterion.strip() for criterion in requirement["acceptance"]) for requirement in requirements))

    def test_mission_analyst_generates_assumptions_and_risks(self):
        self.initialize()
        self.run_cli("assess")
        ledger = read_yaml(self.ledger_path)
        self.assertEqual([item["id"] for item in ledger["assumptions"]], ["A-001"])
        self.assertTrue(ledger["risks"])
        self.assertEqual([item["id"] for item in ledger["risks"]], [f"RISK-{index:03d}" for index in range(1, len(ledger["risks"]) + 1)])
        self.assertTrue(all(item["statement"] for item in ledger["assumptions"] + ledger["risks"]))

    def test_technology_constraints_are_extracted(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        ledger = read_yaml(self.ledger_path)
        statements = [item["statement"] for item in ledger["constraints"]["technical"]]
        self.assertEqual(statements, ["TypeScript is required.", "Node.js is required.", "Docker packaging is required."])
        requirement_statements = [item["statement"] for item in ledger["requirements"]]
        self.assertIn("Create TypeScript Node application", requirement_statements)
        self.assertIn("Containerize application with Docker", requirement_statements)

    def test_security_constraints_are_extracted(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
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
        self.run_cli("assess")
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
        self.run_cli("assess")
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
        self.run_cli("assess")
        ledger = read_yaml(self.ledger_path)
        questions = [item["question"] for item in ledger["clarifications"]]
        self.assertIn("What endpoint path should be used?", questions)
        self.assertIn("What application framework should be used?", questions)
        self.assertIn("What timestamp format should be returned?", questions)
        self.assertTrue(all(item["status"] == "open" for item in ledger["clarifications"]))
        self.assertFalse(any("Express" in item["statement"] for item in ledger["assumptions"]))

    def test_current_owasp_guidance_does_not_produce_blocking_clarification(self):
        self.initialize_with_prompt("Build a secure command line tool. Follow current OWASP guidance.")
        self.run_cli("assess")
        ledger = read_yaml(self.ledger_path)
        questions = [item["question"] for item in ledger.get("clarifications", [])]
        self.assertFalse(any("OWASP" in question for question in questions))
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))
        self.assertFalse(any("OWASP" in item["question"] for item in assessment["outstanding_clarifications"]))

    def test_latest_dotnet_lts_does_not_produce_blocking_clarification(self):
        self.initialize_with_prompt("Build a .NET service using latest .NET LTS.")
        self.run_cli("assess")
        ledger = read_yaml(self.ledger_path)
        questions = [item["question"] for item in ledger.get("clarifications", [])]
        self.assertFalse(any("version" in question.lower() or ".NET" in question for question in questions))

    def test_explicit_versions_are_preserved_without_compatibility_questions(self):
        self.initialize_with_prompt("Build a .NET 8 REST API that follows OWASP API Security Top 10 2023.")
        self.run_cli("assess")
        ledger = read_yaml(self.ledger_path)
        technical = [item["statement"] for item in ledger["constraints"]["technical"]]
        self.assertIn(".NET 8 is specified.", technical)
        self.assertIn("OWASP API Security Top 10 2023 is specified.", technical)
        self.assertIn(
            "OWASP API Security Top 10 2023.",
            read_yaml(self.workspace / "mission.yaml")["mission_prompt"],
        )
        questions = [item["question"] for item in ledger.get("clarifications", [])]
        self.assertFalse(any("version" in question.lower() for question in questions))

    def test_multiple_technologies_create_non_blocking_compatibility_assumption_and_risk(self):
        prompt = (
            "Build a Fastify TypeScript Node REST API running in Docker with /health. "
            "Return HTTP 200. Follow current OWASP guidance. Create happy-path and negative-path tests."
        )
        self.initialize_with_prompt(prompt)
        self.run_cli("assess")
        ledger = read_yaml(self.ledger_path)
        assumptions = [item["statement"] for item in ledger["assumptions"]]
        risks = [item["statement"] for item in ledger["risks"]]
        self.assertIn("Current or explicitly specified technology and standards versions are intentional and preserved as mission intent.", assumptions)
        self.assertIn("The engineering team is responsible for selecting mutually compatible dependency versions.", assumptions)
        self.assertIn("Technology compatibility must be validated during implementation and assurance.", risks)
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))
        self.assertEqual(assessment["readiness"], "READY_WITH_RISK")
        self.assertEqual(assessment["recommendation"], "Proceed to Implementation")

    def test_assessment_always_outputs_engineering_compatibility_disclaimer(self):
        self.initialize_with_prompt("Build a small CLI utility.")
        output = self.run_cli("assess")
        expected = (
            "Framework, SDK, runtime, library, package, platform, and standards versions must always be validated "
            "by the human engineering team for compatibility during implementation, testing, and assurance."
        )
        self.assertIn("Engineering Compatibility Disclaimer", output)
        self.assertIn(expected, output)
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))
        self.assertEqual(assessment["engineering_compatibility_disclaimer"], expected)
        markdown = (self.workspace / "assessment.md").read_text(encoding="utf-8")
        self.assertIn("## Engineering Compatibility Disclaimer", markdown)
        self.assertIn(expected, markdown)

    def test_mission_prompt_remains_immutable_during_contract_generation(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        before = (self.workspace / "mission.yaml").read_bytes()
        self.run_cli("assess")
        self.run_cli("dispatch")
        self.run_cli("report")
        after = (self.workspace / "mission.yaml").read_bytes()
        self.assertEqual(before, after)
        self.assertEqual(read_yaml(self.ledger_path)["mission_prompt"], self.CONSTRAINT_PROMPT)

    def test_assurance_validates_trace_links_and_reports_open_clarifications(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
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
        self.run_cli("assess")
        self.run_cli(
            "clarify", "--resolver", "Jesse Williams",
            "--answer", "Q-001=/health",
            "--answer", "Q-002=Fastify",
            "--answer", "Q-003=ISO-8601 UTC",
        )
        evidence = self.cwd / "evidence" / "mission-validation.txt"
        evidence.parent.mkdir()
        evidence.write_text("All prompt-derived requirements validated.\n", encoding="utf-8")
        ledger = read_yaml(self.ledger_path)
        for requirement in ledger["requirements"]:
            requirement["status"] = "completed"
            requirement["evidence"] = ["evidence/mission-validation.txt"]
            for review in requirement["required_reviews"]:
                review["status"] = "completed"
        write_yaml(self.ledger_path, ledger)
        result = self.result()
        self.assertEqual((result.status, result.recommendation, result.confidence), ("GREEN", "GO", 100))

    def test_clarifications_can_be_resolved_and_reconcile_requirements(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        output = self.run_cli(
            "clarify", "--resolver", "Jesse Williams",
            "--answer", "Q-001=/health",
            "--answer", "Q-002=Fastify",
            "--answer", "Q-003=ISO-8601 UTC",
        )
        ledger = read_yaml(self.ledger_path)
        self.assertIn("Applied 3 clarification action(s)", output)
        self.assertIn("Summary: 3 resolved, 0 still open.", output)
        self.assertTrue(all(item["status"] == "resolved" for item in ledger["clarifications"]))
        self.assertEqual(ledger["clarifications"][0]["answer"], "/health")
        self.assertEqual(ledger["clarifications"][0]["resolved_by"], "Jesse Williams")
        self.assertTrue(ledger["clarifications"][0]["resolved_at"])
        requirements = {item["id"]: item for item in ledger["requirements"]}
        self.assertEqual(requirements["R-001"]["statement"], "Create Fastify TypeScript application")
        self.assertEqual(requirements["R-002"]["statement"], "Implement /health health endpoint")
        self.assertIn("GET /health returns HTTP 200", requirements["R-002"]["acceptance"])
        self.assertIn("Response timestamp uses ISO-8601 UTC format", requirements["R-002"]["acceptance"])
        self.assertIn("Security-relevant failures are handled consistently with specified or current security guidance", requirements["R-005"]["acceptance"])
        self.assertEqual(len(requirements), 7)

    def test_clarification_resolution_creates_auditable_history(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        self.run_cli("clarify", "--resolver", "Jesse Williams", "--answer", "Q-001=/health")
        clarification = read_yaml(self.ledger_path)["clarifications"][0]
        self.assertEqual([entry["action"] for entry in clarification["history"]], ["created", "resolved"])
        self.assertEqual(clarification["history"][0]["actor"], "mission_analyst")
        self.assertEqual(clarification["history"][1]["actor"], "Jesse Williams")
        events = [json.loads(line) for line in (self.workspace / "events.jsonl").read_text().splitlines()]
        created = [event for event in events if event["type"] == "clarification_created"]
        resolved = [event for event in events if event["type"] == "clarification_resolved"]
        reconciled = [event for event in events if event["type"] == "mission_contract_reconciled"]
        self.assertEqual(len(created), 3)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["actor"], "Jesse Williams")
        self.assertEqual(resolved[0]["details"]["value"], "/health")
        self.assertEqual(len(reconciled), 1)

    def test_assurance_rejects_clarification_history_without_matching_audit_event(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        self.run_cli("clarify", "--resolver", "Jesse Williams", "--answer", "Q-001=/health")
        event_path = self.workspace / "events.jsonl"
        events = [json.loads(line) for line in event_path.read_text().splitlines()]
        events = [event for event in events if event["type"] != "clarification_resolved"]
        event_path.write_text("".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events), encoding="utf-8")
        result = self.result()
        self.assertEqual((result.status, result.recommendation), ("RED", "NO-GO"))
        self.assertIn("Mission: Audit trail is missing clarification_resolved event for Q-001", result.findings)

    def test_resolved_clarifications_stop_contributing_assurance_findings(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        before = self.result()
        self.assertEqual(before.clarification_counts["open"], 3)
        self.assertEqual(before.clarification_counts["resolved"], 0)
        self.run_cli(
            "clarify", "--resolver", "Jesse Williams",
            "--answer", "Q-001=/health",
            "--answer", "Q-002=Fastify",
            "--answer", "Q-003=ISO-8601 UTC",
        )
        after = self.result()
        self.assertEqual((after.status, after.recommendation), ("AMBER", "NO-GO"))
        self.assertEqual(after.clarification_counts["open"], 0)
        self.assertEqual(after.clarification_counts["resolved"], 3)
        self.assertFalse(any("Clarification" in finding or "Q-" in finding for finding in after.findings))
        self.assertTrue(any("Mission work remains open" in finding for finding in after.findings))

    def test_interactive_clarify_collects_human_answers(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        responses = iter(["a", "/health", "Fastify", "ISO-8601 UTC", "Jesse Williams"])
        with patch("battalion.cli.sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=lambda _: next(responses)):
            output = self.run_cli("clarify")
        clarifications = read_yaml(self.ledger_path)["clarifications"]
        self.assertEqual([item["answer"] for item in clarifications], ["/health", "Fastify", "ISO-8601 UTC"])
        self.assertTrue(all(item["status"] == "resolved" for item in clarifications))
        self.assertIn("Summary: 3 resolved, 0 still open.", output)
        event_types = [json.loads(line)["type"] for line in (self.workspace / "events.jsonl").read_text().splitlines()]
        self.assertEqual(event_types.count("clarification_resolved"), 3)

    def test_interactive_clarify_blank_answer_leaves_clarification_open(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        responses = iter(["a", "/health", "", "", "Jesse Williams"])
        with patch("battalion.cli.sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=lambda _: next(responses)):
            output = self.run_cli("clarify")
        clarifications = read_yaml(self.ledger_path)["clarifications"]
        self.assertEqual(clarifications[0]["status"], "resolved")
        self.assertEqual(clarifications[0]["answer"], "/health")
        self.assertEqual([item["status"] for item in clarifications[1:]], ["open", "open"])
        self.assertEqual([item.get("answer") for item in clarifications[1:]], [None, None])
        self.assertIn("Summary: 1 resolved, 2 still open.", output)
        events = [json.loads(line) for line in (self.workspace / "events.jsonl").read_text().splitlines()]
        resolved = [event for event in events if event["type"] == "clarification_resolved"]
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["details"]["clarification_id"], "Q-001")

    def test_interactive_clarify_all_blank_answers_do_not_require_resolver(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        responses = iter(["a", "", "", ""])
        with patch("battalion.cli.sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=lambda _: next(responses)):
            output = self.run_cli("clarify")
        clarifications = read_yaml(self.ledger_path)["clarifications"]
        self.assertTrue(all(item["status"] == "open" for item in clarifications))
        self.assertIn("Summary: 0 resolved, 3 still open.", output)
        event_types = [json.loads(line)["type"] for line in (self.workspace / "events.jsonl").read_text().splitlines()]
        self.assertNotIn("clarification_resolved", event_types)

    def test_clarify_only_presents_unresolved_clarifications(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        self.run_cli("clarify", "--resolver", "Jesse Williams", "--answer", "Q-001=/health")
        output = self.run_cli("clarify", "--resolver", "Jesse Williams", "--answer", "Q-002=Fastify")
        self.assertNotIn("\nQ-001\n", output)
        self.assertIn("\nQ-002\n", output)
        self.assertIn("\nQ-003\n", output)
        clarifications = read_yaml(self.ledger_path)["clarifications"]
        self.assertEqual(clarifications[0]["status"], "resolved")
        self.assertEqual(clarifications[1]["status"], "resolved")

    def test_clarify_does_not_generate_assessment_artifacts(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        (self.workspace / "assessment.json").unlink()
        (self.workspace / "assessment.md").unlink()
        self.run_cli("clarify", "--resolver", "Jesse Williams", "--answer", "Q-001=/health")
        self.assertFalse((self.workspace / "assessment.json").exists())
        self.assertFalse((self.workspace / "assessment.md").exists())

    def test_rejected_and_superseded_clarification_states_are_audited(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        self.run_cli("clarify", "--resolver", "Jesse Williams", "--answer", "Q-001=/health")
        self.run_cli("clarify", "--resolver", "Jesse Williams", "--supersede", "Q-001=/status")
        self.run_cli("clarify", "--resolver", "Jesse Williams", "--reject", "Q-002=Framework selection deferred")
        clarifications = read_yaml(self.ledger_path)["clarifications"]
        self.assertEqual(clarifications[0]["status"], "superseded")
        self.assertEqual(clarifications[1]["status"], "rejected")
        self.assertEqual([entry["action"] for entry in clarifications[0]["history"]], ["created", "resolved", "superseded"])
        event_types = [json.loads(line)["type"] for line in (self.workspace / "events.jsonl").read_text().splitlines()]
        self.assertIn("clarification_superseded", event_types)
        self.assertIn("clarification_rejected", event_types)

    def test_mission_analyst_generates_explainable_review_assignments(self):
        self.initialize()
        self.run_cli("assess")
        requirements = read_yaml(self.ledger_path)["requirements"]
        for requirement in requirements:
            self.assertTrue(requirement["required_reviews"])
            for review in requirement["required_reviews"]:
                self.assertEqual(review["status"], "pending")
                self.assertTrue(review["reason"])

    def test_generated_mission_contract_is_traceable_to_prompt(self):
        self.initialize()
        self.run_cli("assess")
        mission = read_yaml(self.workspace / "mission.yaml")
        ledger = read_yaml(self.ledger_path)
        self.assertEqual(ledger["mission_id"], mission["id"])
        self.assertEqual(ledger["mission_prompt"], mission["mission_prompt"])
        event_types = [json.loads(line)["type"] for line in (self.workspace / "events.jsonl").read_text().splitlines()]
        self.assertIn("mission_contract_generated", event_types)

    def test_generated_contract_is_visible_in_mission_report(self):
        self.initialize()
        self.run_cli("assess")
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
        self.run_cli("assess")
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
            ["clarify"],
            ["assess"],
            ["dispatch"],
            ["execute"],
            ["status"],
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
                main(["assess"])
                main(["assure"])
                main(["report"])
        finally:
            os.chdir(original_directory)
        self.assertTrue((outside_repository / ".battalion" / "mission.yaml").is_file())
        self.assertTrue((outside_repository / ".battalion" / "reports" / "mission-report.md").is_file())
        self.assertIn("Status: AMBER", assurance_output.getvalue())

    def test_assess_works_immediately_after_init_and_generates_contract(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        output = self.run_cli("assess")
        ledger = read_yaml(self.ledger_path)
        self.assertIn("Readiness:", output)
        self.assertTrue(ledger["requirements"])
        self.assertTrue(all(requirement["acceptance"] for requirement in ledger["requirements"]))
        self.assertTrue(ledger["constraints"])
        self.assertTrue(ledger["clarifications"])
        self.assertTrue((self.workspace / "assessment.json").is_file())
        self.assertTrue((self.workspace / "assessment.md").is_file())

    def test_assess_interactively_resolves_clarifications_when_answers_are_provided(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        responses = iter(["a", "/health", "Fastify", "ISO-8601 UTC", "Jesse Williams"])
        with patch("battalion.cli.sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=lambda _: next(responses)):
            output = self.run_cli("assess", "--interactive")
        ledger = read_yaml(self.ledger_path)
        self.assertTrue(all(item["status"] == "resolved" for item in ledger["clarifications"]))
        self.assertIn("Resolved 3 clarification(s) during assessment.", output)
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))
        self.assertEqual(assessment["recommendation"], "Proceed to Implementation")

    def test_assess_skipped_interactive_clarifications_remain_open(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        responses = iter(["s"])
        with patch("battalion.cli.sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=lambda _: next(responses)):
            output = self.run_cli("assess", "--interactive")
        ledger = read_yaml(self.ledger_path)
        self.assertTrue(all(item["status"] == "open" for item in ledger["clarifications"]))
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))
        self.assertEqual(assessment["readiness"], "NOT_READY")
        self.assertEqual(assessment["recommendation"], "Resolve Clarifications")
        self.assertIn("No clarification answers provided", output)

    def test_assess_never_prompts_by_default(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        with patch("battalion.cli.sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=AssertionError("assess prompted unexpectedly")):
            output = self.run_cli("assess")
        self.assertIn("Outstanding Clarifications", output)
        self.assertIn("Run:\n  battalion clarify", output)
        ledger = read_yaml(self.ledger_path)
        self.assertTrue(all(item["status"] == "open" for item in ledger["clarifications"]))

    def test_assess_interactive_prompts_only_when_clarifications_exist(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        self.run_cli(
            "clarify", "--resolver", "Jesse Williams",
            "--answer", "Q-001=/health",
            "--answer", "Q-002=Fastify",
            "--answer", "Q-003=ISO-8601 UTC",
        )
        with patch("battalion.cli.sys.stdin.isatty", return_value=True), patch("builtins.input", side_effect=AssertionError("interactive assess prompted without open clarifications")):
            output = self.run_cli("assess", "--interactive")
        self.assertIn("Outstanding Clarifications\n- None", output)

    def test_plan_requires_assessment(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        with self.assertRaises(SystemExit) as raised:
            main(["plan"], self.cwd)
        self.assertEqual(str(raised.exception), "No mission assessment exists. Run battalion assess first.")

    def test_plan_consumes_assessment_output(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        self.run_cli(
            "clarify", "--resolver", "Jesse Williams",
            "--answer", "Q-001=/health",
            "--answer", "Q-002=Fastify",
            "--answer", "Q-003=ISO-8601 UTC",
        )
        self.run_cli("assess")
        output = self.run_cli("plan", "--architecture", "entra-sso.md", "--architecture", "api-security.md")
        plan_path = self.workspace / "mission-plan.md"
        self.assertTrue(plan_path.is_file())
        plan = plan_path.read_text(encoding="utf-8")
        for heading in (
            "# Mission", "## Background", "## Mission Objective", "## Business Outcome",
            "## Readiness Summary", "## Mission Classification", "## Functional Requirements",
            "## Non-Functional Requirements", "## Engineering Constraints", "## Architecture References",
            "## Assumptions", "## Risks", "## Implementation Guidance", "## Suggested Work Breakdown",
            "## Testing Strategy", "## Evidence Required", "## Definition of Done", "## Out of Scope",
            "## Mission Success Criteria",
        ):
            self.assertIn(heading, plan)
        self.assertIn("entra-sso.md", plan)
        self.assertIn("api-security.md", plan)
        self.assertIn("Implementation shall conform to these engineering references.", plan)
        self.assertIn("READY_WITH_RISK", plan)
        self.assertIn("REST_API", plan)
        self.assertIn("GET /health returns HTTP 200", plan)
        self.assertIn("Current or explicitly specified technology", plan)
        self.assertIn("Technology compatibility must be validated", plan)
        self.assertIn("No explicit business outcome was identified during assessment.", plan)
        self.assertIn("No explicit performance requirements were identified during assessment.", plan)
        self.assertIn("R-001", plan)
        self.assertIn("Generated execution-ready mission plan", output)

    def test_plan_refuses_not_ready_missions(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        with self.assertRaises(SystemExit) as raised:
            main(["plan"], self.cwd)
        self.assertIn("Current readiness: NOT_READY", str(raised.exception))
        self.assertFalse((self.workspace / "mission-plan.md").exists())

    def test_plan_refuses_partially_ready_missions(self):
        self.initialize_with_prompt("Build a public REST API endpoint.")
        self.run_cli("assess")
        self.run_cli("clarify", "--resolver", "Jesse Williams", "--answer", "Q-001=/public", "--answer", "Q-002=Fastify")
        self.run_cli("assess")
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))
        self.assertEqual(assessment["readiness"], "PARTIALLY_READY")
        with self.assertRaises(SystemExit) as raised:
            main(["plan"], self.cwd)
        self.assertIn("Current readiness: PARTIALLY_READY", str(raised.exception))

    def test_plan_executes_for_ready_assessment(self):
        self.initialize_with_prompt("Build a command-line utility.")
        self.run_cli("assess")
        assessment_path = self.workspace / "assessment.json"
        assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
        assessment["readiness"] = "READY"
        assessment_path.write_text(json.dumps(assessment, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.run_cli("plan")
        plan = (self.workspace / "mission-plan.md").read_text(encoding="utf-8")
        self.assertIn("- **Readiness:** READY", plan)
        self.assertIn("No architecture reference filenames were supplied for this mission.", plan)

    def test_plan_never_fabricates_engineering_requirements(self):
        self.initialize_with_prompt("Build a command-line utility.")
        self.run_cli("assess")
        assessment_path = self.workspace / "assessment.json"
        assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
        assessment["readiness"] = "READY_WITH_RISK"
        assessment_path.write_text(json.dumps(assessment, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.run_cli("plan")
        plan = (self.workspace / "mission-plan.md").read_text(encoding="utf-8")
        self.assertIn("No explicit performance requirements were identified during assessment.", plan)
        self.assertIn("No explicit observability requirements were identified during assessment.", plan)
        self.assertNotIn("Kubernetes", plan)
        self.assertNotIn("PostgreSQL", plan)
        self.assertNotIn("OAuth", plan)

    def test_assessment_generates_json_and_markdown(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        output = self.run_cli("assess")
        self.assertIn("Readiness: NOT_READY", output)
        self.assertIn("Mission Classification", output)
        self.assertIn("REST_API: classified", output)
        self.assertIn("DATABASE: not_classified", output)
        self.assertIn("hit count", output)
        self.assertIn("Primary Findings", output)
        self.assertIn("Outstanding Clarifications", output)
        self.assertIn("Recommendation: Resolve Clarifications", output)
        self.assertIn("Run:\n  battalion clarify", output)
        assessment_json = self.workspace / "assessment.json"
        assessment_md = self.workspace / "assessment.md"
        self.assertTrue(assessment_json.is_file())
        self.assertTrue(assessment_md.is_file())
        assessment = json.loads(assessment_json.read_text(encoding="utf-8"))
        self.assertEqual(assessment["schema_version"], "battalion.assessment.v2")
        self.assertEqual(assessment["readiness"], "NOT_READY")
        self.assertTrue(assessment["readiness_reason"])
        self.assertEqual(assessment["recommendation"], "Resolve Clarifications")
        self.assertTrue(assessment["recommendation_reason"])
        self.assertIn("REST_API", assessment["mission_attributes"])
        self.assertIn("DOCKER", assessment["mission_attributes"])
        self.assertIn("NODE", assessment["mission_attributes"])
        self.assertIn("TYPESCRIPT", assessment["mission_attributes"])
        self.assertIn("TESTING_REQUIRED", assessment["mission_attributes"])
        self.assertIn("SECURITY", assessment["mission_attributes"])
        self.assertIn("attribute_sources", assessment)
        self.assertIn("mission_classification", assessment)
        rest = next(item for item in assessment["mission_classification"]["attributes"] if item["attribute"] == "REST_API")
        self.assertTrue(rest["classified"])
        self.assertTrue(rest["classification_evidence"])
        self.assertIn("indicator", rest["classification_evidence"][0])
        self.assertIn("source", rest["classification_evidence"][0])
        self.assertGreaterEqual(rest["hit_count"], 1)
        self.assertEqual(rest["threshold"], 2)
        self.assertIn("finding_categories", assessment)
        self.assertTrue(assessment["discipline_findings"])
        markdown = assessment_md.read_text(encoding="utf-8")
        for heading in (
            "## Mission", "## Assessment Summary", "## Readiness", "## Mission Attributes",
            "## Mission Classification", "## Outstanding Clarifications", "## Assumptions", "## Risks", "## Resolved Risks",
            "## Engineering Obligation Summary", "## Finding Categories", "## Discipline Findings",
            "## Recommendation", "## Next Engineering Activity", "## Timestamp", "## Schema Version",
        ):
            self.assertIn(heading, markdown)
        self.assertIn("REST_API", markdown)
        self.assertIn("hit count:", markdown)
        self.assertIn("evidence:", markdown)
        self.assertIn("from mission_prompt", markdown)
        self.assertIn("DATABASE", markdown)
        self.assertIn("classified: no", markdown)

    def test_assessment_is_deterministic_for_unchanged_mission(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        self.run_cli("assess")
        first_json = (self.workspace / "assessment.json").read_text(encoding="utf-8")
        first_markdown = (self.workspace / "assessment.md").read_text(encoding="utf-8")
        self.run_cli("assess")
        self.assertEqual(first_json, (self.workspace / "assessment.json").read_text(encoding="utf-8"))
        self.assertEqual(first_markdown, (self.workspace / "assessment.md").read_text(encoding="utf-8"))

    def test_assessment_changes_when_mission_state_changes(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        self.run_cli("assess")
        before = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))
        self.run_cli(
            "clarify", "--resolver", "Jesse Williams",
            "--answer", "Q-001=/health",
            "--answer", "Q-002=Fastify",
            "--answer", "Q-003=ISO-8601 UTC",
        )
        self.run_cli("assess")
        after = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))
        self.assertEqual(before["readiness"], "NOT_READY")
        self.assertNotEqual(before["readiness"], after["readiness"])
        self.assertEqual(after["readiness"], "READY_WITH_RISK")
        self.assertEqual(after["recommendation"], "Proceed to Implementation")
        self.assertTrue(after["readiness_reason"])
        self.assertTrue(after["recommendation_reason"])

    def test_assessment_resolved_clarifications_eliminate_contradictory_risks(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        self.run_cli(
            "clarify", "--resolver", "Jesse Williams",
            "--answer", "Q-001=/health",
            "--answer", "Q-002=Fastify",
            "--answer", "Q-003=ISO-8601 UTC",
        )
        self.run_cli("assess")
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))
        open_risk_text = " ".join(item["statement"] for item in assessment["risks"])
        resolved_risk_text = " ".join(item["statement"] for item in assessment["resolved_risks"])
        self.assertNotIn("Framework selection remains unresolved", open_risk_text)
        self.assertIn("Framework selection remains unresolved", resolved_risk_text)
        self.assertTrue(all(item["status"] == "RESOLVED" for item in assessment["resolved_risks"]))

    def test_assessment_mission_summary_is_engineering_summary_not_prompt_repeat(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        self.run_cli("assess")
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))
        self.assertNotEqual(assessment["mission_summary"], self.CONSTRAINT_PROMPT)
        self.assertIn("TypeScript", assessment["mission_summary"])
        self.assertIn("Docker", assessment["mission_summary"])
        self.assertLessEqual(len(assessment["mission_summary"].split("\n\n")), 4)

    def test_assessment_readiness_rules_for_missing_requirements_and_acceptance(self):
        self.initialize()
        self.run_cli("assess")
        generated = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))
        self.assertNotEqual(read_yaml(self.ledger_path)["requirements"], [])
        self.assertIn(generated["readiness"], {"PARTIALLY_READY", "READY_WITH_RISK", "READY"})
        self.plan_contract(acceptance=False)
        self.run_cli("assess")
        missing_acceptance = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))
        self.assertEqual(missing_acceptance["readiness"], "NOT_READY")
        self.assertEqual(missing_acceptance["recommendation"], "Refine Requirements")

    def test_assessment_evaluates_obligation_findings_and_recommendation(self):
        self.initialize_with_prompt("Build a public REST API endpoint.")
        self.run_cli("assess")
        self.run_cli("clarify", "--resolver", "Jesse Williams", "--answer", "Q-001=/public", "--answer", "Q-002=Fastify")
        self.run_cli("assess")
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))
        secops_findings = [item for item in assessment["discipline_findings"] if item["discipline"] == "SecOps" and item["status"] == "NEEDS_CLARIFICATION"]
        self.assertTrue(secops_findings)
        self.assertEqual(assessment["readiness"], "PARTIALLY_READY")
        self.assertEqual(assessment["recommendation"], "Perform Security Review")
        self.assertTrue(assessment["recommendation_reason"])

    def test_assessment_only_applicable_obligations_appear(self):
        self.initialize_with_prompt("Build a command-line utility.")
        self.run_cli("assess")
        self.run_cli("assess")
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))
        self.assertFalse(any(item["status"] == "NOT_APPLICABLE" for item in assessment["discipline_findings"]))
        self.assertFalse(any(item["obligation"] == "HTTP method enforcement identified" for item in assessment["discipline_findings"]))
        self.assertFalse(any(item["obligation"] == "Malicious-request tests identified" for item in assessment["discipline_findings"]))

    def test_assessment_does_not_mutate_mission_contract_or_audit(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        before_mission = (self.workspace / "mission.yaml").read_text(encoding="utf-8")
        before_ledger = (self.workspace / "ledger.yaml").read_text(encoding="utf-8")
        before_events = (self.workspace / "events.jsonl").read_text(encoding="utf-8")
        self.run_cli("assess")
        self.assertEqual(before_mission, (self.workspace / "mission.yaml").read_text(encoding="utf-8"))
        self.assertEqual(before_ledger, (self.workspace / "ledger.yaml").read_text(encoding="utf-8"))
        self.assertEqual(before_events, (self.workspace / "events.jsonl").read_text(encoding="utf-8"))

    def test_plan_creates_contract_and_dispatch_updates_audit(self):
        self.initialize()
        self.plan_contract()
        self.run_cli("dispatch")
        requirement = read_yaml(self.ledger_path)["requirements"][0]
        self.assertEqual((requirement["id"], requirement["status"]), ("R-001", "in_progress"))
        self.assertEqual(requirement["acceptance"], ["Unknown issuers are rejected"])
        self.assertEqual([review["status"] for review in requirement["required_reviews"]], ["pending"] * 3)
        assignments = load_assignments(self.workspace)["assignments"]
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0]["id"], "ASG-001")
        self.assertEqual(assignments[0]["requirement_id"], "R-001")
        self.assertEqual(assignments[0]["assigned_unit"], "architect")
        self.assertEqual(assignments[0]["assignment_type"], "review")
        self.assertEqual(assignments[0]["reviewer"], "architect")
        self.assertEqual(assignments[0]["status"], "ASSIGNED")
        events = [json.loads(line)["type"] for line in (self.workspace / "events.jsonl").read_text().splitlines()]
        self.assertIn("requirement_added", events)
        self.assertIn("plan_created", events)
        self.assertIn("assignment_created", events)
        self.assertIn("dispatcher_decision", events)

    def test_dispatcher_creates_architect_review_before_developer_assignment(self):
        self.initialize_with_prompt("Create a simple REST API.")
        self.run_cli("assess")
        output = self.run_cli("dispatch")
        assignment = load_assignments(self.workspace)["assignments"][0]
        self.assertIn("Created assignment ASG-001", output)
        self.assertEqual(assignment["assigned_unit"], "architect")
        self.assertEqual(assignment["assignment_type"], "review")
        self.assertEqual(assignment["reviewer"], "architect")
        self.assertEqual(assignment["status"], "ASSIGNED")
        self.assertEqual(assignment["scoped_context"]["requirement"]["id"], assignment["requirement_id"])
        self.assertNotIn("mission_contract", assignment["scoped_context"])
        self.assertIn("acceptance", assignment["scoped_context"]["requirement"])
        self.assertIn("review evidence", assignment["required_outputs"])

    def test_developer_assignment_waits_for_architect_review_unless_explicitly_allowed(self):
        self.initialize_with_prompt("Create a simple REST API.")
        self.run_cli("assess")
        self.run_cli("dispatch", "--allow-implementation-before-reviews")
        assignment = load_assignments(self.workspace)["assignments"][0]
        self.assertEqual(assignment["assigned_unit"], "developer")
        self.assertEqual(assignment["assignment_type"], "implementation")
        self.assertIn("evidence references", assignment["required_outputs"])

    def test_execute_complete_transitions_assignment_and_dispatches_next(self):
        self.initialize_with_prompt("Create a simple REST API.")
        self.run_cli("assess")
        self.run_cli("dispatch")
        evidence = self.cwd / "evidence" / "asg-001-review.txt"
        evidence.parent.mkdir()
        evidence.write_text("architect review complete\n", encoding="utf-8")
        output = self.run_cli("execute", "--outcome", "COMPLETE", "--evidence", "evidence/asg-001-review.txt")
        assignments = load_assignments(self.workspace)["assignments"]
        self.assertEqual(assignments[0]["status"], "COMPLETE")
        self.assertEqual(assignments[0]["result_packet"]["outcome"], "COMPLETE")
        self.assertEqual(assignments[0]["evidence"], ["evidence/asg-001-review.txt"])
        self.assertEqual(assignments[1]["status"], "ASSIGNED")
        self.assertEqual(assignments[1]["assigned_unit"], "developer")
        self.assertEqual(assignments[1]["assignment_type"], "implementation")
        self.assertIn("Next Assignment: ASG-002", output)
        ledger = read_yaml(self.ledger_path)
        self.assertEqual(ledger["requirements"][0]["status"], "in_progress")
        self.assertEqual(ledger["requirements"][0]["required_reviews"][0]["status"], "completed")
        self.assertEqual(ledger["requirements"][0]["evidence"], [])

    def test_execute_complete_without_evidence_blocks_instead_of_completing(self):
        self.initialize_with_prompt("Create a simple REST API.")
        self.run_cli("assess")
        self.run_cli("dispatch")
        output = self.run_cli("execute", "--outcome", "COMPLETE")
        assignment = load_assignments(self.workspace)["assignments"][0]
        requirement = read_yaml(self.ledger_path)["requirements"][0]
        self.assertEqual(assignment["status"], "BLOCKED")
        self.assertEqual(assignment["result_packet"]["outcome"], "BLOCKED")
        self.assertEqual(assignment["abort_packet"]["failure_type"], "MISSING_CONTEXT")
        self.assertEqual(requirement["status"], "in_progress")
        self.assertNotEqual(requirement["status"], "completed")
        self.assertIn("Dispatcher Decision: retry_assignment", output)

    def test_blocked_assignment_remains_active_for_evidence_retry(self):
        self.initialize_with_prompt("Create a simple REST API.")
        self.run_cli("assess")
        self.run_cli("dispatch")
        self.run_cli("execute", "--outcome", "COMPLETE")
        blocked = load_assignments(self.workspace)["assignments"][0]
        self.assertEqual(blocked["id"], "ASG-001")
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertEqual(blocked["ownership"], "owned")

        dispatch_output = self.run_cli("dispatch")
        self.assertIn("Continuing assignment ASG-001", dispatch_output)
        self.assertEqual(len(load_assignments(self.workspace)["assignments"]), 1)

        retry_output = self.run_cli("execute", "--outcome", "COMPLETE", "--evidence", "evidence/asg-001.txt")
        assignments = load_assignments(self.workspace)["assignments"]
        assignment = assignments[0]
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignment["id"], "ASG-001")
        self.assertEqual(assignment["status"], "COMPLETE")
        self.assertEqual(assignment["ownership"], "released")
        self.assertEqual(assignment["evidence"], ["evidence/asg-001.txt"])
        self.assertNotIn("Next Assignment", retry_output)
        self.assertEqual([entry["status"] for entry in assignment["audit_history"]], [
            "CREATED", "ASSIGNED", "EXECUTING", "BLOCKED", "WAITING", "EXECUTING", "COMPLETE",
        ])
        event_types = [json.loads(line)["type"] for line in (self.workspace / "events.jsonl").read_text().splitlines()]
        for event_type in ("assignment_started", "assignment_blocked", "assignment_waiting", "assignment_resumed", "assignment_completed"):
            self.assertIn(event_type, event_types)

    def test_waiting_assignment_remains_active_for_reexecution(self):
        self.initialize_with_prompt("Create a simple REST API.")
        self.run_cli("assess")
        self.run_cli("dispatch")
        self.run_cli("execute", "--outcome", "NEEDS_CLARIFICATION")
        waiting = load_assignments(self.workspace)["assignments"][0]
        self.assertEqual(waiting["status"], "WAITING")
        self.assertEqual(waiting["ownership"], "owned")

        self.run_cli("execute", "--outcome", "COMPLETE", "--evidence", "evidence/waiting-retry.txt")
        assignments = load_assignments(self.workspace)["assignments"]
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0]["id"], "ASG-001")
        self.assertEqual(assignments[0]["status"], "COMPLETE")
        self.assertEqual(assignments[0]["evidence"], ["evidence/waiting-retry.txt"])

    def test_aborted_assignment_releases_ownership(self):
        self.initialize_with_prompt("Create a simple REST API.")
        self.run_cli("assess")
        self.run_cli("dispatch")
        self.run_cli("execute", "--outcome", "ABORTED", "--reason", "Human stopped work")
        assignment = load_assignments(self.workspace)["assignments"][0]
        self.assertEqual(assignment["status"], "ABORTED")
        self.assertEqual(assignment["ownership"], "released")
        event_types = [json.loads(line)["type"] for line in (self.workspace / "events.jsonl").read_text().splitlines()]
        self.assertIn("assignment_aborted", event_types)

    def test_tester_review_waits_for_implementation_evidence(self):
        self.initialize_with_prompt("Create a simple REST API.")
        self.run_cli("assess")
        self.run_cli("dispatch")
        self.run_cli("execute", "--outcome", "COMPLETE", "--evidence", "evidence/r1-architect.txt")
        self.run_cli("execute", "--outcome", "COMPLETE", "--evidence", "evidence/r1-implementation.txt")
        self.run_cli("execute", "--outcome", "COMPLETE", "--evidence", "evidence/r2-architect.txt")
        assignments = load_assignments(self.workspace)["assignments"]
        self.assertEqual(assignments[-1]["assigned_unit"], "developer")
        self.assertEqual(assignments[-1]["assignment_type"], "implementation")
        self.run_cli("execute", "--outcome", "COMPLETE", "--evidence", "evidence/r2-implementation.txt")
        tester_assignment = load_assignments(self.workspace)["assignments"][-1]
        self.assertEqual(tester_assignment["assigned_unit"], "tester")
        self.assertEqual(tester_assignment["assignment_type"], "review")
        self.assertEqual(tester_assignment["reviewer"], "tester")
        ledger = read_yaml(self.ledger_path)
        self.assertEqual(ledger["requirements"][1]["evidence"], ["evidence/r2-implementation.txt"])
        self.assertEqual(ledger["requirements"][1]["status"], "in_progress")

    def test_execute_failed_persists_abort_packet_and_halts_dispatch(self):
        self.initialize_with_prompt("Create a simple REST API.")
        self.run_cli("assess")
        self.run_cli("dispatch")
        self.run_cli(
            "execute",
            "--outcome", "FAILED",
            "--failure-type", "VALIDATION_FAILED",
            "--reason", "Unit tests failed",
            "--impact", "Cannot validate requirement",
            "--recommendation", "Return work to Developer",
            "--decision-action", "return_work_to_previous_unit",
        )
        assignments = load_assignments(self.workspace)["assignments"]
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0]["status"], "FAILED")
        self.assertEqual(assignments[0]["abort_packet"]["failure_type"], "VALIDATION_FAILED")
        self.assertEqual(assignments[0]["abort_packet"]["reason"], "Unit tests failed")
        self.assertEqual(assignments[0]["result_packet"]["outcome"], "FAILED")
        output = self.run_cli("dispatch")
        self.assertIn("Blocked by assignment ASG-001", output)
        self.assertIn("Decision: halt_for_blocker", output)
        self.assertEqual(len(load_assignments(self.workspace)["assignments"]), 1)
        decisions = [
            json.loads(line)["details"]
            for line in (self.workspace / "events.jsonl").read_text().splitlines()
            if json.loads(line)["type"] == "dispatcher_decision"
        ]
        self.assertTrue(any(item.get("action") == "return_work_to_previous_unit" for item in decisions))

    def test_status_displays_runtime_dashboard(self):
        self.initialize_with_prompt("Create a simple REST API.")
        self.run_cli("assess")
        self.run_cli("dispatch")
        output = self.run_cli("status")
        self.assertIn("Mission: Constraint Mission", output)
        self.assertIn("Current phase: runtime", output)
        self.assertIn("ASG-001 ASSIGNED", output)
        self.assertIn("Blocked work:", output)
        self.assertIn("Pending work:", output)
        self.assertIn("Clarifications:", output)
        self.assertIn("Recommendation: Execute active assignment ASG-001.", output)

    def test_mission_cannot_advance_without_dispatcher_assignment(self):
        self.initialize_with_prompt("Create a simple REST API.")
        self.run_cli("assess")
        with self.assertRaises(SystemExit) as raised:
            main(["execute", "--outcome", "COMPLETE"], self.cwd)
        self.assertIn("No active assignment exists. Run 'battalion dispatch' first.", str(raised.exception))
        self.assertFalse((self.workspace / "assignments.yaml").exists())

    def test_assignment_history_remains_auditable(self):
        self.initialize_with_prompt("Create a simple REST API.")
        self.run_cli("assess")
        self.run_cli("dispatch")
        self.run_cli("execute", "--outcome", "BLOCKED", "--summary", "Need dependency")
        assignment = load_assignments(self.workspace)["assignments"][0]
        self.assertEqual([entry["status"] for entry in assignment["audit_history"]], ["CREATED", "ASSIGNED", "EXECUTING", "BLOCKED"])
        self.assertTrue(all(entry["timestamp"] for entry in assignment["audit_history"]))
        events = [json.loads(line)["type"] for line in (self.workspace / "events.jsonl").read_text().splitlines()]
        self.assertIn("result_packet_received", events)
        self.assertGreaterEqual(events.count("assignment_state_changed"), 3)

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
            "## Mission", "## Mission Contract", "## Extracted Constraints", "## Clarifications", "## Clarification History",
            "## Prompt Traceability", "## Doctrine", "## Standing Agent Team", "## Requirements",
            "## Acceptance Criteria", "## Evidence Summary", "## Review Summary",
            "## Runtime Assignments", "## Assumptions", "## Risks", "## Assurance Result", "## Human Approval",
        ):
            self.assertIn(heading, report)
        self.assertIn("Unknown issuers are rejected", report)
        self.assertIn("architect=completed", report)
        self.assertIn("**Status:** GREEN", report)
        self.assertIn("Decision: PENDING", report)


if __name__ == "__main__":
    unittest.main()
