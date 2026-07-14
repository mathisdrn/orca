<p align="center">
    <a href="https://github.com/mathisdrn/orca?tab=readme-ov-file#orca--a-modern-data-warehouse">
  <img src="https://raw.githubusercontent.com/mathisdrn/mathisdrn.github.io/refs/heads/master/images/orca/orca-banner.svg" alt="Orca logo" width="700">
    </a>
</p>

# Orca – a modern data warehouse

Orca is an implementation of a serverless, declarative and agentic-ready [data warehouse](https://en.wikipedia.org/wiki/Data_warehouse) built with best-in-class, free, and open-source tools.

## Features 

- **Fits most data teams:** Provides a comprehensive framework for data ingestion, transformation, orchestration, observability and reporting capable of scaling to large volumes of data.
- **Serverless:** Runs entirely on ephemeral compute and cost-effective object storage.
- **Declarative:** Built on code and configuration, enabling modern software engineering practices like version control, CI/CD, and reproducible environments.
- **Agentic-ready:** Built-in documentation and workflows for humans and AI agents.
- **Easy setup:** Clone the repository, execute the pipelines and start experimenting.
- **Make it yours:** Easily adaptable and extensible to different needs.

## Content

Orca data warehouse is built around [HackerNews](https://hcker.news/) data. HackerNews is a news aggregator where users submit and vote on articles, comments and discussions. It is a popular source of information for tech enthusiasts, developers and entrepreneurs.

<!-- To complete: explain what Orca do with the data and what is the final goal of the project. -->

## Architecture

<img src="https://github.com/mathisdrn/mathisdrn.github.io/raw/a11a3721b0c3a2213fc710b6ebf69771a5114095/images/orca/orca-warehouse-architecture.png" alt="Orca data warehouse architecture diagram" width="100%">

### Ingestion

Every day, new stories, comments, and user profiles are fetched from the [HackerNews REST API](https://github.com/hackernews/api) and ingested into the `raw` layer of the data warehouse. **Ingestion pipelines** are written using Python and [dlt](https://dlthub.com/product/dlt), which facilitates data extraction, schema inference, normalization, and loading into the warehouse.

<details>
<summary>More about ingestion using dlt</summary>

- dlt extracts data from [REST APIs](https://dlthub.com/docs/tutorial/rest-api), [SQL databases](https://dlthub.com/docs/tutorial/sql-database), [cloud storage](https://dlthub.com/docs/tutorial/filesystem) and [many more](https://dlthub.com/docs/dlt-ecosystem/verified-sources)
- dlt infers [schemas](https://dlthub.com/docs/general-usage/schema) and [data types](https://dlthub.com/docs/general-usage/schema/#data-types), [normalizes the data](https://dlthub.com/docs/general-usage/schema/#data-normalizer), and handles nested data structures.
- dlt supports a variety of [destinations](https://dlthub.com/docs/dlt-ecosystem/destinations/).
- dlt implements [incremental loading](https://dlthub.com/docs/general-usage/incremental-loading), [schema evolution](https://dlthub.com/docs/general-usage/schema-evolution), and [schema and data contracts](https://dlthub.com/docs/general-usage/schema-contracts).
- dlt provides a [dashboard](https://dlthub.com/docs/hub/ingestion/dashboard) to inspect pipelines and visualize data.
</details>

### Transformation

Data is progressively cleaned and structured inside the data warehouse. The `marts` layer contains business-ready tables (materialized as views) that have been joined and structured to form final datasets. **Transformation pipelines** are written using SQL with [dbt](https://docs.getdbt.com/docs/introduction?version=2.0&name=Fusion) transformation framework.

<details>
<summary>More about transformation using dbt</summary>

dbt is a SQL-based data transformation framework:
- dbt transforms data directly in the warehouse using SQL and Jinja templating.
- dbt parses SQL files and generates a dependency graph, allowing for incremental and parallel execution.
- dbt supports data testing (uniqueness, non-null values, and referential integrity).
- dbt auto-generates project documentation and data lineage graphs.
</details>

> [!TIP]
> Explore the dbt models and data lineage of the data warehouse at **https://mathisdrn.github.io/orca/dbt-docs**.

### Orchestration & Observability

The data warehouse ingestion and transformation pipelines are **orchestrated** using [Dagster](https://www.dagster.io/). 

Dagster integrates with `dlt` and `dbt` to generate a unified view of asset dependencies. It manages the execution of ingestion and transformation pipelines while tracking execution details and asset metadata, such as runtime logs, performance, and row counts. [**Dagster UI**](https://docs.dagster.io/guides/operate/webserver) provides a user interface to view asset dependencies and execution history.

> [!TIP]
> Explore the live asset graph and execution history of the data warehouse at **https://orca-datawarehouse.dev/orchestration**
> 
> *The Dagster UI is hosted in **read-only mode** on a serverless Google Cloud Run instance.*

<!-- <img src="" alt="Dagster UI for Orca" width="100%"> -->

### Database storage and compute

Orca uses [DuckDB](https://duckdb.org/) as a fast and lightweight analytical database. Its **database query engine** is used to load, transform and query the data using SQL.

DuckDB stores the warehouse using the [DuckLake](https://ducklake.select/) **lakehouse format** inside the repository. This format stores data using **parquet files** and a `orca.ducklake` **catalog**, designed to track warehouse metadata (such as tables, schemas and file paths).

<details>
<summary>This architecture is called a data lakehouse. Read more about it.</summary>

The **data lakehouse** architecture effectively separates the **storage** layer (parquet files and metadata) from the **compute** layer (DuckDB) and offers several benefits:
- It enables **serverless**, **scalable** and **cost-effective** data warehousing, as the data can be stored in object storage and queried on-demand without requiring a dedicated database server.
- Any DuckLake compatible client (DuckDB, Postgres and [more](https://ducklake.select/docs/stable/#list-of-ducklake-clients)) can **efficiently** and **concurrently** query the data warehouse.
- DuckLake supports **schema evolution** and **data versioning** allowing for incremental updates and [time travel queries](https://ducklake.select/docs/stable/duckdb/usage/time_travel).
</details>

### Execution

The warehouse is updated weekly using a **GitHub Actions** workflow that orchestrates the ingestion and transformation pipelines using Dagster.

<img src="https://github.com/mathisdrn/mathisdrn.github.io/raw/7f96ce024b2b8cc1beb54568c24e46e8b504273e/images/orca/orca-lakehouse-execution.png" alt="Orca data lakehouse execution diagram" width="100%">

Artifacts generated during the execution are pushed to the repository. This includes the lakehouse (`orca.ducklake` + parquet files) and dagster state (execution history and logs).

For **local development**, developers can simply pull the repository and have access to the latest version of the data warehouse.
Execution artifacts are git-ignored for local development and testing but force-pushed to the repository during the weekly execution workflow.

> [!TIP]
> Because the database is publicly hosted on GitHub using DuckLake format, any [query engine that speaks DuckLake](https://ducklake.select/docs/stable/#list-of-ducklake-clients) can remotely query the data lakehouse. The DuckDB team calls this a [frozen DuckLake](https://ducklake.select/2025/10/24/frozen-ducklake/). 
>
> Explore the latest database in your browser using this [Duck-UI query](https://demo.duckui.com/#s=H4sIAAAAAAAAE1WNzU7DMBCEX2XlSyWUH-CYnEyTqlEdIupUIJSLcUxjNbGLvaYqiHdHraiA2-zMtzOf5J1ktxHB416RjPi3kUQENY6n6yEod4TGSQGvzn4oA32Qu1HsFDg1WVTjkUTnn4zEMfzBe4ECDsKpwQb_S0Pw2myhCHJX3EGvxagkJp3pDGtoAcVmvmJ0VeadoW1L50uoFnDftFA-VbzlMLvMZwPi3mdp6sQh2WocwkvwyklrUBlMpJ3SSeCgfe9Map0U6SS0ST1aJ7bq7CSXrhlQDicn78yGlxfZGb5sHoEyBi29YyXPOxPHwDd1TdfVcwmTcOiTU6VW_icsWTlv4QoW66b-DwCr6qqFm-ucREQEtOtgSIYuqK9vAZk7B4MBAAA).

### Semantic layer

Orca uses [Malloy](https://malloydata.dev) as a **semantic layer** to create reusable data models and metrics on top of the data warehouse `marts` layer. Malloy models compile to SQL queries that can be used for consumption by reporting tools and dashboards.

### Reporting

Orca hosts a [Malloy Publisher](https://docs.malloydata.dev/documentation/user_guides/publishing/publishing) server. It contains interactive dashboards and lets users build their own tables and visualizations using the Malloy semantic models.

> [!TIP]
> Explore the dashboards and build your own at [https://orca-datawarehouse.dev/reporting/](https://orca-datawarehouse.dev/reporting/).
> 
> *The Malloy Publisher server runs on a Google Cloud Run serverless instance and uses [MotherDuck](https://www.motherduck.com/) free-tier to query the frozen DuckLake data warehouse.*

Orca also uses [Streamlit](https://streamlit.io/) to create interactive dashboards in Python. The dashboard is publicly accessible at [https://orca-dashboard.streamlit.app](https://orca-dashboard.streamlit.app).

## Agentic-ready

Orca is designed to be easily adopted and used by humans and AI Agents.

Orca includes `AGENTS.MD` files throughout the codebase to provide context and domain knowledge for AI agents.

Orca bakes domain knowledge, context and documentation into the project structure:
- `AGENTS.MD` files provide specific context relevant to the folder they are located in.
- `SKILLS` files describe workflows and tool-specific knowledge.
- [Malloy Publisher MCP Server](https://docs.malloydata.dev/documentation/user_guides/publishing/mcp_agents) helps AI agents efficiently explore Malloy models.

## Get started

To get started with Orca, follow these steps:
1. Clone the repository
2. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
3. Install dependencies using `uv sync`
4. Copy `.env.example` to `.env` and replace {PROJECT_ROOT} with the absolute path to the project.
5. (optional) Install the recommended IDE extensions (VS Code, Cursor, Antigravity IDE).
6. (optional) Ignore local modifications to the database and execution logs:
   ```bash
   git update-index --skip-worktree $(git ls-files storage/orca.ducklake storage/orca.ducklake.files/ orchestration/dagster_home/ | grep -v 'dagster.yaml')
   ```

You can then:
- Run Dagster UI using `dg dev`
- Run ingestion and transformation pipeline using `dg launch --assets "*"`
- Explore the local database using the [DuckDB UI](https://duckdb.org/2025/03/12/duckdb-ui):
  ```bash
  uv run duckdb -ui "ducklake:storage/orca.ducklake"
  ```
- Explore the Malloy semantic layer using the IDE extension.

## Project structure

```text
orca/
├── .agents/             # Agent skills
├── .github/             # GitHub Actions workflows
├── analytics/           # Dashboards and Malloy semantic models
├── ingestion/           # dlt ingestion pipelines and configurations
├── orchestration/       # Dagster orchestration assets and configurations
├── storage/             # DuckLake storage + utils
├── transformation/      # dbt transformation models
│   ├── models/          # dbt models layers
│   │   └── marts/       # Cleaned and structured raw data (views)
├── AGENTS.md            # Documentation entry-points: context and guideline 
└── pyproject.toml       # Project environment and dependencies
```

## Orca in a production environment 

> [!NOTE]
> Orca is designed to be a **complete** and **functional** data warehouse implementation while also being **cost-effective** and **easy to understand, execute, reuse and extend**.

If you are evaluating Orca for an enterprise production environment, keep these architectural limitations and scale-up recommendations in mind:

### Limitations and recommendations

| Feature | Orca | Recommendations |
| --- | --- | --- |
| **Write concurrency** | ❌ DuckDB does not support concurrent writes. | Use a **Postgres** database with the **DuckLake catalog extension** or [MotherDuck](https://www.motherduck.com/) for managed hosting. |
| **Database permissions** | ⚠️ DuckLake only supports basic write/read/superuser permission model. | Use a **Postgres** database with the **DuckLake catalog extension**. |
| **Streaming / Real-time** | ❌ Only supports sequential micro-batching (~10 min intervals). | Consider using specific streaming tools (eg. Kafka, Kinesis). |
| **Database storage** | ⚠️ Hosted on GitHub. | Use private **object storage** or [MotherDuck](https://www.motherduck.com/) for managed hosting instead. |
| **Orchestration storage** | ⚠️ Hosted on GitHub in `dagster_home`. | [Persist Dagster state using a Postgres database](https://docs.dagster.io/deployment/oss/oss-instance-configuration#dagster-storage) and [save Dagster logs to object storage](https://docs.dagster.io/deployment/oss/oss-instance-configuration#compute-log-storage). |
| **CI/CD** | ⚠️ Commits and PR do not trigger warehouse executions or tests. | Use a **CI/CD workflow** to test pull requests and ensure data integrity. |
| **Environments & Backup** | ❌ No dev/prod environments, replication, or backup patterns. | Build custom CI/CD workflows. |
| **Secrets Management** | ❌ No secrets management tool implemented. | Integrate a dedicated secrets manager (eg. HashiCorp Vault). |
| **Containerization** | ❌ No containerization implementation. | Use **Docker** and **Kubernetes** for containerization and infra orchestration. |

> [!TIP]
> [MotherDuck](https://www.motherduck.com/) supports concurrent writes and includes a generous free-tier plan.
>
> [Neon](https://neon.tech/) or [Supabase](https://supabase.com/) are also good alternatives for managed Postgres hosting with free-tier plans.

> [!TIP]
> DuckDB is planning to support concurrent writes via their [Quack protocol](https://duckdb.org/quack/), which is expected to have a stable release around September 2026.

## Further Reading

### Inspiration

Modern data stack implementations that inspired this project:

* [**nba-monte-carlo**](https://github.com/matsonj/nba-monte-carlo) – Originally [*mds-in-a-box*](https://duckdb.org/2022/10/12/modern-data-stack-in-a-box), this project implements a modern data stack around sports data featuring a [reporting front-end](https://mdsinabox.com/).
* [**datadex**](https://datadex.datonic.io/) – A serverless, local-first Open Data Platform.

### Recommended reading

Foundational reading to understand the evolution of data tools and data warehouse architecture.

* [**The Composable Codex**](https://voltrondata.com/codex/) – From 1980s monolithic IBM mainframes to modern tools and architecture. Explores how standards, protocols and Intermediate Representation (IR) have enabled interoperability, composability and extensibility across data tools.
* [**A Sequel to SQL? An introduction to Malloy**](https://carlineng.com/?postid=malloy-intro#blog) – A three-part series exploring the limitations of traditional SQL for analytics and the growing need for semantic layers like Malloy.
* [**Is DuckLake a Step Backward?**](https://www.pracdata.io/p/is-ducklake-a-step-backward) – History of data lakes format and architecture and where DuckLake fits in.

### Emerging standards

Future-facing protocols and standards pushing interoperability and composability further.

* [**Open Semantic Interchange (OSI)**](https://opensemanticinterchange.org/) – An Intermediate Representation (IR) standard for semantic layers.
* [**Substrait**](https://substrait.io/) – A cross-language serialization format for relational algebra, describing compute operations on structured data.
* [**Apache Superset Issue #35003**](https://github.com/apache/superset/issues/35003) – Tracking the integration of a generic semantic layer into Apache Superset.