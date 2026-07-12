---
name: dlt-ingestion
description: Guides the creation, modification, and debugging of dlt (data load tool) ingestion pipelines in the ingestion/ folder. Use when writing new pipelines, adding endpoints, adjusting write dispositions, or configuring credentials.
---

# dlt Ingestion Guidelines

This skill guides the design, implementation, and troubleshooting of `dlt` (data load tool) pipelines in the Orca data warehouse.

## Project Ingestion Layout

In Orca, ingestion pipelines are written in Python under the [ingestion](file:///Users/mathisderenne/GitHub/orca/ingestion/) folder:
*   **Pipeline scripts**: Named using `*_pipeline.py` (e.g., `house_price_pipeline.py`).
*   **Pipeline Helper**: [utils.py](file:///Users/mathisderenne/GitHub/orca/ingestion/utils.py) contains central helpers to set up standard dlt destination configurations.
*   **Secrets & Config**: Stored in the `.dlt/` folder (which is ignored by Git, except for template files).

## Ingestion Principles

### 1. Declaring Sources and Resources
*   **Use Decorators**: Annotate your primary extraction function with `@dlt.source` and individual endpoints/resource streams with `@dlt.resource`.
*   **Parameterize Custom Arguments**: Expose configuration parameters as function arguments, providing sensible defaults:
    ```python
    @dlt.source
    def hackernews_source(
        api_url: str = dlt.config.value,
        api_token: str = dlt.secrets.value,
        limit: int = 100
    ):
        """Loads HackerNews articles.

        Args:
            api_url: Injected from config.toml
            api_token: Injected from secrets.toml
            limit: Standard parameter
        """
        ...
    ```

### 2. Standard Configuration and Secrets
*   **Never Hardcode Credentials**: Always use `dlt.secrets.value` to auto-inject credentials from `.dlt/secrets.toml`.
*   **Never Ask for Secrets in Chat**: Do not prompt the user to paste passwords or API keys in the chat. Instruct them to edit `.dlt/secrets.toml` directly.
*   **Use `replace` for Development**: Use `write_disposition="replace"` during initial development and testing to ensure a clean slate, switching to `append` or incremental loading (using `dlt.sources.incremental`) only when ready.

### 3. Iterative Development & Debugging
*   **Limit Output Size**: When run during development, add limits to prevent overloading the database:
    ```python
    # Load only a single batch or top 10 rows
    source = hackernews_source().with_resources("stories")
    source.add_limit(10)
    pipeline.run(source)
    ```
*   **State Exploration**: If a pipeline runs but results are unexpected, inspect the schema and dlt state using:
    ```bash
    uv run dlt pipeline <pipeline_name> show
    ```

## Step-by-Step Implementation Workflow

1.  **Analyze & Research**: Inspect the source API format and find which authentication method is required.
2.  **Scaffold**: Write a minimal script structure importing `dlt` and your helper `utils.py`.
3.  **Secrets & Configuration**: Add required template blocks to `.dlt/config.toml` and `.dlt/secrets.toml`.
4.  **Local Test Run**: Run the pipeline locally using `uv run python ingestion/<name>_pipeline.py`.
5.  **Refine & Scale**: Add incremental updates, column type casting, and schema contracts if required by the data source.
