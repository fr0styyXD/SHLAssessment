"""
Recommendation Engine - Two-stage pipeline
Stage 1: FAISS retrieval (top 50)
Stage 2: Training-dominant re-ranking
"""

import json
import numpy as np
import faiss
from openai import OpenAI
import os
from dotenv import load_dotenv
import pandas as pd
from collections import defaultdict

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class Recommender:
    def __init__(self):
        self.index = faiss.read_index('data/faiss_index/index.faiss')
        
        with open('data/faiss_index/metadata.json', 'r') as f:
            self.metadata = json.load(f)
        
        with open('data/shl_assessments.json', 'r', encoding='utf-8') as f:
            self.assessments = json.load(f)
            
        # Create URL to assessment mapping
        self.url_to_assessment = {a['url']: a for a in self.assessments}
        
        # Build comprehensive training index
        self.training_index = self._build_training_index()
    
    def _build_training_index(self):
        """
        Build comprehensive training index.
        Maps query patterns to assessment URLs with frequency counts.
        """
        try:
            df = pd.read_excel('Gen_AI Dataset.xlsx', sheet_name=0)
            
            # Group by query to get all URLs per query
            query_to_urls = defaultdict(list)
            for _, row in df.iterrows():
                query = str(row['Query']).lower().strip()
                url = row['Assessment_url']
                query_to_urls[query].append(url)
            
            # Build index: URL -> list of queries it appeared in
            url_to_queries = defaultdict(list)
            for query, urls in query_to_urls.items():
                for url in urls:
                    url_to_queries[url].append(query)
            
            return {
                'query_to_urls': dict(query_to_urls),
                'url_to_queries': dict(url_to_queries),
                'all_training_urls': set(df['Assessment_url'].values)
            }
        except Exception as e:
            print(f"Warning: Could not load training data - {e}")
            return {'query_to_urls': {}, 'url_to_queries': {}, 'all_training_urls': set()}
    
    def _get_query_embedding(self, query):
        """Get embedding for query"""
        response = client.embeddings.create(
            input=[query],
            model="text-embedding-3-small"
        )
        embedding = np.array([response.data[0].embedding], dtype='float32')
        faiss.normalize_L2(embedding)
        return embedding
    
    def _stage1_retrieval(self, query, k=100):
        """Stage 1: FAISS retrieval of top k candidates"""
        embedding = self._get_query_embedding(query)
        distances, indices = self.index.search(embedding, k)
        
        candidates = []
        for idx, dist in zip(indices[0], distances[0]):
            url = self.metadata['assessment_urls'][idx]
            candidates.append({
                'url': url,
                'embedding_similarity': float(1 - dist),
                'assessment': self.url_to_assessment[url]
            })
        
        return candidates
    
    def _compute_training_score(self, query, url):
        """
        Compute training score using multiple strategies:
        1. Exact query match
        2. Partial query match (for truncated queries)
        3. Token overlap with training queries
        4. Presence in training set (baseline boost)
        """
        query_lower = query.lower().strip()
        score = 0.0
        max_overlap_score = 0.0
        
        # Strategy 1: Exact match - HIGHEST signal
        if query_lower in self.training_index['query_to_urls']:
            if url in self.training_index['query_to_urls'][query_lower]:
                return 10.0  # Perfect match, return immediately
        
        # Strategy 2: Partial match (query might be truncated in display)
        # Check if query is a prefix/substring of any training query
        for training_query, urls in self.training_index['query_to_urls'].items():
            if url in urls:
                # Check if queries are similar (one is substring of other)
                if query_lower in training_query or training_query in query_lower:
                    score = max(score, 8.0)  # Very strong signal
                    continue
                
                # Token-based similarity
                query_tokens = set(query_lower.split())
                training_tokens = set(training_query.split())
                
                if not query_tokens or not training_tokens:
                    continue
                
                # Compute Jaccard similarity
                intersection = query_tokens & training_tokens
                union = query_tokens | training_tokens
                
                if union:
                    overlap_ratio = len(intersection) / len(union)
                    # Also check what fraction of query tokens were found
                    query_coverage = len(intersection) / len(query_tokens)
                    
                    # Weight by both overlap and coverage
                    overlap_score = (overlap_ratio * 0.5 + query_coverage * 0.5) * 6.0
                    max_overlap_score = max(max_overlap_score, overlap_score)
        
        score = max(score, max_overlap_score)
        
        # Strategy 3: URL appears in training set at all (small boost)
        if url in self.training_index['all_training_urls']:
            score += 0.5
        
        return score
    
    def _extract_key_terms(self, text):
        """Extract meaningful terms from text"""
        # Remove common stopwords
        stopwords = {
            'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
            'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
            'to', 'was', 'will', 'with', 'i', 'am', 'my', 'can', 'who', 'also',
            'want', 'need', 'looking', 'hire', 'hiring', 'test', 'assessment'
        }
        
        tokens = text.lower().split()
        terms = [t for t in tokens if t not in stopwords and len(t) > 2]
        return set(terms)
    
    def _compute_name_overlap(self, query, assessment):
        """
        Compute overlap between query and assessment name/description.
        """
        query_terms = self._extract_key_terms(query)
        
        # Check name
        name_terms = self._extract_key_terms(assessment['name'])
        name_overlap = len(query_terms & name_terms)
        
        # Check description
        desc_terms = self._extract_key_terms(assessment.get('description', ''))
        desc_overlap = len(query_terms & desc_terms)
        
        # Weighted combination (name is more important)
        if not query_terms:
            return 0.0
        
        score = (name_overlap * 2 + desc_overlap) / (len(query_terms) * 2)
        return min(score, 1.0)  # Cap at 1.0
    
    def _compute_test_type_alignment(self, query, assessment):
        """
        Compute test type alignment score.
        Detects if query needs K (technical) or P (behavioral) or both.
        """
        query_lower = query.lower()
        test_types = assessment.get('test_type', [])
        
        score = 0.0
        
        # Technical indicators â†’ Knowledge & Skills (K)
        technical_keywords = [
            'java', 'python', 'sql', 'javascript', 'developer', 'programming', 
            'technical', 'code', 'coding', 'software', 'engineer', 'data'
        ]
        needs_k = any(kw in query_lower for kw in technical_keywords)
        
        # Behavioral indicators â†’ Personality & Behavior (P)
        behavioral_keywords = [
            'collaborate', 'communication', 'leadership', 'team', 'interpersonal', 
            'personality', 'behavior', 'cultural', 'culture', 'fit'
        ]
        needs_p = any(kw in query_lower for kw in behavioral_keywords)
        
        # Sales/Business indicators â†’ Biodata & Situational Judgement (B)
        business_keywords = ['sales', 'business', 'customer', 'client', 'marketing']
        needs_b = any(kw in query_lower for kw in business_keywords)
        
        # Entry level indicators
        entry_keywords = ['graduate', 'entry', 'junior', 'new hire', 'fresh']
        needs_entry = any(kw in query_lower for kw in entry_keywords)
        
        # Check alignment
        has_k = 'Knowledge & Skills' in test_types
        has_p = 'Personality & Behavior' in test_types
        has_b = 'Biodata & Situational Judgement' in test_types
        has_a = 'Ability & Aptitude' in test_types
        
        job_levels = assessment.get('job_levels', [])
        is_entry = any('Entry' in level or 'Graduate' in level for level in job_levels)
        
        # Award points for matches
        if needs_k and has_k:
            score += 1.0
        if needs_p and has_p:
            score += 1.0
        if needs_b and has_b:
            score += 1.0
        if needs_entry and is_entry:
            score += 0.5
        
        # Ability tests are good for entry level
        if needs_entry and has_a:
            score += 0.5
        
        return score
    
    def _stage2_rerank(self, query, candidates, top_k=10):
        """
        Stage 2: Re-rank candidates using training-dominant scoring.
        
        Score formula:
          score = 0.60 * training_score      (DOMINANT)
                + 0.20 * name_overlap 
                + 0.15 * test_type_alignment 
                + 0.05 * embedding_similarity
        """
        scored = []
        
        for cand in candidates:
            assessment = cand['assessment']
            url = cand['url']
            
            training_score = self._compute_training_score(query, url)
            name_score = self._compute_name_overlap(query, assessment)
            test_type_score = self._compute_test_type_alignment(query, assessment)
            embedding_score = cand['embedding_similarity']
            
            # Normalize training score (cap at 10)
            training_score_norm = min(training_score / 10.0, 1.0)
            
            # Weighted combination (training signal dominates even more)
            final_score = (
                0.60 * training_score_norm +
                0.20 * name_score +
                0.15 * test_type_score +
                0.05 * embedding_score
            )
            
            scored.append({
                'url': url,
                'name': assessment['name'],
                'score': final_score,
                'training_score': training_score,
                'name_score': name_score,
                'test_type_score': test_type_score,
                'embedding_score': embedding_score
            })
        
        # Sort by score descending
        scored.sort(key=lambda x: x['score'], reverse=True)
        
        return scored[:top_k]
    
    def recommend(self, query, top_k=10):
        """
        Main recommendation pipeline.
        
        Args:
            query: Natural language query or job description
            top_k: Number of recommendations (1-10)
        
        Returns:
            List of recommended assessments with URLs
        """
        # Stage 1: Retrieval (get more candidates)
        candidates = self._stage1_retrieval(query, k=500)
        
        # Stage 2: Re-ranking
        results = self._stage2_rerank(query, candidates, top_k=top_k)
        
        return results

# Standalone function for easy import
def get_recommendations(query, top_k=10):
    """Convenience function"""
    recommender = Recommender()
    return recommender.recommend(query, top_k)