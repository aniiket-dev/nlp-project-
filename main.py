from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import base64

app = FastAPI()

# Enable CORS so the browser allows the HTML file to talk to the server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    user_query: str
    db_schema: str

@app.get("/fetch-schema")
async def fetch_schema():
    # Replace this string with your actual DB schema extraction logic
    schema_text = """
    TABLE students (id INT, name TEXT, gpa FLOAT, major TEXT);
    TABLE courses (id INT, title TEXT, credits INT);
    TABLE enrollments (student_id INT, course_id INT, grade TEXT);
    """
    return {"schema": schema_text}

@app.post("/generate-query")
async def generate_query(request: QueryRequest):
    try:
        # LOGIC: This is where you'd call your LLM or Local Model
        # For demonstration, we'll return a mock SQL query and data
        sql = f"SELECT * FROM students WHERE name LIKE '%{request.user_query}%' ORDER BY gpa DESC;"
        
        results = [
            {"id": 101, "name": "Aniket Diwakar", "gpa": 3.9, "major": "Computer Science"},
            {"id": 102, "name": "Nandini", "gpa": 4.0, "major": "Data Science"}
        ]
        
        summary = "I found students matching your criteria, sorted by their academic performance."
        
        return {
            "sql_query": sql,
            "results": results,
            "summary": summary,
            "csv_base64": "", # You can encode a CSV to base64 here for the export button
            "csv_filename": "analysis.csv"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)