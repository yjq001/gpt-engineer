import os
import sys
from pathlib import Path

def get_file_size(file_path):
    """Return file size in MB"""
    return os.path.getsize(file_path) / (1024 * 1024)

def find_largest_files(directory, top_n=10):
    """Find the largest files in the given directory"""
    # Skip these directories
    skip_dirs = ['.git', 'node_modules', '__pycache__', '.venv', '.pytest_cache']
    
    file_sizes = []
    
    for root, dirs, files in os.walk(directory):
        # Skip directories we want to exclude
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        
        for file in files:
            file_path = os.path.join(root, file)
            try:
                size = get_file_size(file_path)
                file_sizes.append((file_path, size))
            except:
                pass
    
    # Sort by size (largest first)
    file_sizes.sort(key=lambda x: x[1], reverse=True)
    
    # Return top N files
    return file_sizes[:top_n]

if __name__ == "__main__":
    # Use current directory if no directory is specified
    directory = "."
    if len(sys.argv) > 1:
        directory = sys.argv[1]
    
    largest_files = find_largest_files(directory)
    
    print(f"Top 10 largest files in {os.path.abspath(directory)}:")
    print("-" * 80)
    for i, (file_path, size) in enumerate(largest_files, 1):
        print(f"{i}. {file_path}")
        print(f"   Size: {size:.2f} MB")
    print("-" * 80) 
