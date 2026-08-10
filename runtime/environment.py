"""
Hard environment/DB-path separation for Wave 1 staging work.

A typo must not be enough to destroy production data. This module is the one
place that decides whether a given `database_url` is allowed to be opened
under a given `environment` label, and produces the startup banner text so
the environment and DB path are always visible to the operator.
"""

from __future__ import annotations

from dataclasses import dataclass

PRODUCTION = "production"
STAGING = "staging"
VALID_ENVIRONMENTS = {PRODUCTION, STAGING}


class EnvironmentMismatchError(RuntimeError):
    """Raised when the resolved database_url does not match the declared environment."""


def _db_path_marker(database_url: str) -> str:
    """Best-effort path fragment for sqlite URLs; non-sqlite URLs fall through untouched."""
    return database_url.replace("sqlite:///", "").replace("\\", "/").lower()


def looks_like_staging_db(database_url: str) -> bool:
    return "staging" in _db_path_marker(database_url)


def looks_like_production_db(database_url: str) -> bool:
    marker = _db_path_marker(database_url)
    return marker.endswith("clank.db") and not looks_like_staging_db(database_url)


def assert_db_matches_environment(database_url: str, environment: str) -> None:
    """
    Fail closed. Only sqlite paths are pattern-checked (the only backend in use
    today); a non-sqlite URL cannot be verified this way and is allowed through
    unchanged rather than guessed at.
    """
    if environment not in VALID_ENVIRONMENTS:
        raise EnvironmentMismatchError(
            f"Unknown environment {environment!r}; expected one of {sorted(VALID_ENVIRONMENTS)}"
        )
    if not database_url.startswith("sqlite"):
        return

    if environment == STAGING and not looks_like_staging_db(database_url):
        raise EnvironmentMismatchError(
            f"Refusing to run --environment staging against database_url={database_url!r}: "
            "the path does not look like a staging database (expected 'staging' in the path). "
            "This guard exists so a config typo cannot point staging collectors at production data."
        )
    if environment == PRODUCTION and looks_like_staging_db(database_url):
        raise EnvironmentMismatchError(
            f"Refusing to run --environment production against database_url={database_url!r}: "
            "the path looks like a staging database. Check --config / CLANK_LOCAL_CONFIG."
        )


def assert_safe_to_destroy(database_url: str) -> None:
    """Gate for any destructive reset command. Production paths are never eligible."""
    if looks_like_production_db(database_url) or not looks_like_staging_db(database_url):
        raise EnvironmentMismatchError(
            f"Refusing destructive reset on database_url={database_url!r}: "
            "only databases with 'staging' in the path may be reset this way."
        )


@dataclass
class Banner:
    environment: str
    database_url: str
    config_path: str

    def render(self) -> str:
        label = "STAGING" if self.environment == STAGING else "PRODUCTION"
        color = "yellow" if self.environment == STAGING else "green"
        lines = [
            f"[bold {color}]ENVIRONMENT: {label}[/bold {color}]",
            f"  config:   {self.config_path}",
            f"  database: {self.database_url}",
        ]
        if self.environment == STAGING:
            lines.append(
                "  [yellow]staging DB — candidate collectors allowed, "
                "no production Discord, no production confidence pollution[/yellow]"
            )
        return "\n".join(lines)
