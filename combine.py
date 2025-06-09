#!/usr/bin/env python3
"""
Combine all markdown files in the /md/ directory into a single markdown file.
Files are processed in alphabetical order. Converts images, YouTube videos, and document links to correct formats / srces.

Usage:
    python3 combine.py                  # Interactive mode - asks before deleting unused images
    python3 combine.py --auto-cleanup   # Automatic mode - deletes unused images without asking
    python3 combine.py -y               # Shorthand for automatic mode

Features:
- Combines all .md files from /md/ directory into README.md
- Processes YouTube videos into clickable thumbnails
- Converts image references to GitHub raw URLs
- Converts document links to full Tumult Hype documentation URLs
- Analyzes and optionally cleans up unused image files
"""

import os
import glob
import re
from pathlib import Path
from html.parser import HTMLParser

class TableParser(HTMLParser):
    """HTML parser specifically for converting tables to markdown."""
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_thead = False
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.in_th = False
        self.current_row = []
        self.current_cell = ""
        self.headers = []
        self.rows = []
        self.markdown_table = ""
        
    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.in_table = True
            self.headers = []
            self.rows = []
        elif tag == 'thead':
            self.in_thead = True
        elif tag == 'tbody':
            self.in_tbody = True
        elif tag == 'tr':
            self.in_tr = True
            self.current_row = []
        elif tag in ['td', 'th']:
            if tag == 'th':
                self.in_th = True
            else:
                self.in_td = True
            self.current_cell = ""
        elif tag == 'br':
            if self.in_td or self.in_th:
                self.current_cell += "<br>"
        elif tag == 'img':
            # Extract image info for markdown
            src = ""
            alt = ""
            for attr_name, attr_value in attrs:
                if attr_name == 'src':
                    src = attr_value
                elif attr_name == 'data-src-retina':
                    src = attr_value  # Prefer retina version
                elif attr_name == 'data-src' and not src:
                    src = attr_value
                elif attr_name == 'alt':
                    alt = attr_value
            
            if src and (self.in_td or self.in_th):
                if alt:
                    self.current_cell += f"![{alt}]({src})"
                else:
                    self.current_cell += f"![]({src})"
    
    def handle_endtag(self, tag):
        if tag == 'table':
            self.in_table = False
            self._generate_markdown_table()
        elif tag == 'thead':
            self.in_thead = False
        elif tag == 'tbody':
            self.in_tbody = False
        elif tag == 'tr':
            self.in_tr = False
            if self.in_thead or (not self.in_tbody and not self.headers):
                self.headers = self.current_row[:]
            else:
                self.rows.append(self.current_row[:])
        elif tag in ['td', 'th']:
            # Clean up the cell content
            cell_content = self.current_cell.strip()
            
            # Replace <br> tags with actual line breaks in markdown
            cell_content = cell_content.replace('<br>', '<br>')
            
            # Normalize whitespace but preserve line breaks
            cell_content = re.sub(r'[ \t]+', ' ', cell_content)  # Normalize spaces and tabs
            cell_content = re.sub(r'<br>\s*', '<br>', cell_content)  # Clean up around br tags
            
            self.current_row.append(cell_content)
            if tag == 'th':
                self.in_th = False
            else:
                self.in_td = False
    
    def handle_data(self, data):
        if self.in_td or self.in_th:
            # Clean up the data and add to current cell
            cleaned_data = data.strip()
            if cleaned_data:
                self.current_cell += cleaned_data
    
    def _generate_markdown_table(self):
        """Generate markdown table from parsed data."""
        if not self.headers and not self.rows:
            return
        
        # If no headers were found, use the first row as headers
        if not self.headers and self.rows:
            self.headers = self.rows.pop(0)
        
        # Ensure we have headers
        if not self.headers:
            return
        
        # Start building markdown table
        lines = []
        
        # Header row
        header_line = "| " + " | ".join(self.headers) + " |"
        lines.append(header_line)
        
        # Separator row
        separator = "| " + " | ".join(["---"] * len(self.headers)) + " |"
        lines.append(separator)
        
        # Data rows
        for row in self.rows:
            # Pad row to match header length
            while len(row) < len(self.headers):
                row.append("")
            # Truncate if too long
            row = row[:len(self.headers)]
            
            row_line = "| " + " | ".join(row) + " |"
            lines.append(row_line)
        
        self.markdown_table = "\n".join(lines)

def convert_html_tables_to_markdown(content):
    """Convert HTML tables to markdown tables."""
    # Find all table tags and convert them one by one
    table_pattern = r'<table[^>]*>.*?</table>'
    
    def replace_table(match):
        table_html = match.group(0)
        parser = TableParser()
        try:
            parser.feed(table_html)
            if parser.markdown_table:
                return "\n" + parser.markdown_table + "\n"
            else:
                # If parsing failed, return original
                return table_html
        except Exception:
            # If parsing failed, return original
            return table_html
    
    return re.sub(table_pattern, replace_table, content, flags=re.DOTALL)

def process_youtube_videos(content):
    """Convert embedded YouTube videos to markdown format with thumbnails."""
    # Pattern to match the YouTube div structure
    youtube_pattern = r'<div class="js-lazyYT" data-youtube-id="([^"]+)"[^>]*>Loading\.\.\.</div>'
    
    def replace_youtube(match):
        video_id = match.group(1)
        # Create markdown with YouTube thumbnail image linking to the video
        return f"[![YouTube Video Thumbnail](https://img.youtube.com/vi/{video_id}/0.jpg)](https://www.youtube.com/watch?v={video_id})"
    
    return re.sub(youtube_pattern, replace_youtube, content)

def process_images(content):
    """Modify images to use data-src-retina as the primary src."""
    # Pattern to match img tags with data-src-retina
    img_pattern = r'<img\s+([^>]*?)data-src-retina="([^"]+)"([^>]*?)>'
    
    def replace_img(match):
        before_attrs = match.group(1)
        retina_src = match.group(2)
        after_attrs = match.group(3)
        
        # Combine all attributes to search through
        all_attrs = before_attrs + after_attrs
        
        # Extract class, width, height, and alt attributes if they exist
        class_match = re.search(r'class="([^"]*)"', all_attrs)
        width_match = re.search(r'width="(\d+)"', all_attrs)
        height_match = re.search(r'height="(\d+)"', all_attrs)
        alt_match = re.search(r'alt="([^"]*)"', all_attrs)
        
        # Build the new img tag
        new_attrs = []
        
        # Add class if it exists
        if class_match:
            new_attrs.append(f'class="{class_match.group(1)}"')
        
        # Add the retina src as the primary src
        new_attrs.append(f'src="{retina_src}"')
        
        # Add width and height if they exist
        if width_match:
            new_attrs.append(f'width="{width_match.group(1)}"')
        if height_match:
            new_attrs.append(f'height="{height_match.group(1)}"')
        
        # Add alt attribute
        if alt_match:
            new_attrs.append(f'alt="{alt_match.group(1)}"')
        else:
            new_attrs.append('alt=""')
        
        return f'<img {" ".join(new_attrs)}/>'
    
    return re.sub(img_pattern, replace_img, content)

def process_data_src_images(content):
    """Convert images with data-src (but not data-src-retina) to use data-src as primary src."""
    # Pattern to match img tags with data-src but NOT data-src-retina
    # This uses negative lookahead to exclude images that have data-src-retina
    img_pattern = r'<img\s+([^>]*?)data-src="([^"]+)"(?![^>]*data-src-retina)([^>]*?)>'
    
    def replace_img(match):
        before_attrs = match.group(1)
        data_src = match.group(2)
        after_attrs = match.group(3)
        
        # Combine all attributes to search through
        all_attrs = before_attrs + after_attrs
        
        # Extract class, width, height, and alt attributes if they exist
        class_match = re.search(r'class="([^"]*)"', all_attrs)
        width_match = re.search(r'width="(\d+)"', all_attrs)
        height_match = re.search(r'height="(\d+)"', all_attrs)
        alt_match = re.search(r'alt="([^"]*)"', all_attrs)
        
        # Build the new img tag
        new_attrs = []
        
        # Add class if it exists
        if class_match:
            new_attrs.append(f'class="{class_match.group(1)}"')
        
        # Add the data-src as the primary src
        new_attrs.append(f'src="{data_src}"')
        
        # Add width and height if they exist
        if width_match:
            new_attrs.append(f'width="{width_match.group(1)}"')
        if height_match:
            new_attrs.append(f'height="{height_match.group(1)}"')
        
        # Add alt attribute
        if alt_match:
            new_attrs.append(f'alt="{alt_match.group(1)}"')
        else:
            new_attrs.append('alt=""')
        
        return f'<img {" ".join(new_attrs)}/>'
    
    return re.sub(img_pattern, replace_img, content)

def process_document_links(content):
    """Convert document/ links to full URLs."""
    # Pattern to match href or src attributes that start with "documents/" (not in the middle of a path)
    #✅ Match: href="documents/something.html"
    #✅ Match: src="documents/image.png"
    #❌ NOT match: href="https://example.com/documents/something.html"
    #❌ NOT match: src="images/documents/file.png"
    doc_pattern = r'((?:href|src)=")documents/'
    
    def replace_doc_link(match):
        attr_start = match.group(1)  # Either 'href="' or 'src="'
        return f'{attr_start}https://tumult.com/hype/documentation/v4/documents/'
    
    return re.sub(doc_pattern, replace_doc_link, content)

def process_image_paths(content):
    """Convert local image/video paths to GitHub raw URLs."""
    # Pattern to match src/href/data-src-2x attributes that start with "images/"
    img_path_pattern = r'((?:src|href|data-src-2x)=")images/'
    
    def replace_img_path(match):
        attr_start = match.group(1)  # 'src="', 'href="', or 'data-src-2x="'
        return f'{attr_start}https://raw.githubusercontent.com/tumult/hype-documentation/refs/heads/main/images/'
    
    return re.sub(img_path_pattern, replace_img_path, content)

def process_markdown_document_links(content):
    """Convert markdown links that reference documents/ folder to full URLs."""
    # Pattern to match markdown links like [text](documents/file.ext)
    # ✅ Match: [Download this document](documents/scenes-transitions.hype.zip)
    # ✅ Match: [view this page](documents/scenes-transitions.html)
    # ❌ NOT match: [text](https://example.com/documents/file.ext)
    markdown_doc_pattern = r'(\[([^\]]+)\]\()documents/'
    
    def replace_markdown_doc_link(match):
        link_start = match.group(1)  # '[text]('
        return f'{link_start}https://tumult.com/hype/documentation/v4/documents/'
    
    return re.sub(markdown_doc_pattern, replace_markdown_doc_link, content)

def combine_markdown_files():
    """Combine all .md files in the current directory into a single markdown file."""
    
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    md_dir = script_dir / "md"
    
    # Find all .md files in the md directory (excluding the output file)
    md_files = []
    for file in md_dir.glob("*.md"):
        if file.name != "README.md":  # Don't include the output file
            md_files.append(file)
    
    # Sort files alphabetically
    md_files.sort(key=lambda x: x.name)
    
    if not md_files:
        print("No markdown files found in the directory.")
        return
    
    # Output file path
    output_file = script_dir / "README.md"
    
    print(f"Combining {len(md_files)} markdown files...")
    print("Files to be combined (in order):")
    for file in md_files:
        print(f"  - {file.name}")
    
    # Combine files
    with open(output_file, 'w', encoding='utf-8') as outfile:
        # Add header at the top of the README.md file
        outfile.write("# Tumult Hype Documentation\n\n")
        
        for i, md_file in enumerate(md_files):
            print(f"Processing: {md_file.name}")
            
            # Add file separator
            # outfile.write(f"<!-- File: {md_file.name} -->\n\n")
            
            try:
                with open(md_file, 'r', encoding='utf-8') as infile:
                    content = infile.read()
                    
                    # Process YouTube videos, images, and document links
                    content = process_youtube_videos(content)
                    content = process_images(content)
                    content = process_data_src_images(content)
                    content = process_document_links(content)
                    content = process_markdown_document_links(content)
                    content = process_image_paths(content)
                    content = process_markdown_document_links(content)
                    
                    # Convert HTML tables to markdown tables
                    content = convert_html_tables_to_markdown(content)
                    
                    # Replace non-breaking spaces with regular spaces
                    content = content.replace('\u00A0', ' ')
                    content = content.replace(' ', ' ')
                    
                    # Write the content
                    outfile.write(content)
                    
                    # Add spacing between files (but not after the last file)
                    if i < len(md_files) - 1:
                        outfile.write("\n\n---\n\n")
                        
            except Exception as e:
                print(f"Error reading {md_file.name}: {e}")
                outfile.write(f"*Error reading file {md_file.name}: {e}*\n\n")
    
    print(f"\nSuccessfully combined files into: {output_file}")
    print(f"Total files processed: {len(md_files)}")

def extract_used_image_filenames(readme_file):
    """Extract all image filenames referenced via GitHub raw URLs in README.md"""
    used_images = set()
    
    with open(readme_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern to match GitHub raw URLs pointing to images
    # This handles both HTML img tags (ending with ") and markdown images (ending with ))
    pattern = r'https://raw\.githubusercontent\.com/[^")]*images/([^")\s]+)'
    matches = re.findall(pattern, content)
    
    for match in matches:
        # Extract just the filename from the URL
        filename = match.split('/')[-1] if '/' in match else match
        used_images.add(filename)
    
    return used_images

def get_image_files_in_folder(images_folder):
    """Get all files in the images folder"""
    images_path = Path(images_folder)
    if not images_path.exists():
        print(f"Images folder '{images_folder}' does not exist!")
        return set()
    
    all_files = set()
    for file_path in images_path.iterdir():
        if file_path.is_file():
            all_files.add(file_path.name)
    
    return all_files

def find_unused_files(used_images, all_files):
    """Find files that exist in the folder but are not referenced in README.md"""
    unused_files = all_files - used_images
    return unused_files

def cleanup_unused_images(script_dir, auto_delete=False):
    """Clean up unused image files by comparing what's referenced in README.md with what's in images folder"""
    readme_file = script_dir / "README.md"
    images_folder = script_dir / "images"
    
    print("\n🔍 Analyzing image usage in README.md...")
    
    # Extract used image filenames from README.md
    used_images = extract_used_image_filenames(readme_file)
    print(f"📋 Found {len(used_images)} unique image files referenced in README.md")
    
    # Get all files in images folder
    all_files = get_image_files_in_folder(images_folder)
    print(f"📁 Found {len(all_files)} total files in images folder")
    
    # Find unused files
    unused_files = find_unused_files(used_images, all_files)
    
    if unused_files:
        print(f"\n🗑️  Found {len(unused_files)} unused files:")
        print("=" * 50)
        
        # Sort unused files for better readability
        for filename in sorted(unused_files):
            file_path = images_folder / filename
            file_size = file_path.stat().st_size if file_path.exists() else 0
            print(f"  📄 {filename} ({file_size:,} bytes)")
        
        print("=" * 50)
        
        # Calculate total size of unused files
        total_size = sum((images_folder / f).stat().st_size for f in unused_files if (images_folder / f).exists())
        print(f"💾 Total size of unused files: {total_size:,} bytes ({total_size/1024/1024:.2f} MB)")
        
        if auto_delete:
            response = 'yes'
        else:
            # Ask for confirmation before deleting
            response = input(f"\n❓ Do you want to delete these {len(unused_files)} unused files? (yes/no): ").lower().strip()
        
        if response in ['yes', 'y']:
            deleted_count = 0
            deleted_size = 0
            
            for filename in unused_files:
                file_path = images_folder / filename
                if file_path.exists():
                    file_size = file_path.stat().st_size
                    try:
                        file_path.unlink()
                        print(f"  ✅ Deleted: {filename}")
                        deleted_count += 1
                        deleted_size += file_size
                    except Exception as e:
                        print(f"  ❌ Error deleting {filename}: {e}")
                else:
                    print(f"  ⚠️  File not found: {filename}")
            
            print(f"\n🎉 Successfully deleted {deleted_count} files ({deleted_size:,} bytes / {deleted_size/1024/1024:.2f} MB)")
        else:
            print("🚫 Deletion cancelled.")
            
            # Save list of unused files to a text file for reference
            unused_files_list = script_dir / "unused_files.txt"
            with open(unused_files_list, 'w') as f:
                f.write("# Unused image files (not referenced in README.md)\n")
                f.write(f"# Total: {len(unused_files)} files, {total_size:,} bytes\n\n")
                for filename in sorted(unused_files):
                    f.write(f"{filename}\n")
            print(f"📝 List of unused files saved to: {unused_files_list}")
    else:
        print("\n✅ All files in the images folder are being used in README.md!")
    
    # Show stats about used files
    print(f"\n📊 Image Usage Summary:")
    print(f"  • Files referenced in README.md: {len(used_images)}")
    print(f"  • Files in images folder: {len(all_files)}")
    print(f"  • Unused files: {len(unused_files)}")
    print(f"  • Usage rate: {((len(all_files) - len(unused_files)) / len(all_files) * 100):.1f}%" if all_files else "N/A")
    
    return len(unused_files) == 0  # Return True if no unused files

def main(auto_cleanup=False):
    """Main function that combines markdown files and optionally cleans up unused images"""
    script_dir = Path(__file__).parent
    
    # Step 1: Combine markdown files
    print("🔄 Step 1: Combining markdown files...")
    combine_markdown_files()
    
    # Step 2: Clean up unused images
    print("\n🔄 Step 2: Cleaning up unused images...")
    cleanup_unused_images(script_dir, auto_delete=auto_cleanup)

if __name__ == "__main__":
    import sys
    
    # Check for command line arguments
    auto_cleanup = '--auto-cleanup' in sys.argv or '-y' in sys.argv
    
    if auto_cleanup:
        print("🚀 Running with automatic cleanup enabled...")
    
    main(auto_cleanup=auto_cleanup)