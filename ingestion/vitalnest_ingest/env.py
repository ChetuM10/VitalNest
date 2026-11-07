"""Local secrets loading for the ingestion commands.

The implementation lives in the backend (app/config/env.py) so the API and the ingestion script
read keys from the same places with the same rules. See that module for the rules.
"""
from app.config.env import default_env_paths, load_env_files

__all__ = ["default_env_paths", "load_env_files"]
