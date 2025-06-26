# pdf_frontend.py
import streamlit as st
import requests
import base64

st.set_page_config(page_title="PDF Intelligence Analyzer", layout="wide")
st.title("📄 PDF Intelligence")

# Add a description
st.markdown("""
This tool analyzes PDF documents to extract text, identify charts/images, and generate summaries.
Perfect for quickly understanding documents, research papers, and visual content.
""")

# Custom CSS for better display
st.markdown("""
<style>
.entity-box {
    padding: 8px;
    margin: 5px 0;
    border-radius: 5px;
}
.entity-PERSON { background-color: #ffcccb; }
.entity-ORG { background-color: #c2f0c2; }
.entity-GPE, .entity-LOC { background-color: #add8e6; }
.entity-DATE, .entity-TIME { background-color: #ffffcc; }
.entity-PRODUCT { background-color: #ccccff; }
.entity-OTHER { background-color: #f0f0f0; }

.image-container {
    border: 1px solid #ddd;
    border-radius: 5px;
    padding: 10px;
    margin-bottom: 15px;
}

.chart-container {
    border: 2px solid #4CAF50;
    border-radius: 5px;
    padding: 10px;
    margin-bottom: 15px;
}

.section-box {
    border-left: 3px solid #2196F3;
    padding-left: 10px;
    margin-bottom: 10px;
}
</style>
""", unsafe_allow_html=True)

uploaded_file = st.file_uploader("Upload a PDF", type="pdf")

if uploaded_file:
    with st.spinner("Analyzing PDF..."):
        files = {"file": uploaded_file}
        res = requests.post("http://localhost:5000/analyze", files=files)

        if res.ok:
            data = res.json()
            
            # Create tabs for different views
            tabs = st.tabs(["Overview", "Content", "Images & Charts", "Entities"])
            
            # Overview tab
            with tabs[0]:
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.subheader("Document Summary")
                    st.write(data["summary"])
                
                with col2:
                    st.subheader("Document Info")
                    st.write(f"**Filename:** {data['filename']}")
                    st.write(f"**Pages:** {data['page_count']}")
                    st.write(f"**Word Count:** {data['structure']['estimated_word_count']}")
                    st.write(f"**Images:** {len(data['images'])}")
                    
                    # Count charts
                    chart_count = sum(1 for img in data['images'] if img.get('is_chart', False))
                    st.write(f"**Charts/Graphs:** {chart_count}")
                
                # Display document structure
                st.subheader("Document Structure")
                if data["structure"]["sections"]:
                    for section in data["structure"]["sections"]:
                        st.markdown(f"""
                        <div class="section-box">
                            <strong>{section['heading']}</strong> (Page {section['page']})
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.write("No clear sections detected")
            
            # Content tab
            with tabs[1]:
                st.subheader("Document Content")
                
                # Allow users to search within the document
                search_term = st.text_input("Search within document")
                
                # Create a page selector
                page_numbers = list(range(1, data["page_count"] + 1))
                selected_page = st.selectbox("Select page", page_numbers)
                
                # Display page content
                if selected_page and selected_page <= data["page_count"]:
                    if "text_by_page" in data and selected_page <= len(data["text_by_page"]):
                        page_content = data["text_by_page"][selected_page - 1]
                        
                        # Highlight search term if provided
                        if search_term and search_term in page_content:
                            highlighted_content = page_content.replace(search_term, f"**{search_term}**")
                            st.markdown(highlighted_content)
                        else:
                            st.text(page_content)
                    else:
                        st.write("Page content not available")
            
            # Images & Charts tab
            with tabs[2]:
                st.subheader("Images & Charts")
                
                # Separate charts and regular images
                charts = [img for img in data["images"] if img.get("is_chart", False)]
                regular_images = [img for img in data["images"] if not img.get("is_chart", False)]
                
                # Display charts first
                if charts:
                    st.write(f"### Charts/Graphs ({len(charts)})")
                    chart_cols = st.columns(2)
                    
                    for i, img in enumerate(charts):
                        col = chart_cols[i % 2]
                        with col:
                            st.markdown(f"""
                            <div class="chart-container">
                                <p><strong>Chart Type:</strong> {img.get('chart_type', 'Unknown').replace('_', ' ').title()}</p>
                                <p><strong>Page:</strong> {img['page']}</p>
                            </div>
                            """, unsafe_allow_html=True)
                            st.image(f"data:image/{img['format']};base64,{img['base64']}", 
                                    caption=f"Chart on page {img['page']}")
                            
                            if img.get('ocr_text'):
                                with st.expander("Text in Chart"):
                                    st.text(img['ocr_text'])
                
                # Display other images
                if regular_images:
                    st.write(f"### Other Images ({len(regular_images)})")
                    img_cols = st.columns(3)
                    
                    for i, img in enumerate(regular_images):
                        col = img_cols[i % 3]
                        with col:
                            st.image(f"data:image/{img['format']};base64,{img['base64']}", 
                                    caption=f"Image on page {img['page']}")
                            
                            if img.get('ocr_text'):
                                with st.expander("OCR Text"):
                                    st.text(img['ocr_text'])
            
            # Entities tab
            with tabs[3]:
                st.subheader("Named Entities")
                
                # Group entities by category
                entity_categories = {}
                for ent in data["entities"]:
                    category = ent["label"]
                    if category not in entity_categories:
                        entity_categories[category] = []
                    entity_categories[category].append(ent["text"])
                
                # Define category order and friendly names
                category_order = ["PERSON", "ORG", "GPE", "LOC", "DATE", "TIME", "PRODUCT"]
                friendly_names = {
                    "PERSON": "People",
                    "ORG": "Organizations",
                    "GPE": "Locations",
                    "LOC": "Locations",
                    "DATE": "Dates",
                    "TIME": "Times",
                    "PRODUCT": "Products",
                    "WORK_OF_ART": "Works/Titles",
                    "CARDINAL": "Numbers",
                    "ORDINAL": "Ordinals",
                    "MONEY": "Financial Values",
                    "PERCENT": "Percentages",
                    "QUANTITY": "Quantities",
                    "LANGUAGE": "Languages"
                }
                
                # Create columns for entity display
                entity_cols = st.columns(2)
                col_idx = 0
                
                # Display entities by category
                for category in category_order:
                    if category in entity_categories:
                        with entity_cols[col_idx]:
                            st.markdown(f"**{friendly_names.get(category, category)}**")
                            for entity in sorted(set(entity_categories[category])):
                                st.markdown(f"""<div class="entity-box entity-{category}">{entity}</div>""", unsafe_allow_html=True)
                            col_idx = (col_idx + 1) % 2
                
                # Show remaining categories
                other_categories = [cat for cat in sorted(entity_categories.keys()) if cat not in category_order]
                if other_categories:
                    with entity_cols[col_idx]:
                        st.markdown("**Other Entities**")
                        for category in other_categories:
                            for entity in sorted(set(entity_categories[category])):
                                st.markdown(f"""<div class="entity-box entity-OTHER">{entity} <small>({category})</small></div>""", unsafe_allow_html=True)
                    
        else:
            st.error("Failed to analyze PDF. Check if Flask server is running.")
