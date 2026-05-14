import re
import time
import logging
import sqlite3
from collections import OrderedDict
from typing import Optional, List, Tuple

import sqlparse
from config import Config
from model_loader import get_pipeline
from schema_loader import get_schema
from query_validator import is_dangerous_query

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Enhanced semantic patterns with stronger rules
SEMANTIC_RULES = {
    "highest": {"direction": "DESC", "aggregate": "MAX"},
    "lowest": {"direction": "ASC", "aggregate": "MIN"},
    "top": {"direction": "DESC", "limit": True},
    "bottom": {"direction": "ASC", "limit": True},
    "alphabetical": {"direction": "ASC", "column_type": "text"},
    "reverse alphabetical": {"direction": "DESC", "column_type": "text"},
    "newest": {"direction": "DESC", "column_type": "date"},
    "oldest": {"direction": "ASC", "column_type": "date"},
    "maximum": {"direction": "DESC", "aggregate": "MAX"},
    "minimum": {"direction": "ASC", "aggregate": "MIN"},
    "most": {"direction": "DESC"},
    "least": {"direction": "ASC"},
    "best": {"direction": "DESC"},
    "worst": {"direction": "ASC"},
}

class NLToSQLTranslator:
    def __init__(self):
        self.pipe = None
        self.schema = ""
        self.table_info = {}  # Store parsed table info
        self.cache = OrderedDict()
        self._init_model()
    
    def _init_model(self):
        """Lazy load the model pipeline."""
        if self.pipe is None:
            self.pipe = get_pipeline()
        self.schema = get_schema()
        self._parse_schema()
    
    def _parse_schema(self):
        """Parse schema into structured format for better prompting."""
        self.table_info = {}
        lines = self.schema.split('\n')
        current_table = None
        
        for line in lines:
            if line.startswith('Table:'):
                current_table = line.replace('Table:', '').strip()
                self.table_info[current_table] = {'columns': [], 'types': {}}
            elif current_table and line.strip():
                # Parse column definitions
                parts = line.strip().split()
                if parts:
                    col_name = parts[0]
                    col_type = parts[1] if len(parts) > 1 else 'TEXT'
                    self.table_info[current_table]['columns'].append(col_name)
                    self.table_info[current_table]['types'][col_name] = col_type
    
    def refresh_schema(self):
        """Reload schema from database."""
        self.schema = get_schema()
        self._parse_schema()
    
    def _detect_semantic_intent(self, nl_query: str) -> dict:
        """
        Enhanced semantic intent detection.
        Returns dict with ordering, aggregation, and limit requirements.
        """
        lower_query = nl_query.lower()
        intent = {
            'direction': None,
            'aggregate': None,
            'limit': None,
            'order_by_col': None,
            'group_by': None
        }
        
        # Detect ordering intent
        for phrase, rules in SEMANTIC_RULES.items():
            if phrase in lower_query:
                intent['direction'] = rules['direction']
                if 'aggregate' in rules:
                    intent['aggregate'] = rules['aggregate']
                if 'limit' in rules:
                    intent['limit'] = 5  # Default limit for "top/bottom"
                break
        
        # Detect aggregation needs
        if any(word in lower_query for word in ['average', 'avg', 'mean']):
            intent['aggregate'] = 'AVG'
        if any(word in lower_query for word in ['total', 'sum']):
            intent['aggregate'] = 'SUM'
        if any(word in lower_query for word in ['count', 'number of']):
            intent['aggregate'] = 'COUNT'
        if any(word in lower_query for word in ['maximum', 'highest', 'max']):
            intent['aggregate'] = 'MAX'
        if any(word in lower_query for word in ['minimum', 'lowest', 'min']):
            intent['aggregate'] = 'MIN'
        
        # Detect group by needs
        if any(word in lower_query for word in ['per', 'each', 'by', 'wise']):
            intent['group_by'] = True
        
        # Detect limit
        limit_match = re.search(r'(?:top|bottom|first|last)\s*(\d+)', lower_query)
        if limit_match:
            intent['limit'] = int(limit_match.group(1))
        
        return intent
    
    def _find_matching_column(self, table_name: str, keywords: List[str]) -> Optional[str]:
        """Find column that matches keywords in a given table."""
        if table_name not in self.table_info:
            return None
        
        columns = self.table_info[table_name]['columns']
        for keyword in keywords:
            for col in columns:
                if keyword.lower() in col.lower():
                    return col
        return None
    
    def _semantic_check(self, sql: str, nl_query: str) -> Tuple[bool, str, dict]:
        """
        Comprehensive semantic validation.
        Returns (is_valid, error_message, correction_hints).
        """
        intent = self._detect_semantic_intent(nl_query)
        hints = {}
        
        # Check ORDER BY direction
        if intent['direction']:
            order_match = re.search(r'ORDER\s+BY\s+(\w+)\s*(ASC|DESC)?', sql, re.IGNORECASE)
            if order_match:
                sql_direction = order_match.group(2).upper() if order_match.group(2) else 'ASC'
                if sql_direction != intent['direction']:
                    hints['wrong_direction'] = f"Should use {intent['direction']} not {sql_direction}"
                    return False, f"Semantic error: Expected {intent['direction']} ordering", hints
            else:
                # ORDER BY missing but needed
                hints['missing_order'] = f"Add ORDER BY with {intent['direction']}"
                return False, "Semantic error: Missing required ORDER BY clause", hints
        
        # Check LIMIT
        if intent['limit'] and 'LIMIT' not in sql.upper():
            hints['missing_limit'] = f"Add LIMIT {intent['limit']}"
            return False, f"Semantic error: Missing LIMIT {intent['limit']}", hints
        
        # Check GROUP BY
        if intent['group_by'] and 'GROUP BY' not in sql.upper():
            hints['missing_groupby'] = "Add GROUP BY clause"
            return False, "Semantic error: Missing GROUP BY clause", hints
        
        return True, "", hints
    
    def _build_enhanced_prompt(self, nl_query: str, error_hint: Optional[str] = None) -> str:
        """
        Build an extremely detailed, structured prompt for better accuracy.
        """
        schema = self.schema
        
        # Analyze query for better prompting
        intent = self._detect_semantic_intent(nl_query)
        lower_query = nl_query.lower()
        
        prompt = f"""You are an expert SQL query generator. Convert natural language to valid SQLite SQL.

### Database Schema
{schema}

### Task
Generate a precise SQLite SELECT query for: "{nl_query}"

### CRITICAL RULES (Follow Exactly)
1. ONLY generate SELECT queries - no INSERT, UPDATE, DELETE, DROP, ALTER
2. Use EXACT table and column names from the schema above
3. Return ONLY the SQL query - no explanations, no markdown formatting
4. Always use proper SQL syntax with correct capitalization

### ORDERING RULES (Very Important)
- "highest", "top", "most", "best", "maximum" → ORDER BY [column] DESC
- "lowest", "bottom", "least", "worst", "minimum" → ORDER BY [column] ASC
- "alphabetical", "a-z", "ascending order" → ORDER BY [column] ASC
- "reverse alphabetical", "z-a", "descending order" → ORDER BY [column] DESC
- "newest", "latest", "recent", "most recent" → ORDER BY [date_column] DESC
- "oldest", "earliest", "first" → ORDER BY [date_column] ASC

### AGGREGATION RULES
- "average", "avg", "mean" → Use AVG(column)
- "total", "sum" → Use SUM(column)
- "count", "number of", "how many" → Use COUNT(*)
- "highest marks", "maximum marks" → Use MAX(marks) with GROUP BY if needed
- "lowest marks", "minimum marks" → Use MIN(marks)

### GROUPING RULES
- "per", "each", "by", "wise" → Always use GROUP BY
- "branch wise", "per branch" → GROUP BY branch
- "count students branch wise" → SELECT branch, COUNT(*) FROM students GROUP BY branch

### LIMIT RULES
- "top 5", "first 5", "best 5" → Add LIMIT 5 at the end
- "top 10", "first 10" → Add LIMIT 10
- Always put LIMIT after ORDER BY

### FILTERING RULES
- "above", "greater than", "more than" → Use > 
- "below", "less than", "under" → Use <
- "equal to", "exactly" → Use =
- "from [city]" → Use WHERE city = '[city]'
- "in [branch]" → Use WHERE branch = '[branch]'

### CORRECT EXAMPLES
Query: "Show all students"
SQL: SELECT * FROM students

Query: "Top 5 students by marks"
SQL: SELECT * FROM students ORDER BY marks DESC LIMIT 5

Query: "Students above 80 marks"
SQL: SELECT * FROM students WHERE marks > 80

Query: "Average marks per branch"
SQL: SELECT branch, AVG(marks) FROM students GROUP BY branch

Query: "Count students branch wise"
SQL: SELECT branch, COUNT(*) FROM students GROUP BY branch

Query: "Highest marks"
SQL: SELECT * FROM students ORDER BY marks DESC LIMIT 1

Query: "Lowest marks"
SQL: SELECT * FROM students ORDER BY marks ASC LIMIT 1

Query: "Alphabetical student list"
SQL: SELECT * FROM students ORDER BY name ASC

Query: "Students from Mumbai city"
SQL: SELECT * FROM students WHERE city = 'Mumbai'

Query: "Newest students"
SQL: SELECT * FROM students ORDER BY registration_date DESC
"""
        
        if error_hint:
            prompt += f"\n### PREVIOUS ERROR TO FIX\n{error_hint}\nPlease correct the SQL to fix this error."
        
        prompt += f"\n### Now generate SQL for this question:\n{nl_query}\n\n### CORRECT SQL:\n"
        return prompt
    
    def _extract_sql(self, generated_text: str, prompt: str) -> str:
        """Extract clean SQL from model output."""
        # Try to find SQL after the prompt
        if "### CORRECT SQL:" in generated_text:
            sql = generated_text.split("### CORRECT SQL:")[-1].strip()
        else:
            # Remove the prompt part
            sql = generated_text[len(prompt):].strip()
        
        # Clean up common issues
        sql = sql.strip()
        sql = re.sub(r'```sql|```', '', sql)  # Remove markdown
        sql = sql.rstrip(';')  # Remove trailing semicolon
        sql = sql.strip()
        
        # Ensure it starts with SELECT
        if not sql.upper().startswith('SELECT'):
            # Try to find SELECT in the text
            select_match = re.search(r'SELECT.*', sql, re.IGNORECASE | re.DOTALL)
            if select_match:
                sql = select_match.group(0)
            else:
                sql = "SELECT " + sql
        
        # Remove any trailing explanations
        sql = re.split(r'\n\n|\n###|\n---', sql)[0].strip()
        
        return sql
    
    def generate_sql(self, nl_query: str) -> dict:
        """
        Main method with enhanced prompting and validation.
        """
        if self.pipe is None:
            self._init_model()
        
        # Check cache
        cache_key = nl_query.strip().lower()
        if cache_key in self.cache:
            logger.info("Returning cached result")
            return self.cache[cache_key]
        
        result = {
            "sql": "", 
            "confidence": 0.0, 
            "execution_time": 0, 
            "retries": 0, 
            "error": None
        }
        start_time = time.time()
        
        error_hint = None
        for attempt in range(Config.MAX_RETRIES + 1):
            try:
                # Build enhanced prompt
                prompt = self._build_enhanced_prompt(nl_query, error_hint)
                
                # Generate with better parameters
                outputs = self.pipe(
                    prompt,
                    max_new_tokens=Config.MAX_NEW_TOKENS,
                    temperature=0.05 if attempt == 0 else 0.1,  # Even lower temperature for precision
                    do_sample=False,
                    pad_token_id=self.pipe.tokenizer.eos_token_id,
                    eos_token_id=self.pipe.tokenizer.eos_token_id,
                    num_return_sequences=1,
                )
                
                generated_text = outputs[0]["generated_text"]
                full_sql = self._extract_sql(generated_text, prompt)
                
                # 1. Safety check
                if is_dangerous_query(full_sql):
                    result["error"] = "Dangerous query blocked. Only SELECT statements allowed."
                    break
                
                # 2. Basic syntax validation
                try:
                    sqlparse.parse(full_sql)
                except:
                    error_hint = "Invalid SQL syntax. Generate a clean, valid SQLite SELECT statement."
                    result["retries"] = attempt + 1
                    continue
                
                # 3. Semantic validation
                valid, msg, hints = self._semantic_check(full_sql, nl_query)
                if not valid:
                    error_hint = msg
                    if hints:
                        error_hint += " Fix: " + ", ".join(hints.values())
                    result["retries"] = attempt + 1
                    if attempt < Config.MAX_RETRIES:
                        continue
                
                # 4. Quick execution check
                conn = sqlite3.connect(Config.DATABASE_URI)
                try:
                    conn.execute(full_sql)
                    result["sql"] = full_sql
                    result["confidence"] = min(0.95, 0.7 + (attempt * 0.1))
                    result["retries"] = attempt
                    break
                except Exception as exec_err:
                    error_hint = f"SQL execution error: {str(exec_err)}. Fix the query."
                    result["retries"] = attempt + 1
                    if attempt < Config.MAX_RETRIES:
                        continue
                    else:
                        result["error"] = f"Failed after {Config.MAX_RETRIES} retries: {str(exec_err)}"
                finally:
                    conn.close()
                
            except Exception as e:
                logger.exception("Generation error")
                error_hint = f"Internal error: {str(e)}"
                result["retries"] = attempt + 1
                if attempt == Config.MAX_RETRIES:
                    result["error"] = f"Failed after {Config.MAX_RETRIES} retries: {str(e)}"
        
        result["execution_time"] = round(time.time() - start_time, 3)
        
        # Cache successful results
        if result["sql"] and not result["error"]:
            # Limit cache size
            if len(self.cache) >= Config.CACHE_SIZE:
                self.cache.popitem(last=False)
            self.cache[cache_key] = result
        
        return result
    
    def execute_query(self, sql: str) -> dict:
        """Safely execute a SELECT query and return formatted results."""
        if is_dangerous_query(sql):
            return {"error": "Query blocked for safety reasons. Only SELECT allowed."}
        
        conn = sqlite3.connect(Config.DATABASE_URI)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            start = time.time()
            cursor.execute(sql)
            rows = cursor.fetchall()
            exec_time = round(time.time() - start, 4)
            
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            data = [dict(zip(columns, row)) for row in rows]
            
            return {
                "success": True,
                "columns": columns,
                "rows": data,
                "row_count": len(data),
                "execution_time": exec_time
            }
        except Exception as e:
            return {"error": f"Execution error: {str(e)}"}
        finally:
            conn.close()