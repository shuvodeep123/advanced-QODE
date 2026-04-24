"""
principles_engine.py — 9 Engineering Principles × 3 Discipline reasoning layer.

The PrinciplesEngine maps user queries to the relevant principle + discipline
intersection, enriching the system prompt with targeted context before the LLM call.

9 Engineering Principles
------------------------
1. Requirement Engineering
2. Code / Data Engineering
3. Quality Engineering
4. Build & Release Engineering
5. Environment Engineering
6. Service Ops
7. Security
8. Reliability
9. Ontology Engineering

3 Core Disciplines
------------------
a. People   b. Process   c. Technology

Public API
----------
    extract_principle_context(query) -> dict
        Returns {"principle": str | None, "discipline": str | None, "enrichment": str}

    PrinciplesEngine.get_enrichment(principle, discipline) -> str
        Returns a focused prompt fragment to inject into the system context.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Principle definitions — keyword triggers + prompt enrichment text
# ---------------------------------------------------------------------------

PRINCIPLES: list[dict] = [
    {
        "id": "req_engg",
        "name": "Requirement Engineering",
        "number": 1,
        "keywords": [
            "requirement", "user story", "backlog", "acceptance criteria",
            "specification", "use case", "epics", "sprint planning", "grooming",
        ],
        "enrichment": {
            "People": (
                "Focus on: Product Owner accountability, BA-to-developer handshake, "
                "RACI clarity for requirement sign-off, and stakeholder alignment gaps."
            ),
            "Process": (
                "Focus on: requirement traceability matrix, definition of done, "
                "change request workflows, and sprint ceremony efficiency."
            ),
            "Technology": (
                "Focus on: toolchain for requirements (Jira, Confluence, Azure DevOps), "
                "integration between requirement and CI/CD systems, and automated traceability."
            ),
        },
    },
    {
        "id": "code_data_engg",
        "name": "Code / Data Engineering",
        "number": 2,
        "keywords": [
            "code", "coding", "data", "engineering", "development", "developer",
            "refactor", "technical debt", "data pipeline", "etl", "api",
        ],
        "enrichment": {
            "People": (
                "Focus on: developer skills gaps, pair programming culture, "
                "code review ownership, and data engineering team structure."
            ),
            "Process": (
                "Focus on: branching strategy, PR review SLAs, data quality gates, "
                "and code-to-deploy cycle time."
            ),
            "Technology": (
                "Focus on: IDE tooling, static analysis (SonarQube), data orchestration "
                "(Airflow, dbt), version control, and code quality automation."
            ),
        },
    },
    {
        "id": "quality_engg",
        "name": "Quality Engineering",
        "number": 3,
        "keywords": [
            "quality", "test", "testing", "qa", "qe", "bug", "defect",
            "regression", "unit test", "integration test", "e2e", "coverage",
        ],
        "enrichment": {
            "People": (
                "Focus on: QE team embedding in squads, shift-left culture, "
                "tester-to-developer ratio, and quality ownership across roles."
            ),
            "Process": (
                "Focus on: test pyramid strategy, defect escape rate, "
                "quality gates in CI/CD, and regression cycle time."
            ),
            "Technology": (
                "Focus on: test automation frameworks (Selenium, Playwright, pytest), "
                "test management tools (Xray, Zephyr), and coverage reporting integration."
            ),
        },
    },
    {
        "id": "build_release_engg",
        "name": "Build & Release Engineering",
        "number": 4,
        "keywords": [
            "build", "release", "deploy", "ci", "cd", "pipeline", "artifact",
            "packaging", "versioning", "rollback", "blue-green", "canary",
        ],
        "enrichment": {
            "People": (
                "Focus on: release manager role, DevOps ownership, on-call accountability, "
                "and developer self-service for deployments."
            ),
            "Process": (
                "Focus on: release cadence, change freeze policies, "
                "deployment frequency (DORA), and rollback procedures."
            ),
            "Technology": (
                "Focus on: CI/CD toolchain (Jenkins, GitHub Actions, ArgoCD, Spinnaker), "
                "artifact management (Nexus, JFrog), and deployment automation."
            ),
        },
    },
    {
        "id": "env_engg",
        "name": "Environment Engineering",
        "number": 5,
        "keywords": [
            "environment", "env", "infrastructure", "iac", "terraform", "ansible",
            "provisioning", "configuration", "drift", "cloud", "kubernetes", "container",
        ],
        "enrichment": {
            "People": (
                "Focus on: Cloud/Ops engineer skills, IaC ownership, "
                "and environment management RACI."
            ),
            "Process": (
                "Focus on: environment promotion strategy (dev→test→staging→prod), "
                "configuration drift detection, and environment request SLAs."
            ),
            "Technology": (
                "Focus on: IaC tooling (Terraform, Pulumi, Ansible), "
                "secrets management (Vault), container orchestration (Kubernetes), "
                "and cloud provider tooling."
            ),
        },
    },
    {
        "id": "service_ops",
        "name": "Service Ops",
        "number": 6,
        "keywords": [
            "ops", "operations", "sre", "on-call", "incident", "toil",
            "runbook", "playbook", "service level", "slo", "sla", "support",
        ],
        "enrichment": {
            "People": (
                "Focus on: SRE team structure, on-call rotation fairness, "
                "toil reduction ownership, and ops-to-dev feedback loops."
            ),
            "Process": (
                "Focus on: incident response process, post-mortem culture, "
                "SLO definition and review cadence, and runbook completeness."
            ),
            "Technology": (
                "Focus on: incident management tooling (PagerDuty, OpsGenie), "
                "observability stack (Prometheus, Grafana, ELK), and AIOps tooling."
            ),
        },
    },
    {
        "id": "security",
        "name": "Security",
        "number": 7,
        "keywords": [
            "security", "devsecops", "vulnerability", "sast", "dast", "sca",
            "secrets", "compliance", "penetration", "zero trust", "iam", "rbac",
        ],
        "enrichment": {
            "People": (
                "Focus on: security champion programme, developer security training, "
                "and Security Engineer embedding in squads."
            ),
            "Process": (
                "Focus on: shift-left security gates, threat modelling in design phase, "
                "vulnerability triage SLAs, and compliance audit cadence."
            ),
            "Technology": (
                "Focus on: SAST/DAST/SCA tooling (Snyk, Checkmarx, OWASP ZAP), "
                "secrets scanning (GitGuardian, Vault), container scanning (Twistlock, Trivy), "
                "and policy-as-code (OPA)."
            ),
        },
    },
    {
        "id": "reliability",
        "name": "Reliability",
        "number": 8,
        "keywords": [
            "reliability", "resilience", "availability", "fault tolerance",
            "disaster recovery", "rto", "rpo", "chaos", "redundancy", "failover",
        ],
        "enrichment": {
            "People": (
                "Focus on: reliability ownership (SRE vs Dev), game day participation, "
                "and DR test accountability."
            ),
            "Process": (
                "Focus on: chaos engineering practice, DR runbooks, "
                "RTO/RPO targets and test cadence, and reliability review in design."
            ),
            "Technology": (
                "Focus on: chaos tooling (Chaos Monkey, Gremlin), "
                "multi-region deployment, circuit breakers, "
                "and auto-scaling configuration."
            ),
        },
    },
    {
        "id": "ontology_engg",
        "name": "Ontology Engineering",
        "number": 9,
        "keywords": [
            "ontology", "knowledge graph", "taxonomy", "entity", "relationship",
            "graph", "semantic", "metadata", "schema", "classification",
        ],
        "enrichment": {
            "People": (
                "Focus on: knowledge engineer roles, ontology governance, "
                "and cross-team taxonomy alignment."
            ),
            "Process": (
                "Focus on: ontology versioning process, entity extraction workflows, "
                "and schema review cadence."
            ),
            "Technology": (
                "Focus on: graph database selection (Neo4j, Amazon Neptune), "
                "ontology tooling (Protégé, OWL), "
                "and knowledge graph ingestion pipelines."
            ),
        },
    },
]

_DISCIPLINE_KEYWORDS: dict[str, list[str]] = {
    "People": ["people", "team", "role", "person", "stakeholder", "human", "talent", "staff"],
    "Process": ["process", "workflow", "procedure", "flow", "cycle", "sdlc", "pipeline", "step"],
    "Technology": ["technology", "tool", "platform", "software", "infra", "automation", "tech"],
}


# ---------------------------------------------------------------------------
# PrinciplesEngine
# ---------------------------------------------------------------------------

class PrinciplesEngine:
    """Maps query text to the correct Principle + Discipline enrichment."""

    def get_enrichment(self, principle_name: str | None, discipline: str) -> str:
        if not principle_name:
            return ""
        for p in PRINCIPLES:
            if principle_name.lower() in p["name"].lower() or principle_name == p["id"]:
                return p["enrichment"].get(discipline, "")
        return ""

    def match_principle(self, query: str) -> dict | None:
        lower = query.lower()
        best: dict | None = None
        best_score = 0
        for p in PRINCIPLES:
            score = sum(1 for kw in p["keywords"] if kw in lower)
            if score > best_score:
                best_score = score
                best = p
        return best if best_score > 0 else None

    def match_discipline(self, query: str) -> str:
        lower = query.lower()
        scores = {d: 0 for d in _DISCIPLINE_KEYWORDS}
        for disc, kws in _DISCIPLINE_KEYWORDS.items():
            for kw in kws:
                if kw in lower:
                    scores[disc] += 1
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else "Technology"


_engine = PrinciplesEngine()


# ---------------------------------------------------------------------------
# Public convenience function
# ---------------------------------------------------------------------------

def extract_principle_context(query: str) -> dict:
    """Extract principle + discipline from a raw user query.

    Returns:
        dict with keys:
          - ``principle``  : str name or None
          - ``discipline`` : str ("People" | "Process" | "Technology")
          - ``enrichment`` : str prompt fragment (empty string if no match)
    """
    matched = _engine.match_principle(query)
    discipline = _engine.match_discipline(query)

    principle_name = matched["name"] if matched else None
    enrichment = _engine.get_enrichment(principle_name, discipline) if matched else ""

    return {
        "principle": principle_name,
        "discipline": discipline,
        "enrichment": enrichment,
    }
