"""Configuration management for Spectronaut UCloud GUI."""
import json
import logging
from os import environ
from pathlib import Path
from typing import Dict, Any, Optional

DEFAULT_CONFIG = {
    'spectronaut_command': ['dotnet', '/usr/lib/spectronaut/SpectronautCMD.dll'],
    'default_dir': '/work',
    'spectronaut_key': None,  # Will be read from environment if not in config
    'port': 8080,
}


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from file or use defaults.
    
    Args:
        config_path: Path to configuration JSON file. If None, searches for
                    'config.json' in ~/.spectronaut_webui/.
    
    Returns:
        Dictionary with configuration values.
    """
    config = DEFAULT_CONFIG.copy()
    
    # Try to find config file
    if config_path is None:
        # Look in user's home directory
        config_path = Path.home().joinpath('.spectronaut_webui', 'config.json')
    else:
        config_path = Path(config_path)
    
    # Load from file if it exists
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                config.update(user_config)
        except (json.JSONDecodeError, OSError) as e:
            # If config file is malformed or unreadable, log warning and use defaults
            logging.getLogger().warning(f"Warning: Could not load config from {config_path}: {e}")
            logging.getLogger().info("Using default configuration.")
    
    # Environment variable takes precedence over config file for license key
    env_key = environ.get('SPECTRONAUTKEY', None)
    if env_key is not None:
        config['spectronaut_key'] = env_key
    
    return config


def create_default_config(config_path: Optional[str] = None) -> Path:
    """Create a default configuration file.
    
    Args:
        config_path: Path where to create the config file. If None, creates
                    'config.json' in ~/.spectronaut_webui/.
    
    Returns:
        Path to the created configuration file.
    """
    if config_path is None:
        config_dir = Path.home().joinpath('.spectronaut_webui')
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir.joinpath('config.json')
    else:
        config_path = Path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, 'w') as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    
    return config_path


def generate_config_cli() -> None:
    """CLI entry point to generate a default configuration file.
    
    Creates a default config.json in ~/.spectronaut_webui/ if it doesn't exist,
    or confirms the existing location.
    """
    config_path = Path.home().joinpath('.spectronaut_webui', 'config.json')
    
    if config_path.exists():
        print(f"Configuration file already exists at: {config_path}")
    else:
        created_path = create_default_config()
        print(f"Default configuration file created at: {created_path}")
        print("\nPlease edit this file to configure:")
        print("  - spectronaut_command: Command to run Spectronaut")
        print("  - spectronaut_key: License key (or set SPECTRONAUTKEY environment variable)")
        print("  - default_dir: Default working directory")
        print("  - port: Web UI port (default: 8080)")
