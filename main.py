from fastmcp import FastMCP
import os
import sqlite3

if os.path.exists('/data/expenses.db'):
    pass
else:
    os.makedirs('/data', exist_ok=True)

DB_PATH = os.environ.get("EXPENSE_DB_PATH", "/data/expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

mcp = FastMCP("ExpenseTracker")

def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute("""
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

@mcp.tool()
def add_expense(date, amount, category, subcategory="", note=""):
    '''Add a new expense entry to the database.'''
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
            (date, amount, category, subcategory, note)
        )
        return {"status": "ok", "id": cur.lastrowid}
    
@mcp.tool()
def list_expenses(start_date, end_date):
    '''List expense entries within an inclusive date range.'''

    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            """
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            WHERE date BETWEEN ? AND ?
            ORDER BY id ASC
            """,
            (start_date, end_date)
        )
        cols = [d[0] for d in cur.description]
        data = [dict(zip(cols, r)) for r in cur.fetchall()]

        prompt_text = system_prompt(str(data))

        return {
            "insturction":prompt_text
            ,"raw_data": data
        }

@mcp.tool()
def list_expenses_by_column_name(column_name, item):
    '''List expense entries within an inclusive date range, grouped by category.'''
    allowed_columns = {"id", "date", "amount", "category", "subcategory", "note"}
    if column_name not in allowed_columns:
        return {"error": f"Invalid column name: {column_name}"}
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            """
            SELECT id, date, amount, subcategory, note, category
            FROM expenses
            WHERE {column_name} = ?
            """,
            (item,)
        )
        cols = [d[0] for d in cur.description]
        data= [dict(zip(cols, r)) for r in cur.fetchall()]
        
        prompt_text = system_prompt(str(data))

        return {
            "insturction":prompt_text
            ,"raw_data": data
        }

@mcp.tool()
def summarize(start_date, end_date, category=None):
    '''Summarize expenses by category within an inclusive date range.'''
    with sqlite3.connect(DB_PATH) as c:
        query = (
            """
            SELECT category, SUM(amount) AS total_amount
            FROM expenses
            WHERE date BETWEEN ? AND ?
            """
        )
        params = [start_date, end_date]

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " GROUP BY category ORDER BY category ASC"

        cur = c.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

@mcp.tool()
def delete_expense(expense_id):
    '''Delete an expense entry by ID.'''
    with sqlite3.connect(DB_PATH) as c:
        c.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        return {"status": "ok", "deleted_id": expense_id}


@mcp.resource("expense://categories", mime_type="application/json")
def categories():
    # Read fresh each time so you can edit the file without restarting
    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        return f.read()

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