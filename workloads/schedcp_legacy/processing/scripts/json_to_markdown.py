#!/usr/bin/env python3
"""
Convert test cases from JSON to individual markdown files
"""

import json
import os
from pathlib import Path


def create_markdown_content(test_case):
    """Convert a test case dictionary to markdown format"""
    md_content = f"# {test_case['name']}\n\n"
    md_content += f"**ID:** `{test_case['id']}`\n\n"
    md_content += f"**Category:** {test_case['category']}\n\n"
    md_content += f"**Description:** {test_case['description']}\n\n"
    
    # Dependencies
    if 'dependencies' in test_case:
        md_content += "## Dependencies\n\n"
        for dep in test_case['dependencies']:
            md_content += f"- {dep}\n"
        md_content += "\n"
    
    # Small setup commands
    md_content += "## Small Setup Commands\n\n"
    md_content += "```bash\n"
    for cmd in test_case['small_setup']:
        md_content += f"{cmd}\n"
    md_content += "```\n\n"
    
    # Large setup commands
    md_content += "## Large Setup Commands\n\n"
    md_content += "```bash\n"
    for cmd in test_case['large_setup']:
        md_content += f"{cmd}\n"
    md_content += "```\n\n"
    
    # Small execution commands
    md_content += "## Small Execution Commands\n\n"
    md_content += "```bash\n"
    for cmd in test_case['small_commands']:
        md_content += f"{cmd}\n"
    md_content += "```\n\n"
    
    # Large execution commands
    md_content += "## Large Execution Commands\n\n"
    md_content += "```bash\n"
    for cmd in test_case['large_commands']:
        md_content += f"{cmd}\n"
    md_content += "```\n\n"
    
    # Cleanup commands
    md_content += "## Cleanup Commands\n\n"
    md_content += "```bash\n"
    for cmd in test_case['cleanup_commands']:
        md_content += f"{cmd}\n"
    md_content += "```\n"
    
    return md_content


def main():
    # Paths
    script_dir = Path(__file__).parent
    workloads_dir = script_dir.parent
    json_file = workloads_dir / "test_cases_parallel.json"
    desc_dir = workloads_dir / "desc"
    
    # Create desc directory if it doesn't exist
    desc_dir.mkdir(exist_ok=True)
    
    # Read JSON file
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # Process each test case
    test_cases = data['test_cases']
    print(f"Processing {len(test_cases)} test cases...")
    
    for test_case in test_cases:
        # Create markdown content
        md_content = create_markdown_content(test_case)
        
        # Write to file
        md_filename = f"{test_case['id']}.md"
        md_path = desc_dir / md_filename
        
        with open(md_path, 'w') as f:
            f.write(md_content)
        
        print(f"Created: {md_path}")
    
    print(f"\nSuccessfully created {len(test_cases)} markdown files in {desc_dir}")


if __name__ == "__main__":
    main()