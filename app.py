"""
Streamlit Frontend for SHL Assessment Recommendation System
Clean interface with API-based recommendations and detailed cards
"""

import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup

# Page config
st.set_page_config(
    page_title="SHL Assessment Recommender",
    layout="wide"
)

# Initialize session state
if 'query' not in st.session_state:
    st.session_state.query = ''

# Title
st.title("SHL Assessment Recommendation System")
st.markdown("Find the most relevant SHL assessments for your hiring needs")

# Sidebar - API Configuration
st.sidebar.header("Settings")

API_URL = st.sidebar.text_input(
    "API URL",
    value="shlassessment-production-4cb9.up.railway.app/health",
    help="URL of the FastAPI backend"
)

# Check API health
def check_api_health(api_url: str) -> bool:
    try:
        response = requests.get(f"{api_url}/health", timeout=5)
        return response.status_code == 200
    except:
        return False

if check_api_health(API_URL):
    st.sidebar.success("API is healthy")
else:
    st.sidebar.error("API is not reachable")
    st.sidebar.info("Make sure the FastAPI server is running:\n```\nuvicorn api.main:app --reload\n```")

# Sidebar - Number of results
top_k = st.sidebar.slider(
    "Number of results", 
    min_value=1, 
    max_value=10, 
    value=10,
    help="How many assessments to recommend"
)

# Sidebar - Example Queries
st.sidebar.markdown("---")
st.sidebar.header("Example Queries")

example_queries = [
    "I am hiring for Java developers who can also collaborate effectively with my business teams",
    "Looking to hire mid-level professionals who are proficient in Python, SQL and JavaScript",
    "Looking for a COO for my company in China"
]

for example in example_queries:
    if st.sidebar.button(example, key=f"ex_{hash(example)}"):
        st.session_state.query = example

# Main Input Section
st.header("Enter Your Query")

# Input type selection
input_type = st.radio(
    "Input type:",
    ["Text Query", "Job Description", "URL"],
    horizontal=True,
    help="Choose how you want to provide input"
)

query = st.session_state.query

if input_type == "Text Query":
    query = st.text_area(
        "Enter your query:",
        value=query,
        placeholder="Example: I am hiring for Java developers who can collaborate effectively...",
        height=100,
        key="text_query"
    )
elif input_type == "Job Description":
    query = st.text_area(
        "Paste full job description:",
        value=query,
        placeholder="Paste the complete job description here...",
        height=200,
        key="jd_query"
    )
else:  # URL
    url = st.text_input(
        "Enter job posting URL:",
        placeholder="https://example.com/job-posting",
        key="url_input"
    )
    
    if url:
        with st.spinner("Fetching content from URL..."):
            try:
                response = requests.get(url, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Remove scripts and styles
                for script in soup(["script", "style", "meta", "link"]):
                    script.decompose()
                
                # Extract text
                text_content = soup.get_text(separator=' ', strip=True)
                
                # Clean up whitespace
                text_content = ' '.join(text_content.split())
                
                # Use first 2000 characters
                query = text_content[:2000] if text_content else f"Job description from URL: {url}"
                
                st.success(f"Extracted {len(text_content)} characters from URL")
                
                # Show preview
                with st.expander("Preview extracted content"):
                    st.text(query[:500] + "..." if len(query) > 500 else query)
            except Exception as e:
                st.error(f"Failed to fetch URL: {e}")
                query = f"Job description from URL: {url}"

# Store query in session state
st.session_state.query = query

def get_recommendations_api(query: str, top_k: int, api_url: str):
    """Get recommendations from API with full details"""
    try:
        response = requests.post(
            f"{api_url}/recommend",
            json={"query": query, "top_k": top_k},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data.get("recommendations", [])
    except Exception as e:
        st.error(f"API Error: {e}")
        return []

# Search button
col1, col2, col3 = st.columns([2, 1, 2])
with col2:
    search_button = st.button("Get Recommendations", type="primary", use_container_width=True)

if search_button:
    if not query or not query.strip():
        st.warning("Please enter a query before submitting.")
    else:
        with st.spinner("Analyzing query and finding best matches..."):
            results = get_recommendations_api(query, top_k, API_URL)
        
        if results:
            st.success(f"Found {len(results)} relevant assessments")
            
            # Load full assessment data for detailed display
            st.markdown("### Recommended Assessments")
            
            try:
                import json
                with open('data/shl_assessments.json', 'r', encoding='utf-8') as f:
                    all_assessments = json.load(f)
                
                url_to_assessment = {a['url']: a for a in all_assessments}
                
                # Display each recommendation as an expandable card
                for idx, result in enumerate(results, 1):
                    # result now contains all fields from API
                    # But we still load from local data for completeness
                    assessment = url_to_assessment.get(result['url'], result)
                    
                    # Main card container
                    with st.container():
                        # Card header with rank and name
                        col_rank, col_name, col_score = st.columns([1, 8, 2])
                        
                        with col_rank:
                            st.markdown(f"### #{idx}")
                        
                        with col_name:
                            st.markdown(f"### {result['name']}")
                        
                        with col_score:
                            # Get score from local recommender for display
                            try:
                                from recommender.recommend import Recommender
                                if 'recommender_cached' not in st.session_state:
                                    st.session_state.recommender_cached = Recommender()
                                
                                # Get single result to check score
                                local_results = st.session_state.recommender_cached.recommend(query, top_k=20)
                                score = None
                                for lr in local_results:
                                    if lr['url'] == result['url']:
                                        score = lr['score']
                                        break
                                
                                if score is not None:
                                    st.metric("Score", f"{score:.3f}")
                            except:
                                pass
                        
                        # Quick info row
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            remote = assessment.get('remote_support', 'Unknown')
                            st.markdown(f"**Remote:** {remote}")
                        
                        with col2:
                            adaptive = assessment.get('adaptive_support', 'Unknown')
                            st.markdown(f"**Adaptive:** {adaptive}")
                        
                        with col3:
                            test_types = assessment.get('test_type', [])
                            if test_types:
                                st.markdown(f"**Types:** {len(test_types)}")
                        # Duration row
                        duration = assessment.get('duration', '')
                        if duration:
                            st.markdown(f"**Duration:** {duration}")
                        
                        # Expandable details
                        with st.expander("View Full Details"):
                            # URL
                            st.markdown("#### Assessment Link")
                            st.markdown(f"[Open Assessment Page]({result['url']})")
                            st.code(result['url'], language=None)
                            
                            # Test Types
                            if test_types:
                                st.markdown("#### Test Types")
                                for tt in test_types:
                                    st.markdown(f"- {tt}")
                            
                            # Job Levels
                            job_levels = assessment.get('job_levels', [])
                            if job_levels:
                                st.markdown("#### Suitable Job Levels")
                                for jl in job_levels:
                                    st.markdown(f"- {jl}")
                            # Duration
                            if duration:
                                st.markdown("#### Assessment Duration")
                                st.markdown(f"{duration}")
                            
                            # Description
                            description = assessment.get('description', '')
                            if description:
                                st.markdown("#### Description")
                                st.markdown(description)
                            else:
                                st.info("No description available")
                        
                        st.divider()
                
                # Download button at the end
                st.markdown("---")
                df_export = pd.DataFrame([
                    {
                        'Rank': i + 1,
                        'Assessment Name': r['name'],
                        'URL': r['url']
                    }
                    for i, r in enumerate(results)
                ])
                
                csv = df_export.to_csv(index=False)
                st.download_button(
                    label="Download All Results as CSV",
                    data=csv,
                    file_name="shl_recommendations.csv",
                    mime="text/csv",
                    use_container_width=False
                )
            
            except Exception as e:
                st.error(f"Could not load detailed assessment data: {e}")
                # Fallback to simple view
                for idx, result in enumerate(results, 1):
                    st.markdown(f"**#{idx}: [{result['name']}]({result['url']})**")
        
        else:
            st.error("No recommendations found. Please try a different query.")

# Sidebar - About Section
st.sidebar.markdown("---")
st.sidebar.markdown("### About")
st.sidebar.markdown("""
This system recommends SHL assessments based on:
- Job descriptions
- Skill requirements  
- Role requirements
- Behavioral needs
- Technical competencies
""")

# Footer

st.markdown("---")
