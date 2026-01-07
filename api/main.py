"""
FastAPI Backend for SHL Assessment Recommendation System
Implements endpoints as specified in assignment PDF
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import sys
import os
import json
import re

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from recommender.recommend import Recommender

app = FastAPI(title="SHL Assessment Recommender API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize recommender (loaded once on startup)
recommender = None

@app.on_event("startup")
async def startup_event():
    """Load recommender on startup"""
    global recommender
    try:
        recommender = Recommender()
        print("✓ Recommender loaded successfully")
    except Exception as e:
        print(f"✗ Failed to load recommender: {e}")
        import traceback
        traceback.print_exc()

class HealthResponse(BaseModel):
    status: str
    message: str

class RecommendRequest(BaseModel):
    query: str
    top_k: int = 10

class Assessment(BaseModel):
    url: str
    name: str
    adaptive_support: str
    description: str
    duration: int
    remote_support: str
    test_type: list[str]

class RecommendResponse(BaseModel):
    query: str
    recommendations: List[Assessment]
    count: int

@app.get("/", response_model=HealthResponse)
def root():
    """Root endpoint"""
    return {
        "status": "online",
        "message": "SHL Assessment Recommender API. Visit /docs for API documentation."
    }

@app.get("/health", response_model=HealthResponse)
def health_check():
    """
    Health check endpoint to verify API is running.
    """
    if recommender is None:
        return {
            "status": "unhealthy",
            "message": "Recommender not initialized. Check server logs."
        }
    
    return {
        "status": "healthy",
        "message": "SHL Assessment Recommender API is running"
    }

@app.post("/recommend", response_model=RecommendResponse)
def recommend(request: RecommendRequest):
    """
    Assessment recommendation endpoint.
    
    Accepts a job description or natural language query and returns
    relevant assessments (1-10) based on the input.
    
    Args:
        query: Job description or natural language query
        top_k: Number of recommendations (1-10, default 10)
    
    Returns:
        query: The input query
        recommendations: List of assessments with name and URL
        count: Number of recommendations returned
    """
    try:
        # Check if recommender is loaded
        if recommender is None:
            raise HTTPException(
                status_code=503,
                detail="Recommender not initialized. Please restart the server."
            )
        
        # Validate query
        if not request.query or not request.query.strip():
            raise HTTPException(
                status_code=400,
                detail="Query cannot be empty"
            )
        
        # Validate top_k
        if request.top_k < 1 or request.top_k > 10:
            raise HTTPException(
                status_code=400, 
                detail="top_k must be between 1 and 10"
            )
        
        # Get recommendations
        print(f"Processing query: {request.query[:50]}...")
        results = recommender.recommend(request.query, top_k=request.top_k)
        print(f"Found {len(results)} recommendations")
        
        # Load full assessment data
        data_file = os.path.join(parent_dir, 'data', 'shl_assessments.json')
        
        if not os.path.exists(data_file):
            raise HTTPException(
                status_code=500,
                detail=f"Assessment data file not found at {data_file}"
            )
        
        with open(data_file, 'r', encoding='utf-8') as f:
            all_assessments = json.load(f)
        
        url_to_assessment = {a['url']: a for a in all_assessments}
        
        # Format response with all required fields
        recommendations = []
        for r in results:
            assessment = url_to_assessment.get(r['url'], {})
            
            if not assessment:
                print(f"Warning: Assessment not found for URL: {r['url']}")
                continue
            
            # Extract duration as integer (parse from string)
            duration_str = assessment.get('duration', '')
            duration_int = 0
            if duration_str:
                numbers = re.findall(r'\d+', duration_str)
                if numbers:
                    # Take first number (e.g., "30-40 minutes" -> 30)
                    duration_int = int(numbers[0])
            
            recommendations.append(Assessment(
                url=r['url'],
                name=r['name'],
                adaptive_support=assessment.get('adaptive_support', 'No'),
                description=assessment.get('description', ''),
                duration=duration_int,
                remote_support=assessment.get('remote_support', 'No'),
                test_type=assessment.get('test_type', [])
            ))
        
        return RecommendResponse(
            query=request.query,
            recommendations=recommendations,
            count=len(recommendations)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in /recommend endpoint: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("Starting SHL Assessment Recommender API...")
    print(f"Parent directory: {parent_dir}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
