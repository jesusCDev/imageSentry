# ImageSentry 🛡️

A vigilant tool to detect and manage broken or corrupted images in your directories.

## Features

- **Broken Image Detection**: Scans directories recursively for corrupted images
- **Smart Moving**: Preserves directory structure when moving broken images
- **Dry Run Mode**: Preview what would be moved before actually doing it
- **Multiple Formats**: Supports PNG, JPG, JPEG, GIF, BMP, TIFF, and WebP

## Installation

1. Clone this repository
2. Install dependencies:
```bash
pip install Pillow
```

3. Make the script executable (optional):
```bash
chmod +x imagesentry.py
```

## Usage

### Basic usage - scan and move broken images:
```bash
python imagesentry.py --source ~/Pictures/Photos --dest ~/Pictures/Broken
```

### Dry run to preview what would be moved:
```bash
python imagesentry.py --source ~/Pictures/Photos --dest ~/Pictures/Broken --dry-run
```

### Just report broken images without moving:
```bash
python imagesentry.py --source ~/Pictures/Photos --dest ~/Pictures/Broken --no-move
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

ImageSentry uses the Python Imaging Library (Pillow) to:
1. Open each image file
2. Verify the image format and structure
3. Attempt to fully load the image data
4. Catch any errors that indicate corruption (like "Loading meta information failed")

When a broken image is found, it's moved to the destination directory while preserving the original folder structure.

## Future Features (Planned)

- **Image Upscaling**: Enhance image resolution using waifu2x or similar tools
- **Image Optimization**: Reduce file sizes while maintaining quality
- **Duplicate Detection**: Find and manage duplicate images
- **Format Conversion**: Batch convert between image formats

## Requirements

- Python 3.7+
- Pillow (PIL)

## License

MIT License - feel free to use and modify as needed.
# imageSentry
