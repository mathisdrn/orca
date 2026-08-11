import logging
from pathlib import Path

from dagster_malloy import MalloyProject

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_manifest() -> None:
    """Pre-compiles Malloy model AST manifests for fast and node-less server startup."""
    analytics_dir = PROJECT_ROOT / "analytics"
    project = MalloyProject(path=analytics_dir)
    manifest_path = project.prepare_if_dev()
    if manifest_path:
        logger.info("Pre-compiled Malloy AST manifest to %s", manifest_path)
    else:
        logger.info("Malloy AST manifest is up-to-date at %s", project.manifest_file)


if __name__ == "__main__":
    build_manifest()
