from datetime import datetime
from database.db import get_db


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT name, email, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    try:
        member_since = datetime.strptime(row["created_at"][:7], "%Y-%m").strftime("%B %Y")
    except (ValueError, TypeError):
        member_since = "—"
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": member_since,
    }


def get_summary_stats(user_id, date_from=None, date_to=None):
    sql = "SELECT amount, category FROM expenses WHERE user_id = ?"
    params = [user_id]
    if date_from:
        sql += " AND date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND date <= ?"
        params.append(date_to)
    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    if not rows:
        return {"total_spent": 0, "transaction_count": 0, "top_category": "—"}
    total_spent = sum(row["amount"] for row in rows)
    transaction_count = len(rows)
    category_totals = {}
    for row in rows:
        category_totals[row["category"]] = (
            category_totals.get(row["category"], 0) + row["amount"]
        )
    top_category = max(category_totals, key=category_totals.get)
    return {
        "total_spent": total_spent,
        "transaction_count": transaction_count,
        "top_category": top_category,
    }


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    sql = (
        "SELECT date, description, category, amount "
        "FROM expenses WHERE user_id = ?"
    )
    params = [user_id]
    if date_from:
        sql += " AND date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND date <= ?"
        params.append(date_to)
    sql += " ORDER BY date DESC"
    if not (date_from or date_to):
        sql += " LIMIT ?"
        params.append(limit)
    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [
        {
            "date": row["date"],
            "description": row["description"],
            "category": row["category"],
            "amount": row["amount"],
        }
        for row in rows
    ]


def get_category_breakdown(user_id, date_from=None, date_to=None):
    sql = (
        "SELECT category, SUM(amount) AS amount "
        "FROM expenses WHERE user_id = ?"
    )
    params = [user_id]
    if date_from:
        sql += " AND date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND date <= ?"
        params.append(date_to)
    sql += " GROUP BY category ORDER BY amount DESC"
    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    if not rows:
        return []
    total = sum(row["amount"] for row in rows)
    pcts = [int(row["amount"] / total * 100) for row in rows]
    pcts[0] += 100 - sum(pcts)
    return [
        {"name": rows[i]["category"], "amount": rows[i]["amount"], "pct": pcts[i]}
        for i in range(len(rows))
    ]
