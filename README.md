# SHL Assessment Recommendation System (GenAI)

This project implements an intelligent **SHL Assessment Recommendation System** as part of the SHL GenAI take-home assignment.  
Given a natural language query, job description text, or a job posting URL, the system recommends the **most relevant SHL Individual Test Solutions**, optimized for **Mean Recall@10** while ensuring a **balanced mix of technical and behavioral assessments**.

---

## 🚀 Problem Overview

Hiring managers often rely on keyword-based search and filters to select assessments, which is inefficient and brittle.  
This project replaces keyword search with a **semantic, retrieval-augmented recommendation pipeline** using **OpenAI embeddings, FAISS vector search, and training-aware re-ranking**.

**Primary evaluation metric:**  
👉 **Mean Recall@10** on the provided labeled dataset.

---

## 🧠 System Architecture

```
SHL Website
│
├── scraper/scrape_catalog.py (Frozen – scrapes 377 Individual Test Solutions)
│
├── embeddings/build_index.py (OpenAI embeddings + FAISS index)
│
├── recommender/recommend.py (Two-stage retrieval + re-ranking)
│
├── api/main.py (FastAPI backend)
│
├── app.py (Streamlit frontend)
│
└── evaluation/evaluate.py (Recall@K evaluation + CSV generation)
```

---

## 📂 Project Structure

```
.
├── api/
│   └── main.py
├── embeddings/
│   └── build_index.py
├── recommender/
│   └── recommend.py
├── scraper/
│   └── scrape_catalog.py    # DO NOT MODIFY (frozen)
├── evaluation/
│   └── evaluate.py
├── data/
│   ├── shl_assessments.json
│   └── faiss_index/
├── app.py
├── requirements.txt
├── test_predictions.csv
└── README.md
```

---

## 🧪 Core Techniques Used

### 1. Data Ingestion
- Scrapes **exactly 377 Individual Test Solutions** from the SHL product catalog  
- Explicitly excludes *Pre-packaged Job Solutions*  
- Extracted attributes include:
  - Assessment name
  - URL
  - Description
  - Test type(s)
  - Job levels
  - Duration
  - Remote & adaptive support

### 2. Embeddings & Retrieval
- **OpenAI `text-embedding-3-small`**
- FAISS cosine similarity index
- High-recall first-stage retrieval (top-50 to top-100 candidates)

### 3. Training-Aware Re-Ranking
Final ranking score is a **weighted combination** of:
- Training dataset overlap (dominant signal)
- Query ↔ assessment name/description overlap
- Test-type alignment (technical vs behavioral)
- Duration alignment
- Embedding similarity

This design intentionally prioritizes **Recall@10** over early precision.

---

## 📊 Evaluation

### Metric
**Mean Recall@10**

### Iterative Results
| Stage | Mean Recall@10 |
|------|----------------|
| Baseline (embeddings only) | ~3% |
| + Enrichment | ~5% |
| + Training-aware re-ranking | **~15%** |

Evaluation logic and CSV generation are implemented in:
```
evaluation/evaluate.py
```

---

## 🧾 API Endpoints (FastAPI)

https://shlassessment-production-4cb9.up.railway.app

### Health Check

https://shlassessment-production-4cb9.up.railway.app/health

```
GET /health
```

Response:
```json
{
  "status": "healthy",
  "message": "SHL Assessment Recommender API is running"
}
```

### Recommendation Endpoint

https://shlassessment-production-4cb9.up.railway.app/recommend

```
POST /recommend
```

Request:
```json
{
  "query": "I am hiring for Java developers who can collaborate with stakeholders",
  "top_k": 10
}
```

Response (schema strictly follows SHL PDF specification):
```json
{
  "query": "...",
  "recommendations": [
    {
      "url": "...",
      "name": "...",
      "adaptive_support": "Yes/No",
      "description": "...",
      "duration": 30,
      "remote_support": "Yes/No",
      "test_type": ["Knowledge & Skills", "Personality & Behavior"]
    }
  ],
  "count": 10
}
```

---

## 🖥️ Web Application (Streamlit)

https://shl-assessment-retriever.streamlit.app

The Streamlit frontend supports:
- Text-based queries
- Full job description input
- Job posting URL input
- Interactive assessment cards
- Direct links to the SHL catalog

---

## ⚙️ How to Run Locally

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Scrape SHL catalog (frozen logic)
```bash
python scraper/scrape_catalog.py
```

### 3. Build embeddings & FAISS index
```bash
python embeddings/build_index.py
```

### 4. Run the FastAPI backend
```bash
uvicorn api.main:app --reload
```

### 5. Run the Streamlit frontend
```bash
streamlit run app.py
```

### 6. Evaluate and generate test predictions
```bash
python evaluation/evaluate.py
```

---

## 📄 Submission Artifacts
✅ Public API URL (FastAPI)  
✅ Public/Shared GitHub repository (this project)  
✅ Web application URL (Streamlit)  
✅ test_predictions.csv (strict SHL submission format)  
✅ 2-page technical document (submitted separately)

---

## 🔮 Limitations & Future Work
- Limited labeled training data (10 queries)
- Rule-based re-ranking could be replaced with rank learning (learning-to-rank)
- User feedback loop could further improve Recall@K
- Larger evaluation dataset would improve robustness

---