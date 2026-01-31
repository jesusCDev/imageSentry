# ImageSentry 🛡️

A vigilant, blazingly fast tool to detect and manage broken or corrupted images in your directories.

## Features

- **🔍 Broken Image Detection**: Scans directories recursively for corrupted images
- **⚡ Multi-threaded Processing**: Auto-detects optimal thread count (2x CPU cores) for blazing fast parallel scanning
- **🔄 Format Conversion**: Convert HEIC/WEBP files to PNG for better compatibility
- **📊 Categorized Results**: Separates issues into corruption, decompression bombs, and unidentifiable files
- **🎨 Rich Terminal UI**: Beautiful progress bars, color-coded output, and detailed statistics
- **🗂️ Smart Moving**: Preserves directory structure and categorizes by error type
- **🔬 Dry Run Mode**: Preview what would be moved before actually doing it
- **🖼️ Multiple Formats**: Supports PNG, JPG, JPEG, GIF, BMP, TIFF, WEBP, HEIC, and HEIF
- **💾 Large Image Support**: Handles high-resolution images up to 500 megapixels
- **🔁 Recursive Scanning**: Automatically scans all subdirectories

## Installation

1. Clone this repository
2. Install dependencies:
```bash
pip install Pillow rich pillow-heif
```

3. Make the script executable (optional):
```bash
chmod +x imagesentry.py
```

## Usage

ImageSentry requires at least one operation flag. You can combine multiple operations.

### Check for and move broken images:
```bash
imagesentry --source ~/Pictures/Photos --dest ~/Pictures/Broken --check-broken
```

### Fix misnamed file extensions:
```bash
imagesentry --source ~/Pictures/Photos --dest ~/Pictures/Fixed --fix-extensions
```
This creates:
- `dest/originals/` - backup of files with wrong extensions
- `dest/fixed/` - files with corrected extensions
- Source files are renamed in place

### Convert HEIC/WEBP files to PNG:
```bash
imagesentry --source ~/Pictures/Photos --dest ~/Pictures/Converted --convert-bad-extensions
```
This creates:
- `dest/converted/` - converted PNG files
- `dest/originals/` - backup of original HEIC/WEBP files
- Original files are removed from source after successful conversion

### Combine operations:
```bash
imagesentry --source ~/Pictures/Photos --dest ~/Pictures/Output --check-broken --fix-extensions --convert-bad-extensions
```

### Dry run to preview changes:
```bash
imagesentry --source ~/Pictures/Photos --dest ~/Pictures/Output --fix-extensions --dry-run
```

### Specify custom thread count:
```bash
imagesentry --source ~/Pictures/Photos --dest ~/Pictures/Output --check-broken --threads 16
```

### Create an alias for convenience:
Add to your `~/.zshrc` or `~/.bashrc`:
```bash
alias imagesentry="python /path/to/ImageSentry/imagesentry.py"
```

Then use it like:
```bash
imagesentry --source ~/Pictures --dest ~/Pictures/Broken
```

## How It Works

ImageSentry uses multi-threaded processing and the Python Imaging Library (Pillow) to:
1. Collect all image files from the source directory
2. Process images in parallel using multiple threads
3. Verify each image's format and structure
4. Attempt to fully load the image data
5. Categorize any errors found:
   - **💀 Corrupt**: Truly broken/corrupted files
   - **💣 Decompression Bomb**: Files exceeding safe size limits
   - **❓ Unidentifiable**: Files PIL cannot parse

When broken images are found, they're moved to categorized subdirectories in the destination folder while preserving the original folder structure.

## Output Structure

The destination directory structure depends on which operations you run:

### With `--check-broken`:
```
destination/
├── corrupt/              # Truly corrupted files
├── decompression_bomb/   # Oversized images (if exceeding 500MP)
└── unidentifiable/       # Files that can't be identified as images
```

### With `--convert-bad-extensions`:
```
destination/
├── converted/            # HEIC/WEBP files converted to PNG
└── originals/            # Backup of original HEIC/WEBP files
```

### With `--fix-extensions`:
```
destination/
├── fixed/                # Files with corrected extensions
└── originals/            # Backup of files before renaming
```

## Future Features (Planned)

- **Image Upscaling**: Enhance image resolution using waifu2x or similar tools
- **Image Optimization**: Reduce file sizes while maintaining quality
- **Duplicate Detection**: Find and manage duplicate images
- **Format Conversion**: Batch convert between image formats

## Requirements

- Python 3.10+
- Pillow (PIL)
- rich
- pillow-heif (optional, for HEIC conversion support)

## Performance

ImageSentry uses intelligent multi-threading to process images in parallel. It automatically detects your CPU core count and uses 2x that number for threads (capped at 32) since image processing is I/O-bound. On a 16-core CPU, expect 6000+ images scanned in ~3-4 minutes.

## License

MIT License - feel free to use and modify as needed.
