"""
FastAPI Backend for SHL Assessment Recommendation System
Implements endpoints as specified in assignment PDF
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import sys
sys.path.append('..')
from recommender.recommend import Recommender

app = FastAPI(title="SHL Assessment Recommender API")

# Initialize recommender (loaded once on startup)
recommender = Recommender()

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

@app.get("/health", response_model=HealthResponse)
def health_check():
    """
    Health check endpoint to verify API is running.
    """
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
        # Validate top_k
        if request.top_k < 1 or request.top_k > 10:
            raise HTTPException(
                status_code=400, 
                detail="top_k must be between 1 and 10"
            )
        
        # Get recommendations
        results = recommender.recommend(request.query, top_k=request.top_k)
        
        # Load full assessment data
        import json
        with open('data/shl_assessments.json', 'r', encoding='utf-8') as f:
            all_assessments = json.load(f)
        
        url_to_assessment = {a['url']: a for a in all_assessments}
        
        # Format response with all required fields
        recommendations = []
        for r in results:
            assessment = url_to_assessment.get(r['url'], {})
            
            # Extract duration as integer (parse from string)
            duration_str = assessment.get('duration', '')
            duration_int = 0
            if duration_str:
                import re
                numbers = re.findall(r'\d+', duration_str)
                if numbers:
                    duration_int = int(numbers[-1] if '-' in duration_str else numbers[0])
            
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
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
