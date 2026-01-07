"""
Evaluation Script
- Computes Recall@10 on training data
- Generates test predictions CSV
"""

import pandas as pd
from recommender.recommend import Recommender

def normalize_url(url):
    return url.strip().lower().rstrip('/')

def compute_recall_at_k(predicted_urls, ground_truth_urls, k=10):
    """
    Compute Recall@K for a single query.
    
    Recall@K = (# relevant items in top K) / (total # relevant items)
    """

    predicted_set = {normalize_url(u) for u in predicted_urls[:k]}
    relevant_set = {normalize_url(u) for u in ground_truth_urls}

    
    if len(relevant_set) == 0:
        return 0.0
    
    hits = len(predicted_set & relevant_set)
    recall = hits / len(relevant_set)
    
    return recall

def evaluate_on_training_data():
    """Evaluate on training set to measure Recall@10"""
    print("=" * 60)
    print("EVALUATION ON TRAINING DATA")
    print("=" * 60)
    
    # Load training data
    df_train = pd.read_excel('Gen_AI Dataset.xlsx', sheet_name=0)
    
    # Debug: Check if queries are complete
    print(f"\nLoaded {len(df_train)} training examples")
    print(f"Sample query length: {len(df_train.iloc[0]['Query'])} chars")
    
    # Group by query to get all relevant URLs per query
    queries = df_train.groupby('Query')['Assessment_url'].apply(list).to_dict()
    
    print(f"Number of unique queries: {len(queries)}")
    
    recommender = Recommender()
    
    recalls = []
    
    for i, (query, ground_truth_urls) in enumerate(queries.items(), 1):
        print(f"\n[{i}/{len(queries)}] Query: {query[:80]}...")
        
        # Get recommendations
        results = recommender.recommend(query, top_k=10)
        predicted_urls = [r['url'] for r in results]
        
        # Compute recall
        recall = compute_recall_at_k(predicted_urls, ground_truth_urls, k=10)
        recalls.append(recall)
        
        print(f"  Ground truth: {len(ground_truth_urls)} assessments")
        print(f"  Recall@10: {recall:.3f}")
        
        # Show hits
        hits = set(predicted_urls[:10]) & set(ground_truth_urls)
        print(f"  Hits: {len(hits)}/{len(ground_truth_urls)}")
        
        # Show top 3 predictions with scores for debugging
        print(f"  Top 3 predictions:")
        for j, r in enumerate(results[:3], 1):
            is_hit = "" if r['url'] in ground_truth_urls else ""
            print(f"    {j}. {is_hit} {r['name'][:50]} (score: {r['score']:.3f}, train: {r['training_score']:.2f})")
    
    # Compute mean recall
    mean_recall = sum(recalls) / len(recalls)
    
    print("\n" + "=" * 60)
    print(f"MEAN RECALL@10: {mean_recall:.3f}")
    print("=" * 60)
    
    return mean_recall

def generate_test_predictions():
    """Generate predictions on test set and save to CSV"""
    print("\n" + "=" * 60)
    print("GENERATING TEST PREDICTIONS")
    print("=" * 60)
    
    # Load test data
    df_test = pd.read_excel('Gen_AI Dataset.xlsx', sheet_name=1)
    
    recommender = Recommender()
    
    predictions = []
    
    for i, row in df_test.iterrows():
        query = row['Query']
        print(f"\n[{i+1}/{len(df_test)}] Query: {query[:60]}...")
        
        # Get recommendations
        results = recommender.recommend(query, top_k=10)
        
        # Add to predictions
        for result in results:
            predictions.append({
                'Query': query,
                'Assessment_url': result['url']
            })
        
        print(f"  Generated {len(results)} recommendations")
    
    # Save to CSV
    df_pred = pd.DataFrame(predictions)
    df_pred.to_csv('test_predictions.csv', index=False)
    
    print(f"\n Saved {len(predictions)} predictions to test_predictions.csv")
    print("=" * 60)

if __name__ == "__main__":
    # Evaluate on training data
    mean_recall = evaluate_on_training_data()
    
    # Generate test predictions
    generate_test_predictions()
    
    print("\n Evaluation complete!")
    print(f" Mean Recall@10: {mean_recall:.3f}")