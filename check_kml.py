import sys
import os
import zipfile
import xml.etree.ElementTree as ET

def parse_kml(kml_content):
    """
    Parses KML content (string) and prints statistics.
    """
    try:
        root = ET.fromstring(kml_content)
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}")
        return

    # Namespaces are often used in KML, usually the default one.
    # We need to handle them. The default namespace usually looks like: {http://www.opengis.net/kml/2.2}
    # To make it easier, we can strip namespaces or try to detect it.
    # For a simple counter, we can iterate all elements and check their tags ignoring namespace.

    counts = {
        'Folder': 0,
        'Placemark': 0,
        'GroundOverlay': 0,
        'NetworkLink': 0,
        'Document': 0
    }

    print("\n--- KML Content Summary ---")
    
    # Iterate over all elements
    for elem in root.iter():
        # Tag might be like '{http://www.opengis.net/kml/2.2}Placemark'
        tag_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        
        if tag_name in counts:
            counts[tag_name] += 1
        
        # If it's a Placemark, try to find coordinates
        if tag_name == 'Placemark':
            name = "Unknown"
            coords = "No coordinates found"
            
            # Search children for name and Point/coordinates
            # We need to handle namespaces in children too
            for child in elem.iter():
                child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if child_tag == 'name':
                    name = child.text
                elif child_tag == 'coordinates':
                    coords = child.text.strip()
            
            print(f"Placemark: {name} | Coordinates: {coords}")

    print("\n---------------------------")

    for key, value in counts.items():
        print(f"Total {key}: {value}")
        
    print("---------------------------\n")

def process_file(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        return

    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext == '.kmz':
        print(f"Processing KMZ file: {file_path}")
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                # Find the first .kml file in the archive
                kml_files = [f for f in z.namelist() if f.lower().endswith('.kml')]
                if not kml_files:
                    print("Error: No KML file found inside the KMZ archive.")
                    return
                
                kml_filename = kml_files[0]
                print(f"Found KML inside KMZ: {kml_filename}")
                with z.open(kml_filename) as f:
                    content = f.read()
                    parse_kml(content)
        except zipfile.BadZipFile:
            print("Error: Invalid KMZ (zip) file.")
    
    elif ext == '.kml':
        print(f"Processing KML file: {file_path}")
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                parse_kml(content)
        except Exception as e:
            print(f"Error reading file: {e}")
            
    else:
        print("Error: Unsupported file extension. Please provide a .kml or .kmz file.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_kml.py <path_to_kml_or_kmz>")
    else:
        process_file(sys.argv[1])
