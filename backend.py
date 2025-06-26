# pdf_backend.py
import os
import fitz
import pytesseract
from PIL import Image
import io
import re
import numpy as np
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import spacy
import base64
import json

# Load the larger language model for better accuracy
nlp = spacy.load("en_core_web_lg")

app = Flask(__name__)
UPLOAD_FOLDER = "./uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def extract_text_from_pdf(file_path):
    """Extract text from PDF document"""
    doc = fitz.open(file_path)
    text_by_page = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        text_by_page.append(page.get_text())
        
    return text_by_page

def extract_images_from_pdf(file_path):
    """Extract images from PDF with metadata"""
    doc = fitz.open(file_path)
    image_data = []
    
    for page_index in range(len(doc)):
        page = doc[page_index]
        image_list = page.get_images(full=True)
        
        for img_index, img in enumerate(image_list):
            try:
                xref = img[0]
                base_image = doc.extract_image(xref)
                
                image_bytes = base_image["image"]
                image = Image.open(io.BytesIO(image_bytes))
                
                # Convert CMYK to RGB if needed
                if image.mode == 'CMYK':
                    image = image.convert('RGB')
                
                # Convert to base64 for frontend display
                buffered = io.BytesIO()
                image.save(buffered, format="PNG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
                
                # Get image position on page
                rect = page.get_image_bbox(img)
                
                # Store image data
                image_data.append({
                    "page": page_index + 1,
                    "position": {"x": rect.x0, "y": rect.y0, "width": rect.width, "height": rect.height},
                    "base64": img_str,
                    "size": {"width": image.width, "height": image.height},
                    "format": base_image["ext"],
                    "ocr_text": pytesseract.image_to_string(image)
                })
            except Exception as e:
                print(f"Error processing image: {e}")
                # Continue with next image
    
    return image_data

def detect_charts(image):
    """Basic chart detection based on image properties"""
    try:
        # Convert to numpy array for analysis
        img_array = np.array(image)
        
        # Check if image is grayscale or has alpha channel
        if len(img_array.shape) == 2:  # Grayscale
            return False, None
        
        if img_array.shape[2] == 1:  # Single channel
            return False, None
            
        if img_array.shape[2] == 4:  # RGBA
            # Use only RGB channels
            img_array = img_array[:, :, :3]
        
        # Simple heuristics for chart detection:
        # 1. Check for consistent color patterns (charts often have distinct colors)
        # 2. Look for grid-like structures
        
        # Count unique colors (charts often have limited color palette)
        unique_colors = len(np.unique(img_array.reshape(-1, img_array.shape[2]), axis=0))
        
        # Check for horizontal/vertical lines (common in charts)
        edges_h = np.sum(np.abs(np.diff(img_array, axis=0)))
        edges_v = np.sum(np.abs(np.diff(img_array, axis=1)))
        
        # Calculate edge ratio (charts often have structured edges)
        edge_ratio = np.sum(edges_h) / (np.sum(edges_v) + 1e-10)
        
        # Determine if image is likely a chart
        is_chart = (
            (unique_colors < 50) and  # Limited color palette
            (edge_ratio > 0.5 and edge_ratio < 2.0)  # Balanced edges
        )
        
        chart_type = None
        if is_chart:
            # Simple chart type detection
            if edge_ratio > 1.2:
                chart_type = "bar_chart"
            elif edge_ratio < 0.8:
                chart_type = "line_chart"
            else:
                chart_type = "other_chart"
        
        return is_chart, chart_type
        
    except Exception as e:
        print(f"Error in chart detection: {e}")
        return False, None

def clean_text(text):
    """Clean text for better processing"""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove special characters that might interfere with NLP
    text = re.sub(r'[^\w\s.,;:!?()-]', '', text)
    return text.strip()

def extract_entities(text):
    """Extract named entities from text"""
    # Process the text
    doc = nlp(clean_text(text[:100000]))  # Limit text length for performance
    
    # Filter out low-confidence entities and duplicates
    entities = []
    seen_entities = set()
    
    for ent in doc.ents:
        # Skip very short entities (likely noise)
        if len(ent.text.strip()) <= 1:
            continue
            
        # Skip entities that are just numbers
        if re.match(r'^\d+$', ent.text.strip()):
            continue
            
        # Create a unique key for this entity
        entity_key = (ent.text.lower(), ent.label_)
        
        # Skip if we've seen this entity before
        if entity_key in seen_entities:
            continue
            
        # Add to our results and mark as seen
        seen_entities.add(entity_key)
        entities.append({"text": ent.text, "label": ent.label_})
    
    return entities

def summarize_text(text):
    """Generate a summary of the text"""
    # Clean the text first
    clean = clean_text(text)
    
    # Use spaCy to extract sentences
    doc = nlp(clean[:10000])  # Limit to first 10000 chars for performance
    
    # Get the most important sentences (first few sentences)
    summary_sentences = list(doc.sents)[:5]
    
    # Join sentences into a summary
    summary = " ".join(str(s) for s in summary_sentences)
    
    # If summary is too short, just return the first 300 characters
    if len(summary) < 100 and len(clean) > 100:
        summary = clean[:300] + "..."
        
    return summary

def analyze_document_structure(text_by_page):
    """Analyze document structure to identify sections, headings, etc."""
    structure = {
        "total_pages": len(text_by_page),
        "sections": [],
        "estimated_word_count": 0
    }
    
    combined_text = ""
    current_section = None
    
    for page_num, page_text in enumerate(text_by_page):
        combined_text += page_text
        
        # Estimate word count
        words = re.findall(r'\b\w+\b', page_text)
        structure["estimated_word_count"] += len(words)
        
        # Try to identify section headings (simple heuristic)
        lines = page_text.split('\n')
        for line in lines:
            line = line.strip()
            # Check if line looks like a heading (short, ends with no punctuation, etc.)
            if (len(line) > 0 and len(line) < 100 and 
                line.isupper() or 
                re.match(r'^[0-9]+\.\s+[A-Z]', line) or
                re.match(r'^[A-Z][a-z]+(\s+[A-Z][a-z]+){0,3}$', line)):
                
                # Start new section
                if current_section:
                    structure["sections"].append(current_section)
                
                current_section = {
                    "heading": line,
                    "page": page_num + 1
                }
    
    # Add the last section if there is one
    if current_section:
        structure["sections"].append(current_section)
    
    return structure, combined_text

# Custom JSON encoder to handle non-serializable types
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

# Update Flask app to use custom encoder
app.json_encoder = CustomJSONEncoder

@app.route("/analyze", methods=["POST"])
def analyze_pdf():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)

    # Extract text by page
    text_by_page = extract_text_from_pdf(file_path)
    
    # Analyze document structure
    structure, combined_text = analyze_document_structure(text_by_page)
    
    # Extract images with analysis
    images = extract_images_from_pdf(file_path)
    
    # Process images for charts/graphs
    for img_data in images:
        if "base64" in img_data:
            try:
                # Decode base64 image for analysis
                img_bytes = base64.b64decode(img_data["base64"])
                img = Image.open(io.BytesIO(img_bytes))
                
                # Check if image is a chart
                is_chart, chart_type = detect_charts(img)
                img_data["is_chart"] = is_chart
                if chart_type:
                    img_data["chart_type"] = chart_type
            except Exception as e:
                print(f"Error processing image: {e}")
                img_data["is_chart"] = False

    # Extract entities and generate summary
    entities = extract_entities(combined_text)
    summary = summarize_text(combined_text)

    return jsonify({
        "filename": filename,
        "summary": summary,
        "structure": structure,
        "entities": entities,
        "images": images,
        "page_count": len(text_by_page),
        "text_by_page": text_by_page  # Include page text for frontend display
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000)
