"""
SHL Product Catalog Scraper - FIXED VERSION

This script scrapes ONLY the "Individual Test Solutions" table from SHL catalog.
It correctly identifies the table by heading text and extracts exactly 377 assessments.
For each assessment, it also scrapes the detail page to get description and job levels.

Requirements:
- Scrape from: https://www.shl.com/products/product-catalog/?start={offset}&type=1
- Extract exactly 377 Individual Test Solutions across 32 pages
- Each assessment must have: name, URL, test_type, remote_support, adaptive_support, description, job_levels
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import os
from urllib.parse import urljoin

# Base URL with type=1 parameter for Individual Test Solutions ONLY
BASE_URL = "https://www.shl.com"
CATALOG_URL = "https://www.shl.com/products/product-catalog/"

def get_page_content(url):
    """
    Fetch HTML content from a URL.
    
    Args:
        url: The URL to fetch
        
    Returns:
        BeautifulSoup object or None if request fails
    """
    try:
        # Headers to mimic a browser request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser')
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def extract_assessment_details(assessment_url):
    """
    Extract detailed information from an individual assessment page.
    This includes description and job levels which are critical for RAG retrieval.
    
    Args:
        assessment_url: URL of the assessment detail page
        
    Returns:
        Dictionary with 'description' and 'job_levels', or None if extraction fails
    """
    soup = get_page_content(assessment_url)
    if not soup:
        return None
    
    details = {
        'description': '',
        'job_levels': [],
        'duration': ''
    }
    
    # ============================================================
    # EXTRACT DESCRIPTION
    # ============================================================
    
    description_text = ''
    
    # Strategy 1: Find the "Description" heading and get the text that follows
    # Look for h2, h3, or other headings with text "Description"
    for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5']):
        if heading.get_text(strip=True).lower() == 'description':
            # Found the Description heading!
            # Now get all paragraph text that follows until we hit another heading or section
            description_parts = []
            
            # Get all next siblings until we hit another heading
            for sibling in heading.find_next_siblings():
                # Stop if we hit another heading (new section)
                if sibling.name in ['h1', 'h2', 'h3', 'h4', 'h5']:
                    break
                
                # Get text from paragraphs
                if sibling.name == 'p':
                    text = sibling.get_text(strip=True)
                    if len(text) > 20:  # Meaningful text only
                        description_parts.append(text)
                
                # Also check for paragraphs inside divs
                paragraphs = sibling.find_all('p')
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if len(text) > 20 and text not in description_parts:
                        description_parts.append(text)
            
            if description_parts:
                description_text = ' '.join(description_parts)
                break
    
    # Strategy 2: If Strategy 1 didn't work, look for common description containers
    if not description_text:
        # Look for divs or sections that might contain the description
        desc_containers = soup.find_all(['div', 'section'], class_=lambda x: x and 'description' in x.lower())
        
        for container in desc_containers:
            paragraphs = container.find_all('p')
            description_parts = []
            
            for p in paragraphs:
                text = p.get_text(strip=True)
                # Skip common UI elements
                if len(text) > 30 and 'interactive demos' not in text.lower() and 'try an online' not in text.lower():
                    description_parts.append(text)
            
            if description_parts:
                description_text = ' '.join(description_parts)
                break
    
    # Strategy 3: Look for the main content after the H1 title
    if not description_text:
        h1 = soup.find('h1')
        if h1:
            # Get the next few meaningful paragraphs after h1
            description_parts = []
            
            for elem in h1.find_all_next(['p']):
                text = elem.get_text(strip=True)
                
                # Skip navigation, sidebars, footers
                parent_classes = []
                parent = elem.parent
                while parent:
                    parent_classes.extend(parent.get('class', []))
                    parent = parent.parent
                
                parent_class_str = ' '.join(parent_classes).lower()
                
                # Skip common non-content areas
                if any(skip in parent_class_str for skip in ['nav', 'sidebar', 'menu', 'footer', 'header', 'breadcrumb']):
                    continue
                
                # Skip UI text
                if any(skip in text.lower() for skip in ['interactive demos', 'try an online', 'contact us', 'learn more', 'request demo']):
                    continue
                
                # Only keep substantial paragraphs
                if len(text) > 40:
                    description_parts.append(text)
                    
                    # Stop after collecting enough text (3-5 good paragraphs)
                    if len(description_parts) >= 3 and sum(len(p) for p in description_parts) > 200:
                        break
            
            if description_parts:
                description_text = ' '.join(description_parts)
    
    # Strategy 4: Look for meta description as last resort
    if not description_text or len(description_text) < 50:
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if not meta_desc:
            meta_desc = soup.find('meta', attrs={'property': 'og:description'})
        
        if meta_desc and meta_desc.get('content'):
            description_text = meta_desc.get('content', '').strip()
    
    # Clean and limit description length
    if description_text:
        # Remove extra whitespace
        description_text = ' '.join(description_text.split())
        # Limit to 1000 characters for better embedding quality
        details['description'] = description_text[:1000]
    
    # ============================================================
    # EXTRACT JOB LEVELS
    # ============================================================
    # Job levels are typically shown as a list or in a dedicated section
    # Common job levels: Entry Level, Mid Level, Senior Level, Executive, etc.
    
    job_levels = []
    page_text = soup.get_text().lower()
    
    # Strategy 1: Look for "Job Level" or "Suitable for" sections
    job_level_keywords = ['job level', 'job levels', 'suitable for', 'target audience', 'appropriate for']
    
    for keyword in job_level_keywords:
        if keyword in page_text:
            # Find the section containing this keyword
            for elem in soup.find_all(['div', 'section', 'p', 'li', 'span']):
                elem_text = elem.get_text(strip=True)
                if keyword in elem_text.lower():
                    # Extract job levels from this element and its siblings
                    # Look for common job level terms
                    level_terms = {
                        'entry': 'Entry Level',
                        'junior': 'Entry Level',
                        'graduate': 'Entry Level',
                        'mid': 'Mid Level',
                        'intermediate': 'Mid Level',
                        'experienced': 'Mid Level',
                        'senior': 'Senior Level',
                        'lead': 'Senior Level',
                        'executive': 'Executive',
                        'manager': 'Management',
                        'director': 'Executive',
                        'c-level': 'Executive',
                        'professional': 'Professional'
                    }
                    
                    elem_lower = elem_text.lower()
                    for term, level in level_terms.items():
                        if term in elem_lower and level not in job_levels:
                            job_levels.append(level)
    
    # Strategy 2: Look for bullet points or lists containing job levels
    lists = soup.find_all(['ul', 'ol'])
    for list_elem in lists:
        list_text = list_elem.get_text().lower()
        
        # Check if this list is about job levels
        if any(kw in list_text for kw in ['level', 'suitable', 'appropriate', 'target']):
            level_terms = {
                'entry': 'Entry Level',
                'junior': 'Entry Level',
                'graduate': 'Entry Level',
                'mid': 'Mid Level',
                'intermediate': 'Mid Level',
                'senior': 'Senior Level',
                'executive': 'Executive',
                'manager': 'Management',
                'professional': 'Professional'
            }
            
            for term, level in level_terms.items():
                if term in list_text and level not in job_levels:
                    job_levels.append(level)
    
    # Strategy 3: General page scan for job level mentions
    if not job_levels:
        # If no specific section found, do a general scan
        level_patterns = {
            'entry level': 'Entry Level',
            'junior level': 'Entry Level',
            'mid level': 'Mid Level',
            'mid-level': 'Mid Level',
            'senior level': 'Senior Level',
            'senior-level': 'Senior Level',
            'executive level': 'Executive',
            'management level': 'Management',
            'professional level': 'Professional'
        }
        
        for pattern, level in level_patterns.items():
            if pattern in page_text and level not in job_levels:
                job_levels.append(level)
    
    # If still no job levels found, mark as "All Levels" (common default)
    if not job_levels:
        job_levels.append('All Levels')
    
    details['job_levels'] = job_levels

    # ============================================================
    # EXTRACT DURATION / ASSESSMENT LENGTH
    # ============================================================
    duration = ''
    
    # Strategy 1: Look for "Assessment length" section
    duration_keywords = ['assessment length', 'completion time', 'duration', 'time to complete', 'approximate completion time']
    
    for keyword in duration_keywords:
        if keyword in page_text:
            # Find elements containing this keyword
            for elem in soup.find_all(['div', 'section', 'p', 'li', 'span', 'td', 'th']):
                elem_text = elem.get_text(strip=True)
                elem_lower = elem_text.lower()
                
                if keyword in elem_lower:
                    # Extract the duration value
                    # Common patterns: "30 minutes", "max 30", "20-30 minutes", etc.
                    import re
                    
                    # Look for time patterns in this element and nearby elements
                    # Pattern: number followed by "minute(s)" or "min"
                    time_pattern = r'(\d+(?:-\d+)?)\s*(?:minute|minutes|min|mins)'
                    matches = re.findall(time_pattern, elem_lower)
                    
                    if matches:
                        duration = matches[0] + ' minutes'
                        break
                    
                    # Also check "max XX" pattern
                    max_pattern = r'max\s*(\d+)'
                    max_matches = re.findall(max_pattern, elem_lower)
                    if max_matches:
                        duration = 'max ' + max_matches[0] + ' minutes'
                        break
                    
                    # Check next sibling or child elements for the actual time value
                    next_elem = elem.find_next_sibling()
                    if next_elem:
                        next_text = next_elem.get_text(strip=True).lower()
                        matches = re.findall(time_pattern, next_text)
                        if matches:
                            duration = matches[0] + ' minutes'
                            break
            
            if duration:
                break
    
    # Strategy 2: Look in table cells (duration often appears in structured data)
    if not duration:
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                for i, cell in enumerate(cells):
                    cell_text = cell.get_text(strip=True).lower()
                    
                    # Check if this cell contains a duration keyword
                    if any(kw in cell_text for kw in duration_keywords):
                        # The next cell might contain the actual duration
                        if i + 1 < len(cells):
                            next_cell = cells[i + 1].get_text(strip=True)
                            duration = next_cell
                            break
                        # Or this cell itself might contain it
                        else:
                            import re
                            time_pattern = r'(\d+(?:-\d+)?)\s*(?:minute|minutes|min|mins)'
                            matches = re.findall(time_pattern, cell_text)
                            if matches:
                                duration = matches[0] + ' minutes'
                                break
                
                if duration:
                    break
            if duration:
                break
    
    # Strategy 3: Look for the specific structure shown in the image
    # "Assessment length" heading followed by the time value
    if not duration:
        for heading in soup.find_all(['dt', 'h3', 'h4', 'strong', 'b']):
            heading_text = heading.get_text(strip=True).lower()
            if 'assessment length' in heading_text or 'completion time' in heading_text:
                # Look for the corresponding value (could be in <dd>, next sibling, etc.)
                value_elem = heading.find_next_sibling(['dd', 'p', 'span', 'div'])
                if value_elem:
                    duration = value_elem.get_text(strip=True)
                    break
    
    # Clean up duration text
    if duration:
        # Remove extra text, keep only the essential time info
        duration = duration.replace('Approximate Completion Time in minutes =', '').strip()
        duration = duration.replace('=', '').strip()
        
        # Ensure it contains actual time information
        import re
        if not re.search(r'\d+', duration):
            duration = ''
    
    details['duration'] = duration
    
    return details

def find_individual_test_solutions_table(soup):
    """
    Find the correct table by locating the "Individual Test Solutions" heading.
    CRITICAL: Must skip "Pre-packaged Job Solutions" table.
    
    Args:
        soup: BeautifulSoup object of the page
        
    Returns:
        Table element or None if not found
    """
    # Find ALL tables on the page
    all_tables = soup.find_all('table')
    
    if len(all_tables) == 0:
        print("ERROR: No tables found on page")
        return None
    
    # Strategy 1: Find the heading "Individual Test Solutions" and get the table after it
    for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'div', 'span', 'p']):
        heading_text = heading.get_text(strip=True)
        
        # EXACT match for "Individual Test Solutions"
        if heading_text == 'Individual Test Solutions':
            print(f"Found 'Individual Test Solutions' heading")
            
            # Find the table that comes after this heading
            table = heading.find_next('table')
            if table:
                print(f"Found table associated with 'Individual Test Solutions'")
                return table
    
    # Strategy 2: Check each table for context clues
    # The Individual Test Solutions table should NOT contain "Pre-packaged" in nearby text
    for idx, table in enumerate(all_tables):
        # Get text before this table (previous siblings)
        context_before = ""
        prev_sibling = table.find_previous_sibling()
        
        # Get up to 3 previous siblings to understand context
        for _ in range(3):
            if prev_sibling:
                context_before = prev_sibling.get_text(strip=True) + " " + context_before
                prev_sibling = prev_sibling.find_previous_sibling()
        
        # Check if this table is for Individual Test Solutions
        is_individual = 'Individual Test Solutions' in context_before
        is_prepackaged = 'Pre-packaged' in context_before or 'Pre-Packaged' in context_before
        
        if is_individual and not is_prepackaged:
            print(f"Found Individual Test Solutions table (table index: {idx})")
            return table
    
    # Strategy 3: If we have multiple tables, the Individual Test Solutions 
    # table is typically the LAST table (Pre-packaged comes first)
    if len(all_tables) >= 2:
        print(f"Using fallback: selecting last table (index {len(all_tables)-1})")
        return all_tables[-1]  # Return the last table
    
    # Fallback: return the first table (risky, but better than nothing)
    print(f"WARNING: Could not definitively identify table, using first table")
    return all_tables[0] if all_tables else None

def check_for_green_dot(cell):
    """
    Check if a table cell contains a green dot indicator.
    Green dots typically indicate "Yes" for features like remote/adaptive support.
    
    Args:
        cell: BeautifulSoup table cell element
        
    Returns:
        "Yes" if green dot found, "No" otherwise
    """
    if not cell:
        return "No"
    
    # Look for common green dot indicators
    # These could be: images, spans with specific classes, or unicode characters
    
    # Check for images with 'green' or 'check' in src/alt
    images = cell.find_all('img')
    for img in images:
        src = img.get('src', '').lower()
        alt = img.get('alt', '').lower()
        if 'green' in src or 'check' in src or 'yes' in alt or 'tick' in src:
            return "Yes"
    
    # Check for spans or divs with green-related classes
    elements = cell.find_all(['span', 'div', 'i'])
    for elem in elements:
        classes = ' '.join(elem.get('class', [])).lower()
        if 'green' in classes or 'check' in classes or 'yes' in classes or 'active' in classes:
            return "Yes"
    
    # Check for unicode check marks or bullets
    cell_text = cell.get_text(strip=True)
    if '✓' in cell_text or '✔' in cell_text or '●' in cell_text:
        return "Yes"
    
    return "No"

def extract_test_types(row):
    """
    Extract test types from a table row.
    Test types appear as small dark boxes with white letters (A, B, C, D, E, K, P, S).
    Each assessment can have multiple test types (e.g., "B K S A").
    
    SHL has 8 test type categories:
    A = Ability & Aptitude
    B = Biodata & Situational Judgement
    C = Competencies
    D = Development & 360
    E = Assessment Exercises
    K = Knowledge & Skills
    P = Personality & Behavior
    S = Simulations
    
    Args:
        row: BeautifulSoup table row element
        
    Returns:
        List of test type strings
    """
    # Mapping from letter codes to full test type names
    TEST_TYPE_MAP = {
        'A': 'Ability & Aptitude',
        'B': 'Biodata & Situational Judgement',
        'C': 'Competencies',
        'D': 'Development & 360',
        'E': 'Assessment Exercises',
        'K': 'Knowledge & Skills',
        'P': 'Personality & Behavior',
        'S': 'Simulations'
    }
    
    test_types = []
    found_letters = set()  # Track unique letters found
    
    # Find the "Test Type" column (usually the last column)
    cells = row.find_all(['td', 'th'])
    
    if len(cells) < 4:
        return ['Other']
    
    # The Test Type column is typically the 4th column (index 3)
    # But let's check all cells to be safe
    test_type_cell = cells[-1]  # Last column is Test Type
    
    # Strategy 1: Look for images with alt text containing single letters
    images = test_type_cell.find_all('img')
    for img in images:
        alt = img.get('alt', '').strip().upper()
        title = img.get('title', '').strip().upper()
        
        # Check if alt or title is a single letter A-Z
        if len(alt) == 1 and alt in TEST_TYPE_MAP:
            found_letters.add(alt)
        if len(title) == 1 and title in TEST_TYPE_MAP:
            found_letters.add(title)
    
    # Strategy 2: Look for spans or divs with single letter text
    # Test type icons are often rendered as styled divs/spans with letters
    for elem in test_type_cell.find_all(['span', 'div', 'i', 'strong', 'b']):
        text = elem.get_text(strip=True).upper()
        
        # Check if this element contains only a single letter
        if len(text) == 1 and text in TEST_TYPE_MAP:
            found_letters.add(text)
    
    # Strategy 3: Parse all text in the Test Type cell
    # Sometimes letters appear directly as text (e.g., "B K S A")
    cell_text = test_type_cell.get_text(strip=True).upper()
    
    # Extract single capital letters that are test type codes
    # Split by spaces and check each token
    tokens = cell_text.split()
    for token in tokens:
        # Remove any non-letter characters
        clean_token = ''.join(c for c in token if c.isalpha())
        
        # Check if it's a valid test type letter
        if len(clean_token) == 1 and clean_token in TEST_TYPE_MAP:
            found_letters.add(clean_token)
    
    # Strategy 4: Check for class names or data attributes
    # Icons might have classes like "test-type-k" or data-type="K"
    for elem in test_type_cell.find_all():
        classes = ' '.join(elem.get('class', [])).upper()
        data_type = elem.get('data-type', '').strip().upper()
        
        # Check classes for letter codes
        for letter in TEST_TYPE_MAP.keys():
            if f'TYPE-{letter}' in classes or f'TYPE_{letter}' in classes:
                found_letters.add(letter)
        
        # Check data-type attribute
        if data_type in TEST_TYPE_MAP:
            found_letters.add(data_type)
    
    # Convert found letters to full test type names
    for letter in sorted(found_letters):  # Sort for consistent ordering
        test_type_name = TEST_TYPE_MAP[letter]
        if test_type_name not in test_types:
            test_types.append(test_type_name)
    
    # If no test types found, mark as 'Other'
    if not test_types:
        test_types.append('Other')
    
    return test_types

def scrape_page(start_offset):
    """
    Scrape a single page of the catalog.
    For each assessment, also fetch its detail page to get description and job levels.
    
    Args:
        start_offset: The pagination offset (0, 12, 24, etc.)
        
    Returns:
        List of assessment dictionaries from this page
    """
    # Build URL with type=1 for Individual Test Solutions ONLY
    url = f"{CATALOG_URL}?start={start_offset}&type=1"
    print(f"Scraping page with start={start_offset}...")
    
    soup = get_page_content(url)
    if not soup:
        print(f"Failed to fetch page at start={start_offset}")
        return []
    
    # Find the correct table by heading text
    table = find_individual_test_solutions_table(soup)
    
    if not table:
        print(f"Could not find 'Individual Test Solutions' table at start={start_offset}")
        return []
    
    assessments = []
    
    # Find all table rows (skip header row)
    rows = table.find_all('tr')
    
    # Skip the first row if it's a header
    data_rows = rows[1:] if len(rows) > 1 else rows
    
    for idx, row in enumerate(data_rows, 1):
        # Find all cells in this row
        cells = row.find_all(['td', 'th'])
        
        if len(cells) < 3:  # Need at least name, remote, adaptive columns
            continue
        
        # Extract the assessment name and URL (usually first cell with <a> tag)
        name_cell = None
        assessment_link = None
        
        # Find the cell with the assessment link
        for cell in cells:
            link = cell.find('a')
            if link and link.get('href'):
                name_cell = cell
                assessment_link = link
                break
        
        if not assessment_link:
            continue  # Skip rows without a link
        
        # Extract data
        name = assessment_link.get_text(strip=True)
        relative_url = assessment_link.get('href')
        
        # CRITICAL VALIDATION: Skip Pre-packaged Job Solutions
        # Check if name or URL contains indicators of pre-packaged solutions
        if 'solution' in name.lower() and any(word in name.lower() for word in ['job', 'manager', 'professional', 'clerk', 'agent']):
            print(f"  SKIPPING Pre-packaged solution: {name}")
            continue
        
        # Additional check: Pre-packaged URLs often contain '/solutions/' or specific patterns
        if '/solutions/' in relative_url.lower() and 'job' in relative_url.lower():
            print(f"  SKIPPING Pre-packaged solution URL: {relative_url}")
            continue
        
        # Convert to absolute URL
        detail_url = urljoin(BASE_URL, relative_url)
        
        # Extract remote support (typically 2nd or 3rd column)
        # Look for cells that might contain green dots
        remote_support = "No"
        adaptive_support = "No"
        
        # Check each cell for green dots
        # Typically: Column 1 = Name, Column 2 = Remote, Column 3 = Adaptive, Column 4+ = Test Type
        if len(cells) >= 2:
            remote_support = check_for_green_dot(cells[1])
        if len(cells) >= 3:
            adaptive_support = check_for_green_dot(cells[2])
        
        # Extract test types (look across all cells)
        test_type = extract_test_types(row)
        
        # Create assessment dictionary with basic info
        # Create assessment dictionary with basic info
        assessment = {
            'name': name,
            'url': detail_url,
            'remote_support': remote_support,
            'adaptive_support': adaptive_support,
            'test_type': test_type,
            'description': '',
            'job_levels': [],
            'duration': ''
        }
        
        # Now fetch the detail page to get description and job levels
        print(f"  Fetching details for: {name}")
        details = extract_assessment_details(detail_url)
        
        if details:
            assessment['description'] = details['description']
            assessment['job_levels'] = details['job_levels']
            assessment['duration'] = details['duration']
            print(f"     Description: {len(details['description'])} chars")
            print(f"     Job Levels: {', '.join(details['job_levels'])}")
            print(f"     Duration: {details['duration'] if details['duration'] else 'Not found'}")
        else:
            print(f"     Could not fetch details")
        
        assessments.append(assessment)
        
        # Be polite - add small delay between detail page requests
        time.sleep(0.5)
    
    print(f"Found {len(assessments)} assessments on this page")
    return assessments

def scrape_catalog():
    """
    Main function to scrape all pages of the SHL product catalog.
    
    Returns:
        List of all assessment dictionaries
    """
    print("Starting SHL Individual Test Solutions scrape...")
    print("=" * 60)
    
    all_assessments = []
    
    # Pagination: 32 pages total
    # Pages 1-31 have 12 assessments each
    # Page 32 has 5 assessments
    # Total = 377 assessments
    
    # Start offsets: 0, 12, 24, 36, ..., 372
    page_num = 1
    start_offset = 0
    
    while True:
        print(f"\n--- Page {page_num} (start={start_offset}) ---")
        
        # Scrape this page
        page_assessments = scrape_page(start_offset)
        
        # If no assessments found, we've reached the end
        if not page_assessments:
            print("No more assessments found. Stopping.")
            break
        
        # Add to our collection
        all_assessments.extend(page_assessments)
        
        print(f"Total assessments so far: {len(all_assessments)}")
        
        # Check if we've reached 377 (the exact total)
        if len(all_assessments) >= 377:
            print("\nReached 377 assessments. Stopping.")
            break
        
        # Move to next page
        # Each page shows 12 assessments, so increment by 12
        start_offset += 12
        page_num += 1
        
        # Safety check: don't scrape more than 35 pages
        if page_num > 35:
            print("Reached maximum page limit (35). Stopping.")
            break
        
        # Be polite - add small delay between requests
        time.sleep(0.5)
    
    print("\n" + "=" * 60)
    print(f"Scraping complete! Total assessments collected: {len(all_assessments)}")
    
    return all_assessments

def validate_and_deduplicate(assessments):
    """
    Validate that we have exactly 377 assessments and remove duplicates.
    Also verify that NO Pre-packaged Job Solutions were scraped.
    
    Args:
        assessments: List of assessment dictionaries
        
    Returns:
        Deduplicated list of assessments
    """
    print("\n" + "=" * 60)
    print("VALIDATION")
    print("=" * 60)
    
    print(f"Total assessments scraped: {len(assessments)}")
    
    # CRITICAL CHECK: Detect and remove any Pre-packaged Job Solutions
    # Pre-packaged solutions typically have names like:
    # - "Account Manager Solution"
    # - "Administrative Professional - Short Form"
    # - "Agency Manager Solution"
    prepackaged_keywords = [
        'solution',  # Most pre-packaged have "Solution" in name
    ]
    
    # Check for assessments that look like Pre-packaged Job Solutions
    suspicious_assessments = []
    clean_assessments = []
    
    for assessment in assessments:
        name = assessment['name'].lower()
        
        # Flag if name contains "solution" AND job-related terms
        is_suspicious = False
        if 'solution' in name:
            job_terms = ['manager', 'professional', 'agent', 'clerk', 'supervisor', 
                         'administrator', 'representative', 'specialist', 'officer',
                         'assistant', 'associate', 'coordinator', 'job focused']
            
            if any(term in name for term in job_terms):
                is_suspicious = True
                suspicious_assessments.append(assessment['name'])
        
        if not is_suspicious:
            clean_assessments.append(assessment)
        else:
            print(f"REMOVED Pre-packaged: {assessment['name']}")
    
    if suspicious_assessments:
        print(f"\nWARNING: Removed {len(suspicious_assessments)} Pre-packaged solutions")
    
    # Use clean_assessments for further processing
    assessments = clean_assessments
    
    # Deduplicate by URL
    seen_urls = set()
    unique_assessments = []
    
    for assessment in assessments:
        url = assessment['url']
        if url not in seen_urls:
            seen_urls.add(url)
            unique_assessments.append(assessment)
    
    duplicates_removed = len(assessments) - len(unique_assessments)
    if duplicates_removed > 0:
        print(f"Removed {duplicates_removed} duplicate(s)")
    
    print(f"Unique assessments: {len(unique_assessments)}")
    
    # CRITICAL: Validate exactly 377 assessments
    if len(unique_assessments) != 377:
        error_msg = f"ERROR: Expected exactly 377 assessments, but found {len(unique_assessments)}"
        print("\n" + "!" * 60)
        print(error_msg)
        print("!" * 60)
        raise ValueError(error_msg)
    
    print("\nSUCCESS: Found exactly 377 unique Individual Test Solutions")
    print("NO Pre-packaged Job Solutions included")
    
    return unique_assessments

def save_assessments(assessments, output_file='data/shl_assessments.json'):
    """
    Save assessments to JSON file.
    
    Args:
        assessments: List of assessment dictionaries
        output_file: Path to output JSON file
    """
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(assessments, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved {len(assessments)} assessments to {output_file}")

if __name__ == "__main__":
    # Step 1: Scrape the catalog
    assessments = scrape_catalog()
    
    # Step 2: Validate and deduplicate
    try:
        unique_assessments = validate_and_deduplicate(assessments)
    except ValueError as e:
        print("\nScraping failed validation. Please check the scraping logic.")
        exit(1)
    
    # Step 3: Save to JSON file
    save_assessments(unique_assessments)
    
    # Step 4: Print summary statistics
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total unique assessments: {len(unique_assessments)}")
    
    # Count by test type
    test_type_counts = {}
    for assessment in unique_assessments:
        for test_type in assessment.get('test_type', []):
            test_type_counts[test_type] = test_type_counts.get(test_type, 0) + 1
    
    print("\nTest types found:")
    for test_type, count in sorted(test_type_counts.items()):
        print(f"  {test_type}: {count}")
    
    # Count remote support
    remote_count = sum(1 for a in unique_assessments if a.get('remote_support') == 'Yes')
    print(f"\nRemote support: {remote_count}/{len(unique_assessments)}")
    
    # Count adaptive support
    adaptive_count = sum(1 for a in unique_assessments if a.get('adaptive_support') == 'Yes')
    print(f"Adaptive support: {adaptive_count}/{len(unique_assessments)}")
    
    # Count by job levels
    job_level_counts = {}
    for assessment in unique_assessments:
        for job_level in assessment.get('job_levels', []):
            job_level_counts[job_level] = job_level_counts.get(job_level, 0) + 1
    
    print("\nJob levels found:")
    for job_level, count in sorted(job_level_counts.items()):
        print(f"  {job_level}: {count}")

    # Count assessments with duration
    with_duration = sum(1 for a in unique_assessments if a.get('duration'))
    print(f"\nAssessments with duration: {with_duration}/{len(unique_assessments)}")
    
    # Count assessments with descriptions
    with_desc = sum(1 for a in unique_assessments if a.get('description'))
    print(f"\nAssessments with descriptions: {with_desc}/{len(unique_assessments)}")
    
    print("\n" + "=" * 60)
    print("SCRAPING COMPLETED SUCCESSFULLY")
    print("=" * 60)