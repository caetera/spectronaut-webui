# Configuration

The Spectronaut UCloud GUI can be configured using a `config.json` file placed in `~/.spectronaut_webui/` directory in your home folder.

## Generating Configuration File

You can generate a default configuration file by running:

```bash
spectronaut-ui-config
```

This will create a `config.json` file in `~/.spectronaut_webui/` with default values.

## Configuration File

If no `config.json` file exists, the application will use default values:

- **spectronaut_command**: `["dotnet", "/usr/lib/spectronaut/SpectronautCMD.dll"]`
- **default_dir**: `/work`
- **spectronaut_key**: Read from `SPECTRONAUTKEY` environment variable

## Example Configuration

You can either:
1. Run `spectronaut-ui-config` to generate a default config file, then edit it
2. Copy the provided `config.json.example` to `~/.spectronaut_webui/config.json` and edit as necessary
3. Manually create `~/.spectronaut_webui/config.json` with the following structure:

```json
{
  "spectronaut_command": [
    "dotnet",
    "/usr/lib/spectronaut/SpectronautCMD.dll"
  ],
  "default_dir": "/work",
  "spectronaut_key": null,
  "port": 8080
}
```

## Configuration Options

### spectronaut_command
Type: `list of strings`

The command used to invoke Spectronaut CLI. Typically includes the runtime (e.g., `dotnet`) and the path to the Spectronaut command-line executable.

### default_dir
Type: `string`

The default directory shown in file picker dialogs when selecting input files and output directories.

### spectronaut_key
Type: `string` or `null`

The Spectronaut license key. If set to `null` or omitted, the key will be read from the `SPECTRONAUTKEY` environment variable.

**Note**: The environment variable always takes precedence over the config file for the license key.

### port
Type: `int`

The port to run the interface on.

## Priority

Configuration values are applied in the following order (later sources override earlier ones):

1. Default values (hardcoded in `config.py`)
2. Values from `config.json` file
3. Environment variables (only for `spectronaut_key`)
