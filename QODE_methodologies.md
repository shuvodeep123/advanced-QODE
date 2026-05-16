# QODE Assessment Methodologies
## Reference Guide for People, Process & Technology Propensity Scoring

> **Source:** *Assessing DevOps — For Information Technology, Business and Industry*  
> Authors: Manas Shome & Raghubir Bose  
> Extracted and structured for use in QODE propensity diagram generation.

---

## Table of Contents

1. [Core Philosophy](#core-philosophy)
2. [The Three Dimensions](#the-three-dimensions)
3. [Engineering Practices](#engineering-practices)
4. [The Three Propensities (Cultural Aspect)](#the-three-propensities)
5. [People Patterns from Propensity Combinations](#people-patterns)
6. [Pre-Assessment Questionnaire](#pre-assessment-questionnaire)
7. [Readiness Scoring Model](#readiness-scoring-model)
8. [Portfolio Prioritization](#portfolio-prioritization)
9. [Quantitative Assessment (CPM-based)](#quantitative-assessment)
10. [Detailed Activity Questionnaire](#detailed-activity-questionnaire)
11. [Critical Path Analysis](#critical-path-analysis)
12. [As-Is → To-Be Transformation](#as-is-to-be-transformation)
13. [Key Metrics](#key-metrics)
14. [Quick Reference: Propensity Scoring Tables](#quick-reference)

---

## 1. Core Philosophy

The book defines three primary tenets for DevOps assessment:

1. **Primary objective of DevOps = IT Agility**  
   IT Agility = Dev Agility + Ops Agility + Business Agility

2. **Achieving IT Agility requires both Dev and Ops agility** — not just one side.

3. **DevOps can be assessed and executed as a set of Engineering Practices** — giving deterministic rather than heuristic outcomes.

### Why Quantitative Assessment Matters

Traditional DevOps assessments are qualitative and heuristic. The QODE methodology:
- Quantifies People, Process, and Technology dimensions
- Uses a modified Critical Path Method (CPM) to optimize IT cycle time
- Produces deterministic recommendations (not "multiple likely solutions")
- Models cultural behavior quantitatively through propensity scores

---

## 2. The Three Dimensions

Every DevOps assessment is structured across three interdependent dimensions:

| Dimension | What It Covers | Assessment Focus |
|-----------|---------------|-----------------|
| **People / Culture** | Team behavioral propensities, collaboration patterns, role structures | Practice propensity, technology usage propensity, collaborative propensity |
| **Process** | IT lifecycle activities, sequencing, automation vs. manual effort, cycle time | Activity mapping, critical path, waste elimination, preponing |
| **Technology** | Tools, toolchains, automation platforms, CI/CD infrastructure | Tool types used (documentation → configuration → coding-centric), coverage |

The DevOps Pipeline is formally defined as:
> *"A collection of discrete, deterministic and finite automata covering some or all aspects of software engineering discipline from conceptualization to production... that enables orchestration of the three dimensions so that the time to deploy is minimized."*

---

## 3. Engineering Practices

The following engineering practice categories form the backbone of assessment. Each practice maps to traditional IT roles and defines scope boundaries for propensity analysis.

| Practice Category | Traditional Role | Description |
|---|---|---|
| **Requirements Engineering** | IT Product Owner / Lead | Capturing, translating, categorizing, and integrating requirements; traceability automation |
| **Code Engineering** | Developer | Modularity, microservices architecture, in-line code quality, model-driven code generation, application security |
| **Data Engineering** | Data Architect / Modeler | Schema optimization, unstructured data management, data migration, data security, archival automation |
| **Quality Engineering** | Tester / QA Team | TDD/BDD, in-sprint automation, regression and performance test automation, shift-left testing |
| **Build & Release Engineering** | Operations / Release Team | CI/CD frameworks, toolchain integration, zero-downtime deployment, release pipeline reliability |
| **Environment Engineering** | Operations / Infrastructure Team | Infrastructure-as-code, environment provisioning automation, configuration management, containerization, cloud |
| **Service Operations Engineering** | Operations / Production Support | Production monitoring, automated incident detection and resolution, feedback loops to SDLC, ITSM workflows |
| **Security Engineering** | IT Security Team | Application, data, infrastructure, and code security; vulnerability scanning; chaos engineering for security; DevSecOps |
| **Reliability Engineering** | Ops / SRE | Monitoring-based failure detection, self-healing, chaos engineering, SLO/SLA management |

> **Note for QODE:** Each engineering practice becomes a grouping axis for activities in the process network diagram. Propensity values are computed per practice, per team role.

---

## 4. The Three Propensities

Culture is quantified through three independent propensity dimensions. Each can be rated **Low, Medium, or High** (or mapped to a numeric scale for composite scoring).

---

### 4.1 Practice Propensity

> *Affiliation of the current people/team with respect to their engineering practice.*

Measures whether a team's mindset is oriented towards:

| Level | Description | Indicator Behaviors |
|---|---|---|
| **Low — Managerial Oriented** | Coordination and process orchestration via human management | Ticket-based handoffs, manual approvals, committee-driven decisions |
| **Medium — Engineering Oriented** | Technical problem solving, writing automation scripts, designing systems | Scripting environments, configuring CI pipelines, IaC adoption |
| **High — High Automation Oriented** | Self-orchestrating systems; intelligent automation; minimal human intervention | Full CI/CD pipelines, auto-scaling, self-healing, AIOps |

**Transformation direction:** Managerial → Engineering → High Automation

---

### 4.2 Technology Usage Propensity

> *Technology-based behavioral propensity — what type of tool does the team gravitate toward?*

| Level | Description | Example Tools / Behaviors |
|---|---|---|
| **Low — Documentation-Based** | Spreadsheets, email, Word documents for tracking/managing IT activities | Excel test cases, email-based release plans, manual checklists |
| **Medium — Configuration-Centric** | Tools with UI-driven configuration, drop-down rule setup, template-based automation | Jira for test tracking, ServiceNow workflows, Jenkins job configs |
| **High — Coding-Centric** | Tools where entire workflows are expressed as code or scripts | Pipeline-as-code (Jenkinsfile), Terraform, Ansible playbooks, Selenium scripts |

**Transformation direction:** Documentation → Configuration → Coding-Centric

> **Key insight for QODE:** Technology usage propensity gives insights into what tool category should be recommended in the To-Be technology architecture for a given team.

---

### 4.3 Collaborative Propensity

> *Interpersonal behavioral patterns in terms of affinity to collaborate vs. work in silos.*

| Level | Description | Indicator Behaviors |
|---|---|---|
| **Low — Silo-Based** | Teams work independently; minimal cross-team communication; "throw over the wall" handoffs | Separate Dev / QA / Ops with no shared ceremonies; blame culture |
| **Medium — Intra-Group Oriented** | Strong collaboration within the team but limited cross-team engagement | Dev team collaborates internally; Ops manages releases independently |
| **High — Inter-Group Oriented** | Active cross-team collaboration; shared ceremonies, joint ownership of outcomes | Joint Scrums (Dev + QA + Ops); shared dashboards; cross-role pairing |

**Transformation direction:** Silo → Intra-Group → Inter-Group

---

## 5. People Patterns

The three propensities (Practice – Technology Usage – Collaboration) combine to create distinct **people patterns**. These patterns determine organizational structure and indicate what changes are needed.

Use this table for QODE people propensity diagram generation:

| Pattern (P–T–C) | People Pattern Name | Organizational Characteristics | Typical Structure |
|---|---|---|---|
| **Low–Low–Low** | Traditional Waterfall + Ops Silo | Waterfall dev, manual testing, traditional L1/L2 infra support; no cross-team collaboration; teams completely separate | Dev ‖ QA ‖ Ops (separate silos) |
| **Low–Low–High** | Collaborative Waterfall | High collaboration within teams but low automation; Ops manages releases and environments; DevOps team formed but still silo | Dev–QA pair; Ops manages pipeline/releases independently |
| **Low–High–High** | Tool-Rich but Engineering-Weak | Coding-centric tools present; high collaboration; but no automation engineering mindset → tool under-utilization. Three sub-scenarios: (a) Dev+Ops single team, (b) Mature IaC Ops, (c) Dev cloud self-service | Dev+Ops hybrid; or Ops-IaC team; or Dev with cloud self-service |
| **High–High–High** | Mature DevOps / NoOps Emerging | Highly mature; Dev and Ops as single team; engineering practices across full SDLC; progressing towards NoOps state; reliability and self-healing engineering active | Unified Dev+Ops; coded pipelines; SRE emerging |
| **High–High–Low** | Platform Engineering | High automation, coding-centric, but individual sub-teams work independently; auto-scaling cloud containers, microservices; self-service infra | Multiple Dev sub-teams for services; Ops as platform team |
| **High–Low–Low** | Niche IT-for-IT Team | Advanced automation/research but no formal tools; no collaboration; niche innovation team; product thrown over wall to Ops | Small innovation team; separate Ops for support |
| **High–Low–High** | Script-Heavy Collaborative | High practice propensity + high collaboration + documentation/config tools; TDD/BDD + microservices; Ops manages coded pipelines | Dev with script-based workflow; Ops release automation team |
| **Low–High–Low** | Tool-Overloaded Siloed Team | High tool investment, silo culture, no engineering mindset → maximum waste; tools procured without integrated pipeline; classic "DevOps theater" | Disconnected tool stacks; no shared pipeline |

> **QODE Usage:** Map each team/role from the questionnaire responses to one of these patterns. Use the pattern to determine the propensity scores and generate the As-Is people diagram. The To-Be target pattern drives the recommended organizational change.

---

## 6. Pre-Assessment Questionnaire

The pre-assessment captures qualitative DevOps readiness across four dimensions using a structured questionnaire. Answers map to RAG (Red/Amber/Green) readiness scores.

### 6.1 Scope and Direction Questions

| # | Question | Scoring Basis |
|---|---|---|
| 1 | Single application stack vs. multi-stack vs. enterprise? | Difficulty: more stacks = higher difficulty |
| 2 | Scope: SDLC only, ITSM only, or both? | Difficulty: more depth = higher difficulty |
| 3 | Geographic distribution of IT teams? | Difficulty: more dispersed + heterogeneous = higher difficulty |
| 4 | Vendor involvement? | Informational (no score; informs cultural analysis) |
| 5 | Top pain areas (cycle time, availability, maintainability, scalability, reliability, visibility, security)? | Difficulty: more pain areas + higher criticality = higher difficulty |

### 6.2 Culture Questions

| # | Question | Scoring Basis |
|---|---|---|
| 1 | Is there a DevOps champion / group? | Maturity: champion exists + propagates practices = higher maturity |
| 2 | Is Agile practiced by Dev + QA as one team? Does Ops join Scrums? | Maturity: all three together = highest |
| 3 | How are activities tracked (Scrum board, Kanban, spreadsheet, email)? | Maturity: formalized tool-based = higher |
| 4 | Is there an Architecture Review Board (ARB)? | Maturity: ARB maps architecture to all projects = highest |
| 5 | Is there an IT security group? | Maturity: active compliance mapping to projects = higher |
| 6 | Are team members cross-trained across Dev/QA/Ops + Agile/DevOps? | Maturity: wider coverage = higher |
| 7 | Does the team dynamically self-organize across roles? | Maturity: wider role coverage within same Sprint = higher |

### 6.3 Process Questions

| # | Question | Scoring Basis |
|---|---|---|
| 1 | Is there a process handbook covering Agile + DevOps? | Maturity: includes Agile Ops + DevOps automation guidelines = higher |
| 2 | What technology-led paradigms are practiced (TDD, BDD, ZDD, auto-incident resolution, etc.)? | Maturity: more practices on-ground = higher |
| 3 | What process management tools are used (Agile tracking, ITSM, dashboards, knowledge mgmt)? | Maturity: more tools + integrated = higher |
| 4 | How are IT costs / ROI tracked? | Maturity: predictive analytics + automated = highest |

### 6.4 Technology Questions

| # | Question | Scoring Basis |
|---|---|---|
| 1 | What DevOps tools are currently in use (CI, CD, SCM, TDD/BDD, env provisioning, monitoring)? | Maturity: more toolchain coverage = higher |
| 2 | What tools are planned for procurement? | Informational (no score; informs To-Be architecture) |
| 3 | What environments are applications deployed to, and how? | Maturity: automated, immutable, cloud-native = higher |

### 6.5 Metrics Questions

| # | Question | Key Metrics Captured |
|---|---|---|
| 1 | Key IT metrics? | Release frequency, lead time to change, change success ratio, MTTR, MTBF |
| 2 | Top SDLC metrics? | % tests automated, functional vs. NFR defect ratio, build failure rate, test data refresh cycle time, environment provisioning cycle time |
| 3 | Top ITSM metrics? | SLA compliance %, incident break-up (infra/app/security), % auto-resolved incidents |
| 4 | Top reliability metrics? | System availability %, toolchain performance under load, tool failure impact on time-to-market |

---

## 7. Readiness Scoring Model

### 7.1 Score Calculation

**Single-response question:**
```
Si = Wi × Ri
Sp = Si / (Wi × Rmax)    [percentage score]
```

**Multi-response question:**
```
Si = Wi × ΣRi
Sp = Si / (Wi × ΣRmax)
```

**Variables:**
- `Si` = Score for question i
- `Wi` = Weight of question i (assigned based on organizational objectives)
- `Ri` = Rating of selected response
- `Rmax` = Maximum possible rating

### 7.2 RAG Thresholds

| Color | Meaning | Numeric Equivalent |
|---|---|---|
| 🟢 Green | Substantial readiness; well established | 3 |
| 🟡 Yellow | Partial readiness; needs improvement and focus | 2 |
| 🔴 Red | Little or no readiness; needs substantial improvement | 1 |

### 7.3 Dimension Score

```
Sd = (Σ Sp) / n
```
where `n` = number of parameters for dimension `d` (culture, process, technology, metrics).

Round to nearest integer (1, 2, or 3) for portfolio comparison.

### 7.4 Portfolio Consolidated Score

```
Ci = Σ(Wj × Aj) / Σ Wj
```
where:
- `Ci` = consolidated score for portfolio i
- `Wj` = weight of dimension j
- `Aj` = average score for dimension j

**Recommended weights:** Culture > Process > Technology > Metrics  
*(Culture and process carry highest weight; metrics is a derived governance outcome)*

---

## 8. Portfolio Prioritization

### 8.1 Portfolio Heatmap

After pre-assessing all portfolios, plot each on a 2×2 matrix:

| | **High Business Criticality** | **Low Business Criticality** |
|---|---|---|
| **High DevOps Readiness (Easy)** | ⭐ **Prioritize First** — Quick wins with business impact | ✅ **Test the Waters** — Low risk for experimentation |
| **Low DevOps Readiness (Difficult)** | ⚠️ **Plan Carefully** — High impact but high effort; assess change management readiness | 🔽 **Defer or Skip** — Low priority |

### 8.2 Decision Criteria

- **Easy + Critical:** Fast business visibility; creates "quick win" business case; requires strong technology foundation
- **Easy + Less Critical:** Good for first-time DevOps adopters; organizational confidence building
- **Difficult + Critical:** Requires substantial time/effort; high change management complexity; do after quick wins
- **Difficult + Less Critical:** Lowest priority; may be excluded from DevOps scope

---

## 9. Quantitative Assessment (Modified CPM)

The book uses a **modified Critical Path Method (CPM)** as the quantitative backbone. Traditional CPM is adapted for IT processes as follows:

### 9.1 Modifications to Traditional CPM

| Traditional CPM | QODE Modification |
|---|---|
| Only duration per activity | Duration + manual time + automation time + role + criticality + input/output entity type |
| Single critical path by duration | Critical path filtered by output entity type (Material preferred) + average criticality |
| Cost as constraint | Cultural behavior (propensity scores) as constraint for time estimation |
| No entity typing | Events typed as: Initial, Interim, Final; entities typed as Material or Information |
| Idle time tracked | Idle time excluded (organizations don't track it) |
| Four time parameters | Simplified to relative start time + duration only |

### 9.2 Activity Entity Types

| Entity Type | Definition | Examples |
|---|---|---|
| **Material** | Core IT deliverable actually used by business/users | Source code, build binary, environment, deployed application |
| **Information** | Supporting record; aids IT personnel but not consumed by business | Test cases, SRS documents, architecture diagrams, test results |

> **Key rule for QODE:** Outputs of type "Information" contribute to **waste**. The To-Be state should aim to eliminate or derive them automatically from Material outputs wherever possible.

### 9.3 Activity Transformation Types

| Code | Transformation | Example Activity |
|---|---|---|
| **a** | Material → Material | Configure environment (config scripts → configured VM) |
| **b** | Information → Information | Create SRS from BRS (BRS → SRS) |
| **c** | Material → Information | Capture infra capacity (infra details → request form) |
| **d** | Information → Material | Provision VM from request form (environment request → VM) |

### 9.4 Relative Start Time Formula

```
T_R = Maximum(T_{R-1} + L_{R-1})
```

Where:
- `T_R` = relative start time of activity R
- `T_{R-1}` = relative start time of each preceding activity
- `L_{R-1}` = duration (lead time) of each preceding activity

Lead time breakdown:
```
L_R = P_R + M_R
```
- `P_R` = automation (machine) time for activity R
- `M_R` = manual (process) time for activity R

---

## 10. Detailed Activity Questionnaire

Each IT activity is captured with the following fields for quantitative analysis:

| Field | Description | QODE Propensity Signal |
|---|---|---|
| **Activity Category (Epic)** | Phase / type (Requirements, Environment, Coding, Build, Testing, Release) | Engineering practice category |
| **Activity Description (Story)** | Specific task performed | Process propensity indicator |
| **Total Time Taken** | Lead time from start to finish (in days/hours) | Process efficiency metric |
| **Manual Time Taken** | Time spent by human (vs. automation) | Practice propensity indicator: high manual = low practice propensity |
| **Predecessor Activities** | Sequential dependencies | Network diagram construction |
| **Criticality** | High / Medium / Low (or numeric: H=3, M=2, L=1) | Critical path weighting |
| **Role / Team** | Dev, QA, Ops-Infra, Ops-Release, DevOps Engineer, Release Manager | People propensity mapping |
| **Input Entity** | What the activity consumes | Entity type classification (Material/Information) |
| **Output Entity** | What the activity produces | Waste identification |
| **Automation Tool Used** | Tool name + coverage scope | Technology usage propensity |

### Activity Category → Engineering Practice Mapping

| Activity Epic | Engineering Practice |
|---|---|
| Requirements Analysis / SDLC-Requirements | Requirements Engineering |
| SDLC - Coding | Code Engineering |
| SDLC - Environment Provisioning | Environment Engineering |
| SDLC - Build and Package | Build & Release Engineering |
| SDLC - Testing | Quality Engineering |
| SDLC - Application Release and Deployment | Build & Release Engineering |
| ITSM - Incident / Problem / Change | Service Operations Engineering |
| Security-related activities | Security Engineering |

---

## 11. Critical Path Analysis

### 11.1 Path Selection Criteria (in priority order)

1. **Final output type = "Material"** (primary filter — paths ending in Information are not critical)
2. **Longest net duration** (after adjusting for float times)
3. **Average criticality = High** across the path (optional secondary filter)

### 11.2 Float Time

Float time occurs when:
- **Dependency-driven:** Activity must wait for a parallel path to complete
- **Cultural/Behavioral:** Team introduces delay between activities due to process overhead or recurring technical issues

Net duration (considering float):
```
Net Duration = Total Cycle Time - Float Time
```

Use net duration (not raw cycle time) to select the true critical path.

### 11.3 Path Table Structure

For each identified path from the process network diagram:

| Path # | Path Activities | Start Time | End Time | Total Cycle Time | Min Float | Max Float | Net Duration (Min Float) | Net Duration (Max Float) | Final Output Type | Avg Criticality |
|---|---|---|---|---|---|---|---|---|---|---|

---

## 12. As-Is → To-Be Transformation

### 12.1 Activity Change Types

Each activity on the critical path is evaluated for one of four change types:

| Change Type | Description | Impact on People | Impact on Technology |
|---|---|---|---|
| **Prepone** | Start the activity earlier; brings parallelism | Role needs to engage earlier in the process | Tool must be available earlier in the pipeline |
| **Enhance/Alter Scope** | Increase or change what the activity does | Role may change; new skills needed | Tool capabilities expanded or replaced |
| **Eliminate** | Remove waste-generating activities | Role may be absorbed into another activity | Tool retired or superseded |
| **Add** | Introduce new activities for robustness | New role introduced (e.g., DevOps Engineer) | New tool added to toolchain |

> **Note:** Postponing activities is rarely recommended as it increases cycle time.

### 12.2 Color Convention for To-Be Diagrams

| Color | Meaning |
|---|---|
| 🟣 Purple/Dark | DevOps implementation activities (one-time setup) |
| 🔵 Blue | Activities on the As-Is critical path (changed or preponed) |
| 🟢 Green | Activities on other paths (changed relative to critical path changes) |

### 12.3 DevOps Implementation Stories

These are **one-time** activities needed to build the DevOps infrastructure:
- They have **negative relative start times** (must complete before the main IT lifecycle begins)
- They are often executed by a **DevOps Engineer (DE)** role
- They include: selecting/installing orchestrators, configuring NEXUS/binary repositories, setting up CI/CD pipelines, configuring toolchains

---

## 13. Key Metrics

### 13.1 Process Metrics

| Metric | Description | Target Direction |
|---|---|---|
| IT Cycle Time | Time from requirements to production rollout | ↓ Minimize |
| Release Frequency | How often releases reach production vs. business expectation | ↑ Increase |
| Lead Time to Change | Time from issue/requirement to production deployment | ↓ Minimize |
| Issue-to-Code Success Ratio | % of changes that succeed in production vs. pre-production | ↑ Increase |
| Manual Time Ratio | Proportion of manual vs. automated time per activity | ↓ Minimize |
| Float Time | Waiting time between activities in critical path | ↓ Minimize |

### 13.2 People Metrics

| Metric | Description |
|---|---|
| Cross-Training Coverage | % of team members trained across Dev/QA/Ops roles |
| Agile Participation Rate | % of Ops/QA participating in Agile ceremonies with Dev |
| Self-Organization Index | Frequency of team members switching roles within a Sprint |
| DevOps Champion Effectiveness | % of DevOps practices actively propagated by champion/group |

### 13.3 Technology Metrics

| Metric | Description | Target Direction |
|---|---|---|
| % Tests Automated | Regression + NFR test automation coverage | ↑ Increase |
| Build Failure Rate | % of builds failing post code commit | ↓ Minimize |
| Test Data Refresh Cycle Time | Time to prepare/refresh test bed | ↓ Minimize |
| Environment Spin-up Time | Time to provision a pre-production environment | ↓ Minimize |
| % Incidents Auto-Resolved | Proportion resolved without human intervention | ↑ Increase |
| SLA Compliance % | Production incidents resolved within SLA | ↑ Increase |
| MTTR (Mean Time to Repair) | Average time to fix production failures | ↓ Minimize |
| MTBF (Mean Time Between Failures) | Average time between production failures | ↑ Increase |

---

## 14. Quick Reference: Propensity Scoring Tables

### 14.1 Practice Propensity Score

| Score | Level | Observable Indicators |
|---|---|---|
| 1 | Managerial | Manual approvals, email-based workflows, no CI/CD, committee decisions, no scripting |
| 2 | Engineering | Some automation scripting, configures CI pipelines, IaC beginning, code quality gates |
| 3 | High Automation | Full CI/CD pipelines, auto-scaling, self-healing systems, policy-as-code, AIOps elements |

### 14.2 Technology Usage Propensity Score

| Score | Level | Tool Examples |
|---|---|---|
| 1 | Documentation-Based | MS Excel, MS Word, Confluence (passive), Email, SharePoint |
| 2 | Configuration-Centric | Jira, ServiceNow, Jenkins (job-config UI), Puppet/Chef (config files), TestNG XML |
| 3 | Coding-Centric | Jenkinsfile, Terraform, Ansible playbooks, Selenium scripts, Cucumber/Gherkin, Docker Compose |

### 14.3 Collaborative Propensity Score

| Score | Level | Observable Indicators |
|---|---|---|
| 1 | Silo-Based | Separate team ceremonies; handoff via tickets; blame culture; no shared metrics |
| 2 | Intra-Group | Strong within-team collaboration; limited cross-team; joint standups within Dev or Ops |
| 3 | Inter-Group | Joint Dev+QA+Ops ceremonies; shared dashboards; cross-team pairing; collective ownership |

### 14.4 Pre-Assessment Dimension Score → Propensity Mapping

| Dimension Score | Readiness | Corresponding Propensity Level |
|---|---|---|
| 3 (Green) | Substantial | High |
| 2 (Yellow) | Partial | Medium |
| 1 (Red) | Low/None | Low |

### 14.5 Tool Category → Technology Usage Propensity Mapping

Use this table when parsing questionnaire responses for technology tool identification:

| Tool Category | Examples | Technology Usage Propensity |
|---|---|---|
| Agile Tracking (config) | Jira, Azure DevOps Boards, Trello | Medium |
| CI Server (config-based) | Jenkins (job DSL), GitHub Actions (YAML) | Medium → High |
| CI Pipeline-as-Code | Jenkinsfile, GitLab CI pipeline | High |
| Source Code Management | Git, Subversion | Medium |
| Binary Repository | NEXUS, Artifactory | Medium |
| Build Tools | Maven, Gradle, npm | Medium |
| Unit Test Frameworks | JUnit, pytest, Jest | Medium |
| Test Automation (scripted) | Selenium, Cypress, Playwright | High |
| Performance Testing | HP LoadRunner, JMeter, Gatling | Medium → High |
| Environment Provisioning (script) | Puppet, Chef, Ansible | High |
| IaC / Orchestration | Terraform, Vagrant, AWS OpsWorks | High |
| Containerization | Docker, Kubernetes | High |
| Release Automation | Octopus Deploy, Spinnaker | High |
| Service Management | ServiceNow | Medium |
| Monitoring | Zabbix, Datadog, Prometheus, Grafana | Medium → High |
| Incident Management (ALM) | Jira, BMC Remedy | Medium |
| Documentation | Confluence, SharePoint, Word | Low |
| Spreadsheets | Microsoft Excel | Low |

### 14.6 Role → Engineering Practice → People Propensity Mapping

| Role / Team | Primary Engineering Practice | Default Practice Propensity |
|---|---|---|
| Business / Product Owner | Requirements Engineering | Low (Managerial) |
| IT Lead / Architect | Requirements Engineering, Code Engineering | Medium |
| Developer (Dev) | Code Engineering, Build Engineering | Medium → High |
| QA / Tester | Quality Engineering | Medium → High (depends on automation maturity) |
| Ops-Infrastructure | Environment Engineering, Reliability Engineering | Low → Medium |
| Ops-Release | Build & Release Engineering | Low → Medium |
| DevOps Engineer (DE) | Environment + Build + Release Engineering | High |
| Release Manager (RM) | Build & Release Engineering | Low (Managerial) |
| Production Support | Service Operations Engineering | Low → Medium |
| IT Security | Security Engineering | Medium |

---

## Usage in QODE Pipeline

### Generating People Propensity Diagram

**Inputs from questionnaire:**
- Team role breakdown (Dev, QA, Ops-Infra, Ops-Release, DevOps Engineer, etc.)
- Collaborative propensity score per team (1–3)
- Practice propensity score per team (1–3)
- Technology usage propensity score per team (1–3)

**Logic:**
1. Look up the propensity combination in the People Patterns table (Section 5)
2. Map to the corresponding people pattern name and organizational structure
3. Generate As-Is diagram showing current team topology with propensity scores
4. Apply transformation rules (Section 12) to derive To-Be target state

### Generating Process Propensity Diagram (Network Diagram)

**Inputs from questionnaire:**
- Activity list with: total time, manual time, predecessors, criticality, role, input, output, tool

**Logic:**
1. Compute relative start times for all activities
2. Build process network diagram (CPM network)
3. Enumerate all paths; compute cycle times and float times
4. Select critical path using: Material output type → longest net duration → highest criticality
5. Color-code As-Is vs. To-Be changes

### Generating Technology Usage Propensity Diagram

**Inputs from questionnaire:**
- Current tools per activity per practice category
- Tool coverage and degree of adoption

**Logic:**
1. Map each tool to its tool category and propensity level (Low/Medium/High) using Section 14.5
2. Compute average technology usage propensity per engineering practice
3. Identify gaps between As-Is and target state (High automation)
4. Recommend To-Be tool categories for each practice where propensity is below target
