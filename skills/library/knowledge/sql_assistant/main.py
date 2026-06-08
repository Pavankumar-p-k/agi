import re
from skills.utils import success_response, error_response

SQL_TEMPLATES = {
    "find all users": "SELECT * FROM users;",
    "select all": "SELECT * FROM {table};",
    "find users by email": "SELECT * FROM users WHERE email = '{value}';",
    "count users": "SELECT COUNT(*) as total FROM users;",
    "find recent orders": "SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;",
    "get users with orders": "SELECT u.* FROM users u JOIN orders o ON u.id = o.user_id;",
    "total sales by product": "SELECT p.name, SUM(o.quantity * p.price) as total FROM products p JOIN order_items o ON p.id = o.product_id GROUP BY p.id ORDER BY total DESC;",
    "find products low stock": "SELECT * FROM products WHERE stock < 10 ORDER BY stock ASC;",
    "get customer order history": "SELECT o.id, o.total, o.created_at FROM orders o WHERE o.user_id = {id} ORDER BY o.created_at DESC;",
    "average order value": "SELECT AVG(total) as avg_order FROM orders;",
    "monthly revenue": "SELECT DATE_TRUNC('month', created_at) as month, SUM(total) as revenue FROM orders GROUP BY month ORDER BY month;",
    "find duplicates by email": "SELECT email, COUNT(*) as count FROM users GROUP BY email HAVING COUNT(*) > 1;",
    "most popular products": "SELECT p.name, COUNT(oi.product_id) as times_ordered FROM products p JOIN order_items oi ON p.id = oi.product_id GROUP BY p.id ORDER BY times_ordered DESC LIMIT 10;",
    "active users last month": "SELECT DISTINCT u.* FROM users u JOIN orders o ON u.id = o.user_id WHERE o.created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH);",
    "table size estimate": "SELECT table_name, ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb FROM information_schema.TABLES WHERE table_schema = DATABASE();",
}

DESCRIPTION_MAP = {
    "user": "SELECT * FROM users;",
    "users": "SELECT * FROM users;",
    "all users": "SELECT * FROM users;",
    "count users": "SELECT COUNT(*) as total FROM users;",
    "find user": "SELECT * FROM users WHERE id = {id};",
    "find user by email": "SELECT * FROM users WHERE email = '{email}';",
    "find user by id": "SELECT * FROM users WHERE id = {id};",
    "recent orders": "SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;",
    "orders": "SELECT * FROM orders;",
    "products": "SELECT * FROM products;",
    "all products": "SELECT * FROM products;",
    "low stock": "SELECT * FROM products WHERE stock < 10 ORDER BY stock ASC;",
    "total sales": "SELECT SUM(total) as total_sales FROM orders;",
    "average order": "SELECT AVG(total) as avg_order FROM orders;",
    "count orders": "SELECT COUNT(*) as total FROM orders;",
    "duplicate emails": "SELECT email, COUNT(*) as count FROM users GROUP BY email HAVING COUNT(*) > 1;",
    "monthly revenue": "SELECT DATE_FORMAT(created_at, '%Y-%m') as month, SUM(total) as revenue FROM orders GROUP BY month ORDER BY month;",
    "top products": "SELECT p.name, COUNT(oi.product_id) as times_ordered FROM products p JOIN order_items oi ON p.id = oi.product_id GROUP BY p.id ORDER BY times_ordered DESC LIMIT 10;",
    "active users": "SELECT DISTINCT u.* FROM users u JOIN orders o ON u.id = o.user_id WHERE o.created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH);",
    "customer orders": "SELECT o.id, o.total, o.created_at FROM orders o WHERE o.user_id = {id} ORDER BY o.created_at DESC;",
    "tables": "SELECT table_name FROM information_schema.TABLES WHERE table_schema = DATABASE();",
}

def format_sql(query: str) -> str:
    keywords = [
        "SELECT", "FROM", "WHERE", "AND", "OR", "JOIN", "LEFT JOIN", "RIGHT JOIN",
        "INNER JOIN", "OUTER JOIN", "ON", "GROUP BY", "ORDER BY", "HAVING",
        "LIMIT", "OFFSET", "INSERT INTO", "VALUES", "UPDATE", "SET", "DELETE FROM",
        "CREATE TABLE", "ALTER TABLE", "DROP TABLE", "INDEX", "CREATE INDEX",
        "UNION", "ALL", "DISTINCT", "AS", "IN", "NOT", "BETWEEN", "LIKE",
    ]
    out = query.strip()
    for kw in sorted(keywords, key=len, reverse=True):
        out = re.sub(rf"(?i)\b{re.escape(kw)}\b", kw, out)
    for kw in ["SELECT", "FROM", "WHERE", "ORDER BY", "GROUP BY", "HAVING", "LIMIT"]:
        out = re.sub(rf"(?i)({re.escape(kw)})", r"\n\1", out)
    for kw in ["AND", "OR"]:
        out = re.sub(rf"(?i)(\s)({re.escape(kw)})", r"\1  \2", out)
    out = re.sub(r"\n\s*\n", "\n", out.strip())
    return out

def explain_query(query: str) -> str:
    parts = []
    if "SELECT" in query.upper():
        parts.append("This query retrieves data from the database.")
    if "COUNT(" in query:
        parts.append("It counts rows matching the given conditions.")
    if "SUM(" in query:
        parts.append("It calculates the sum of values in a column.")
    if "AVG(" in query:
        parts.append("It computes the average of values in a column.")
    if "GROUP BY" in query.upper():
        parts.append("Results are grouped by the specified column(s).")
    if "ORDER BY" in query.upper():
        parts.append("Results are sorted by the specified column(s).")
    if "HAVING" in query.upper():
        parts.append("Groups are filtered using the HAVING clause.")
    if "JOIN" in query.upper():
        parts.append("Data is combined from multiple tables using a join.")
    if "WHERE" in query.upper():
        parts.append("Rows are filtered by the WHERE condition.")
    if "LIMIT" in query.upper():
        m = re.search(r"LIMIT\s+(\d+)", query, re.I)
        if m:
            parts.append(f"Only the first {m.group(1)} rows are returned.")
    if "DISTINCT" in query.upper():
        parts.append("Duplicate rows are removed from the results.")
    if "COUNT(*)" in query.upper() and "GROUP BY" not in query.upper():
        parts.append("The total number of matching rows is returned.")
    if not parts:
        parts.append("This SQL statement manipulates or queries data.")
    return " ".join(parts)

async def sql_assistant(params: dict) -> dict:
    action = params.get("action", "").strip().lower()
    description = params.get("description", "").strip()
    query = params.get("query", "").strip()

    if action == "generate":
        if not description:
            return error_response("Please provide a 'description' for generating SQL.")
        desc_lower = description.lower().strip().rstrip(".")
        if desc_lower in DESCRIPTION_MAP:
            sql = DESCRIPTION_MAP[desc_lower]
        else:
            for key, val in DESCRIPTION_MAP.items():
                if desc_lower in key or key in desc_lower:
                    sql = val
                    break
            else:
                sql = SQL_TEMPLATES.get(desc_lower, f"SELECT * FROM {desc_lower.replace(' ', '_')};")
        return success_response({
            "action": "generate",
            "description": description,
            "query": format_sql(sql),
            "explanation": explain_query(sql)
        })

    elif action == "explain":
        if not query:
            return error_response("Please provide a 'query' to explain.")
        return success_response({
            "action": "explain",
            "query": format_sql(query),
            "explanation": explain_query(query)
        })

    elif action == "format":
        if not query:
            return error_response("Please provide a 'query' to format.")
        return success_response({
            "action": "format",
            "original": query,
            "formatted": format_sql(query)
        })

    else:
        return error_response("Action must be 'generate', 'explain', or 'format'.")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
