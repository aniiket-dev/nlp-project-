import os
import torch

class Config:
    # Use a model specifically trained for SQL for better accuracy
    # Phi-3 is good for general text but SqlCoder is specialized for SQL
    MODEL_NAME = os.environ.get("MODEL_NAME", "defog/sqlcoder-7b-2")
    
    # If you have limited VRAM, use Phi-3 (smaller but less accurate)
    # MODEL_NAME = os.environ.get("MODEL_NAME", "microsoft/Phi-3-mini-4k-instruct")
    
    USE_4BIT = os.environ.get("USE_4BIT", "true").lower() == "true"
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    
    DATABASE_URI = os.path.join(os.path.dirname(__file__), "database.db")
    
    # More conservative settings for better accuracy
    MAX_NEW_TOKENS = 512
    TEMPERATURE = 0.05  # Very low for deterministic outputs
    DO_SAMPLE = False
    
    # Retry settings - more retries for better results
    MAX_RETRIES = 4
    
    CACHE_SIZE = 200
    
    EXAMPLE_QUERIES = [
        "Show all students",
        "Top 5 students by marks",
        "Students above 80 marks",
        "Average marks per branch",
        "Count students branch wise",
        "Highest marks",
        "Lowest marks",
        "Alphabetical student list",
        "Students from Mumbai city",
        "Newest students by registration date"
    ]