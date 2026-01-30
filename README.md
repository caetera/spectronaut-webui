# Spectronaut WebUI

A NiceGUI-based web interface for [Spectronaut](https://biognosys.com/software/spectronaut/) proteomics software, designed to simplify mass spectrometry data processing workflows in cloud and command-line environments.

**Note:** This is an independent tool and is not officially affiliated with or endorsed by Biognosys AG.

## Features

- **Web-based GUI** - Modern, intuitive interface built with NiceGUI
- **Multiple Workflows** - Support for Convert, DirectDIA, DIA, and Combine workflows
- **File Management** - Interactive file browser for local file selection
- **Batch Processing** - Process multiple files with metadata (conditions, replicates, fractions)
- **Real-time Logging** - Live console output during processing
- **Process Control** - Start, monitor, and abort long-running processes

## Quick Start

### Installation

```bash
pip install spectronaut-webui
```

### Configuration

Generate a default configuration file:

```bash
spectronaut-ui-config
```

Edit `~/.spectronaut_webui/config.json` to set your Spectronaut command path and license key.

### Run

Start the web interface:

```bash
spectronaut-ui
```

Then open your browser to `http://localhost:8080`.

## Documentation

- **[Installation Guide](doc/INSTALLATION.md)** - Detailed installation instructions
- **[Configuration](doc/CONFIG.md)** - Configuration options and setup
- **[Usage Guide](doc/USAGE.md)** - Workflow tutorials and examples

## Requirements

- Python 3.10 or higher
- Spectronaut Command Line Interface
- Valid Spectronaut license key

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Author

Vladimir Gorshkov
