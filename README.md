<p align="center">
    <a href="https://github.com/mathisdrn/orca">
  <img src="https://raw.githubusercontent.com/mathisdrn/mathisdrn.github.io/refs/heads/master/images/orca-banner.svg" alt="Orca logo" width="700">
    </a>
</p>

# Orca – a modern data platform

Orca is a template for building a production and agentic-ready **data warehouse**. It leverages a local-first development workflow that seamlessly scales to the cloud using entirely free and open-source tools.

> Orca is currently in early development. Feedback and contributions are welcome!

**Orca** is not a tool but a reference implementation of a modern data stack that can be easily incrementally adopted and extended. It provides a comprehensive framework for data ingestion, transformation, modeling, analytics, machine learning and reporting.

## Design Philosophy

- **Open:** Rely on open code, standards, formats and protocols.
- **Composable:** Components can be easily replaced, extended, or removed.
- **Declarative:** Code-based tools enable modern development practices and agentic workflows. It also improves interoperability and reproducibility.

## Core Value Proposition

- **Production-ready:** Provide a solid foundation for production workloads (managing environment, deployments, CI/CD, secrets management).
- **Benefit from modern development practices:** Version control, changes are one commit away, CI/CD, testing, code review and more.
- **Agentic-ready:**  Enable agentic behavior by providing agents with the right context, tools and security boundaries.
- **Quick onboarding:** Quickly get up and running with your sources of data and with a clear path to build your data warehouse.

## Architecture

**Orca** uses the following stack:
| Role | Tool | Purpose |
| :--- | :--- | :--- |
| **Environment** | **[uv](https://docs.astral.sh/uv/)** | Python environment management. |
| **Orchestration** | **[Dagster](https://dagster.io/)** | Orchestrates the asset graph, providing observability, scheduling, and orchestration. |
| **Ingestion** | **[dlt](https://dlthub.com/)** | Handles robust, schema-evolving data loading from APIs and external sources. |
| **Compute** | **[DuckDB](https://duckdb.org/)** | Provides serverless, in-process SQL compute for fast analytical queries. |
| **Storage** | **[DuckLake](https://ducklake.select/)** | Manages the data lake layer, decoupling storage (S3/Parquet/Iceberg) from compute. |
| **Transformation** | **[SQLMesh](https://sqlmesh.readthedocs.io/en/stable/)** | Brings CI/CD, virtual environments, and column-level lineage to SQL transformations. |
| **Modeling** | **[Malloy](https://www.malloydata.dev/)** | Defines a rich and composable semantic layer. |
| **Reporting** | **[Evidence](https://evidence.dev/)** | Generates static BI reports using Markdown and SQL. |
| **Data Apps** | **[Streamlit](https://streamlit.io/)** | Builds interactive data applications using pure Python. |
| **Notebooks** | **[Marimo](https://marimo.io/)** | Provides a reactive, reproducible notebook environment for exploration and ML. |

### Agentic-Ready

Orca is designed to be agentic-ready, allowing agents to operate autonomously across the stack:
- Add a new data source from API docs.
- Create a new transformation to clean and join data.
- Define a new semantic model to represent a business concept.
- Create a Streamlit dashboard to share insights with stakeholders.

The agentic-ready architecture is enabled by **infrastructure-as-context** approach:
1. **Progressive Context Loading:** Using AGENTS.md files at the root and within subfolders like /ingestion or /reporting, agents gain situational awareness of the directory structure, local conventions, and coding best practices.
2. **Documentation access:** The [Context7 MCP](https://context7.com/) grants agents direct access to external documentation, ensuring they can reference the official specs for every tool in the stack.
3. **Specialized Skills:** Dynamically loaded instructions sets and guidance for specific workflows:
    - **project-onboarding:** Guides users to understand the stack and connect their data up to a working dashboard.
    - **dev-ops:** Assist users with DevOps-related questions (managing environment, deployments, CI/CD, secrets management).
    - **data-ingestion:** Scaffolds advanced dlt pipelines with schema evolution, testing, and monitoring.
    - **data-transformation:**
        - Creates SQLMesh transformation pipelines.
        - Enforces SQLMesh best practices
        - Implements and tests [SCD Type 1, 2 and 3](https://en.wikipedia.org/wiki/Slowly_changing_dimension) and Star/Snowflake schemas.
    - **data-analyst-python:**
        - Querying the data warehouse using Python.
        - Creating plot using altair.
        - Transforming data using polars.
        - Creating Streamlit dashboards.
    - **data-scientist**
        - Creating advanced sklearn pipeline and models.
        - Explaining model results using PDP, SHAP and LIME.
4. **Security Boundaries:** Agents operate within a role-based, least-privilege execution environment to ensure safe command execution.

### Get started

1. Click on **Use this template** and **Create a new repository**.
2. Clone this new repository and open it in VS Code.
2. Read `.agents/skills/project-onboarding/SKILL.md` or simply ask an agent to `Get onboarded`. If properly configured, it will quickly help you integrate your data or get to know the architecture better. For a quick demo see [Orca-demo]().

### Staying Up-to-Date

To incorporate the latest features, improvements and fixes from the core template, follow this workflow:

```bash
# Ensure upstream remote is configured (ignores error if already exists)
git remote add upstream https://github.com/mathisdrn/Orca.git || true

# Fetch and merge latest changes
git fetch upstream
git merge upstream/main --allow-unrelated-histories

# Sync the Python environment
uv sync
```

*After running these commands, manually resolve merge conflicts.*

## References

### Prior Art & Inspiration

Real-world implementations of the modern data stack that inspired this project.

* **[datadex](https://datadex.dev/)** – A serverless, local-first Open Data Platform.
* **[nba-monte-carlo](https://github.com/matsonj/nba-monte-carlo)** – Originally *mds-in-a-box*, this project implements a full stack around NBA/NFL data with a custom [reporting front-end](https://mdsinabox.com/).
* **[Modern Data Stack in a Box](https://duckdb.org/2022/10/12/modern-data-stack-in-a-box)** – A reference implementation built on DuckDB, Meltano, dbt, and Apache Superset.

### Core Concepts & Philosophy

Foundational reading to understand the architectural decisions behind this platform.

* **[The Composable Codex](https://voltrondata.com/codex/)** – A comprehensive series on the principles, benefits, and evolution of the composable data stack.
* **[A Sequel to SQL? An introduction to Malloy](https://carlineng.com/?postid=malloy-intro#blog)** – A three-part series comparing SQL with Malloy, essential for understanding the shift in semantic modeling.

### Emerging Standards & Interoperability

Future-facing protocols and standards relevant to the platform's roadmap.

* **[Open Semantic Interchange (OSI)](https://opensemanticinterchange.org/)** – An Intermediate Representation (IR) standard for semantic layers.
* **[Substrait](https://substrait.io/)** – A cross-language serialization format for relational algebra, describing compute operations on structured data.
* **[Apache Superset Issue #35003](https://github.com/apache/superset/issues/35003)** – Tracking the integration of a generic semantic layer into Apache Superset.