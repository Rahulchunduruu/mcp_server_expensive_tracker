from fastmcp import FastMCP
import os
import requests

TURSO_URL   = os.environ.get("TURSO_DB_URL", "")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")

mcp = FastMCP("ExpenseTracker")

# ── Helper: execute SQL via Turso HTTP API ─────────────
def query(sql, params=None):
    response = requests.post(
        f"{TURSO_URL}/v2/pipeline",
        headers={
            "Authorization": f"Bearer {TURSO_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "requests": [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": sql,
                        "args": [{"type": "text", "value": str(p)} for p in (params or [])]
                    }
                },
                {"type": "close"}
            ]
        }
    )
    response.raise_for_status()
    return response.json()["results"][0]["response"]["result"]

# ── Helper: parse Turso rows ───────────────────────────
def parse_rows(result):
    cols = [c["name"] for c in result["cols"]]
    # ✅ rows are plain lists, NOT dicts with "values" key
    return [dict(zip(cols, [v["value"] for v in row])) for row in result["rows"]]

# ── Init table ─────────────────────────────────────────
def init_db():
    query("""
        CREATE TABLE IF NOT EXISTS expenses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            subcategory TEXT DEFAULT '',
            note TEXT DEFAULT ''
        )
    """)

init_db()

# ── Prompt helper ──────────────────────────────────────
def build_prompt(problem: str):
    return f"""
        You are an expert financial data analyst.
        Solve the problem step by step:
        {problem}
        Give:
        1. A clear and concise explanation of spending till now
        2. If you find any duplicated transaction, highlight it bold and give the id
        3. If you find any transaction with missing category, highlight it bold
        4. Show the data in red colour where amount is greater than 10000
        5. Show the data in a basic tabular format.
    """

@mcp.prompt()
def system_prompt(problem: str):
    return build_prompt(problem)

# ── Tools ──────────────────────────────────────────────

@mcp.tool()
def add_expense(date, amount, category, subcategory="", note=""):
    '''Add a new expense entry to the database.'''
    result = query(
        "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
        [date, amount, category, subcategory, note]
    )
    return {"status": "ok", "id": result["last_insert_rowid"]}

@mcp.tool()
def list_expenses(start_date, end_date):
    '''List expense entries within an inclusive date range.'''
    result = query(
        "SELECT id, date, amount, category, subcategory, note FROM expenses WHERE date BETWEEN ? AND ? ORDER BY id ASC",
        [start_date, end_date]
    )
    data = parse_rows(result)  # ✅ fixed
    return {"instruction": build_prompt(str(data)), "raw_data": data}

@mcp.tool()
def list_expenses_by_column_name(column_name, item):
    '''List expense entries filtered by a column value.'''
    allowed = {"id", "date", "amount", "category", "subcategory", "note"}
    if column_name not in allowed:
        return {"error": f"Invalid column: {column_name}"}
    result = query(
        f"SELECT id, date, amount, subcategory, note, category FROM expenses WHERE {column_name} = ?",
        [item]
    )
    data = parse_rows(result)  # ✅ fixed
    return {"instruction": build_prompt(str(data)), "raw_data": data}  # ✅ build_prompt not system_prompt

@mcp.tool()
def summarize(start_date, end_date, category=None):
    '''Summarize expenses by category within a date range.'''
    sql = "SELECT category, SUM(amount) AS total_amount FROM expenses WHERE date BETWEEN ? AND ?"
    params = [start_date, end_date]
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " GROUP BY category ORDER BY category ASC"
    result = query(sql, params)
    return parse_rows(result)  # ✅ fixed

@mcp.tool()
def delete_expense(expense_id: int):
    '''Delete an expense entry by ID.'''
    query("DELETE FROM expenses WHERE id = ?", [expense_id])
    return {"status": "ok", "deleted_id": expense_id}

@mcp.tool()
def delete_expense_list(expense_ids: list):
    '''Delete multiple expense entries by IDs.'''
    placeholders = ','.join('?' * len(expense_ids))
    query(f"DELETE FROM expenses WHERE id IN ({placeholders})", expense_ids)
    return {"status": "ok", "deleted_ids": expense_ids}

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)