# Qora Architecture: Code Intelligence Layer

This module serves as the central nervous system for EcodiaOS's advanced AI agents like Evo and Nova. It continuously scans the codebase to build and maintain a live **Knowledge Graph** in Neo4j.

## Core Components

1.  **The Knowledge Graph:** A real-time, queryable "digital twin" of the entire codebase. It models every file, function, method, and tool, along with their properties and relationships.

2.  **The "Patrol" Daemon (`patrol.py`):** A scanner that walks the specified codebase, parses source files (starting with Python), and idempotently updates the knowledge graph. It's the ETL pipeline that keeps the graph synchronized with the code on disk.

## Purpose

-   **Discovery & Planning:** Enables "architect" agents like Evo/Nova to perform sophisticated queries across the entire codebase to understand dependencies, find relevant functions, and formulate precise, targeted tasks.
-   **Execution:** Allows "executor" agents like Simula to receive these precise tasks without needing to perform broad discovery themselves, making their job more focused and reliable.
-   **Audit & Analysis:** Creates a rich, historical record of how code is being proposed, reviewed, and changed by AI agents.

## Setup & Usage

### 1. Initialize the Graph Schema

Before the first run, you must set up the necessary constraints and indexes in your Neo4j database. This ensures data integrity and high-performance queries.

```bash
# Ensure your NEO4J_* environment variables are set
python -m systems.qora.core.architecture.graph_setup