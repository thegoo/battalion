import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import yaml

from battalion.assurance import assure
from battalion.classification import ATTRIBUTE_SCHEMA_VERSION, AttributeCatalogLoader, MissionClassifier, default_attribute_catalog
from battalion.cli import main
from battalion.dispatcher import load_assignments
from battalion.mission_analyst import generate_mission_contract
from battalion.models import AssuranceResult
from battalion.storage import read_yaml, write_yaml


class FakeProcess:
    def __init__(self, return_code=0, running_polls=0):
        self.return_code = return_code
        self.running_polls = running_polls

    def poll(self):
        if self.running_polls:
            self.running_polls -= 1
            return None
        return self.return_code


def runtime_http_response(status="Healthy", timestamp="2026-07-03T02:44:00.284Z", code=200):
    body = json.dumps({"status": status, "timestamp": timestamp})
    return {
        "ok": True,
        "url": "http://127.0.0.1:48151/v1/health",
        "status_code": code,
        "headers": {"content-type": "application/json", "x-diagnostic": "full-header-value"},
        "body": body,
        "json": json.loads(body),
        "error": None,
    }


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

    def write_assurance_contract(self, acceptance, evidence=None, review_status="pending", requirement_status="completed"):
        self.initialize_with_prompt("Build a production-ready REST API with GET /v1/health returning status Healthy.")
        evidence = evidence or []
        ledger = read_yaml(self.ledger_path)
        ledger["requirements"] = [{
            "id": "R-001",
            "statement": "Implement health endpoint",
            "status": requirement_status,
            "owner": "developer",
            "acceptance": acceptance,
            "evidence": evidence,
            "assumptions": [],
            "risks": [],
            "required_reviews": [
                {"reviewer": "architect", "status": review_status},
                {"reviewer": "tester", "status": review_status},
            ],
        }]
        write_yaml(self.ledger_path, ledger)
        (self.workspace / "assessment.json").write_text(json.dumps({
            "schema_version": "battalion.assessment.v2",
            "readiness": "READY",
            "mission_attributes": ["REST_API", "HTTP_ENDPOINT"],
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (self.workspace / "mission-plan.md").write_text("# Mission\n\n## Evidence Required\n\n- Health response evidence\n", encoding="utf-8")

    def create_engineering_brief(self, architecture_references=None):
        architecture_references = architecture_references or []
        self.initialize_with_prompt("Build a command-line utility.")
        lines = [
            "# Mission",
            "",
            "## Mission Objective",
            "",
            "Build a command-line utility.",
            "",
            "## Architecture References",
            "",
        ]
        if architecture_references:
            lines.extend(f"- {reference}" for reference in architecture_references)
        else:
            lines.append("No architecture reference filenames were supplied for this mission.")
        lines.extend([
            "",
            "## Functional Requirements",
            "",
            "- Provide deterministic CLI behavior.",
            "",
        ])
        (self.workspace / "mission-plan.md").write_text("\n".join(lines), encoding="utf-8")

    def create_resolve_context(self, engineering_status="RED", checks=None):
        self.create_engineering_brief()
        (self.workspace / "assessment.json").write_text(json.dumps({
            "schema_version": "battalion.assessment.v2",
            "readiness": "READY",
            "mission_attributes": ["REST_API", "HTTP_ENDPOINT"],
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        checks = checks if checks is not None else [
            {
                "check_id": "ENG-001",
                "requirement_id": "R-001",
                "criterion": "CLI exits successfully",
                "check_type": "process_exit",
                "expected": 0,
                "observed": 0,
                "evidence": ["tests/test_cli.py"],
                "result": "VERIFIED",
                "finding": "R-001: Verified CLI exits successfully.",
                "recommendation": "No action required.",
            },
            {
                "check_id": "ENG-002",
                "requirement_id": "R-002",
                "criterion": "Response body status equals Healthy",
                "check_type": "response_body_literal",
                "expected": {"field": "status", "value": "Healthy"},
                "observed": {"field": "status", "value": "ok"},
                "evidence": ["src/app.ts"],
                "result": "FAILED",
                "finding": 'R-002: Expected response status field "Healthy"; observed "ok".',
                "recommendation": "Update implementation or engineering contract.",
            },
            {
                "check_id": "ENG-003",
                "requirement_id": "R-003",
                "criterion": "Docker image builds successfully",
                "check_type": "docker_build",
                "expected": "docker build succeeds",
                "observed": None,
                "evidence": [],
                "result": "UNABLE_TO_VERIFY",
                "finding": "R-003: Unable to verify Docker build.",
                "recommendation": "Provide Docker build evidence.",
            },
        ]
        assurance = {
            "status": "RED" if engineering_status == "RED" else "GREEN",
            "recommendation": "NO-GO" if engineering_status != "GREEN" else "GO",
            "confidence": 100,
            "findings": [check["finding"] for check in checks if check["result"] == "FAILED"],
            "clarification_counts": {"open": 0, "resolved": 0, "superseded": 0, "rejected": 0},
            "engineering_result": {
                "status": engineering_status,
                "recommendation": "NO-GO" if engineering_status != "GREEN" else "GO",
                "summary": {
                    "verified": sum(1 for check in checks if check["result"] == "VERIFIED"),
                    "failed": sum(1 for check in checks if check["result"] == "FAILED"),
                    "unable_to_verify": sum(1 for check in checks if check["result"] == "UNABLE_TO_VERIFY"),
                    "runtime_checks": 0,
                    "static_checks": len(checks),
                },
                "checks": checks,
            },
            "governance_result": {
                "status": "AMBER",
                "recommendation": "NO-GO",
                "findings": ["R-001: Required review is pending: architect"],
            },
        }
        (self.workspace / "assurance.json").write_text(json.dumps(assurance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return assurance

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

    def test_generated_yaml_artifacts_are_proper_yaml_not_json_formatted(self):
        self.initialize_with_prompt("Mission\n\nBuild a production-ready REST API.\n\nBackground\n\nOperators need a health check.")
        for name in ("mission.yaml", "agents.yaml", "ledger.yaml"):
            content = (self.workspace / name).read_text(encoding="utf-8")
            self.assertNotRegex(content.lstrip(), r"^[\[{]")
            self.assertNotIn('{\n  "', content)
            self.assertIsInstance(yaml.safe_load(content), dict)
        mission_content = (self.workspace / "mission.yaml").read_text(encoding="utf-8")
        ledger_content = (self.workspace / "ledger.yaml").read_text(encoding="utf-8")
        agents_content = (self.workspace / "agents.yaml").read_text(encoding="utf-8")
        self.assertIn("id: M-001", mission_content)
        self.assertIn("mission_prompt: |", mission_content)
        self.assertIn("  Build a production-ready REST API.", mission_content)
        self.assertNotIn("\\n", mission_content)
        self.assertIn("doctrine:", mission_content)
        self.assertIn("mission_prompt: |", ledger_content)
        self.assertIn("requirements: []", ledger_content)
        self.assertIn("agents:", agents_content)
        self.assertIn("- id: mission_analyst", agents_content)

    def test_yaml_serialization_preserves_data_and_is_deterministic(self):
        data = {
            "mission_id": "M-001",
            "requirements": [
                {
                    "id": "R-001",
                    "statement": "Validate YAML serialization",
                    "acceptance": ["artifact parses", "schema preserved"],
                    "evidence": [],
                }
            ],
        }
        first = self.cwd / "first.yaml"
        second = self.cwd / "second.yaml"
        write_yaml(first, data)
        write_yaml(second, data)
        self.assertEqual(first.read_text(encoding="utf-8"), second.read_text(encoding="utf-8"))
        self.assertEqual(read_yaml(first), data)
        self.assertEqual(yaml.safe_load(first.read_text(encoding="utf-8")), data)
        self.assertNotRegex(first.read_text(encoding="utf-8").lstrip(), r"^[\[{]")

    def test_yaml_serialization_uses_literal_blocks_for_multiline_strings(self):
        mission_prompt = (
            "Mission\n\n"
            "Build a production-ready REST API that exposes a single application health endpoint.\n\n"
            "Background\n\n"
            "Operators need a simple health check."
        )
        path = self.cwd / "mission.yaml"
        write_yaml(path, {"mission_prompt": mission_prompt})
        content = path.read_text(encoding="utf-8")
        self.assertIn("mission_prompt: |", content)
        self.assertIn("  Build a production-ready REST API", content)
        self.assertNotIn("\\n", content)
        self.assertNotIn("\\", content)
        self.assertEqual(read_yaml(path)["mission_prompt"], mission_prompt)

    def test_console_entry_point_is_registered(self):
        repository = Path(__file__).resolve().parents[1]
        pyproject = (repository / "pyproject.toml").read_text(encoding="utf-8")
        setup_compatibility = (repository / "setup.py").read_text(encoding="utf-8")
        self.assertIn('battalion = "battalion.cli:main"', pyproject)
        self.assertIn('"battalion=battalion.cli:main"', setup_compatibility)
        self.assertIn('dependencies = ["PyYAML>=6.0,<7.0", "pytest>=8,<10"]', pyproject)
        self.assertIn('install_requires=["PyYAML>=6.0,<7.0", "pytest>=8,<10"]', setup_compatibility)
        self.assertIn('version = "0.8.0"', pyproject)
        self.assertIn('version="0.8.0"', setup_compatibility)
        self.assertIn('battalion = ["attributes.yml", "playbooks.yml"]', pyproject)
        self.assertIn('package_data={"battalion": ["attributes.yml", "playbooks.yml"]}', setup_compatibility)

    def test_repository_doctrine_structure_is_documented(self):
        repository = Path(__file__).resolve().parents[1]
        expected_paths = [
            "doctrine/README.md",
            "docs/ROADMAP.md",
            "docs/repository-structure.md",
            "docs/development-workflow.md",
            "playbooks/README.md",
            "templates/README.md",
            "review-signals/README.md",
            "skills/README.md",
            "src/README.md",
            "REPOSITORY_REALIGNMENT_REPORT.md",
        ]

        for relative_path in expected_paths:
            with self.subTest(path=relative_path):
                self.assertTrue((repository / relative_path).is_file())

        doctrine = (repository / "doctrine" / "README.md").read_text(encoding="utf-8")
        self.assertIn("Battalion owns the WHAT", doctrine)
        self.assertIn("Executors own the HOW", doctrine)
        self.assertIn("Battalion remains boring", doctrine)
        self.assertIn("Battalion eats its own dogfood", doctrine)

        report = (repository / "REPOSITORY_REALIGNMENT_REPORT.md").read_text(encoding="utf-8")
        for heading in ["## Summary", "## Kept", "## Refactored", "## Removed", "## Deferred", "## Risks", "## Recommendations"]:
            self.assertIn(heading, report)
        self.assertIn("Plan Template v1 / Dogfooded Plan Artifact", report)

    def test_cli_help_executes_successfully(self):
        output = StringIO()
        with self.assertRaises(SystemExit) as raised, redirect_stdout(output):
            main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("Battalion v0.8.0", output.getvalue())

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
        self.assertIn("Assessment Result", output)
        self.assertNotIn("Readiness:", output)

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

    def test_plan_template_mission_generates_specific_contract(self):
        self.run_cli(
            "assess", "--requirement",
            "Create Plan Template v1. Render the authoritative `.battalion/mission-plan.md` artifact with required sections, doctrine boundaries, regression tests, and no pull request work.",
        )
        ledger = read_yaml(self.ledger_path)
        statements = [item["statement"] for item in ledger["requirements"]]

        self.assertIn("Render Plan Template v1 to .battalion/mission-plan.md", statements)
        self.assertIn("Include the required Plan Template v1 sections", statements)
        self.assertIn("Encode Battalion doctrine in the plan artifact", statements)
        self.assertIn("Cover Plan Template v1 with deterministic regression tests", statements)
        self.assertIn("Document the Plan Template v1 surface", statements)
        self.assertEqual(ledger["clarifications"], [])
        test_requirement = next(item for item in ledger["requirements"] if item["statement"] == "Cover Plan Template v1 with deterministic regression tests")
        self.assertTrue(any("Happy-path tests" in item for item in test_requirement["acceptance"]))
        self.assertTrue(any("Negative-path tests" in item for item in test_requirement["acceptance"]))

    def test_plan_template_output_pins_out_of_scope_boundaries(self):
        self.run_cli(
            "assess", "--requirement",
            (
                "Create Plan Template v1 by following Battalion doctrine and eating our own dogfood. "
                "Render the authoritative `.battalion/mission-plan.md` artifact with required sections, "
                "doctrine boundaries, regression tests, and no review engines, Evidence Report changes, "
                "skill systems, catalog migration, integrations, commits, or PR work."
            ),
        )
        assessment_path = self.workspace / "assessment.json"
        assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
        assessment["readiness"] = "READY_WITH_RISK"
        assessment_path.write_text(json.dumps(assessment, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        self.run_cli("plan")

        plan = (self.workspace / "mission-plan.md").read_text(encoding="utf-8")
        self.assertIn("## Out of Scope", plan)
        for item in (
            "- Review engines.",
            "- Evidence Report changes.",
            "- Skill systems.",
            "- Catalog migration.",
            "- Integrations.",
            "- Runtime template loader.",
            "- Dispatch behavior changes.",
            "- Commit, push, merge, or pull request work unless explicitly authorized.",
        ):
            self.assertIn(item, plan)

    def test_assess_requirement_retargets_existing_workspace_title(self):
        self.initialize_with_prompt("Build a health endpoint.")
        self.run_cli("assess", "--requirement", "Create Plan Template v1 for `.battalion/mission-plan.md`.")

        mission = read_yaml(self.workspace / "mission.yaml")
        self.assertEqual(mission["title"], "Create Plan Template v1 for `.battalion/mission-plan.md`.")
        self.assertEqual(mission["original_prompt"], "Create Plan Template v1 for `.battalion/mission-plan.md`.")

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

    def test_assessment_records_but_does_not_print_engineering_compatibility_disclaimer(self):
        self.initialize_with_prompt("Build a small CLI utility.")
        output = self.run_cli("assess")
        expected = (
            "Framework, SDK, runtime, library, package, platform, and standards versions must always be validated "
            "by the human engineering team for compatibility during implementation, testing, and assurance."
        )
        self.assertNotIn("Engineering Compatibility Disclaimer", output)
        self.assertNotIn(expected, output)
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
            "Run:\n\n  battalion assess --requirement \"Describe the mission\"\n\n"
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

    def test_assess_requirement_initializes_workspace_without_explicit_init(self):
        output = self.run_cli("assess", "--requirement", "Create a blank README.md to initialize the repo")

        self.assertTrue((self.workspace / "mission.yaml").is_file())
        self.assertTrue((self.workspace / "ledger.yaml").is_file())
        self.assertTrue((self.workspace / "agents.yaml").is_file())
        self.assertTrue((self.workspace / "attributes.yml").is_file())
        self.assertTrue((self.workspace / "events.jsonl").is_file())
        self.assertTrue((self.workspace / "reports").is_dir())
        self.assertTrue((self.workspace / "assessment.json").is_file())
        self.assertIn("Assessment Result", output)
        self.assertEqual(read_yaml(self.workspace / "mission.yaml")["mission_prompt"], "Create a blank README.md to initialize the repo")

    def mission_contexts(self):
        return sorted((self.workspace / "missions").glob("*/mission-context.yml"))

    def test_assess_writes_mission_context_for_clarification_required_mission(self):
        output = self.run_cli("assess", "--requirement", "Create README.md.")
        contexts = self.mission_contexts()
        self.assertEqual(len(contexts), 1)
        context = read_yaml(contexts[0])

        self.assertIn(f"Mission Context: {contexts[0].relative_to(self.cwd)}", output)
        self.assertEqual(context["schemaVersion"], 1)
        self.assertEqual(context["mission"]["status"], "clarification_required")
        self.assertTrue(context["mission"]["id"].endswith("create-readme-md"))
        self.assertEqual(context["source"]["requirement"], "Create README.md.")
        self.assertIsNone(context["source"]["requirementPath"])
        self.assertEqual(context["classification"], {"parent": "documentation", "subtype": "readme", "confidence": "high"})
        self.assertEqual(context["intent"]["summary"], "Create a README.md file.")
        self.assertEqual(context["scope"]["in"], ["documentation"])
        self.assertEqual(context["scope"]["out"], ["api", "data", "ui", "infrastructure"])
        self.assertEqual(
            [item["id"] for item in context["questions"]["unanswered"]],
            ["readme.intent", "readme.audience", "readme.content_depth"],
        )
        self.assertEqual(context["questions"]["answered"], [])
        self.assertEqual(context["assumptions"], [])
        self.assertEqual(context["constraints"], [])
        self.assertEqual(context["notes"], [])
        self.assertNotIn("readiness", str(context).lower())
        self.assertNotIn("assurance", str(context).lower())

    def test_assess_writes_understood_mission_context_without_unanswered_questions(self):
        self.run_cli("assess", "--requirement", "Create a blank README.md to initialize the repo.")
        context = read_yaml(self.mission_contexts()[0])

        self.assertEqual(context["mission"]["status"], "understood")
        self.assertEqual(context["intent"]["summary"], "Create a blank README.md file to initialize the repository.")
        self.assertEqual(context["questions"], {"unanswered": [], "answered": []})
        self.assertIn("No application code changes are required.", context["assumptions"])

    def test_assess_writes_requirement_path_for_file_input(self):
        story = self.cwd / "story.md"
        story.write_text("Create a blank README.md to initialize the repo.", encoding="utf-8")

        self.run_cli("assess", "--requirement", str(story))
        context = read_yaml(self.mission_contexts()[0])

        self.assertEqual(context["source"]["requirement"], "Create a blank README.md to initialize the repo.")
        self.assertEqual(context["source"]["requirementPath"], str(story))

    def test_assess_creates_separate_mission_directories_per_run(self):
        self.run_cli("assess", "--requirement", "Create a blank README.md to initialize the repo.")
        self.run_cli("assess", "--requirement", "Create a blank README.md to initialize the repo.")

        contexts = self.mission_contexts()
        self.assertEqual(len(contexts), 2)
        self.assertNotEqual(contexts[0].parent.name, contexts[1].parent.name)

    def test_generic_api_mission_context_persists_unanswered_api_questions(self):
        self.run_cli("assess", "--requirement", "Create API")
        context = read_yaml(self.mission_contexts()[0])

        self.assertEqual(context["mission"]["status"], "clarification_required")
        self.assertEqual(context["classification"]["parent"], "api")
        self.assertEqual(context["classification"]["subtype"], "endpoint")
        self.assertEqual(context["intent"]["summary"], "Create or update the requested API endpoint.")
        self.assertEqual(
            [item["id"] for item in context["questions"]["unanswered"]],
            ["api.purpose", "api.data_flow", "api.operations", "api.security", "api.volume"],
        )

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
        self.assertIn("Assessment Result", output)
        self.assertNotIn("Readiness:", output)
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
        self.assertIn("Questions", output)
        self.assertNotIn("Outstanding Clarifications", output)
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
        self.assertIn("Assessment Result", output)

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
            "# Mission", "## Objective", "## Doctrine and Constraints", "## Dependencies",
            "## Security Requirements", "## Operational Requirements", "## Planning Status",
            "## Assumptions", "## Risks", "## Human Decisions", "## Requirements",
            "## Deliverables", "## Out of Scope", "## Execution Strategy", "## Validation Plan",
            "## Evidence Required", "## Definition of Complete",
        ):
            self.assertIn(heading, plan)
        self.assertIn("entra-sso.md", plan)
        self.assertIn("api-security.md", plan)
        self.assertIn("GET /health returns HTTP 200", plan)
        self.assertIn("The mission exists to provide a lightweight health endpoint", plan)
        self.assertIn("Recommendations are not decisions.", plan)
        self.assertIn("Humans decide whether to proceed, accept risk, defer, reject, or approve the work.", plan)
        self.assertIn("Deterministic validation must prove each requirement by ID", plan)
        self.assertIn("- Acceptance Criteria:", plan)
        self.assertIn("Current or explicitly specified technology", plan)
        self.assertIn("Technology compatibility must be validated", plan)
        self.assertIn("Open risks:", plan)
        self.assertNotIn("Implementation must satisfy", plan)
        self.assertNotIn("This mission delivers a TypeScript Node.js service", plan)
        self.assertNotIn("READY_WITH_RISK", plan)
        self.assertNotIn("## Definition of Done", plan)
        self.assertNotIn("No explicit performance requirements were identified during assessment.", plan)
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
        self.assertIn("## Planning Status", plan)
        self.assertIn("- Open assumptions:", plan)
        self.assertNotIn("Readiness:", plan)
        self.assertNotIn("No architecture reference filenames were supplied for this mission.", plan)

    def test_plan_never_fabricates_engineering_requirements(self):
        self.initialize_with_prompt("Build a command-line utility.")
        self.run_cli("assess")
        assessment_path = self.workspace / "assessment.json"
        assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
        assessment["readiness"] = "READY_WITH_RISK"
        assessment_path.write_text(json.dumps(assessment, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.run_cli("plan")
        plan = (self.workspace / "mission-plan.md").read_text(encoding="utf-8")
        self.assertNotIn("No explicit performance requirements were identified during assessment.", plan)
        self.assertNotIn("No explicit security requirements were identified during assessment.", plan)
        self.assertNotIn("No explicit observability requirements were identified during assessment.", plan)
        self.assertNotIn("No explicit accessibility requirements were identified during assessment.", plan)
        self.assertNotIn("Kubernetes", plan)
        self.assertNotIn("PostgreSQL", plan)
        self.assertNotIn("OAuth", plan)

    def test_dispatch_unsupported_executor_fails(self):
        self.create_engineering_brief()
        with self.assertRaises(SystemExit) as raised:
            main(["dispatch", "--executor", "banana"], self.cwd)
        self.assertIn("Unsupported executor: banana", str(raised.exception))
        self.assertIn("Supported executors: claude-code, codex, copilot", str(raised.exception))

    def test_dispatch_missing_mission_plan_fails(self):
        self.initialize_with_prompt("Build a command-line utility.")
        with self.assertRaises(SystemExit) as raised:
            main(["dispatch", "--executor", "codex"], self.cwd)
        self.assertIn("Run battalion plan first", str(raised.exception))

    def test_dispatch_missing_architecture_reference_filename_fails(self):
        self.create_engineering_brief(["architecture.md"])
        with self.assertRaises(SystemExit) as raised:
            main(["dispatch", "--executor", "codex"], self.cwd)
        self.assertIn("Architecture reference filename not found: architecture.md", str(raised.exception))

    def test_dispatch_generates_executor_wrapper_and_preserves_brief(self):
        self.create_engineering_brief(["architecture.md"])
        (self.cwd / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
        before = (self.workspace / "mission-plan.md").read_text(encoding="utf-8")
        with patch("battalion.executor_dispatch.subprocess.Popen", return_value=FakeProcess()) as runner:
            output = self.run_cli("dispatch", "--executor", "codex")

        after = (self.workspace / "mission-plan.md").read_text(encoding="utf-8")
        self.assertEqual(before, after)
        self.assertIn("Dispatching engineering mission...", output)
        self.assertIn("Executor: Codex", output)
        self.assertIn("Mode: standard", output)
        self.assertIn("Mission: .battalion/mission-plan.md", output)
        self.assertIn("Dispatch package: DSP-001", output)
        self.assertIn("Starting executor...", output)
        self.assertIn("Dispatch complete.", output)
        self.assertIn("Next:\nbattalion assure", output)
        package = self.workspace / "dispatches" / "DSP-001"
        instructions = (package / "instructions.md").read_text(encoding="utf-8")
        self.assertIn("Battalion Dispatch Package — Codex", instructions)
        self.assertIn("- Do not modify `.battalion/mission-plan.md`.", instructions)
        self.assertIn("- Do not invoke `battalion assure`", instructions)
        self.assertIn("- architecture.md", instructions)
        self.assertIn("```markdown\n# Mission", instructions)
        self.assertIn("Build a command-line utility.", instructions)
        runner.assert_called_once()
        self.assertEqual(runner.call_args.kwargs["cwd"], self.cwd)
        self.assertEqual(runner.call_args.args[0][0:2], ["codex", "exec"])

    def test_dispatch_records_metadata_and_audit_events(self):
        self.create_engineering_brief()
        with patch("battalion.executor_dispatch.subprocess.Popen", return_value=FakeProcess()):
            self.run_cli("dispatch", "--executor", "claude-code")
        metadata = read_yaml(self.workspace / "dispatches" / "DSP-001" / "metadata.yaml")
        self.assertEqual(metadata["dispatch_id"], "DSP-001")
        self.assertEqual(metadata["executor"], "claude-code")
        self.assertEqual(metadata["executor_name"], "Claude Code")
        self.assertEqual(metadata["status"], "COMPLETED")
        self.assertEqual(metadata["return_code"], 0)
        self.assertEqual(metadata["mission_plan"], "mission-plan.md")
        self.assertEqual(metadata["instructions"], "instructions.md")
        self.assertEqual(metadata["next_step"], "Run battalion assure after reviewing executor output.")
        metadata_content = (self.workspace / "dispatches" / "DSP-001" / "metadata.yaml").read_text(encoding="utf-8")
        self.assertNotRegex(metadata_content.lstrip(), r"^[\[{]")
        self.assertIn("dispatch_id: DSP-001", metadata_content)
        self.assertIn("executor: claude-code", metadata_content)
        self.assertEqual(yaml.safe_load(metadata_content), metadata)
        events = [json.loads(line) for line in (self.workspace / "events.jsonl").read_text().splitlines()]
        self.assertTrue(any(event["type"] == "dispatch_started" for event in events))
        self.assertTrue(any(event["type"] == "dispatch_completed" for event in events))

    def test_dispatch_auto_mode_allows_local_work_but_blocks_source_control_authority(self):
        self.create_engineering_brief()
        with patch("battalion.executor_dispatch.subprocess.Popen", return_value=FakeProcess()) as runner:
            self.run_cli("dispatch", "--executor", "codex", "--mode", "auto")
        command = runner.call_args.args[0]
        self.assertIn("--full-auto", command)
        metadata = read_yaml(self.workspace / "dispatches" / "DSP-001" / "metadata.yaml")
        self.assertEqual(metadata["mode"], "auto")
        instructions = (self.workspace / "dispatches" / "DSP-001" / "instructions.md").read_text(encoding="utf-8")
        self.assertIn("Auto mode is enabled.", instructions)
        self.assertIn("creating files, modifying files, switching local branches when required, running builds, executing tests", instructions)
        self.assertIn("does not authorize git commit, git push, pull request creation, merge operations, deployment, or remote repository modification", instructions)

    def test_dispatch_executor_selection_supports_codex_claude_and_copilot(self):
        self.create_engineering_brief()
        selections = [
            ("codex", ["codex", "exec"]),
            ("claude-code", ["claude", "-p"]),
            ("copilot", ["gh", "copilot", "suggest"]),
        ]
        for index, (executor, command_prefix) in enumerate(selections, start=1):
            with self.subTest(executor=executor):
                with patch("battalion.executor_dispatch.subprocess.Popen", return_value=FakeProcess()) as runner:
                    self.run_cli("dispatch", "--executor", executor)
                self.assertEqual(runner.call_args.args[0][:len(command_prefix)], command_prefix)
                metadata = read_yaml(self.workspace / "dispatches" / f"DSP-{index:03d}" / "metadata.yaml")
                self.assertEqual(metadata["executor"], executor)

    def test_dispatch_reports_failed_executor_completion_without_assurance(self):
        self.create_engineering_brief()
        with patch("battalion.executor_dispatch.subprocess.Popen", return_value=FakeProcess(return_code=7)):
            output = self.run_cli("dispatch", "--executor", "copilot")
        metadata = read_yaml(self.workspace / "dispatches" / "DSP-001" / "metadata.yaml")
        self.assertEqual(metadata["status"], "FAILED")
        self.assertEqual(metadata["return_code"], 7)
        self.assertIn("Dispatch failed.", output)
        self.assertIn("Executor: GitHub Copilot CLI", output)
        self.assertIn("Failure reason: Executor exited with a non-zero status.", output)
        self.assertIn("Exit code: 7", output)
        self.assertIn("Recommended action: Review executor output above, correct the issue, and retry dispatch.", output)
        self.assertFalse((self.workspace / "reports" / "mission-report.md").exists())

    def test_dispatch_command_not_found_prints_actionable_failure_summary(self):
        self.create_engineering_brief()
        output = StringIO()
        with (
            patch("battalion.executor_dispatch.subprocess.Popen", side_effect=FileNotFoundError()),
            self.assertRaises(SystemExit) as raised,
            redirect_stdout(output),
        ):
            main(["dispatch", "--executor", "codex"], self.cwd)
        rendered = output.getvalue()
        self.assertIn("Dispatch failed.", rendered)
        self.assertIn("Executor: Codex", rendered)
        self.assertIn("Failure reason: Executor command not found: codex", rendered)
        self.assertIn("Exit code: unavailable", rendered)
        self.assertIn("Recommended action: Install or configure Codex and try again.", rendered)
        self.assertIn("Install or configure Codex", str(raised.exception))

    def test_dispatch_heartbeat_is_displayed_while_executor_is_running(self):
        self.create_engineering_brief()
        with (
            patch("battalion.executor_dispatch.subprocess.Popen", return_value=FakeProcess(running_polls=1)),
            patch("battalion.executor_dispatch.time.monotonic", side_effect=[0, 31, 31.2, 31.4]),
            patch("battalion.executor_dispatch.time.sleep"),
        ):
            output = self.run_cli("dispatch", "--executor", "codex")
        self.assertIn("Still executing...", output)
        self.assertIn("Elapsed: 31 seconds", output)

    def test_dispatch_forwards_executor_output_without_modification_where_testable(self):
        self.create_engineering_brief()

        def fake_invoke(command, cwd, started, heartbeat_interval, poll_interval, output):
            output("executor says: build started")
            output("executor says: build complete")
            return 0

        with patch("battalion.executor_dispatch.invoke_executor", side_effect=fake_invoke):
            output = self.run_cli("dispatch", "--executor", "codex")
        self.assertIn("executor says: build started", output)
        self.assertIn("executor says: build complete", output)

    def test_resolve_requires_assurance_report(self):
        self.create_engineering_brief()
        (self.workspace / "assessment.json").write_text(json.dumps({"readiness": "READY"}, indent=2) + "\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as raised:
            main(["resolve"], self.cwd)
        self.assertIn("Run battalion assure", str(raised.exception))
        self.assertFalse((self.workspace / "resolutions").exists())

    def test_resolve_green_assurance_produces_no_package(self):
        verified = [{
            "check_id": "ENG-001",
            "requirement_id": "R-001",
            "criterion": "CLI exits successfully",
            "check_type": "process_exit",
            "expected": 0,
            "observed": 0,
            "evidence": ["tests/test_cli.py"],
            "result": "VERIFIED",
            "finding": "R-001: Verified CLI exits successfully.",
            "recommendation": "No action required.",
        }]
        self.create_resolve_context("GREEN", verified)
        output = self.run_cli("resolve")
        self.assertIn("No engineering failures require resolution.", output)
        self.assertFalse((self.workspace / "resolutions").exists())

    def test_resolve_package_contains_only_failed_engineering_findings(self):
        self.create_resolve_context()
        output = self.run_cli("resolve")
        self.assertIn("Mission Resolve package created.", output)
        self.assertIn("Resolution: RES-001", output)
        package = self.workspace / "resolutions" / "RES-001"
        instructions = (package / "instructions.md").read_text(encoding="utf-8")
        metadata = read_yaml(package / "metadata.yaml")
        self.assertIn("Battalion Resolve Package", instructions)
        self.assertIn("Build a command-line utility.", instructions)
        self.assertIn("Response body status equals Healthy", instructions)
        self.assertIn('"value": "Healthy"', instructions)
        self.assertIn('"value": "ok"', instructions)
        self.assertIn("src/app.ts", instructions)
        self.assertIn("Correct the implementation.", instructions)
        self.assertIn("Do not modify the mission.", instructions)
        self.assertIn("Do not modify acceptance criteria.", instructions)
        self.assertIn("Do not weaken tests.", instructions)
        self.assertIn("```markdown\n# Mission", instructions)
        self.assertNotIn("CLI exits successfully", instructions)
        self.assertNotIn("Docker image builds successfully", instructions)
        self.assertNotIn("Required review is pending", instructions)
        self.assertEqual(metadata["resolution_id"], "RES-001")
        self.assertEqual(metadata["status"], "PENDING")
        self.assertEqual(metadata["mission"], "mission.yaml")
        self.assertEqual(metadata["mission_plan"], "mission-plan.md")
        self.assertEqual(metadata["assurance_report"], "assurance.json")
        self.assertEqual(len(metadata["failed_findings"]), 1)
        self.assertEqual(metadata["failed_findings"][0]["check_id"], "ENG-002")

    def test_resolve_executor_invocation_matches_dispatch(self):
        self.create_resolve_context()
        with patch("battalion.executor_dispatch.subprocess.Popen", return_value=FakeProcess()) as runner:
            output = self.run_cli("resolve", "--executor", "codex")
        self.assertIn("Starting executor...", output)
        self.assertIn("Resolve complete.", output)
        runner.assert_called_once()
        self.assertEqual(runner.call_args.kwargs["cwd"], self.cwd)
        self.assertEqual(runner.call_args.args[0][0:2], ["codex", "exec"])
        self.assertIn("Battalion resolve package", runner.call_args.args[0][-1])
        metadata = read_yaml(self.workspace / "resolutions" / "RES-001" / "metadata.yaml")
        self.assertEqual(metadata["executor"], "codex")
        self.assertEqual(metadata["executor_name"], "Codex")
        self.assertEqual(metadata["status"], "COMPLETED")
        self.assertEqual(metadata["return_code"], 0)
        self.assertEqual(metadata["next_step"], "Run battalion assure after reviewing executor corrections.")

    def test_resolve_package_generation_is_deterministic(self):
        self.create_resolve_context()
        self.run_cli("resolve")
        first = (self.workspace / "resolutions" / "RES-001" / "instructions.md").read_text(encoding="utf-8")
        first_metadata = read_yaml(self.workspace / "resolutions" / "RES-001" / "metadata.yaml")
        self.run_cli("resolve")
        second = (self.workspace / "resolutions" / "RES-002" / "instructions.md").read_text(encoding="utf-8")
        second_metadata = read_yaml(self.workspace / "resolutions" / "RES-002" / "metadata.yaml")
        self.assertEqual(first, second)
        self.assertEqual(first_metadata["failed_findings"], second_metadata["failed_findings"])
        self.assertEqual(first_metadata["assurance_sha256"], second_metadata["assurance_sha256"])

    def test_plan_review_reports_only_doctrine_approved_questions(self):
        self.initialize_with_prompt("Create Plan Review v1.")
        (self.workspace / "mission-plan.md").write_text(
            "\n".join([
                "# Mission",
                "",
                "## Requirements",
                "",
                "### R-001",
                "",
                "- Statement: Render review output",
                "- Acceptance Criteria:",
                "  - Review output answers: What did the Plan require?",
                "  - Review output answers: What evidence exists?",
                "",
                "### R-002",
                "",
                "- Statement: Preserve human authority",
                "- Acceptance Criteria:",
                "  - Review output does not approve, reject, merge, deploy, authorize execution, or make the human decision.",
                "",
                "## Out of Scope",
                "",
                "- Evidence Report v1.",
                "- Skills.",
            ]),
            encoding="utf-8",
        )
        evidence = self.cwd / "evidence" / "review.txt"
        evidence.parent.mkdir()
        evidence.write_text(
            "R-001 PASS\n"
            "Review output answers: What did the Plan require?\n"
            "Review output answers: What evidence exists?\n"
            "R-002 PASS\n",
            encoding="utf-8",
        )

        output = self.run_cli("review", "--evidence", "evidence/review.txt")
        review = (self.workspace / "plan-review.md").read_text(encoding="utf-8")
        data = json.loads((self.workspace / "plan-review.json").read_text(encoding="utf-8"))

        for heading in (
            "## What did the Plan require?",
            "## What evidence exists?",
            "## What matches?",
            "## What does not match?",
            "## What could not be verified?",
        ):
            self.assertIn(heading, review)
        self.assertEqual(data["schema_version"], "battalion.plan_review.v1")
        self.assertEqual(len(data["matches"]), 3)
        self.assertEqual(data["does_not_match"], [])
        self.assertEqual(data["could_not_verify"], [])
        self.assertIn("Plan Review reports facts and advisory recommendations.", review)
        self.assertIn("Humans make engineering decisions.", review)
        self.assertNotIn("Decision: APPROVED", review)
        self.assertNotIn("Decision: REJECTED", review)
        self.assertNotIn("Decision: MERGE", review)
        self.assertNotIn("Decision: DEPLOY", review)
        self.assertIn("Plan Review", output)

    def test_plan_review_covers_mismatch_and_unable_to_verify(self):
        self.initialize_with_prompt("Create Plan Review v1.")
        (self.workspace / "mission-plan.md").write_text(
            "\n".join([
                "# Mission",
                "",
                "## Requirements",
                "",
                "### R-001",
                "",
                "- Statement: Compare evidence",
                "- Acceptance Criteria:",
                "  - Matching criterion.",
                "",
                "### R-002",
                "",
                "- Statement: Report mismatch",
                "- Acceptance Criteria:",
                "  - Mismatching criterion.",
                "",
                "### R-003",
                "",
                "- Statement: Report unknowns",
                "- Acceptance Criteria:",
                "  - Missing criterion.",
            ]),
            encoding="utf-8",
        )
        evidence = self.cwd / "evidence" / "review.txt"
        evidence.parent.mkdir()
        evidence.write_text("Matching criterion.\nR-002 FAILED: observed mismatch.\n", encoding="utf-8")

        self.run_cli("review", "--evidence", "evidence/review.txt")
        data = json.loads((self.workspace / "plan-review.json").read_text(encoding="utf-8"))
        review = (self.workspace / "plan-review.md").read_text(encoding="utf-8")

        self.assertEqual([item["requirement_id"] for item in data["matches"]], ["R-001"])
        self.assertEqual([item["requirement_id"] for item in data["does_not_match"]], ["R-002"])
        self.assertEqual([item["requirement_id"] for item in data["could_not_verify"]], ["R-003"])
        self.assertIn("## What does not match?", review)
        self.assertIn("## What could not be verified?", review)

    def test_plan_review_records_out_of_scope_evidence_without_reviewing_it_as_plan_work(self):
        self.initialize_with_prompt("Create Plan Review v1.")
        (self.workspace / "mission-plan.md").write_text(
            "\n".join([
                "# Mission",
                "",
                "## Requirements",
                "",
                "### R-001",
                "",
                "- Statement: Keep review narrow",
                "- Acceptance Criteria:",
                "  - Plan Review v1 stays deterministic.",
                "",
                "## Out of Scope",
                "",
                "- Evidence Report v1.",
                "- Skills.",
                "- Integrations.",
                "- Catalog migration.",
                "- Executor changes.",
                "- Autonomous gating.",
            ]),
            encoding="utf-8",
        )
        evidence = self.cwd / "evidence" / "review.txt"
        evidence.parent.mkdir()
        evidence.write_text(
            "Plan Review v1 stays deterministic.\n"
            "Implemented Evidence Report v1.\n"
            "Added catalog migration.\n",
            encoding="utf-8",
        )

        self.run_cli("review", "--evidence", "evidence/review.txt")
        data = json.loads((self.workspace / "plan-review.json").read_text(encoding="utf-8"))

        self.assertEqual([item["requirement_id"] for item in data["matches"]], ["R-001"])
        self.assertEqual(
            [item["scope_item"] for item in data["out_of_scope_evidence"]],
            ["Evidence Report v1", "Catalog migration"],
        )

    def test_plan_review_reports_pr_decision_evidence_without_manual_artifact_edits(self):
        self.initialize_with_prompt("Improve human decision UX.")
        (self.workspace / "mission-plan.md").write_text(
            "\n".join([
                "# Mission",
                "",
                "## Requirements",
                "",
                "### R-001",
                "",
                "- Statement: Report human decision sources",
                "- Acceptance Criteria:",
                "  - Review output reports PR approval as human review evidence.",
                "  - Review output reports PR merge as authorization evidence.",
                "  - Manual artifact updates remain an optional fallback.",
            ]),
            encoding="utf-8",
        )
        evidence = self.cwd / "evidence" / "review.txt"
        evidence.parent.mkdir()
        evidence.write_text(
            "R-001 PASS\n"
            "Review output reports PR approval as human review evidence.\n"
            "Review output reports PR merge as authorization evidence.\n"
            "Manual artifact updates remain an optional fallback.\n",
            encoding="utf-8",
        )

        output = self.run_cli(
            "review",
            "--evidence", "evidence/review.txt",
            "--decision-evidence", "pr-approval=observed:PR #28 approved by human reviewer",
            "--decision-evidence", "pr-merge=executed:PR #28 merged by repository maintainer",
        )
        review = (self.workspace / "plan-review.md").read_text(encoding="utf-8")
        data = json.loads((self.workspace / "plan-review.json").read_text(encoding="utf-8"))

        self.assertIn("PR approval: OBSERVED", output)
        self.assertIn("PR merge: EXECUTED", output)
        self.assertIn("Human decision evidence:", review)
        self.assertIn("PR approval [OBSERVED]", review)
        self.assertIn("PR merge [EXECUTED]", review)
        self.assertIn("Manual artifact updates are optional fallback evidence for workflows without a pull request.", review)
        self.assertEqual(
            [(item["source"], item["status"]) for item in data["human_decision_evidence"]],
            [("pr-approval", "OBSERVED"), ("pr-merge", "EXECUTED")],
        )
        self.assertNotIn("manually edit", review.lower())
        self.assertNotIn("Decision: APPROVED", review)
        self.assertNotIn("Decision: MERGE", review)

    def test_plan_review_defaults_manual_artifact_to_optional_fallback(self):
        self.initialize_with_prompt("Improve human decision UX.")
        (self.workspace / "mission-plan.md").write_text(
            "\n".join([
                "# Mission",
                "",
                "## Requirements",
                "",
                "### R-001",
                "",
                "- Statement: Keep manual record optional",
                "- Acceptance Criteria:",
                "  - Manual artifact updates remain an optional fallback.",
            ]),
            encoding="utf-8",
        )

        self.run_cli("review")
        review = (self.workspace / "plan-review.md").read_text(encoding="utf-8")
        data = json.loads((self.workspace / "plan-review.json").read_text(encoding="utf-8"))

        self.assertIn("Manual artifact update [OPTIONAL_FALLBACK]", review)
        self.assertIn("Passing tests, implementation completion, and Battalion recommendations are never human approval.", review)
        self.assertEqual(data["human_decision_evidence"][0]["source"], "manual-artifact")
        self.assertEqual(data["human_decision_evidence"][0]["status"], "OPTIONAL_FALLBACK")

    def test_plan_template_human_decisions_support_pr_evidence_sources(self):
        self.initialize_with_prompt(
            "Implement Human Decision UX v1. PR approval may satisfy review evidence. "
            "PR merge may satisfy authorization evidence. Manual artifact updates are fallback only."
        )
        self.run_cli("assess")
        self.run_cli("plan")
        plan = (self.workspace / "mission-plan.md").read_text(encoding="utf-8")

        self.assertIn("manual Plan or evidence edits are not the default completion mechanism", plan)
        self.assertIn("PR approval may satisfy human review evidence when observed.", plan)
        self.assertIn("PR merge may satisfy authorization or completion evidence when observed.", plan)
        self.assertIn("Manual artifact updates remain an optional fallback for workflows without a PR.", plan)
        self.assertIn("Passing tests, implementation completion, and Battalion recommendations must never be inferred as human approval.", plan)

    def test_assessment_generates_json_and_markdown(self):
        self.initialize_with_prompt(self.CONSTRAINT_PROMPT)
        self.run_cli("assess")
        output = self.run_cli("assess")
        self.assertIn("Assessment Result", output)
        self.assertIn("Mission Type", output)
        self.assertIn("Mission Intent", output)
        self.assertIn("Understanding", output)
        self.assertIn("Questions", output)
        self.assertIn("Recommendation\nProceed to planning.", output)
        self.assertNotIn("Readiness:", output)
        self.assertNotIn("Engineering Compatibility Disclaimer", output)
        self.assertNotIn("Mission Classification", output)
        self.assertNotIn("Primary Findings", output)
        self.assertNotIn("Outstanding Clarifications", output)
        self.assertNotIn("Proceed to Implementation", output)
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

    def test_assess_requirement_inline_api_endpoint_proceeds_with_assumptions(self):
        output = self.run_cli("assess", "--requirement", "Create an API endpoint to retrieve customer email by customer id.")
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))

        self.assertIn("PROCEED_WITH_ASSUMPTIONS", output)
        self.assertEqual(assessment["assessment_outcome"], "PROCEED_WITH_ASSUMPTIONS")
        self.assertEqual(assessment["requirement_assessment"]["detected_scale"], "task")
        self.assertIn("api", assessment["requirement_assessment"]["detected_domains"])
        self.assertIn("Existing API conventions apply.", assessment["requirement_assessment"]["assumptions"])
        self.assertEqual(assessment["requirement_assessment"]["questions"], [])

    def test_assess_requirement_file_input(self):
        story = self.cwd / "story.md"
        story.write_text("Update README with installation instructions.", encoding="utf-8")

        self.run_cli("assess", "--requirement", str(story))
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))

        self.assertEqual(assessment["assessment_outcome"], "PROCEED_WITH_ASSUMPTIONS")
        self.assertEqual(assessment["requirement_assessment"]["detected_domains"], ["documentation"])
        self.assertEqual(assessment["requirement_assessment"]["questions"], [])

    def test_assess_requirement_data_only_does_not_require_ui_or_api(self):
        self.run_cli("assess", "--requirement", "Add EmailAddress column to Customer table.")
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))

        self.assertEqual(assessment["assessment_outcome"], "PROCEED_WITH_ASSUMPTIONS")
        self.assertEqual(assessment["requirement_assessment"]["detected_domains"], ["data"])
        self.assertIn("ui", assessment["requirement_assessment"]["out_of_scope"])
        self.assertIn("api", assessment["requirement_assessment"]["out_of_scope"])
        self.assertEqual(assessment["requirement_assessment"]["questions"], [])

    def test_assess_requirement_search_ambiguity_requires_clarification(self):
        self.run_cli("assess", "--requirement", "Add customer search.")
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))

        self.assertEqual(assessment["assessment_outcome"], "CLARIFICATION_REQUIRED")
        self.assertIn("Should search be exact, partial, fuzzy, or full text?", assessment["requirement_assessment"]["questions"])
        self.assertIn("Which fields should customer search include?", assessment["requirement_assessment"]["questions"])

    def test_assess_requirement_ui_only_minimizes_questions(self):
        self.run_cli("assess", "--requirement", "Add a settings page with a save button.")
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))

        self.assertEqual(assessment["assessment_outcome"], "PROCEED_WITH_ASSUMPTIONS")
        self.assertEqual(assessment["requirement_assessment"]["detected_domains"], ["ui"])
        self.assertEqual(assessment["requirement_assessment"]["questions"], [])

    def test_assess_cli_uses_requirement_argument(self):
        parser_output = StringIO()
        parser_error = StringIO()
        with self.assertRaises(SystemExit) as raised, redirect_stdout(parser_output), redirect_stderr(parser_error):
            main(["assess", "--prompt", "Create a task."], self.cwd)

        self.assertNotEqual(raised.exception.code, 0)
        self.run_cli("assess", "--requirement", "Update README with installation instructions.")
        self.assertEqual(read_yaml(self.workspace / "mission.yaml")["mission_prompt"], "Update README with installation instructions.")

    def test_assess_readme_cli_output_is_only_mission_assessment(self):
        output = self.run_cli("assess", "--requirement", "Create a README.md")

        self.assertIn("Assessment Result\n-----------------\nCLARIFICATION_REQUIRED", output)
        self.assertIn("Confidence: High", output)
        self.assertIn("Mission Type\nDocumentation / README", output)
        self.assertIn("Mission Intent\nCreate a README.md file.", output)
        self.assertIn("1. What is the intent of this README?", output)
        self.assertIn("2. Who is the intended audience?", output)
        self.assertIn("3. Should this be blank, lightweight, or detailed?", output)
        self.assertIn("Recommendation\nAnswer mission questions before planning.", output)
        self.assertIn("Artifacts\n- Mission Context: .battalion/missions/", output)
        self.assertIn("- Assessment Report: .battalion/missions/", output)
        self.assertNotIn("Readiness", output)
        self.assertNotIn("Engineering Compatibility Disclaimer", output)
        self.assertNotIn("Mission Classification", output)
        self.assertNotIn("Primary Findings", output)
        self.assertNotIn("Outstanding Clarifications", output)
        self.assertNotIn("Proceed to Implementation", output)
        self.assertNotIn("Deployment environment", output)
        self.assertNotIn("Architecture", output)
        self.assertNotIn("Engineering obligation", output)
        self.assertNotIn("API", output)
        self.assertNotIn("Data", output)
        self.assertNotIn("Infrastructure", output)

    def test_assess_blank_readme_does_not_ask_unnecessary_questions(self):
        output = self.run_cli("assess", "--requirement", "Create a blank README.md to initialize the repo")

        self.assertIn("Assessment Result\n-----------------\nPROCEED_WITH_ASSUMPTIONS", output)
        self.assertIn("Mission Type\nDocumentation / README", output)
        self.assertIn("Mission Intent\nCreate a blank README.md file to initialize the repository.", output)
        self.assertIn("Questions\n- None", output)
        self.assertIn("Recommendation\nProceed to planning.", output)
        self.assertIn("Artifacts\n- Mission Context: .battalion/missions/", output)

    def test_assess_api_cli_output_excludes_unrelated_later_phase_concerns(self):
        output = self.run_cli("assess", "--requirement", "Create GET /customers/{id}/email")

        self.assertIn("Mission Type\nAPI / Endpoint", output)
        self.assertIn("Existing data model contains the referenced field or entity.", output)
        self.assertIn("Existing authentication middleware applies unless the requirement says otherwise.", output)
        self.assertIn("Questions\n- None", output)
        self.assertIn("Recommendation\nProceed to planning.", output)
        self.assertIn("Artifacts\n- Mission Context: .battalion/missions/", output)
        self.assertNotIn("deployment", output.lower())
        self.assertNotIn("runtime", output.lower())
        self.assertNotIn("ci/cd", output.lower())
        self.assertNotIn("architecture", output.lower())
        self.assertNotIn("framework", output.lower())

    def test_playbook_classifies_data_model_requirements(self):
        output = self.run_cli("assess", "--requirement", "Add EmailAddress column to Customer.")
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))

        self.assertIn("Mission Type\nData / Model", output)
        self.assertEqual(assessment["requirement_assessment"]["mission_type"]["key"], "data.model")
        self.assertIn("Questions\n- None", output)
        self.assertNotIn("frontend", output.lower())

    def test_playbook_classifies_deployment_requirements(self):
        output = self.run_cli("assess", "--requirement", "Deploy application to Azure App Service.")
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))

        self.assertIn("Mission Type\nInfrastructure / Deployment", output)
        self.assertEqual(assessment["requirement_assessment"]["mission_type"]["key"], "infrastructure.deployment")
        self.assertIn("What deployment artifact should be produced?", output)
        self.assertIn("What rollback behavior is required?", output)

    def test_playbook_classifies_adr_requirements(self):
        output = self.run_cli("assess", "--requirement", "Create ADR for database choice.")
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))

        self.assertIn("Mission Type\nDocumentation / ADR", output)
        self.assertEqual(assessment["requirement_assessment"]["mission_type"]["key"], "documentation.adr")
        self.assertIn("What context led to this decision?", output)

    def test_playbook_classifies_open_knowledge_requirements(self):
        output = self.run_cli("assess", "--requirement", "Create open knowledge framework overview.")
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))

        self.assertIn("Mission Type\nDocumentation / Open Knowledge", output)
        self.assertEqual(assessment["requirement_assessment"]["mission_type"]["key"], "documentation.open_knowledge")
        self.assertIn("Who is the intended audience?", output)

    def test_testing_playbook_accepts_existing_regression_tests_as_location(self):
        output = self.run_cli("assess", "--requirement", "Create regression tests in tests/test_cli.py to validate Plan Template v1 output.")
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))

        self.assertEqual(assessment["requirement_assessment"]["mission_type"]["key"], "testing.automated")
        self.assertNotIn("Where should the tests live?", output)

    def test_playbook_tie_returns_single_mission_type_clarification(self):
        output = self.run_cli("assess", "--requirement", "Create README API")
        assessment = json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))

        self.assertIn("Mission Type\nAmbiguous Mission Type", output)
        self.assertEqual(assessment["assessment_outcome"], "CLARIFICATION_REQUIRED")
        self.assertEqual(assessment["requirement_assessment"]["mission_type"]["tie_candidates"], ["api.endpoint", "documentation.readme"])
        self.assertEqual(len(assessment["requirement_assessment"]["questions"]), 1)
        self.assertIn("Which mission type applies: api.endpoint, documentation.readme?", output)

    def mission_scoped_assessment(self, requirement):
        self.run_cli("assess", "--requirement", requirement)
        return json.loads((self.workspace / "assessment.json").read_text(encoding="utf-8"))

    def unsatisfied_assessment_findings(self, assessment):
        return [item for item in assessment["discipline_findings"] if item["status"] == "NEEDS_CLARIFICATION"]

    def finding_text(self, findings):
        return " ".join(f"{item['discipline']} {item['obligation']} {item['recommendation']}" for item in findings)

    def test_mission_scoped_readme_assessment_has_no_project_readiness_findings(self):
        assessment = self.mission_scoped_assessment("Create README.md")
        findings = self.unsatisfied_assessment_findings(assessment)
        text = self.finding_text(findings)

        self.assertEqual(assessment["requirement_assessment"]["detected_domains"], ["documentation"])
        self.assertNotIn("Deployment environment", text)
        self.assertNotIn("Runtime selection", text)
        self.assertNotIn("Technology stack", text)
        self.assertNotIn("framework", text.lower())

    def test_mission_scoped_data_assessment_has_no_ui_or_deployment_findings(self):
        assessment = self.mission_scoped_assessment("Add EmailAddress column to Customer.")
        findings = self.unsatisfied_assessment_findings(assessment)
        text = self.finding_text(findings)

        self.assertEqual(assessment["requirement_assessment"]["detected_domains"], ["data"])
        self.assertNotIn("UX", text)
        self.assertNotIn("Deployment environment", text)
        self.assertNotIn("frontend", text.lower())

    def test_mission_scoped_api_assessment_assumes_adjacent_context_without_frontend_findings(self):
        assessment = self.mission_scoped_assessment("Create GET /customers/{id}/email.")
        findings = self.unsatisfied_assessment_findings(assessment)
        text = self.finding_text(findings)

        self.assertIn("api", assessment["requirement_assessment"]["detected_domains"])
        self.assertIn("Existing data model contains the referenced field or entity.", assessment["requirement_assessment"]["assumptions"])
        self.assertIn("Existing authentication middleware applies unless the requirement says otherwise.", assessment["requirement_assessment"]["assumptions"])
        self.assertNotIn("frontend", text.lower())
        self.assertNotIn("Deployment environment", text)
        self.assertEqual(assessment["requirement_assessment"]["questions"], [])

    def test_mission_scoped_ui_assessment_has_no_database_or_deployment_findings(self):
        assessment = self.mission_scoped_assessment("Update login page styling.")
        findings = self.unsatisfied_assessment_findings(assessment)
        text = self.finding_text(findings)

        self.assertIn("ui", assessment["requirement_assessment"]["detected_domains"])
        self.assertNotIn("database", text.lower())
        self.assertNotIn("Deployment environment", text)

    def test_mission_scoped_deployment_assessment_keeps_deployment_findings(self):
        assessment = self.mission_scoped_assessment("Deploy application to Azure App Service.")
        findings = assessment["discipline_findings"]

        self.assertIn("infra", assessment["requirement_assessment"]["detected_domains"])
        self.assertTrue(any(item["discipline"] == "DevOps" and item["obligation"] == "Deployment environment identified" for item in findings))

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
        assignments_content = (self.workspace / "assignments.yaml").read_text(encoding="utf-8")
        self.assertNotRegex(assignments_content.lstrip(), r"^[\[{]")
        self.assertIn("assignments:", assignments_content)
        self.assertIn("- id: ASG-001", assignments_content)
        self.assertEqual(yaml.safe_load(assignments_content)["assignments"][0]["id"], "ASG-001")
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

    def test_assurance_generates_json_and_markdown_artifacts(self):
        evidence = self.cwd / "evidence" / "health-response.json"
        evidence.parent.mkdir()
        evidence.write_text('{"status": "Healthy", "timestamp": "2026-07-03T02:44:00.284Z"}\n', encoding="utf-8")
        self.write_assurance_contract(["Health endpoint returns status Healthy"], ["evidence/health-response.json"], "completed")
        output = self.run_cli("assure")
        self.assertTrue((self.workspace / "assurance.json").is_file())
        self.assertTrue((self.workspace / "assurance.md").is_file())
        data = json.loads((self.workspace / "assurance.json").read_text(encoding="utf-8"))
        self.assertEqual(data["engineering_result"]["status"], "GREEN")
        self.assertEqual(data["engineering_result"]["checks"][0]["result"], "VERIFIED")
        self.assertIn("Mission Assurance", (self.workspace / "assurance.md").read_text(encoding="utf-8"))
        self.assertIn("Engineering Result: GREEN", output)
        self.assertIn("Artifacts:", output)

    def test_assurance_health_endpoint_status_mismatch_is_engineering_red(self):
        evidence = self.cwd / "evidence" / "health-response.json"
        evidence.parent.mkdir()
        evidence.write_text('{"status": "ok", "timestamp": "2026-07-03T02:44:00.284Z"}\n', encoding="utf-8")
        self.write_assurance_contract(["Health endpoint returns status Healthy"], ["evidence/health-response.json"], "pending")
        result = self.result()
        self.assertEqual((result.status, result.recommendation), ("RED", "NO-GO"))
        self.assertEqual(result.engineering_result["status"], "RED")
        self.assertEqual(result.governance_result["status"], "AMBER")
        failed = [check for check in result.engineering_result["checks"] if check["result"] == "FAILED"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["expected"], {"field": "status", "value": "Healthy"})
        self.assertEqual(failed[0]["observed"], {"field": "status", "value": "ok"})
        self.assertIn('Expected response status field "Healthy"; observed "ok".', failed[0]["finding"])
        self.assertIn("Update implementation or tests", failed[0]["recommendation"])
        self.assertTrue(any("Required review is pending" in finding for finding in result.governance_result["findings"]))

    def test_assurance_unable_to_verify_without_evidence_is_amber(self):
        self.write_assurance_contract(["Structured logging behavior is enabled"], [], "completed", "planned")
        result = self.result()
        self.assertEqual((result.status, result.recommendation), ("AMBER", "NO-GO"))
        self.assertEqual(result.engineering_result["status"], "AMBER")
        self.assertEqual(result.engineering_result["summary"]["unable_to_verify"], 1)
        check = result.engineering_result["checks"][0]
        self.assertEqual(check["result"], "UNABLE_TO_VERIFY")
        self.assertIn("Unable to verify acceptance criterion", check["finding"])

    def test_assurance_engineering_findings_precede_governance_findings_in_cli(self):
        evidence = self.cwd / "evidence" / "health-response.json"
        evidence.parent.mkdir()
        evidence.write_text('{"status": "ok"}\n', encoding="utf-8")
        self.write_assurance_contract(["Health endpoint returns status Healthy"], ["evidence/health-response.json"], "pending")
        output = self.run_cli("assure")
        self.assertLess(output.index("Failed:"), output.index("Governance:"))
        self.assertIn('Expected response status field "Healthy"; observed "ok".', output)
        self.assertIn("Required review is pending", output)

    def test_assurance_engineering_result_is_deterministic(self):
        evidence = self.cwd / "evidence" / "health-response.json"
        evidence.parent.mkdir()
        evidence.write_text('{"status": "ok"}\n', encoding="utf-8")
        self.write_assurance_contract(["Health endpoint returns status Healthy"], ["evidence/health-response.json"], "pending")
        first = self.result().to_dict()
        second = self.result().to_dict()
        self.assertEqual(first["engineering_result"], second["engineering_result"])
        first_json = json.loads((self.workspace / "assurance.json").read_text(encoding="utf-8"))
        self.result()
        second_json = json.loads((self.workspace / "assurance.json").read_text(encoding="utf-8"))
        self.assertEqual(first_json["engineering_result"], second_json["engineering_result"])

    def test_assure_performs_static_validation_by_default(self):
        self.write_assurance_contract([
            "GET http://127.0.0.1:48151/v1/health returns HTTP 200",
            "Health endpoint returns JSON response",
            "Response body status equals Healthy",
        ], [], "completed", "planned")
        with patch("battalion.assurance._runtime_http_get", return_value=runtime_http_response()) as runtime:
            output = self.run_cli("assure")
        runtime.assert_not_called()
        data = json.loads((self.workspace / "assurance.json").read_text(encoding="utf-8"))
        self.assertEqual(data["engineering_result"]["summary"]["runtime_checks"], 0)
        self.assertEqual(data["engineering_result"]["summary"]["static_checks"], 3)
        self.assertEqual(data["engineering_result"]["status"], "AMBER")
        self.assertIn("Runtime Checks: 0", output)

    def test_assure_run_performs_runtime_validation(self):
        self.write_assurance_contract([
            "GET http://127.0.0.1:48151/v1/health returns HTTP 200",
            "Health endpoint returns JSON response",
            "Response body status equals Healthy",
            "Response body timestamp is ISO 8601 UTC",
        ], [], "completed", "planned")
        with patch("battalion.assurance._runtime_http_get", return_value=runtime_http_response()) as runtime:
            output = self.run_cli("assure", "--run")
        runtime.assert_called_once_with("http://127.0.0.1:48151/v1/health")
        data = json.loads((self.workspace / "assurance.json").read_text(encoding="utf-8"))
        engineering = data["engineering_result"]
        self.assertEqual(engineering["status"], "GREEN")
        self.assertEqual(engineering["summary"]["verified"], 4)
        self.assertEqual(engineering["summary"]["runtime_checks"], 4)
        self.assertTrue(all(check["result"] == "VERIFIED" for check in engineering["checks"]))
        self.assertTrue(all(check["validation_mode"] == "runtime" for check in engineering["checks"]))
        self.assertIn("Runtime Checks: 4", output)

    def test_assure_run_detects_health_endpoint_status_contract_violation_without_manual_evidence(self):
        self.write_assurance_contract([
            "GET http://127.0.0.1:48151/v1/health returns HTTP 200",
            "Health endpoint returns JSON response",
            "Response body status equals Healthy",
            "Response body timestamp is ISO 8601 UTC",
        ], [], "completed", "planned")
        with patch("battalion.assurance._runtime_http_get", return_value=runtime_http_response(status="ok")):
            output = self.run_cli("assure", "--run")
        data = json.loads((self.workspace / "assurance.json").read_text(encoding="utf-8"))
        engineering = data["engineering_result"]
        failed = [check for check in engineering["checks"] if check["result"] == "FAILED"]
        self.assertEqual(engineering["status"], "RED")
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["expected"], {"field": "status", "value": "Healthy"})
        self.assertEqual(failed[0]["observed"], {"field": "status", "value": "ok"})
        self.assertEqual(failed[0]["validation_mode"], "runtime")
        self.assertRegex(failed[0]["execution_timestamp"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertIn('"status": "ok"', failed[0]["evidence"][0]["body"])
        self.assertIn("Expected response status field", output)
        self.assertIn("Observed:", output)

    def test_assure_run_prints_runtime_target_and_concise_default_evidence(self):
        self.write_assurance_contract([
            "GET http://127.0.0.1:48151/v1/health returns HTTP 200",
            "Response body status equals Healthy",
        ], [], "completed", "planned")
        with patch("battalion.assurance._runtime_http_get", return_value=runtime_http_response(status="ok")):
            output = self.run_cli("assure", "--run")
        self.assertIn("Runtime Target:", output)
        self.assertIn("Base URL: http://127.0.0.1:48151", output)
        self.assertIn("Endpoint: /v1/health", output)
        self.assertIn("Full URL: http://127.0.0.1:48151/v1/health", output)
        self.assertIn('Expected: {"field": "status", "value": "Healthy"}', output)
        self.assertIn('Observed: {"field": "status", "value": "ok"}', output)
        self.assertIn("HTTP response (url=http://127.0.0.1:48151/v1/health, status=200", output)
        self.assertNotIn("x-diagnostic", output)
        data = json.loads((self.workspace / "assurance.json").read_text(encoding="utf-8"))
        evidence = data["engineering_result"]["checks"][1]["evidence"][0]
        self.assertEqual(evidence["headers"]["x-diagnostic"], "full-header-value")

    def test_assure_run_verbose_includes_full_runtime_evidence(self):
        self.write_assurance_contract([
            "GET http://127.0.0.1:48151/v1/health returns HTTP 200",
            "Response body status equals Healthy",
        ], [], "completed", "planned")
        with patch("battalion.assurance._runtime_http_get", return_value=runtime_http_response(status="ok")):
            output = self.run_cli("assure", "--run", "--verbose")
        self.assertIn("x-diagnostic", output)
        self.assertIn('"headers": {"content-type": "application/json", "x-diagnostic": "full-header-value"}', output)

    def test_assure_run_reports_stale_runtime_and_build_diagnostics_without_overriding_failure(self):
        self.write_assurance_contract([
            "GET http://127.0.0.1:48151/v1/health returns HTTP 200",
            "Response body status equals Healthy",
        ], [], "completed", "planned")
        (self.cwd / "src").mkdir()
        (self.cwd / "dist").mkdir()
        (self.cwd / "src" / "app.ts").write_text('response.json({ status: "Healthy" });\n', encoding="utf-8")
        (self.cwd / "dist" / "app.js").write_text('response.json({ status: "ok" });\n', encoding="utf-8")
        (self.cwd / "package.json").write_text(json.dumps({"scripts": {"build": "tsc", "test": "node --test dist"}}), encoding="utf-8")
        with patch("battalion.assurance._runtime_http_get", return_value=runtime_http_response(status="ok")):
            output = self.run_cli("assure", "--run")
        data = json.loads((self.workspace / "assurance.json").read_text(encoding="utf-8"))
        failed = [check for check in data["engineering_result"]["checks"] if check["result"] == "FAILED"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["observed"], {"field": "status", "value": "ok"})
        self.assertTrue(any("running process may be stale" in item for item in failed[0]["diagnostics"]))
        self.assertTrue(any("Build artifacts may be stale" in item for item in failed[0]["diagnostics"]))
        self.assertIn("The running process may be stale", output)
        self.assertIn("Build artifacts may be stale", output)
        self.assertEqual(data["engineering_result"]["status"], "RED")

    def test_assure_run_reports_missing_node_dependencies(self):
        self.write_assurance_contract([
            "GET http://127.0.0.1:48151/v1/health returns HTTP 200",
        ], [], "completed", "planned")
        (self.cwd / "package.json").write_text(json.dumps({"scripts": {"build": "tsc", "test": "tsx src/app.test.ts"}}), encoding="utf-8")
        with patch("battalion.assurance._runtime_http_get", return_value=runtime_http_response()):
            output = self.run_cli("assure", "--run")
        data = json.loads((self.workspace / "assurance.json").read_text(encoding="utf-8"))
        diagnostics = data["engineering_result"]["diagnostics"]
        self.assertIn("Dependencies are not installed. Run npm install, then rerun assurance.", diagnostics)
        self.assertTrue(any("command not found: tsc" in item for item in diagnostics))
        self.assertTrue(any("command not found: tsx" in item for item in diagnostics))
        self.assertIn("Dependencies are not installed. Run npm install, then rerun assurance.", output)

    def test_assure_run_eliminates_duplicated_findings(self):
        self.write_assurance_contract([
            "GET http://127.0.0.1:48151/v1/health returns HTTP 200",
            "Response body status equals Healthy",
        ], [], "completed", "planned")
        with patch("battalion.assurance._runtime_http_get", return_value=runtime_http_response(status="ok")):
            result = assure(self.workspace, run=True)
        status_findings = [finding for finding in result.findings if 'Expected response status field "Healthy"; observed "ok".' in finding]
        self.assertEqual(len(status_findings), 1)
        self.assertEqual(len(result.engineering_result["checks"]), 2)

    def test_assure_run_runtime_evidence_artifacts_are_deterministic(self):
        self.write_assurance_contract([
            "GET http://127.0.0.1:48151/v1/health returns HTTP 200",
            "Response body status equals Healthy",
        ], [], "completed", "planned")
        with patch("battalion.assurance._runtime_http_get", return_value=runtime_http_response(status="ok")):
            first = assure(self.workspace, run=True).engineering_result
            first_json = json.loads((self.workspace / "assurance.json").read_text(encoding="utf-8"))["engineering_result"]
            second = assure(self.workspace, run=True).engineering_result
            second_json = json.loads((self.workspace / "assurance.json").read_text(encoding="utf-8"))["engineering_result"]
        self.assertEqual(first, second)
        self.assertEqual(first_json, second_json)
        self.assertTrue(any(check["evidence"] for check in first["checks"]))

    def test_assure_run_derives_localhost_url_from_project_documentation(self):
        self.write_assurance_contract([
            "A valid GET request returns HTTP 200",
            "The response provides a machine-readable health result",
        ], [], "completed", "planned")
        readme = self.cwd / "README.md"
        readme.write_text("Run curl http://127.0.0.1:3000/v1/health to validate the service.\n", encoding="utf-8")
        with patch("battalion.assurance._runtime_http_get", return_value=runtime_http_response()) as runtime:
            result = assure(self.workspace, run=True)
        runtime.assert_called_once_with("http://127.0.0.1:3000/v1/health")
        self.assertEqual(result.engineering_result["summary"]["runtime_checks"], 2)
        self.assertTrue(all(check["result"] == "VERIFIED" for check in result.engineering_result["checks"]))

    def test_assure_lifts_expected_health_status_from_mission_prompt_for_generic_criteria(self):
        self.write_assurance_contract([
            "The response provides a machine-readable health result",
        ], [], "completed", "planned")
        source = self.cwd / "src" / "app.ts"
        source.parent.mkdir()
        source.write_text('response.status(200).json({ status: "ok", timestamp: new Date().toISOString() });\n', encoding="utf-8")
        result = assure(self.workspace)
        failed = [check for check in result.engineering_result["checks"] if check["result"] == "FAILED"]
        self.assertEqual(result.engineering_result["status"], "RED")
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["expected"], {"field": "status", "value": "Healthy"})
        self.assertEqual(failed[0]["observed"], {"field": "status", "value": "ok"})

    def test_assurance_does_not_treat_test_type_annotations_as_observed_response_status(self):
        self.write_assurance_contract([
            "The response provides a machine-readable health result",
        ], [], "completed", "planned")
        source = self.cwd / "src" / "app.ts"
        source.parent.mkdir()
        source.write_text('response.status(200).json({ status: "Healthy", timestamp: new Date().toISOString() });\n', encoding="utf-8")
        test = self.cwd / "src" / "app.test.ts"
        test.write_text(
            "type HttpResponse = {\n"
            "  status: number;\n"
            "  body: string;\n"
            "};\n",
            encoding="utf-8",
        )
        result = assure(self.workspace)
        check = result.engineering_result["checks"][0]
        self.assertEqual(check["result"], "VERIFIED")
        self.assertEqual(check["observed"], {"field": "status", "value": "Healthy"})
        self.assertEqual(check["evidence"], ["src/app.ts"])

    def test_assure_static_verifies_common_project_artifacts(self):
        self.write_assurance_contract([
            "Application source is implemented in TypeScript",
            "The application executes on Node.js",
            "A documented application entrypoint starts successfully",
            "A health endpoint exists",
            "The response includes a timestamp in the clarified format",
            "POST requests are rejected",
            "Documentation explains how to run the solution",
        ], [], "completed", "planned")
        (self.cwd / "src").mkdir()
        (self.cwd / "src" / "server.ts").write_text(
            'createApp().listen(3000); app.get("/v1/health", handler); app.all("/v1/health", methodNotAllowed); response.status(405).json({ error: { message: "Method not allowed" }}); response.json({ timestamp: new Date().toISOString() });\n',
            encoding="utf-8",
        )
        (self.cwd / "package.json").write_text(json.dumps({"scripts": {"start": "node dist/server.js"}, "engines": {"node": ">=20"}}), encoding="utf-8")
        (self.cwd / "README.md").write_text("Install and run with npm start.\n", encoding="utf-8")
        result = assure(self.workspace)
        checks = result.engineering_result["checks"]
        self.assertEqual(result.engineering_result["summary"]["verified"], len(checks))
        self.assertTrue(all(check["result"] == "VERIFIED" for check in checks))

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
