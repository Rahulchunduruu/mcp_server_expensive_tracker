from fastmcp import FastMCP
import os
import libsql_client

# ── Turso config (set these as env vars in Prefect) ──
TURSO_URL   = os.environ["TURSO_DB_URL"]      # libsql://your-db.turso.io
TURSO_TOKEN = os.environ["TURSO_AUTH_TOKEN"]  # your token

mcp = FastMCP("ExpenseTracker")

# ── Helper: run any query ──────────────────────────────
def query(sql, params=None):
    with libsql_client.create_client_sync(
        url=TURSO_URL,
        auth_token=TURSO_TOKEN
    ) as client:
        if params:
            return client.execute(sql, params)
        return client.execute(sql)

# ── Init table on startup ──────────────────────────────
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

# ── Tools ──────────────────────────────────────────────

@mcp.tool()
def add_expense(date, amount, category, subcategory="", note=""):
    '''Add a new expense entry to the database.'''
    result = query(
        "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
        [date, amount, category, subcategory, note]
    )
    return {"status": "ok", "id": result.last_insert_rowid}

@mcp.tool()
def list_expenses(start_date, end_date):
    '''List expense entries within an inclusive date range.'''
    result = query(
        """
        SELECT id, date, amount, category, subcategory, note
        FROM expenses
        WHERE date BETWEEN ? AND ?
        ORDER BY id ASC
        """,
        [start_date, end_date]
    )
    cols = result.columns
    data = [dict(zip(cols, row)) for row in result.rows]
    return {"instruction": system_prompt(str(data)), "raw_data": data}

@mcp.tool()
def list_expenses_by_column_name(column_name, item):
    '''List expense entries filtered by a column value.'''
    allowed = {"id", "date", "amount", "category", "subcategory", "note"}
    if column_name not in allowed:
        return {"error": f"Invalid column: {column_name}"}
    result = query(
        f"""
        SELECT id, date, amount, subcategory, note, category
        FROM expenses
        WHERE {column_name} = ?
        """,
        [item]
    )
    cols = result.columns
    data = [dict(zip(cols, row)) for row in result.rows]
    return {"instruction": system_prompt(str(data)), "raw_data": data}

@mcp.tool()
def summarize(start_date, end_date, category=None):
    '''Summarize expenses by category within a date range.'''
    sql = """
        SELECT category, SUM(amount) AS total_amount
        FROM expenses
        WHERE date BETWEEN ? AND ?
    """
    params = [start_date, end_date]
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " GROUP BY category ORDER BY category ASC"
    result = query(sql, params)
    cols = result.columns
    return [dict(zip(cols, row)) for row in result.rows]

@mcp.tool()
def delete_expense(expense_id):
    '''Delete an expense entry by ID.'''
    query("DELETE FROM expenses WHERE id = ?", [expense_id])
    return {"status": "ok", "deleted_id": expense_id}

@mcp.prompt()
def system_prompt(problem: str):
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

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
