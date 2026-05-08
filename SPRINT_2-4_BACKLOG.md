# Sprint 2-4 Backlog

This document provides a comprehensive breakdown of Sprint 2, Sprint 3, and Sprint 4 work items for the advanced-QODE project.

## Overview

- **Total Stories**: 15
- **Total Tasks**: 62
- **Sprint 2 Tasks**: 21 (Core Diagram Generation & Validation)
- **Sprint 3 Tasks**: 21 (RAG Pipeline Foundation)
- **Sprint 4 Tasks**: 20 (Advanced Features & Production Readiness)

## Files

- **Sprint_2-4_Backlog.xlsx** - Full Excel workbook with formatting, filters, and color coding
- **Sprint_2-4_Backlog.csv** - CSV version for easy import/export
- **generate_sprint_backlog.py** - Python script to regenerate the backlog

## Sprint 2: Core Diagram Generation & Validation

### Stories
1. **AQ-301**: Process Network Diagram Validation (5 tasks)
2. **AQ-302**: People Diagram Validation (4 tasks)
3. **AQ-303**: Technology Diagram Validation (4 tasks)
4. **AQ-304**: Multi-format Diagram Export (4 tasks)
5. **AQ-305**: Document Export Capability (4 tasks)

### Key Deliverables
- Stable predecessor/INIT interpretation rules
- Accurate people handoff mapping
- Reduced duplicate edges in technology diagram
- Consistent multi-format diagram outputs
- Download-ready export package

## Sprint 3: RAG Pipeline Foundation

### Stories
1. **AQ-201**: Document Ingestion Pipeline (5 tasks)
2. **AQ-202**: ChromaDB Vector Store Integration (4 tasks)
3. **AQ-203**: Knowledge Graph Construction (4 tasks)
4. **AQ-204**: Hybrid Retrieval Implementation (4 tasks)
5. **AQ-205**: RAG Evaluation Framework (4 tasks)

### Key Deliverables
- Multi-format ingestion support (xlsm, xlsx, docx, pdf, txt)
- Higher-value retrieval corpus
- Complete knowledge graph node model
- Hybrid retrieval optimization
- Repeatable validation checklist

## Sprint 4: Advanced Features & Production Readiness

### Stories
1. **AQ-401**: Engineering Principles Framework (4 tasks)
2. **AQ-402**: Graph-RAG Enhancements (4 tasks)
3. **AQ-403**: To-Be & Gap Analysis Diagrams (4 tasks)
4. **AQ-404**: Multi-Format Document Export (4 tasks)
5. **AQ-405**: Production Features (4 tasks)

### Key Deliverables
- Principle-to-discipline mapping baseline
- Hybrid Graph-RAG retriever
- To-Be diagram generation pipeline
- Production-ready export downloads (Word, Excel, PowerPoint, PDF)
- LLM traceability with Langfuse

## Task Structure

Each task follows this format:

| Column | Description |
|--------|-------------|
| **Sprint No.** | Sprint number (2, 3, or 4) |
| **Story ID** | Unique story identifier (e.g., AQ-301) |
| **Task ID** | Unique task identifier (e.g., AQ-301-T1) |
| **Task Description** | Brief description of the task |
| **Task Story Points** | Effort estimate (1-3 points) |
| **Dependencies** | Task dependencies (None or task IDs) |
| **Deliverables** | Expected outcome/artifact |

## Story Points Guide

- **1 point**: Small task, < 4 hours
- **2 points**: Medium task, 4-8 hours
- **3 points**: Large task, 1-2 days

## How to Use

### View in Excel
Open `Sprint_2-4_Backlog.xlsx` with Microsoft Excel, LibreOffice Calc, or Google Sheets:
- Color-coded by sprint (Green = Sprint 2, Orange = Sprint 3, Blue = Sprint 4)
- Frozen header row for easy scrolling
- Auto-filters enabled for all columns

### View in CSV
Open `Sprint_2-4_Backlog.csv` in any text editor or spreadsheet application for a simple view.

### Regenerate
Run the Python script to regenerate the backlog:

```bash
python generate_sprint_backlog.py
```

## Story Dependency Map

### Sprint 2 Dependencies
- AQ-301 (Process) → AQ-304 (Multi-format Export)
- AQ-302 (People) → AQ-304 (Multi-format Export)
- AQ-303 (Technology) → AQ-304 (Multi-format Export)
- AQ-304 (Export) → AQ-305 (Document Export)

### Sprint 3 Dependencies
- AQ-201 (Ingestion) → AQ-202 (Vector Store)
- AQ-201 (Ingestion) → AQ-203 (Knowledge Graph)
- AQ-202, AQ-203 → AQ-204 (Hybrid Retrieval)
- AQ-204 (Retrieval) → AQ-205 (Evaluation)

### Sprint 4 Dependencies
- AQ-203 (from Sprint 3) → AQ-401 (Principles Framework)
- AQ-203 (from Sprint 3) → AQ-402 (Graph-RAG)
- AQ-401, AQ-402 → AQ-403 (To-Be Diagrams)
- AQ-401 → AQ-404 (Document Export)
- AQ-402 → AQ-405 (Production Features)

## Notes

- This backlog is based on the advanced-QODE repository development history
- Task breakdown follows agile best practices with 3-point maximum per task
- All tasks have clear deliverables and dependencies
- Color coding in Excel helps visualize sprint boundaries

## Version History

- **v1.0** (2026-05-08): Initial Sprint 2-4 backlog creation
