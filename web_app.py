from __future__ import annotations

import base64
import os
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Any

from flask import Flask, flash, redirect, render_template, request, url_for
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None

DB_FILE = "laundry.db"
PAYMENT_QR_FILE = "payment_qr.png"
STATUSES = ["Mới nhận", "Đang giặt", "Đã sấy", "Hoàn tất", "Đã trả"]
SERVICES = ["Giặt thường", "Giặt nhanh", "Giặt hấp", "Giặt sấy"]
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
IS_POSTGRES = bool(DATABASE_URL)

app = Flask(
    __name__,
    template_folder="web_templates",
    static_folder="web_static",
)
app.secret_key = "huong-thinh-laundry-secret"


def normalized_database_url() -> str:
    if DATABASE_URL.startswith("postgres://"):
        return DATABASE_URL.replace("postgres://", "postgresql://", 1)
    return DATABASE_URL


def get_conn():
    if IS_POSTGRES:
        if psycopg2 is None:
            raise RuntimeError("Thiếu thư viện psycopg2-binary cho PostgreSQL.")
        return psycopg2.connect(normalized_database_url(), cursor_factory=RealDictCursor)
    conn = sqlite3.connect(os.getenv("DB_FILE", DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def sql(query: str) -> str:
    if IS_POSTGRES:
        return query.replace("?", "%s")
    return query


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()
    if IS_POSTGRES:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                address TEXT DEFAULT '',
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id BIGSERIAL PRIMARY KEY,
                customer_id BIGINT NOT NULL REFERENCES customers(id),
                service_type TEXT NOT NULL,
                weight_kg DOUBLE PRECISION NOT NULL,
                unit_price DOUBLE PRECISION NOT NULL,
                total_amount DOUBLE PRECISION NOT NULL,
                paid_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                due_date DATE,
                note TEXT DEFAULT '',
                created_at TIMESTAMP NOT NULL
            )
            """
        )
    else:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                address TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                service_type TEXT NOT NULL,
                weight_kg REAL NOT NULL,
                unit_price REAL NOT NULL,
                total_amount REAL NOT NULL,
                paid_amount REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                due_date TEXT,
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(id)
            )
            """
        )
    conn.commit()
    conn.close()


def upsert_customer(name: str, phone: str, address: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")
    if IS_POSTGRES:
        cur.execute(
            """
            INSERT INTO customers(name, phone, address, created_at)
            VALUES (%s, %s, %s, %s::timestamp)
            ON CONFLICT(phone) DO UPDATE
            SET name = EXCLUDED.name,
                address = EXCLUDED.address
            RETURNING id
            """,
            (name, phone, address, now),
        )
        customer_id = cur.fetchone()["id"]
        conn.commit()
    else:
        cur.execute("SELECT id FROM customers WHERE phone = ?", (phone,))
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE customers SET name = ?, address = ? WHERE id = ?", (name, address, row["id"]))
            conn.commit()
            customer_id = row["id"]
        else:
            cur.execute(
                """
                INSERT INTO customers(name, phone, address, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, phone, address, now),
            )
            conn.commit()
            customer_id = cur.lastrowid
    conn.close()
    return int(customer_id)


def normalize_money(value: str) -> float:
    clean = value.strip().replace(".", "").replace(",", "")
    if not clean:
        return 0.0
    return float(clean)


def list_orders(keyword: str = "") -> list[sqlite3.Row]:
    conn = get_conn()
    cur = conn.cursor()

    base = """
        SELECT o.id, c.name, c.phone, c.address, o.service_type, o.weight_kg,
               o.unit_price, o.total_amount, o.paid_amount,
               (o.total_amount - o.paid_amount) AS debt_amount,
               o.status, o.due_date, o.note, o.created_at
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
    """

    clean_keyword = keyword.strip()
    lowered = clean_keyword.lower()
    digit_only = "".join(ch for ch in clean_keyword if ch.isdigit())
    allow_phone_search = len(digit_only) >= 5
    debt_mode = ("nợ" in lowered) or ("khach no" in lowered) or ("khách nợ" in lowered)

    if debt_mode:
        customer_hint = lowered
        for token in ("khách nợ", "khach no", "khách", "khach", "nợ", "no"):
            customer_hint = customer_hint.replace(token, " ")
        customer_hint = " ".join(customer_hint.split())

        if customer_hint:
            kw = f"%{customer_hint}%"
            conditions = ["LOWER(c.name) LIKE ?", "CAST(o.id AS TEXT) LIKE ?"]
            params: list[Any] = [kw, kw]
            if allow_phone_search:
                conditions.append("c.phone LIKE ?")
                params.append(kw)
            query = f"""
                {base}
                WHERE (o.total_amount - o.paid_amount) > 0
                AND ({' OR '.join(conditions)})
                ORDER BY o.id DESC
            """
            cur.execute(sql(query), tuple(params))
        else:
            cur.execute(
                f"""
                {base}
                WHERE (o.total_amount - o.paid_amount) > 0
                ORDER BY o.id DESC
                """
            )
    elif clean_keyword:
        kw = f"%{clean_keyword}%"
        conditions = [
            "c.name LIKE ?",
            "o.status LIKE ?",
            "o.service_type LIKE ?",
            "CAST(o.id AS TEXT) LIKE ?",
        ]
        params: list[Any] = [kw, kw, kw, kw]
        if allow_phone_search:
            conditions.append("c.phone LIKE ?")
            params.append(kw)
        cur.execute(
            sql(
            f"""
            {base}
            WHERE {' OR '.join(conditions)}
            ORDER BY o.id DESC
            """,
            ),
            tuple(params),
        )
    else:
        cur.execute(
            f"""
            {base}
            ORDER BY o.id DESC
            """
        )

    rows = cur.fetchall()
    conn.close()
    return rows


def revenue_between(start_date: str, end_date: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        sql(
            """
            SELECT
                COUNT(*) AS total_orders,
                COALESCE(SUM(total_amount), 0) AS gross_revenue,
                COALESCE(SUM(paid_amount), 0) AS paid_revenue
            FROM orders
            WHERE DATE(created_at) BETWEEN DATE(?) AND DATE(?)
            """
        ),
        (start_date, end_date),
    )
    row = cur.fetchone()
    conn.close()
    return row


def get_order(order_id: int) -> sqlite3.Row | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        sql(
        """
        SELECT o.id, c.name, c.phone, c.address, o.service_type, o.weight_kg,
               o.unit_price, o.total_amount, o.paid_amount,
               (o.total_amount - o.paid_amount) AS debt_amount,
               o.status, o.due_date, o.note, o.created_at
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
        WHERE o.id = ?
        """,
        ),
        (order_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row


def update_order(order_id: int, status: str, paid_amount: float, note: str) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        sql(
        """
        UPDATE orders
        SET status = ?, paid_amount = ?, note = ?
        WHERE id = ?
        """,
        ),
        (status, paid_amount, note, order_id),
    )
    conn.commit()
    conn.close()


def money(value: float) -> str:
    return f"{value:,.0f} VND".replace(",", ".")


def qr_base64() -> str | None:
    path = Path(PAYMENT_QR_FILE)
    if not path.exists():
        return None
    data = path.read_bytes()
    return base64.b64encode(data).decode("ascii")


@app.route("/")
def index():
    keyword = request.args.get("q", "").strip()
    report_from = request.args.get("report_from", str(date.today())).strip() or str(date.today())
    report_to = request.args.get("report_to", str(date.today())).strip() or str(date.today())

    rows = list_orders(keyword)
    total_debt = sum(max(float(r["debt_amount"]), 0) for r in rows)
    debt_customers = {r["name"] for r in rows if float(r["debt_amount"]) > 0}
    report = revenue_between(report_from, report_to)
    gross = float(report["gross_revenue"] or 0)
    paid = float(report["paid_revenue"] or 0)
    unpaid = gross - paid

    return render_template(
        "index.html",
        rows=rows,
        keyword=keyword,
        statuses=STATUSES,
        services=SERVICES,
        today=str(date.today()),
        report_from=report_from,
        report_to=report_to,
        report_total_orders=int(report["total_orders"] or 0),
        report_gross=gross,
        report_paid=paid,
        report_unpaid=unpaid,
        total_debt=total_debt,
        debt_customers=len(debt_customers),
        money=money,
    )


@app.post("/orders/create")
def create_order():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    service = request.form.get("service_type", "Giặt thường").strip()
    status = request.form.get("status", STATUSES[0]).strip()
    due_date = request.form.get("due_date", "").strip()
    note = request.form.get("note", "").strip()

    if not name or not phone:
        flash("Tên và số điện thoại không được để trống.", "error")
        return redirect(url_for("index"))

    try:
        weight = float(request.form.get("weight_kg", "0"))
        unit_price = normalize_money(request.form.get("unit_price", "0"))
        paid_amount = normalize_money(request.form.get("paid_amount", "0"))
    except ValueError:
        flash("Số kg/đơn giá/đã trả không hợp lệ.", "error")
        return redirect(url_for("index"))

    if weight <= 0 or unit_price < 0 or paid_amount < 0:
        flash("Dữ liệu tiền hoặc khối lượng không hợp lệ.", "error")
        return redirect(url_for("index"))

    customer_id = upsert_customer(name, phone, address)
    total_amount = weight * unit_price
    now = datetime.now().isoformat(timespec="seconds")

    conn = get_conn()
    cur = conn.cursor()
    if IS_POSTGRES:
        cur.execute(
            """
            INSERT INTO orders(
                customer_id, service_type, weight_kg, unit_price,
                total_amount, paid_amount, status, due_date, note, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, NULLIF(%s, '')::date, %s, %s::timestamp)
            RETURNING id
            """,
            (
                customer_id,
                service,
                weight,
                unit_price,
                total_amount,
                paid_amount,
                status,
                due_date,
                note,
                now,
            ),
        )
        conn.commit()
        order_id = cur.fetchone()["id"]
    else:
        cur.execute(
            """
            INSERT INTO orders(
                customer_id, service_type, weight_kg, unit_price,
                total_amount, paid_amount, status, due_date, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_id,
                service,
                weight,
                unit_price,
                total_amount,
                paid_amount,
                status,
                due_date,
                note,
                now,
            ),
        )
        conn.commit()
        order_id = cur.lastrowid
    conn.close()

    flash(f"Đã tạo đơn #{order_id}.", "success")
    return redirect(url_for("index"))


@app.post("/orders/<int:order_id>/update")
def update_order_route(order_id: int):
    row = get_order(order_id)
    if not row:
        flash("Không tìm thấy đơn hàng.", "error")
        return redirect(url_for("index"))

    status = request.form.get("status", row["status"]).strip()
    note = request.form.get("note", row["note"] or "").strip()

    paid_mode = request.form.get("paid_mode", "paid")
    paid_raw = request.form.get("paid_amount", "").strip()
    debt_raw = request.form.get("debt_amount", "").strip()

    total = float(row["total_amount"])
    current_paid = float(row["paid_amount"])

    try:
        if status == "Đã trả":
            if paid_mode == "debt":
                debt = normalize_money(debt_raw)
                paid = total - debt
            else:
                paid = normalize_money(paid_raw)
        else:
            paid = normalize_money(paid_raw) if paid_raw else current_paid
    except ValueError:
        flash("Số tiền không hợp lệ.", "error")
        return redirect(url_for("index"))

    if paid < 0:
        flash("Số tiền đã trả không hợp lệ.", "error")
        return redirect(url_for("index"))

    paid = min(paid, total)
    debt = max(total - paid, 0)

    if status == "Đã trả":
        payment_note = f"Thanh toán khi trả đồ: đã thu {money(paid)}, còn nợ {money(debt)}"
        note = f"{note} | {payment_note}" if note else payment_note

    update_order(order_id, status, paid, note)
    flash(f"Đã cập nhật đơn #{order_id}.", "success")
    return redirect(url_for("index"))


@app.route("/invoice/<int:order_id>")
def invoice(order_id: int):
    row = get_order(order_id)
    if not row:
        flash("Không tìm thấy đơn hàng.", "error")
        return redirect(url_for("index"))

    return render_template(
        "invoice.html",
        order=row,
        qr=qr_base64(),
        money=money,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
