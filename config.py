"""Configuration management for BGA to BGG sync tool."""

import os
import json
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv
import yaml


class Config:
    """Manages application configuration from .env and config.yaml files."""

    def __init__(self, env_path: str = ".env", config_path: str = "config.yaml"):
        """Initialize configuration.

        Args:
            env_path: Path to .env file
            config_path: Path to config.yaml file
        """
        # Load environment variables
        load_dotenv(env_path)

        # Load YAML config
        self.yaml_config = self._load_yaml(config_path)

        # BGA configuration
        self.bga_player_id = os.getenv("BGA_PLAYER_ID")
        self.bga_username = os.getenv("BGA_USERNAME")
        self.bga_cookies = self._parse_json_env("BGA_COOKIES")

        # BGG configuration
        self.bgg_username = os.getenv("BGG_USERNAME")
        self.bgg_user_id = os.getenv("BGG_USER_ID")
        self.bgg_cookies = self._parse_json_env("BGG_COOKIES")

        # Database path
        db_path = self.yaml_config.get("database_path", "~/.bga2bgg/data.db")
        self.database_path = Path(db_path).expanduser()

        # Settings
        self.dry_run = self.yaml_config.get("dry_run", False)
        self.auto_confirm_high_confidence = self.yaml_config.get("auto_confirm_high_confidence", True)
        self.request_delay = self.yaml_config.get("request_delay", 1)
        self.max_retries = self.yaml_config.get("max_retries", 3)
        self.retry_backoff = self.yaml_config.get("retry_backoff", 2)
        self.log_level = self.yaml_config.get("log_level", "INFO")

        # Player name mappings (BGA -> BGG)
        self.player_mappings = self.yaml_config.get("player_mappings", {})

        # Validate configuration
        self.validate()

    def _load_yaml(self, config_path: str) -> Dict[str, Any]:
        """Load YAML configuration file.

        Args:
            config_path: Path to YAML file

        Returns:
            Configuration dictionary
        """
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            print(f"Warning: Config file {config_path} not found, using defaults")
            return {}

    def _parse_json_env(self, var_name: str) -> Dict[str, str]:
        """Parse JSON string from environment variable.

        Args:
            var_name: Environment variable name

        Returns:
            Parsed dictionary or empty dict if parsing fails
        """
        value = os.getenv(var_name)
        if not value:
            return {}

        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            print(f"Warning: Failed to parse {var_name}: {e}")
            return {}

    def validate(self) -> None:
        """Validate configuration and raise errors for missing required fields."""
        errors = []

        # Check BGA configuration
        if not self.bga_player_id:
            errors.append("BGA_PLAYER_ID not set in .env")

        if not self.bga_username:
            errors.append("BGA_USERNAME not set in .env")

        if not self.bga_cookies:
            errors.append("BGA_COOKIES not set or invalid JSON in .env")
        else:
            required_bga_cookies = ["PHPSESSID", "TournoiEnLigneid", "TournoiEnLignetk"]
            missing = [c for c in required_bga_cookies if c not in self.bga_cookies]
            if missing:
                errors.append(f"Missing required BGA cookies: {', '.join(missing)}")

        # Check BGG configuration
        if not self.bgg_username:
            errors.append("BGG_USERNAME not set in .env")

        if not self.bgg_user_id:
            errors.append("BGG_USER_ID not set in .env")

        if not self.bgg_cookies:
            errors.append("BGG_COOKIES not set or invalid JSON in .env")
        else:
            required_bgg_cookies = ["bggusername", "bggpassword", "SessionID"]
            missing = [c for c in required_bgg_cookies if c not in self.bgg_cookies]
            if missing:
                errors.append(f"Missing required BGG cookies: {', '.join(missing)}")

        if errors:
            error_msg = "\n".join([f"  - {e}" for e in errors])
            raise ValueError(f"Configuration errors:\n{error_msg}\n\nPlease check your .env file.")

    def ensure_database_directory(self) -> None:
        """Ensure the database directory exists."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
