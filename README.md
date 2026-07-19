# 🔍 Hallucination Catcher — RAG Evaluation & LLM Trust Dashboard

> An LLM-as-a-judge evaluation system that detects hallucinations in AI-generated responses, helping build more trustworthy AI applications.
>
> **🔗 Live Demo:** https://hallucination-catcher.onrender.com 
**📂 GitHub:**  https://github.com/Rev-ImranKhan/Hallucination-Catcher

## 🎯 Overview

As AI systems get deployed in production, a critical challenge is **trusting AI outputs** 
— language models can generate confident-sounding but factually incorrect responses 
(hallucinations). Hallucination Catcher addresses this by building a RAG (Retrieval-Augmented 
Generation) pipeline combined with an **LLM-as-a-judge evaluation framework** — automatically 
scoring AI responses for factual accuracy against source documents.

## 🧠 Why This Project Matters

This project demonstrates advanced **AI evaluation and reliability engineering** skills:
- **RAG pipeline design** — document retrieval grounding LLM responses in source truth
- **LLM-as-a-judge methodology** — using a second LLM to evaluate the first LLM's outputs
- **Hallucination detection** — quantifying factual accuracy and flagging unsupported claims
- **Evaluation dashboards** — visualizing trust metrics for AI system monitoring

## ✨ Key Features

| Feature | Description |
|---|---|
| 📄 Document-Grounded RAG | Retrieves relevant context from uploaded PDFs using ChromaDB vector search |
| 🤖 LLM-as-a-Judge Scoring | A second Gemini call evaluates response accuracy against retrieved context |
| 📊 Interactive Dashboard | Chart.js visualizations of hallucination scores and evaluation trends |
| 🔬 Response Comparison | Side-by-side view of AI answers vs. source document evidence |
| ⚠️ Hallucination Flagging | Automatically flags claims not supported by retrieved context |

## 🧠 AI/GenAI Architecture

| Component | Role |
|---|---|
| **ChromaDB** | Vector database for semantic document retrieval (RAG) |
| **Google Gemini** | Primary LLM for response generation + secondary judge LLM for evaluation |
| **LLM-as-a-Judge** | Evaluation methodology scoring factual grounding and accuracy |
| **Chart.js** | Frontend visualization of evaluation metrics and trends |

## 🛠️ Tech Stack

**Backend:** Python, Flask  
**AI:** Google Gemini, ChromaDB (vector search)  
**Frontend:** HTML, Chart.js  
**Methodology:** RAG + LLM-as-a-Judge evaluation

## 📂 Project Structure
hallucination-catcher/
├── app.py                 # Main Flask application
├── rag_core.py             # RAG pipeline: retrieval + generation
├── evaluator.py             # LLM-as-a-judge evaluation logic
├── data/                    # Source documents for RAG grounding
├── templates/               # Dashboard HTML templates
└── static/                  # CSS, JS, Chart.js visualizations

## 🚀 Getting Started

### 1. Install Dependencies
```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

**Note:** ChromaDB on Python 3.13 requires:
```bash
pip install chromadb --only-binary :all:
```

### 2. Configure Environment
Create a `.env` file in the root directory with:
GEMINI_API_KEY=your_gemini_key_here

### 3. Run the App
```bash
python app.py
```
Visit: http://localhost:5000

## 📌 Roadmap / Future Improvements

- [ ] Support for multiple LLM judges (ensemble evaluation) for higher reliability
- [ ] Automated regression testing for RAG pipeline changes
- [ ] Export evaluation reports as PDF for audit trails

## 👤 About the Developer

Built by **Imran Khan** — BCA final-year student specializing in **Applied AI Engineering** 
and **AI evaluation systems**, focused on building tools that make AI applications more 
trustworthy and production-ready.

📫 Open to **AI Solution Developer** / **Applied AI Engineer** roles.  
🔗 [GitHub](https://github.com/Rev-ImranKhan)
