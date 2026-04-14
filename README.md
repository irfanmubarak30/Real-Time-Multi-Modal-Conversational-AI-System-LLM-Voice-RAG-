# 🤖 Real-Time Multi-Modal Conversational AI System

A real-time conversational AI system integrating Large Language Models (LLMs), voice processing, and retrieval-augmented generation (RAG) with event-driven workflows and session-aware decision making.

---

## 🧠 System Overview

This system is designed as a **stateful, event-driven conversational pipeline** capable of handling multi-modal inputs (text + voice) and delivering context-aware responses in real time.

Key capabilities include:

* Session-aware conversation handling
* Multi-language interaction (English & Malayalam)
* Automated engagement workflows with follow-up logic
* Retrieval-Augmented Generation (RAG) for contextual responses

---

## ⚙️ Architecture

### 🔄 Core Pipeline

User Input → Webhook → Session Manager → Intent Detection →
RAG / Response Engine → Action Trigger → Follow-up System

---

### 🧩 Key Components

* **LLM Engine**
  OpenAI / Gemini for contextual response generation

* **Voice Processing Module**
  Whisper-based speech-to-text pipeline

* **RAG Pipeline**
  Context retrieval + response synthesis

* **Session Manager**
  Tracks user state and conversation history

* **Event & Follow-up Engine**
  Handles inactivity detection and automated engagement

* **Data Layer**
  Google Sheets for logging and analytics

---

## 🚀 Key Features

* Real-time conversational AI with low-latency responses
* Multi-modal interaction (text + voice input)
* Event-driven follow-up automation
* Stateful session management
* AI-driven intent detection and routing
* Scalable FastAPI-based backend



## 🛠 Tech Stack

* **Backend:** FastAPI, Python
* **AI/ML:** OpenAI, Gemini, Whisper, LangChain
* **Data:** Google Sheets, Pinecone (Vector DB)
* **APIs:** WhatsApp Cloud API / Twilio
* **Infra:** Async processing (Uvicorn)

---

## 🎯 Applications

* Conversational AI systems
* Real-time customer interaction pipelines
* Multi-modal AI assistants
* Event-driven automation systems

---

## 🧠 Key Concepts Demonstrated

* Real-time AI systems
* Event-driven architecture
* Multi-agent / modular pipelines
* Retrieval-Augmented Generation (RAG)
* Stateful distributed interaction systems

---

⭐ *Designed as a real-time AI system rather than a simple chatbot*
