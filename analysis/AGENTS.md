# AGENTS.md - analysis/

## Overview
This directory contains things that create value out of data: 
- Dashboards using Streamlit, 
- EDA notebooks
- Machine learning experiments

## SQL Best Practices
- Always query from `c_marts.*` tables; avoid querying raw or staging.
- Prefer explicit `SELECT` lists over `SELECT *`.

## Python Code Style
- Prefer Polars instead of Pandas for DataFrame operations.
- Use explicit type hints
- Prefer explicit imports
