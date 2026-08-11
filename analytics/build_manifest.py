import json
import logging
from pathlib import Path

from dagster_malloy.cli_client import MalloyCliClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_manifest() -> None:
    """Pre-compiles Malloy model AST manifests for fast and node-less server startup."""
    analytics_dir = PROJECT_ROOT / "analytics"
    malloy_files = list(analytics_dir.glob("**/*.malloy")) + list(
        analytics_dir.glob("**/*.malloynb")
    )

    client = MalloyCliClient()
    for file_path in malloy_files:
        try:
            ast_dict = client.parse_ast(file_path)
            manifest_path = file_path.parent / f"{file_path.stem}.malloy.json"
            manifest_path.write_text(json.dumps(ast_dict, indent=2), encoding="utf-8")
            logger.info(
                "Pre-compiled Malloy AST manifest: %s -> %s",
                file_path.name,
                manifest_path.name,
            )
        except Exception:
            logger.exception("Failed to pre-compile AST manifest for %s", file_path.name)


if __name__ == "__main__":
    build_manifest()
