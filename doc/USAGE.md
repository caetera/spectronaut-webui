# Usage Guide

This guide explains how to use Spectronaut WebUI for various proteomics data processing workflows.

## Starting the Application

Start the web interface:

```bash
spectronaut-ui
```

By default, the application runs on `http://localhost:8080`. Open this URL in your web browser.

**Note** Console output will contain debug logs, if necessary redirect it to a file

## Interface Overview

The application has a navigation bar with the following pages:

- **Info** - Welcome page with basic instructions
- **Convert** - Convert raw MS files to Spectronaut format
- **Combine** - Combine multiple Spectronaut reports (coming soon)
- **DirectDIA** - Library-free DIA analysis workflow
- **DIA** - Spectral library-based DIA analysis (coming soon)

Each workflow page has two main tabs:
- **Parameters** - Configure input files and settings
- **Output** - View processing logs and results

## Common Operations

### Adding Files

All workflows support multiple methods for adding input files:

1. **Local File Browser** - Click "Add..." buttons to browse your filesystem
   - Use **Shift** to select multiple files or ranges
   - Use the filter field to search for specific file types

2. **Direct Upload** - Click "Upload" buttons to upload files through the browser
   - Useful for remote access scenarios
   - Files are temporarily stored during processing

### File Selection Tips

- **Bruker .d folders**: Use "Add Bruker D" button
- **Thermo .raw files**: Use "Add Thermo Raw" button
- **Zipped Bruker data**: Use "Add zipped Bruker D" for `.d.zip` files

### Managing File Lists

- **Delete Selected** - Remove selected rows from the data table
- **Clear All** - Remove all files from the data table
- **Edit Cells** - Click on condition/replicate/fraction cells to edit values directly

## Workflows

### Convert Workflow

Convert raw mass spectrometry files to Spectronaut HTRMS format.

#### Steps:

1. Navigate to the **Convert** page
2. Add input files:
   - Click "Add Bruker D" for Bruker `.d` folders
   - Click "Add Thermo Raw" for Thermo `.raw` files
   - Click "Add zipped Bruker D" for `.d.zip` archives
3. (Optional) Select a settings file (`.prop`, `.txt`, or `.json`)
4. Choose an output directory
5. (Optional) Configure advanced options:
   - Temp directory for intermediate files
   - Verbose output for detailed logs
   - Segmented dia-PASEF support
   - Termination after the first error
6. Click **Start Processing**

#### Output:

Converted files are saved to the specified output directory. Check the Output tab for processing logs and status.

---

### DirectDIA Workflow

Perform library-free Direct DIA analysis with full experiment metadata.

#### Steps:

1. Navigate to the **DirectDIA** page

2. **Add Data Files:**
   - Click "Add Bruker D" / "Add Thermo Raw" / "Add zipped Bruker D"
   - Files appear in the data table

3. **Configure Metadata:**
   
   Define metadata for experimental design:
   
   - **Condition** - Experimental condition (e.g., "Control", "Treatment")
   - **Replicate** - Replicate number within a condition (e.g., "1", "2", "3")
   - **Fraction** - Fraction number for fractionated samples (e.g., "1", "2")
   - **Reference** - Mark as reference sample (checkbox)

   **Note:** All unassigned/empty Conditions and Fractions will receive `NA` label; empty Replicates will
   will be assigned consequitive number labels based on Condition and Fraction (only if all Replicates are empty)
   
   **Methods to set metadata:**
   
   a. **Edit cells directly** - Click on any condition/replicate/fraction cell
   
   b. **Apply to multiple files:**
      - Select rows in the table
      - Click "Apply condition to selected" or "Apply fraction to selected"
      - Enter value in the dialog
   
   c. **Auto-assign replicates:**
      - Set conditions and fractions first
      - Click "Assign replicates" to automatically number replicates within each condition/fraction group

4. **Configure Search Parameters:**
   
   - **Experiment Name** - Name for this analysis (if not assigned, the name of the first file is used)
   - **Properties File** - Spectronaut search settings (`.prop`, `.txt`, `.json`)
   - **Report Schema** (Optional) - Custom report format (`.rs`)
   - **FASTA File** - Protein sequence database (`.fasta`, `.bgsfasta`)
   - **GO File** (Optional) - Gene Ontology annotations (`.goannotation`, `.goa`)

5. **Set Output:**
   
   - **Output Directory** - Where results will be saved
   - **Temp Directory** (Optional) - For intermediate files

6. **Advanced Options** (Optional):
   
   - Custom modification repository
   - Custom enzyme database
   - Verbose output
   - Segmented dia-PASEF (beta)
   - Parquet output format
   - Terminate after the first error

7. Click **Start Processing**

#### Output:

Results are organized in the output directory:
```
output_directory/
├── data/              # Processed data files, such as unzipped Bruker D archives (*.d.zip)
├── params/            # Parameter files used, such as FASTA file, conditions, etc
└── [results]          # Spectronaut output files (typically will be placed in a timestammped folder)
```

#### Tips:

- Use meaningful condition names for easier result interpretation
- Start with small test datasets to verify settings
- Check the Output tab regularly for progress and errors

---

### DIA Workflow

Spectral library-based DIA analysis (coming soon).

---

### Combine Workflow

Combine multiple Spectronaut reports (coming soon).

## Process Control

### Monitoring Progress

- Switch to the **Output** tab to view real-time logs
- Progress bars show current operation status
- Success/error indicators appear when processing completes

### Aborting Processing

- Click the **Abort** button in the Output tab
- The application will gracefully terminate ongoing processes
- Partial results may be available in the output directory

### Auto-Shutdown

Enable "Terminate the app when processing is done" to automatically shut down the server after completion (useful for automated workflows).

## Keyboard Shortcuts

While using the file browser:
- **Shift + Click** - Select a range of files
- **Click** - Toggle individual file selection
- **Enter** in path field - Navigate to the entered path

## Best Practices

### File Organization

- Keep raw data in organized folders by experiment
- Use consistent naming conventions for conditions
- Document your experimental design before starting (all used settings will be stored
in `params` subfolder)

### Settings Management

- Save and reuse properties files for consistent processing
- Test settings on small datasets first

### Performance Tips

- Monitor disk space in output and temp directories
- Close the browser tab while processing to free resources (server keeps running)

### Troubleshooting During Processing

If processing fails:
1. Check the Output tab for error messages
2. Verify input file integrity
3. Ensure sufficient disk space
4. Review the detailed logs (console) for specific errors

## Advanced Usage

### Custom Configuration

For specialized setups, edit `~/.spectronaut_webui/config.json` to change:
- Default file browser starting directory
- Server port
- Spectronaut command and arguments

See [CONFIG.md](CONFIG.md) for details.

## Getting Help

If you encounter issues:

1. Check the [Installation Guide](INSTALLATION.md) for setup problems
2. Review the [Configuration Guide](CONFIG.md) for configuration issues
3. Open an issue on [GitHub](https://github.com/caetera/spectronaut-webui/issues)
4. Include relevant log output and system information

## Example Workflows

### Example 1: Simple Conversion

Convert a folder of Thermo .raw files:

1. Navigate to Convert page
2. Click "Add Thermo Raw", select all .raw files
3. Choose output directory
4. Click "Start Processing"

### Example 2: DirectDIA Experiment

Process a two-condition experiment with triplicates:

1. Navigate to DirectDIA page
2. Add 6 raw files (3 per condition)
3. Select files 1-3, click "Apply condition to selected", enter "Control"
4. Select files 4-6, click "Apply condition to selected", enter "Treatment"
5. Click "Assign replicates" (automatically assigns 1, 2, 3 to each condition)
6. Set experiment name, FASTA, and properties file
7. Choose output directory
8. Click "Start Processing"

The condition file will be automatically generated:
```
File              Condition    Replicate    Fraction
file1.raw         Control      1            1
file2.raw         Control      2            1
file3.raw         Control      3            1
file4.raw         Treatment    1            1
file5.raw         Treatment    2            1
file6.raw         Treatment    3            1
```
