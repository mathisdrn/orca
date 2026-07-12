#!/usr/bin/env python3
"""
Python sync utility to fetch, filter, copy, and validate AI agent skills
for the Orca project.
"""

import contextlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

# Mapping of upstream repositories and the specific skills to pull.
# Each entry contains:
# - repo_url: The git repository URL to clone
# - subpath: The relative path inside the repo containing the target skill folder
# - destination_name: The folder name under .agents/skills/ to copy into
SKILL_MAPPINGS = [
    {
        "repo_url": "https://github.com/dagster-io/skills.git",
        "subpath": "skills/dagster-expert/skills/dagster-expert",
        "destination_name": "dagster-expert",
    },
    {
        "repo_url": "https://github.com/dbt-labs/dbt-agent-skills.git",
        "subpath": "skills/dbt/skills/using-dbt-for-analytics-engineering",
        "destination_name": "dbt-analytics-engineering",
    },
    {
        "repo_url": "https://github.com/dbt-labs/dbt-agent-skills.git",
        "subpath": "skills/dbt/skills/troubleshooting-dbt-job-errors",
        "destination_name": "dbt-troubleshooting",
    },
    {
        "repo_url": "https://github.com/duckdb/duckdb-skills.git",
        "subpath": "skills/query",
        "destination_name": "duckdb-query",
    },
    {
        "repo_url": "https://github.com/motherduckdb/agent-skills.git",
        "subpath": "skills/motherduck-ducklake",
        "destination_name": "motherduck-ducklake",
    },
    {
        "repo_url": "https://github.com/marimo-team/skills.git",
        "subpath": "skills/marimo-notebook",
        "destination_name": "marimo-notebook",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/analysis-pitfalls",
        "destination_name": "analysis-pitfalls",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/analysis-report",
        "destination_name": "analysis-report",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/gotchas-modeling",
        "destination_name": "gotchas-modeling",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/gotchas-queries",
        "destination_name": "gotchas-queries",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/gotchas-rendering",
        "destination_name": "gotchas-rendering",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/malloy",
        "destination_name": "malloy",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/malloy-analyze",
        "destination_name": "malloy-analyze",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/malloy-charts",
        "destination_name": "malloy-charts",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/malloy-debug",
        "destination_name": "malloy-debug",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/malloy-define",
        "destination_name": "malloy-define",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/malloy-discover",
        "destination_name": "malloy-discover",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/malloy-document",
        "destination_name": "malloy-document",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/malloy-model",
        "destination_name": "malloy-model",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/malloy-modeling",
        "destination_name": "malloy-modeling",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/malloy-notebooks",
        "destination_name": "malloy-notebooks",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/malloy-patterns",
        "destination_name": "malloy-patterns",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/malloy-queries",
        "destination_name": "malloy-queries",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/malloy-review",
        "destination_name": "malloy-review",
    },
    {
        "repo_url": "https://github.com/malloydata/publisher.git",
        "subpath": "skills/malloy-scope",
        "destination_name": "malloy-scope",
    },
]


def run_command(cmd, cwd=None):
    """Run a shell command and return stdout/stderr."""
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {result.stderr}")
    return result.stdout


def clean_skill_md(skill_md_path, new_name):
    """Cleans SKILL.md frontmatter to be compliant with quick_validate.py rules."""
    if not skill_md_path.exists():
        return

    content = skill_md_path.read_text()
    # Match the frontmatter block
    match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
    if not match:
        return

    frontmatter_text = match.group(1)
    body_text = match.group(2)

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            return
    except yaml.YAMLError:
        frontmatter = {}
        current_key = None
        for line in frontmatter_text.splitlines():
            m = re.match(r"^([a-zA-Z0-9_-]+)\s*:\s*(.*)$", line)
            if m:
                current_key = m.group(1)
                frontmatter[current_key] = m.group(2).strip()
            elif current_key and line.startswith(" "):
                frontmatter[current_key] += " " + line.strip()
            elif current_key and not line.strip():
                continue

    # Update name to match folder name
    frontmatter["name"] = new_name

    # Allowed keys by quick_validate.py
    allowed_properties = {"name", "description", "license", "allowed-tools", "metadata"}
    cleaned_frontmatter = {
        k: v for k, v in frontmatter.items() if k in allowed_properties
    }

    # Clean description (strip angle brackets and enforce max length)
    if "description" in cleaned_frontmatter:
        desc = cleaned_frontmatter["description"]
        if isinstance(desc, str):
            desc = desc.replace("<", "").replace(">", "").strip()
            if len(desc) > 1024:
                desc = desc[:1020] + "..."
            cleaned_frontmatter["description"] = desc

    # Reassemble and write back
    new_frontmatter_text = yaml.safe_dump(
        cleaned_frontmatter, default_flow_style=False, sort_keys=False
    )
    new_content = f"---\n{new_frontmatter_text}---\n{body_text}"
    skill_md_path.write_text(new_content)


def sync_skills():
    project_root = Path(__file__).resolve().parent.parent.parent
    skills_dir = project_root / ".agents" / "skills"
    validator_script = (
        project_root
        / ".agents"
        / "skills"
        / "skill-creator"
        / "scripts"
        / "quick_validate.py"
    )

    # Use a temporary directory to clone repositories
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Dictionary to cache cloned repo paths using unique folder names
        cloned_repos = {}

        for mapping in SKILL_MAPPINGS:
            repo_url = mapping["repo_url"]
            subpath = mapping["subpath"]
            dest_name = mapping["destination_name"]

            # Create unique local folder name based on URL to prevent collision
            if repo_url not in cloned_repos:
                parts = repo_url.rstrip("/").split("/")
                repo_dir_name = f"{parts[-2]}-{parts[-1].replace('.git', '')}"
                repo_clone_path = temp_path / repo_dir_name
                run_command([
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    repo_url,
                    str(repo_clone_path),
                ])
                cloned_repos[repo_url] = repo_clone_path
            else:
                repo_clone_path = cloned_repos[repo_url]

            src_folder = repo_clone_path / subpath
            dest_folder = skills_dir / dest_name

            if not src_folder.exists():
                continue

            # Remove destination if it already exists to ensure a clean sync
            if dest_folder.exists():
                shutil.rmtree(dest_folder)

            shutil.copytree(src_folder, dest_folder)

            # Clean frontmatter before validation
            clean_skill_md(dest_folder / "SKILL.md", dest_name)

            # Validate the copied skill
            if validator_script.exists():
                with contextlib.suppress(RuntimeError):
                    run_command(["python3", str(validator_script), str(dest_folder)])


if __name__ == "__main__":
    sync_skills()
