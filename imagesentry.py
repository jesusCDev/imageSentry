#!/usr/bin/env python3
"""
ImageSentry - Detect and manage broken or corrupted images
"""

import argparse
import sys
import warnings
import os
from pathlib import Path
from PIL import Image
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, MofNCompleteColumn
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

# Try to import HEIC support
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:
    HEIC_SUPPORTED = False

# Increase decompression bomb threshold - many large legitimate images trigger this
Image.MAX_IMAGE_PIXELS = 500_000_000  # 500 megapixels

# Suppress PIL warnings - we handle these ourselves
warnings.filterwarnings('ignore', category=Image.DecompressionBombWarning)

console = Console()


class ErrorCategory(Enum):
    """Categories of image errors"""
    CORRUPT = "corrupt"  # Truly broken/corrupted files
    DECOMPRESSION_BOMB = "decompression_bomb"  # Files exceeding size limits
    UNIDENTIFIABLE = "unidentifiable"  # Files PIL can't parse
    

@dataclass
class ImageResult:
    """Result of checking an image"""
    path: Path
    is_broken: bool
    category: ErrorCategory | None
    error: str
    is_misnamed: bool = False
    actual_format: str | None = None
    

def categorize_error(error_msg: str) -> ErrorCategory:
    """Determine the category of error from the error message"""
    error_lower = error_msg.lower()
    
    if "decompression bomb" in error_lower:
        return ErrorCategory.DECOMPRESSION_BOMB
    elif "cannot identify" in error_lower:
        return ErrorCategory.UNIDENTIFIABLE
    else:
        return ErrorCategory.CORRUPT


def is_image_broken(image_path: Path) -> ImageResult:
    """
    Check if an image file is broken or corrupted.
    
    Returns:
        ImageResult with detailed information
    """
    try:
        # Try to open the image
        with Image.open(image_path) as img:
            actual_format = img.format
            # Try to load the image data
            img.verify()
        
        # Verify doesn't load the full image, so open again to fully test
        with Image.open(image_path) as img:
            # Force load all data by accessing pixels
            img.load()
            # Try to get basic info to ensure it's readable
            _ = img.size
            _ = img.mode
        
        # Check if file extension matches actual format
        extension = image_path.suffix.lower().lstrip('.')
        expected_extensions = {
            'PNG': ['png'],
            'JPEG': ['jpg', 'jpeg'],
            'GIF': ['gif'],
            'BMP': ['bmp'],
            'TIFF': ['tiff', 'tif'],
            'WEBP': ['webp'],
            'HEIF': ['heic', 'heif'],
        }
        
        is_misnamed = False
        if actual_format and actual_format in expected_extensions:
            if extension not in expected_extensions[actual_format]:
                is_misnamed = True
        
        return ImageResult(image_path, False, None, "", is_misnamed, actual_format if is_misnamed else None)
    except Exception as e:
        error_msg = str(e)
        category = categorize_error(error_msg)
        return ImageResult(image_path, True, category, error_msg, False, None)


def get_category_emoji(category: ErrorCategory) -> str:
    """Get emoji for error category"""
    return {
        ErrorCategory.CORRUPT: "💀",
        ErrorCategory.DECOMPRESSION_BOMB: "💣",
        ErrorCategory.UNIDENTIFIABLE: "❓",
    }[category]


def get_category_color(category: ErrorCategory) -> str:
    """Get color for error category"""
    return {
        ErrorCategory.CORRUPT: "bright_red",
        ErrorCategory.DECOMPRESSION_BOMB: "yellow",
        ErrorCategory.UNIDENTIFIABLE: "orange1",
    }[category]


def convert_image_to_png(image_path: Path, dest_dir: Path, source_dir: Path) -> tuple[bool, str, str]:
    """
    Convert an image to PNG format and backup original.
    
    Returns:
        tuple: (success, output_path_or_error, backup_path)
    """
    try:
        # Preserve relative path structure
        rel_path = image_path.relative_to(source_dir)
        output_path = dest_dir / "converted" / rel_path.with_suffix('.png')
        backup_path = dest_dir / "originals" / rel_path
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Backup original first
        shutil.copy2(str(image_path), str(backup_path))
        
        # Open and convert
        with Image.open(image_path) as img:
            # Convert to RGB if necessary (RGBA -> RGB for JPEG compatibility)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Save as PNG
            img.save(output_path, 'PNG', optimize=True)
        
        return True, str(output_path), str(backup_path)
    except Exception as e:
        return False, str(e), ""


def optimize_png_lossless(image_path: Path, dest_dir: Path, source_dir: Path) -> tuple[bool, str, str]:
    """
    Optimize PNG image with lossless compression.
    
    Returns:
        tuple: (success, output_path_or_error, backup_path)
    """
    try:
        # Preserve relative path structure
        rel_path = image_path.relative_to(source_dir)
        output_path = dest_dir / "optimized" / rel_path
        backup_path = dest_dir / "originals" / rel_path
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Backup original first
        shutil.copy2(str(image_path), str(backup_path))
        
        # Open and optimize
        with Image.open(image_path) as img:
            # Save with optimize flag for lossless compression
            img.save(output_path, img.format, optimize=True)
        
        return True, str(output_path), str(backup_path)
    except Exception as e:
        return False, str(e), ""


def convert_to_webp(image_path: Path, dest_dir: Path, source_dir: Path, quality: int = 95) -> tuple[bool, str, str]:
    """
    Convert an image to WebP format.
    
    Args:
        image_path: Path to source image
        dest_dir: Destination directory
        source_dir: Source directory (for preserving structure)
        quality: WebP quality (1-100, 95 = near-lossless)
    
    Returns:
        tuple: (success, output_path_or_error, backup_path)
    """
    try:
        # Preserve relative path structure
        rel_path = image_path.relative_to(source_dir)
        output_path = dest_dir / "optimized" / rel_path.with_suffix('.webp')
        backup_path = dest_dir / "originals" / rel_path
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Backup original first
        shutil.copy2(str(image_path), str(backup_path))
        
        # Open and convert
        with Image.open(image_path) as img:
            # Convert to RGB if necessary (WebP doesn't support all modes)
            if img.mode in ('RGBA', 'LA'):
                # Keep transparency for RGBA
                pass
            elif img.mode == 'P':
                img = img.convert('RGBA')
            elif img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGB')
            
            # Save as WebP
            img.save(output_path, 'WEBP', quality=quality, method=6)  # method=6 = best compression
        
        return True, str(output_path), str(backup_path)
    except Exception as e:
        return False, str(e), ""


def scan_directory(source_dir: Path, dest_dir: Path, move: bool = True, dry_run: bool = False, max_workers: int = 8, convert_bad_extensions: bool = False, fix_extensions: bool = False, check_broken: bool = False, optimize_lossless: bool = False, convert_webp: bool = False, webp_quality: int = 95):
    """
    Scan directory for broken images and optionally move them.
    
    Args:
        source_dir: Directory to scan
        dest_dir: Destination directory for broken images
        move: If True, move files; if False, just report
        dry_run: If True, don't actually move files
        max_workers: Number of parallel threads for processing
        convert_bad_extensions: If True, convert HEIC/WEBP to PNG
        fix_extensions: If True, fix misnamed file extensions
        check_broken: If True, check for broken images
        optimize_lossless: If True, optimize PNG images with lossless compression
        convert_webp: If True, convert images to WebP format
        webp_quality: WebP quality level (1-100)
    """
    # Common image extensions
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp', '.heic', '.heif'}
    convert_extensions = {'.heic', '.heif', '.webp'} if convert_bad_extensions else set()
    
    # Display header
    header = Panel(
        f"[bold cyan]Source:[/] {source_dir}\n[bold magenta]Destination:[/] {dest_dir}",
        title="[bold white]═══ ImageSentry ═══[/]",
        border_style="cyan",
        box=box.DOUBLE
    )
    console.print(header)
    console.print()
    
    # Collect all image files first
    console.print("[dim]⊙ Collecting image files...[/]")
    image_files = []
    for ext in image_extensions:
        for image_path in source_dir.rglob(f"*{ext}"):
            if image_path.is_file():
                image_files.append(image_path)
    
    if not image_files:
        console.print("[yellow]⚠ No image files found[/]")
        return []
    
    console.print(f"[dim]⊙ Found {len(image_files)} images to check[/]\n")
    
    # Results tracking
    results_by_category = {
        ErrorCategory.CORRUPT: [],
        ErrorCategory.DECOMPRESSION_BOMB: [],
        ErrorCategory.UNIDENTIFIABLE: [],
    }
    healthy_count = 0
    converted_count = 0
    conversion_failures = []
    misnamed_files = []
    optimized_count = 0
    optimization_failures = []
    webp_count = 0
    webp_failures = []
    
    # First pass: scan all images
    files_to_convert = []
    files_to_optimize = []
    files_to_webp = []
    
    with Progress(
        SpinnerColumn(spinner_name="dots", style="cyan"),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=40, style="cyan", complete_style="bright_cyan"),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console,
        transient=False
    ) as progress:
        
        task = progress.add_task("Scanning images", total=len(image_files))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_path = {executor.submit(is_image_broken, img): img for img in image_files}
            
            # Process completed tasks
            for future in as_completed(future_to_path):
                result = future.result()
                image_path = future_to_path[future]
                progress.advance(task)
                
                # Check if this file should be converted (by extension OR by actual format)
                should_convert = False
                if convert_bad_extensions:
                    # Check extension first
                    if image_path.suffix.lower() in convert_extensions:
                        should_convert = True
                    # Also check if it's a misnamed HEIF/WEBP file
                    elif result.is_misnamed and result.actual_format in ['HEIF', 'WEBP']:
                        should_convert = True
                
                if should_convert:
                    files_to_convert.append(image_path)
                    continue
                
                # Check if file should be optimized or converted to WebP
                if not result.is_broken:
                    # Optimize PNG files
                    if optimize_lossless and image_path.suffix.lower() == '.png':
                        files_to_optimize.append(image_path)
                    
                    # Convert to WebP (all image types)
                    if convert_webp and image_path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.bmp', '.tiff'}:
                        files_to_webp.append(image_path)
                
                if result.is_broken:
                    results_by_category[result.category].append(result)
                    
                    # Only show and process if check_broken is enabled
                    if check_broken:
                        # Show broken image inline
                        emoji = get_category_emoji(result.category)
                        color = get_category_color(result.category)
                        rel_path = result.path.relative_to(source_dir) if result.path.is_relative_to(source_dir) else result.path.name
                        
                        console.print(f"  [{color}]{emoji} {rel_path}[/]")
                        
                        if move and not dry_run:
                            # Determine destination based on category
                            category_dir = dest_dir / result.category.value
                            rel_path_full = result.path.relative_to(source_dir)
                            dest_path = category_dir / rel_path_full
                            dest_path.parent.mkdir(parents=True, exist_ok=True)
                            
                            try:
                                shutil.move(str(result.path), str(dest_path))
                            except Exception as e:
                                console.print(f"    [red]✗ Failed to move: {e}[/]")
                else:
                    # Check if file is misnamed
                    if result.is_misnamed:
                        misnamed_files.append(result)
                        rel_path = result.path.relative_to(source_dir) if result.path.is_relative_to(source_dir) else result.path.name
                        console.print(f"  [yellow]⚠ {rel_path} (actually {result.actual_format})[/]")
                        
                        # Fix extension if requested
                        if fix_extensions and not dry_run:
                            # Determine correct extension
                            ext_map = {
                                'PNG': '.png',
                                'JPEG': '.jpg',
                                'GIF': '.gif',
                                'BMP': '.bmp',
                                'TIFF': '.tiff',
                                'WEBP': '.webp',
                                'HEIF': '.heic',
                            }
                            correct_ext = ext_map.get(result.actual_format)
                            if correct_ext:
                                # Backup original first
                                rel_path_full = result.path.relative_to(source_dir)
                                backup_path = dest_dir / "originals" / rel_path_full
                                backup_path.parent.mkdir(parents=True, exist_ok=True)
                                
                                try:
                                    shutil.copy2(str(result.path), str(backup_path))
                                    
                                    # Save new fixed file
                                    new_path = result.path.with_suffix(correct_ext)
                                    fixed_rel_path = new_path.relative_to(source_dir.parent) if source_dir.parent in new_path.parents else new_path.name
                                    fixed_dest_path = dest_dir / "fixed" / new_path.relative_to(source_dir).parent / new_path.name
                                    fixed_dest_path.parent.mkdir(parents=True, exist_ok=True)
                                    
                                    # Rename and copy to fixed folder
                                    result.path.rename(new_path)
                                    shutil.copy2(str(new_path), str(fixed_dest_path))
                                    
                                    console.print(f"    [green]✓ Renamed to: {new_path.name}[/]")
                                    console.print(f"    [dim]Original backed up to: originals/[/]")
                                except Exception as e:
                                    console.print(f"    [red]✗ Failed to fix: {e}[/]")
                    healthy_count += 1
    
    # Second pass: convert files in parallel
    if files_to_convert and convert_bad_extensions:
        console.print()
        console.print(f"[dim]⊙ Converting {len(files_to_convert)} files to PNG...[/]\n")
        
        with Progress(
            SpinnerColumn(spinner_name="dots", style="cyan"),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=40, style="cyan", complete_style="bright_cyan"),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            console=console,
            transient=False
        ) as progress:
            
            task = progress.add_task("Converting images", total=len(files_to_convert))
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all conversion tasks
                future_to_path = {executor.submit(convert_image_to_png, img, dest_dir, source_dir): img for img in files_to_convert}
                
                # Process completed conversions
                for future in as_completed(future_to_path):
                    image_path = future_to_path[future]
                    progress.advance(task)
                    
                    if not dry_run:
                        success, output, backup = future.result()
                        rel_path = image_path.relative_to(source_dir) if image_path.is_relative_to(source_dir) else image_path.name
                        
                        if success:
                            console.print(f"  [cyan]🔄 {rel_path} → PNG[/]")
                            console.print(f"    [dim]Original backed up to: originals/[/]")
                            converted_count += 1
                            # Remove original from source after successful conversion
                            try:
                                image_path.unlink()
                            except Exception as e:
                                console.print(f"    [yellow]⚠ Could not remove original: {e}[/]")
                        else:
                            console.print(f"  [red]✗ Failed to convert {rel_path}: {output}[/]")
                            conversion_failures.append((image_path, output))
                    else:
                        console.print(f"  [cyan]🔄 Would convert {image_path.name} → PNG[/]")
                        converted_count += 1
    
    # Third pass: optimize PNG files in parallel
    if files_to_optimize and optimize_lossless:
        console.print()
        console.print(f"[dim]⊙ Optimizing {len(files_to_optimize)} PNG files (lossless)...[/]\n")
        
        with Progress(
            SpinnerColumn(spinner_name="dots", style="cyan"),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=40, style="cyan", complete_style="bright_cyan"),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            console=console,
            transient=False
        ) as progress:
            
            task = progress.add_task("Optimizing images", total=len(files_to_optimize))
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all optimization tasks
                future_to_path = {executor.submit(optimize_png_lossless, img, dest_dir, source_dir): img for img in files_to_optimize}
                
                # Process completed optimizations
                for future in as_completed(future_to_path):
                    image_path = future_to_path[future]
                    progress.advance(task)
                    
                    if not dry_run:
                        success, output, backup = future.result()
                        rel_path = image_path.relative_to(source_dir) if image_path.is_relative_to(source_dir) else image_path.name
                        
                        if success:
                            console.print(f"  [green]✨ {rel_path} → Optimized[/]")
                            optimized_count += 1
                            # Remove original from source after successful optimization
                            try:
                                image_path.unlink()
                            except Exception as e:
                                console.print(f"    [yellow]⚠ Could not remove original: {e}[/]")
                        else:
                            console.print(f"  [red]✗ Failed to optimize {rel_path}: {output}[/]")
                            optimization_failures.append((image_path, output))
                    else:
                        console.print(f"  [green]✨ Would optimize {image_path.name}[/]")
                        optimized_count += 1
    
    # Fourth pass: convert to WebP in parallel
    if files_to_webp and convert_webp:
        console.print()
        console.print(f"[dim]⊙ Converting {len(files_to_webp)} files to WebP (quality {webp_quality})...[/]\n")
        
        with Progress(
            SpinnerColumn(spinner_name="dots", style="cyan"),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=40, style="cyan", complete_style="bright_cyan"),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            console=console,
            transient=False
        ) as progress:
            
            task = progress.add_task("Converting to WebP", total=len(files_to_webp))
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all WebP conversion tasks
                future_to_path = {executor.submit(convert_to_webp, img, dest_dir, source_dir, webp_quality): img for img in files_to_webp}
                
                # Process completed conversions
                for future in as_completed(future_to_path):
                    image_path = future_to_path[future]
                    progress.advance(task)
                    
                    if not dry_run:
                        success, output, backup = future.result()
                        rel_path = image_path.relative_to(source_dir) if image_path.is_relative_to(source_dir) else image_path.name
                        
                        if success:
                            console.print(f"  [magenta]🎨 {rel_path} → WebP[/]")
                            webp_count += 1
                            # Remove original from source after successful conversion
                            try:
                                image_path.unlink()
                            except Exception as e:
                                console.print(f"    [yellow]⚠ Could not remove original: {e}[/]")
                        else:
                            console.print(f"  [red]✗ Failed to convert {rel_path}: {output}[/]")
                            webp_failures.append((image_path, output))
                    else:
                        console.print(f"  [magenta]🎨 Would convert {image_path.name} → WebP[/]")
                        webp_count += 1
    
    console.print()
    
    # Summary statistics
    total_broken = sum(len(results) for results in results_by_category.values())
    
    # Create summary table
    table = Table(
        title="[bold white]═══ Scan Results ═══[/]",
        box=box.DOUBLE_EDGE,
        border_style="cyan",
        show_header=True,
        header_style="bold bright_cyan"
    )
    
    table.add_column("Category", style="bold", width=20)
    table.add_column("Count", justify="right", width=10)
    table.add_column("Percentage", justify="right", width=12)
    table.add_column("Status", width=30)
    
    # Healthy images
    healthy_pct = (healthy_count / len(image_files) * 100) if image_files else 0
    table.add_row(
        "[green]✓ Healthy[/]",
        f"[green]{healthy_count}[/]",
        f"[green]{healthy_pct:.1f}%[/]",
        "[dim]No issues detected[/]"
    )
    
    # Converted files
    if converted_count > 0:
        conv_pct = (converted_count / len(image_files) * 100)
        status = "Converted" if not dry_run else "Would convert"
        table.add_row(
            "[cyan]🔄 Converted[/]",
            f"[cyan]{converted_count}[/]",
            f"[cyan]{conv_pct:.1f}%[/]",
            f"[dim]{status} to: {dest_dir / 'converted'}[/]"
        )
    
    # Optimized files
    if optimized_count > 0:
        opt_pct = (optimized_count / len(image_files) * 100)
        status = "Optimized" if not dry_run else "Would optimize"
        table.add_row(
            "[green]✨ Optimized[/]",
            f"[green]{optimized_count}[/]",
            f"[green]{opt_pct:.1f}%[/]",
            f"[dim]{status} to: {dest_dir / 'optimized'}[/]"
        )
    
    # WebP converted files
    if webp_count > 0:
        webp_pct = (webp_count / len(image_files) * 100)
        status = "Converted to WebP" if not dry_run else "Would convert"
        table.add_row(
            "[magenta]🎨 WebP[/]",
            f"[magenta]{webp_count}[/]",
            f"[magenta]{webp_pct:.1f}%[/]",
            f"[dim]{status} to: {dest_dir / 'optimized'}[/]"
        )
    
    # Misnamed files
    if misnamed_files:
        misnamed_count = len(misnamed_files)
        misnamed_pct = (misnamed_count / len(image_files) * 100)
        table.add_row(
            "[yellow]⚠ Misnamed[/]",
            f"[yellow]{misnamed_count}[/]",
            f"[yellow]{misnamed_pct:.1f}%[/]",
            "[dim]Wrong file extension[/]"
        )
    
    # Broken images by category (only if check_broken is enabled)
    if check_broken:
        for category, results in results_by_category.items():
            if results:
                count = len(results)
                pct = (count / len(image_files) * 100)
                emoji = get_category_emoji(category)
                color = get_category_color(category)
                
                status = "Moved" if move and not dry_run else ("Would move" if dry_run else "Found")
                
                table.add_row(
                    f"[{color}]{emoji} {category.value.replace('_', ' ').title()}[/]",
                    f"[{color}]{count}[/]",
                    f"[{color}]{pct:.1f}%[/]",
                    f"[dim]{status} to: {dest_dir / category.value}[/]" if move else "[dim]Not moved[/]"
                )
    
    table.add_section()
    table.add_row(
        "[bold]Total Scanned[/]",
        f"[bold]{len(image_files)}[/]",
        "[bold]100.0%[/]",
        ""
    )
    
    console.print(table)
    
    if dry_run:
        console.print("\n[yellow]⚠ Dry run - no files were actually moved[/]")
    
    # Return flattened list for backward compatibility
    all_broken = []
    for results in results_by_category.values():
        all_broken.extend([(r.path, r.error) for r in results])
    
    return all_broken


def main():
    parser = argparse.ArgumentParser(
        description="ImageSentry - Detect and manage broken or corrupted images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan and move broken images
  imagesentry --source ~/Pictures/Photos --dest ~/Pictures/Broken
  
  # Dry run to see what would be moved
  imagesentry --source ~/Pictures/Photos --dest ~/Pictures/Broken --dry-run
  
  # Just report broken images without moving
  imagesentry --source ~/Pictures/Photos --dest ~/Pictures/Broken --no-move
        """
    )
    
    parser.add_argument(
        '--source',
        type=Path,
        required=True,
        help='Source directory to scan for broken images'
    )
    
    parser.add_argument(
        '--dest',
        type=Path,
        default=None,
        help='Destination directory for broken images (default: <source>/imagesentry_output)'
    )
    
    parser.add_argument(
        '--no-move',
        action='store_true',
        help='Only report broken images, do not move them'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be moved without actually moving files'
    )
    
    parser.add_argument(
        '--threads',
        type=int,
        default=None,
        help='Number of parallel threads for processing (default: auto-detect)'
    )
    
    parser.add_argument(
        '--convert-bad-extensions',
        action='store_true',
        help='Convert HEIC/WEBP files to PNG format'
    )
    
    parser.add_argument(
        '--fix-extensions',
        action='store_true',
        help='Fix misnamed files by renaming them with correct extensions'
    )
    
    parser.add_argument(
        '--check-broken',
        action='store_true',
        help='Check for and move broken/corrupted images'
    )
    
    parser.add_argument(
        '--optimize-lossless',
        action='store_true',
        help='Optimize PNG images with lossless compression (10-40%% size reduction)'
    )
    
    parser.add_argument(
        '--convert-webp',
        action='store_true',
        help='Convert images to WebP format (60-80%% size reduction)'
    )
    
    parser.add_argument(
        '--quality',
        type=int,
        default=95,
        help='WebP quality level (1-100, default: 95 = near-lossless)'
    )
    
    args = parser.parse_args()
    
    # Require at least one operation flag
    operations = [args.check_broken, args.convert_bad_extensions, args.fix_extensions, args.optimize_lossless, args.convert_webp]
    if not any(operations):
        console.print("[red]Error: At least one operation flag is required:[/]")
        console.print("  [yellow]--check-broken[/]          Check for broken images")
        console.print("  [yellow]--convert-bad-extensions[/] Convert HEIC/WEBP to PNG")
        console.print("  [yellow]--fix-extensions[/]        Fix misnamed file extensions")
        console.print("  [yellow]--optimize-lossless[/]     Optimize PNG images (lossless)")
        console.print("  [yellow]--convert-webp[/]          Convert to WebP format")
        console.print("\nYou can combine multiple operations.")
        return 1
    
    # Auto-detect optimal thread count if not specified
    if args.threads is None:
        cpu_count = os.cpu_count() or 4
        # Use 2x CPU count for I/O-bound work, capped at 32
        args.threads = min(cpu_count * 2, 32)
        console.print(f"[dim]💻 Auto-detected {args.threads} threads (CPU cores: {cpu_count})[/]\n")
    
    # Validate source directory
    if not args.source.exists():
        console.print(f"[red]Error: Source directory does not exist: {args.source}[/]", file=sys.stderr)
        return 1
    
    if not args.source.is_dir():
        console.print(f"[red]Error: Source path is not a directory: {args.source}[/]", file=sys.stderr)
        return 1
    
    # Set default destination directory if not provided
    if args.dest is None:
        args.dest = args.source / 'imagesentry_output'
        console.print(f"[dim]📁 No destination specified, using: {args.dest}[/]\n")
    
    # Check HEIC support if conversion is requested
    if args.convert_bad_extensions and not HEIC_SUPPORTED:
        console.print("[yellow]⚠ Warning: pillow-heif not installed. HEIC files may fail to convert.[/]")
        console.print("[yellow]  Install with: pip install pillow-heif[/]\n")
    
    # Create destination directory if it doesn't exist (always, not just for moving)
    if not args.dry_run:
        args.dest.mkdir(parents=True, exist_ok=True)
    
    # Scan and process
    move = not args.no_move
    scan_directory(
        args.source, 
        args.dest, 
        move=move, 
        dry_run=args.dry_run, 
        max_workers=args.threads, 
        convert_bad_extensions=args.convert_bad_extensions, 
        fix_extensions=args.fix_extensions,
        check_broken=args.check_broken,
        optimize_lossless=args.optimize_lossless,
        convert_webp=args.convert_webp,
        webp_quality=args.quality
    )
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
