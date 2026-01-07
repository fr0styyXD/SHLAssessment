"""
Embedding Builder - Creates FAISS index from SHL assessments
Uses OpenAI text-embedding-3-small for vectorization
"""

import json
import os
import numpy as np
import faiss
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def create_embedding_text(assessment):
    """
    Create structured text for embedding.
    Format: name + description + test types + job levels + duration
    """
    parts = [
        assessment['name'],
        assessment.get('description', ''),
        ' '.join(assessment.get('test_type', [])),
        ' '.join(assessment.get('job_levels', []))
    ]
    
    # Add duration if available - extract only numeric value
    duration = assessment.get('duration', '')
    if duration:
        import re
        # Extract all numbers from duration string
        numbers = re.findall(r'\d+', duration)
        if numbers:
            # Take the first number (or last for ranges like "20-30")
            duration_value = numbers[-1] if '-' in duration else numbers[0]
            # Add multiple variations for better matching
            parts.append(f"{duration_value} minutes")
            parts.append(f"Duration {duration_value} minutes")
            parts.append(f"Assessment length {duration_value} minutes")
    
    return ' '.join(filter(None, parts))

def get_embeddings(texts, batch_size=100):
    """Get embeddings from OpenAI in batches"""
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        print(f"Processing batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}")
        
        response = client.embeddings.create(
            input=batch,
            model="text-embedding-3-small"
        )
        
        embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(embeddings)
    
    return np.array(all_embeddings, dtype='float32')

def build_faiss_index(embeddings):
    """
    Build FAISS index with L2 distance on normalized vectors.
    Normalization converts L2 to cosine similarity.
    """
    # Normalize vectors for cosine similarity
    faiss.normalize_L2(embeddings)
    
    # Create flat L2 index
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)
    
    return index

def main():
    print("=" * 60)
    print("BUILDING FAISS INDEX")
    print("=" * 60)
    
    # Load assessments
    with open('data/shl_assessments.json', 'r', encoding='utf-8') as f:
        assessments = json.load(f)
    
    print(f"\nLoaded {len(assessments)} assessments")
    
    # Create embedding texts
    print("\nCreating embedding texts...")
    texts = [create_embedding_text(a) for a in assessments]
    
    # Get embeddings
    print("\nGenerating embeddings with OpenAI...")
    embeddings = get_embeddings(texts)
    
    print(f"Generated {len(embeddings)} embeddings of dimension {embeddings.shape[1]}")
    
    # Build FAISS index
    print("\nBuilding FAISS index...")
    index = build_faiss_index(embeddings)
    
    # Save index
    os.makedirs('data/faiss_index', exist_ok=True)
    faiss.write_index(index, 'data/faiss_index/index.faiss')
    
    # Save metadata
    metadata = {
        'assessment_urls': [a['url'] for a in assessments],
        'assessment_names': [a['name'] for a in assessments],
        'test_types': [a.get('test_type', []) for a in assessments],
        'job_levels': [a.get('job_levels', []) for a in assessments],
        'durations': [a.get('duration', '') for a in assessments]
    }
    
    with open('data/faiss_index/metadata.json', 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    print("\n Index saved to data/faiss_index/")
    print(f" Total vectors: {index.ntotal}")
    print("=" * 60)

if __name__ == "__main__":
    main()