import logging
from typing import Any

import polars as pl
from sqlmesh import ExecutionContext, model
from sqlmesh.core.model import ModelKindName


@model(
    name="a_raw.python_example",
    description="Example raw model: a toy dataset of sample products built with Polars",
    kind=dict(name=ModelKindName.FULL),
    grain="product_id",
    columns={
        "product_id": "int",
        "name": "text",
        "category": "text",
        "price": "float",
        "in_stock": "boolean",
    },
    column_descriptions={
        "product_id": "Unique product identifier",
        "name": "Product display name",
        "category": "Product category",
        "price": "Unit price in USD",
        "in_stock": "Whether the product is currently in stock",
    },
)
def execute(
    context: ExecutionContext,  # noqa: ARG001
    **kwargs: Any,  # noqa: ARG001, ANN401
) -> pl.DataFrame:
    """Return a toy Polars DataFrame of sample products.

    This model demonstrates how to write a Python-based SQLMesh model using Polars.
    Replace this with your own data-fetching or generation logic.
    """
    logger = logging.getLogger(__name__)
    logger.info("Building example product dataset")

    df = pl.DataFrame(
        {
            "product_id": [1, 2, 3, 4, 5],
            "name": ["Widget A", "Widget B", "Gadget X", "Gadget Y", "Gizmo Z"],
            "category": ["Widgets", "Widgets", "Gadgets", "Gadgets", "Gizmos"],
            "price": [9.99, 14.99, 24.99, 34.99, 49.99],
            "in_stock": [True, True, False, True, True],
        }
    )

    return df
