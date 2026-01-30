# Installation Guide

This guide covers installing Spectronaut WebUI on your system.

## Prerequisites

Before installing, ensure you have:

- **Python 3.10 or higher** installed
- **Spectronaut Command Line Interface** installed and accessible
- A valid **Spectronaut license key**

### Check Python Version

```bash
python --version
# or
python3 --version
```

If Python is not installed or the version is too old, download it from [python.org](https://www.python.org/downloads/).

## Installation Methods

### Method 1: Install from PyPI (Recommended)

Install the latest stable version using pip:

```bash
pip install spectronaut-webui
```

### Method 2: Install from Source

For the latest development version or to contribute:

```bash
# Clone the repository
git clone https://github.com/yourusername/spectronaut-webui.git
cd spectronaut-webui

# Install in development mode
pip install -e .
```

### Method 3: Install with Development Dependencies

If you plan to develop or test the package:

```bash
# Clone the repository
git clone https://github.com/yourusername/spectronaut-webui.git
cd spectronaut-webui

# Install with development dependencies
pip install -e ".[dev]"
```

## Post-Installation Setup

### 1. Generate Configuration File

After installation, generate the default configuration:

```bash
spectronaut-ui-config
```

This creates `~/.spectronaut_webui/config.json` with default settings.

### 2. Configure Spectronaut Path

Edit the configuration file to set the correct path to Spectronaut:

```bash
# On Linux/Mac
nano ~/.spectronaut_webui/config.json

# On Windows
notepad %USERPROFILE%\.spectronaut_webui\config.json
```

Update the `spectronaut_command` field:

```json
{
  "spectronaut_command": [
    "dotnet",
    "/path/to/SpectronautCMD.dll"
  ],
  "default_dir": "/work",
  "spectronaut_key": null,
  "port": 8080
}
```

### 3. Set License Key

You have two options for providing the Spectronaut license key:

**Option A: Environment Variable (Recommended)**

```bash
# Linux/Mac
export SPECTRONAUTKEY="your-license-key-here"

# Windows (Command Prompt)
set SPECTRONAUTKEY=your-license-key-here

# Windows (PowerShell)
$env:SPECTRONAUTKEY="your-license-key-here"
```

To make it permanent, add it to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.).

**Option B: Configuration File**

Edit `~/.spectronaut_webui/config.json`:

```json
{
  "spectronaut_key": "your-license-key-here"
}
```

**Note:** The environment variable takes precedence over the config file.

## Verify Installation

Test that everything is installed correctly:

```bash
# Start the web interface (press Ctrl+C to stop)
spectronaut-ui
```

If the server starts successfully, open your browser to `http://localhost:8080`.

## Troubleshooting

### Command Not Found

If `spectronaut-ui` is not found after installation:

1. Ensure pip's script directory is in your PATH
2. Try using `python -m spectronaut_webui.main` instead

### Permission Errors

If you encounter permission errors during installation:

```bash
# Use --user flag to install for current user only
pip install --user spectronaut-webui
```

### Dependency Conflicts

If you have dependency conflicts:

```bash
# Create a virtual environment
python -m venv spectronaut-env
source spectronaut-env/bin/activate  # On Windows: spectronaut-env\Scripts\activate

# Install in the virtual environment
pip install spectronaut-webui
```

### Port Already in Use

If port 8080 is already in use, change it in the config file:

```json
{
  "port": 8090
}
```

## Upgrading

To upgrade to the latest version:

```bash
pip install --upgrade spectronaut-webui
```

## Uninstalling

To remove Spectronaut WebUI:

```bash
pip uninstall spectronaut-webui
```

Configuration files in `~/.spectronaut_webui/` are not automatically removed.

## Next Steps

- See [Configuration Guide](CONFIG.md) for detailed configuration options
- See [Usage Guide](USAGE.md) for workflow tutorials
