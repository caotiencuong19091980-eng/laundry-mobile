import sqlite3
import tkinter as tk
import os
import shutil
import base64
import html
import webbrowser
from datetime import datetime, date
from tkinter import ttk, messagebox, filedialog


DB_FILE = "laundry.db"
PAYMENT_QR_FILE = "payment_qr.png"
STATUSES = ["Mới nhận", "Đang giặt", "Đã sấy", "Hoàn tất", "Đã trả"]


class LaundryDB:
    def __init__(self, db_file: str):
        self.conn = sqlite3.connect(db_file)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        cur = self.conn.cursor()
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
        self.conn.commit()

    def upsert_customer(self, name: str, phone: str, address: str = "") -> int:
        cur = self.conn.cursor()
        now = datetime.now().isoformat(timespec="seconds")
        cur.execute("SELECT id FROM customers WHERE phone = ?", (phone,))
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE customers SET name = ?, address = ? WHERE id = ?",
                (name, address, row["id"]),
            )
            self.conn.commit()
            return row["id"]

        cur.execute(
            """
            INSERT INTO customers(name, phone, address, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, phone, address, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def create_order(
        self,
        customer_id: int,
        service_type: str,
        weight_kg: float,
        unit_price: float,
        paid_amount: float,
        status: str,
        due_date: str,
        note: str,
    ) -> int:
        total = weight_kg * unit_price
        now = datetime.now().isoformat(timespec="seconds")
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO orders(
                customer_id, service_type, weight_kg, unit_price,
                total_amount, paid_amount, status, due_date, note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_id,
                service_type,
                weight_kg,
                unit_price,
                total,
                paid_amount,
                status,
                due_date,
                note,
                now,
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_orders(self, keyword: str = ""):
        cur = self.conn.cursor()
        base_select = """
            SELECT o.id, c.name, c.phone, o.service_type, o.weight_kg,
                   o.unit_price, o.total_amount, o.paid_amount,
                   (o.total_amount - o.paid_amount) AS debt_amount,
                   o.status, o.due_date, o.note, o.created_at
            FROM orders o
            JOIN customers c ON o.customer_id = c.id
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
                debt_conditions = ["LOWER(c.name) LIKE ?", "CAST(o.id AS TEXT) LIKE ?"]
                params = [kw, kw]
                if allow_phone_search:
                    debt_conditions.append("c.phone LIKE ?")
                    params.append(kw)
                cur.execute(
                    f"""
                    {base_select}
                    WHERE (o.total_amount - o.paid_amount) > 0
                      AND ({' OR '.join(debt_conditions)})
                    ORDER BY o.id DESC
                    """,
                    tuple(params),
                )
            else:
                cur.execute(
                    f"""
                    {base_select}
                    WHERE (o.total_amount - o.paid_amount) > 0
                    ORDER BY o.id DESC
                    """
                )
        elif clean_keyword:
            kw = f"%{clean_keyword}%"
            search_conditions = [
                "c.name LIKE ?",
                "o.status LIKE ?",
                "o.service_type LIKE ?",
                "CAST(o.id AS TEXT) LIKE ?",
            ]
            params = [kw, kw, kw, kw]
            if allow_phone_search:
                search_conditions.append("c.phone LIKE ?")
                params.append(kw)
            cur.execute(
                f"""
                {base_select}
                WHERE {' OR '.join(search_conditions)}
                ORDER BY o.id DESC
                """,
                tuple(params),
            )
        else:
            cur.execute(
                f"""
                {base_select}
                ORDER BY o.id DESC
                """
            )
        return cur.fetchall()

    def get_order_detail(self, order_id: int):
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT o.id, c.name, c.phone, c.address, o.service_type, o.weight_kg,
                   o.unit_price, o.total_amount, o.paid_amount, o.status,
                   o.due_date, o.note, o.created_at
            FROM orders o
            JOIN customers c ON o.customer_id = c.id
            WHERE o.id = ?
            """,
            (order_id,),
        )
        return cur.fetchone()

    def update_order(self, order_id: int, status: str, paid_amount: float, note: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            UPDATE orders
            SET status = ?, paid_amount = ?, note = ?
            WHERE id = ?
            """,
            (status, paid_amount, note, order_id),
        )
        self.conn.commit()

    def revenue_between(self, start_date: str, end_date: str):
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT
                COUNT(*) AS total_orders,
                COALESCE(SUM(total_amount), 0) AS gross_revenue,
                COALESCE(SUM(paid_amount), 0) AS paid_revenue
            FROM orders
            WHERE DATE(created_at) BETWEEN DATE(?) AND DATE(?)
            """,
            (start_date, end_date),
        )
        return cur.fetchone()

    def close(self) -> None:
        self.conn.close()


class LaundryApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Hệ thống quản lý giặt là Hương Thịnh cơ sở 1")
        self.geometry("1360x840")
        self.minsize(1180, 720)
        self.option_add("*Font", ("Times New Roman", 11))
        self._configure_styles()
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self.db = LaundryDB(DB_FILE)
        self._build_ui()
        self.load_orders()

    def _configure_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TLabel", font=("Times New Roman", 11), background="#ecf8f7")
        style.configure(
            "Header.TLabel",
            font=("Times New Roman", 32, "bold"),
            foreground="#0c4a6e",
            background="#ecf8f7",
        )
        style.configure("SubHeader.TLabel", font=("Times New Roman", 12), foreground="#0f766e", background="#ecf8f7")
        style.configure("Credit.TLabel", font=("Times New Roman", 9), foreground="#475569", background="#ecf8f7")
        style.configure("TButton", font=("Times New Roman", 11, "bold"), padding=(10, 6), background="#22c55e", foreground="#ffffff")
        style.map("TButton", background=[("active", "#16a34a"), ("pressed", "#15803d")], foreground=[("active", "#ffffff")])
        style.configure("TEntry", font=("Times New Roman", 11), fieldbackground="#ffffff")
        style.configure("TCombobox", font=("Times New Roman", 11), fieldbackground="#ffffff")
        style.configure("TLabelframe", background="#ecf8f7", borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", font=("Times New Roman", 12, "bold"), foreground="#0f172a", background="#ecf8f7")
        style.configure("Treeview", font=("Times New Roman", 10), rowheight=28)
        style.configure("Treeview.Heading", font=("Times New Roman", 11, "bold"), background="#bae6fd")
        style.configure("TNotebook", background="#ecf8f7")
        style.configure("TNotebook.Tab", font=("Times New Roman", 11, "bold"), padding=(12, 8), background="#a7f3d0")
        style.map("TNotebook.Tab", background=[("selected", "#34d399"), ("active", "#6ee7b7")], foreground=[("selected", "#083344")])

    def _build_ui(self):
        self.configure(bg="#ecf8f7")

        header = ttk.Frame(self, padding=(14, 10))
        header.pack(fill=tk.X)
        ttk.Label(
            header,
            text="A software program authored by Cuongct",
            style="Credit.TLabel",
            anchor=tk.E,
        ).pack(side=tk.RIGHT, padx=(12, 0), pady=(4, 0))
        title_wrap = ttk.Frame(header)
        title_wrap.pack(fill=tk.X, expand=True)
        ttk.Label(
            title_wrap,
            text="Hệ thống quản lý giặt là Hương Thịnh cơ sở 1",
            style="Header.TLabel",
            anchor=tk.CENTER,
        ).pack(fill=tk.X)
        ttk.Label(
            title_wrap,
            text="Quản lý đơn hàng, trạng thái xử lý và doanh thu theo ngày.",
            style="SubHeader.TLabel",
            anchor=tk.CENTER,
        ).pack(fill=tk.X, pady=(2, 0))

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))

        self.tab_orders = ttk.Frame(notebook)
        self.tab_reports = ttk.Frame(notebook)

        notebook.add(self.tab_orders, text="Đơn hàng")
        notebook.add(self.tab_reports, text="Báo cáo")

        self._build_orders_tab()
        self._build_reports_tab()

        status_bar = ttk.Frame(self, padding=(12, 6))
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(status_bar, textvariable=self.status_var, style="SubHeader.TLabel").pack(anchor=tk.W)

    def _build_orders_tab(self):
        top_section = ttk.Frame(self.tab_orders)
        top_section.pack(fill=tk.X, padx=8, pady=(6, 4))

        self.var_name = tk.StringVar()
        self.var_phone = tk.StringVar()
        self.var_address = tk.StringVar()
        self.var_service = tk.StringVar(value="Giặt thường")
        self.var_weight = tk.StringVar(value="1")
        self.var_price = tk.StringVar(value="15000")
        self.var_paid = tk.StringVar(value="0")
        self.var_status = tk.StringVar(value=STATUSES[0])
        self.var_due = tk.StringVar(value=str(date.today()))
        self.var_note = tk.StringVar()
        self.var_search = tk.StringVar()
        self.var_quick_order_id = tk.StringVar()
        self.var_quick_status = tk.StringVar(value=STATUSES[0])
        self.var_edit_id = tk.StringVar()
        self.var_edit_status = tk.StringVar(value=STATUSES[0])
        self.var_edit_paid = tk.StringVar(value="0")
        self.var_edit_note = tk.StringVar()

        form_frame = ttk.LabelFrame(top_section, text="Tạo đơn mới")
        form_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        row1 = ttk.Frame(form_frame)
        row1.pack(fill=tk.X, padx=5, pady=2)
        row2 = ttk.Frame(form_frame)
        row2.pack(fill=tk.X, padx=5, pady=2)
        row3 = ttk.Frame(form_frame)
        row3.pack(fill=tk.X, padx=5, pady=2)

        ttk.Label(row1, text="Tên KH", width=12).pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.var_name, width=24).pack(side=tk.LEFT, padx=4)
        ttk.Label(row1, text="Điện thoại", width=12).pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.var_phone, width=18).pack(side=tk.LEFT, padx=4)
        ttk.Label(row1, text="Địa chỉ", width=10).pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.var_address, width=28).pack(side=tk.LEFT, padx=4)

        ttk.Label(row2, text="Dịch vụ", width=12).pack(side=tk.LEFT)
        service_cb = ttk.Combobox(
            row2,
            textvariable=self.var_service,
            values=["Giặt thường", "Giặt nhanh", "Giặt hấp", "Giặt sấy"],
            width=21,
            state="readonly",
        )
        service_cb.pack(side=tk.LEFT, padx=4)
        ttk.Label(row2, text="Số kg", width=12).pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.var_weight, width=10).pack(side=tk.LEFT, padx=4)
        ttk.Label(row2, text="Đơn giá", width=10).pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.var_price, width=12).pack(side=tk.LEFT, padx=4)
        ttk.Label(row2, text="Đã trả", width=10).pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.var_paid, width=12).pack(side=tk.LEFT, padx=4)

        ttk.Label(row3, text="Trạng thái", width=12).pack(side=tk.LEFT)
        ttk.Combobox(
            row3, textvariable=self.var_status, values=STATUSES, width=21, state="readonly"
        ).pack(side=tk.LEFT, padx=4)
        ttk.Label(row3, text="Hẹn trả (YYYY-MM-DD)", width=18).pack(side=tk.LEFT)
        ttk.Entry(row3, textvariable=self.var_due, width=16).pack(side=tk.LEFT, padx=4)
        ttk.Label(row3, text="Ghi chú", width=10).pack(side=tk.LEFT)
        ttk.Entry(row3, textvariable=self.var_note, width=30).pack(side=tk.LEFT, padx=4)

        form_actions = ttk.Frame(form_frame)
        form_actions.pack(fill=tk.X, padx=5, pady=(4, 6))
        ttk.Button(form_actions, text="Tạo mới", command=self.create_order).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(form_actions, text="Làm mới form", command=self.reset_form).pack(side=tk.LEFT, padx=6)

        controls_frame = ttk.LabelFrame(top_section, text="Thao tác nhanh")
        controls_frame.pack(side=tk.LEFT, fill=tk.Y)
        controls_frame.configure(width=350)
        controls_frame.pack_propagate(False)

        ttk.Label(controls_frame, text="Tìm kiếm đơn").pack(anchor=tk.W, padx=10, pady=(10, 2))
        search_row = ttk.Frame(controls_frame)
        search_row.pack(fill=tk.X, padx=10)
        ttk.Entry(search_row, textvariable=self.var_search).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(search_row, text="Tìm kiếm", command=self.load_orders).pack(side=tk.LEFT, padx=(6, 0))

        control_buttons = ttk.Frame(controls_frame)
        control_buttons.pack(fill=tk.X, padx=10, pady=(8, 6))
        ttk.Button(control_buttons, text="Tải danh sách", command=self.load_orders).pack(fill=tk.X, pady=3)
        ttk.Button(control_buttons, text="Export đơn đã chọn", command=self.export_selected_order).pack(
            fill=tk.X, pady=3
        )

        quick_status = ttk.LabelFrame(controls_frame, text="Cập nhật trạng thái nhanh")
        quick_status.pack(fill=tk.X, padx=10, pady=(2, 10))
        ttk.Label(quick_status, text="Mã đơn").pack(anchor=tk.W, padx=8, pady=(8, 2))
        ttk.Entry(quick_status, textvariable=self.var_quick_order_id, width=20).pack(anchor=tk.W, padx=8)
        ttk.Label(quick_status, text="Trạng thái mới").pack(anchor=tk.W, padx=8, pady=(8, 2))
        ttk.Combobox(
            quick_status,
            textvariable=self.var_quick_status,
            values=STATUSES,
            state="readonly",
            width=18,
        ).pack(anchor=tk.W, padx=8)
        ttk.Button(
            quick_status,
            text="Cập nhật trạng thái",
            command=self.update_status_quick,
        ).pack(fill=tk.X, padx=8, pady=(10, 10))

        table_frame = ttk.LabelFrame(self.tab_orders, text="Danh sách đơn")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(2, 8))

        cols = (
            "id",
            "name",
            "phone",
            "service",
            "kg",
            "price",
            "total",
            "paid",
            "debt",
            "status",
            "due",
            "note",
            "created",
        )
        self.table = ttk.Treeview(table_frame, columns=cols, show="headings", height=19)
        headers = {
            "id": ("Mã đơn", 60),
            "name": ("Khách", 150),
            "phone": ("Điện thoại", 110),
            "service": ("Dịch vụ", 110),
            "kg": ("Kg", 60),
            "price": ("Đơn giá", 95),
            "total": ("Thành tiền", 105),
            "paid": ("Đã trả", 95),
            "debt": ("Còn nợ", 100),
            "status": ("Trạng thái", 115),
            "due": ("Hẹn trả", 100),
            "note": ("Ghi chú", 160),
            "created": ("Ngày tạo", 140),
        }
        for key, (text, width) in headers.items():
            self.table.heading(key, text=text)
            self.table.column(key, width=width, anchor=tk.CENTER)

        yscroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.table.yview)
        self.table.configure(yscrollcommand=yscroll.set)
        self.table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.table.tag_configure("odd", background="#f8fafc")
        self.table.tag_configure("even", background="#ffffff")
        self.table.bind("<<TreeviewSelect>>", self.on_select_order)
        self.table.bind("<Button-3>", self.on_table_right_click)
        self.context_order_id = None
        self._build_table_context_menu()

        inline_edit = ttk.LabelFrame(self.tab_orders, text="Chỉnh sửa đơn hàng đã chọn (theo dòng đơn)")
        inline_edit.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(inline_edit, text="Mã đơn", width=10).pack(side=tk.LEFT, padx=(6, 4), pady=6)
        ttk.Entry(inline_edit, textvariable=self.var_edit_id, width=10, state="readonly").pack(
            side=tk.LEFT, padx=4
        )
        ttk.Label(inline_edit, text="Trạng thái", width=10).pack(side=tk.LEFT, padx=4)
        ttk.Combobox(
            inline_edit,
            textvariable=self.var_edit_status,
            values=STATUSES,
            state="readonly",
            width=15,
        ).pack(side=tk.LEFT, padx=4)
        ttk.Label(inline_edit, text="Đã trả", width=8).pack(side=tk.LEFT, padx=4)
        ttk.Entry(inline_edit, textvariable=self.var_edit_paid, width=12).pack(side=tk.LEFT, padx=4)
        ttk.Label(inline_edit, text="Ghi chú", width=8).pack(side=tk.LEFT, padx=4)
        ttk.Entry(inline_edit, textvariable=self.var_edit_note, width=34).pack(side=tk.LEFT, padx=4)
        ttk.Button(inline_edit, text="Edit", command=self.update_order).pack(side=tk.LEFT, padx=10)

    def _build_table_context_menu(self):
        self.table_menu = tk.Menu(self, tearoff=0, font=("Times New Roman", 11))
        status_menu = tk.Menu(self.table_menu, tearoff=0, font=("Times New Roman", 11))
        for status in STATUSES:
            status_menu.add_command(
                label=status,
                command=lambda s=status: self.update_status_from_context_menu(s),
            )
        self.table_menu.add_cascade(label="Cập nhật trạng thái", menu=status_menu)
        self.table_menu.add_separator()
        self.table_menu.add_command(label="Export đơn đã chọn", command=self.export_selected_order)

    def on_table_right_click(self, event):
        row_id = self.table.identify_row(event.y)
        if not row_id:
            return
        self.table.selection_set(row_id)
        self.table.focus(row_id)
        self.on_select_order()
        values = self.table.item(row_id, "values")
        if not values:
            return
        self.context_order_id = int(values[0])
        try:
            self.table_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.table_menu.grab_release()

    def update_status_from_context_menu(self, new_status: str):
        if self.context_order_id is None:
            messagebox.showerror("Lỗi", "Chưa chọn đơn hàng để cập nhật.")
            return
        order = self.db.get_order_detail(self.context_order_id)
        if not order:
            messagebox.showerror("Lỗi", "Không tìm thấy đơn hàng.")
            return

        paid_amount = order["paid_amount"]
        note = order["note"] or ""
        if new_status == "Đã trả":
            payment_result = self.ask_payment_or_debt(order)
            if payment_result is None:
                return
            paid_amount, note = payment_result

        self.db.update_order(
            order_id=self.context_order_id,
            status=new_status,
            paid_amount=paid_amount,
            note=note,
        )
        self.status_var.set(f"Đã cập nhật trạng thái đơn #{self.context_order_id} -> {new_status}.")
        messagebox.showinfo("Thành công", f"Đã cập nhật trạng thái đơn #{self.context_order_id}.")
        self.load_orders()


    def _build_reports_tab(self):
        box = ttk.LabelFrame(self.tab_reports, text="Thống kê doanh thu")
        box.pack(fill=tk.X, padx=8, pady=8)

        self.var_report_from = tk.StringVar(value=str(date.today()))
        self.var_report_to = tk.StringVar(value=str(date.today()))

        ttk.Label(box, text="Từ ngày (YYYY-MM-DD)", width=20).pack(side=tk.LEFT, padx=4, pady=6)
        ttk.Entry(box, textvariable=self.var_report_from, width=16).pack(side=tk.LEFT, padx=4)
        ttk.Label(box, text="Đến ngày", width=10).pack(side=tk.LEFT, padx=4)
        ttk.Entry(box, textvariable=self.var_report_to, width=16).pack(side=tk.LEFT, padx=4)
        ttk.Button(box, text="Xem báo cáo", command=self.load_report).pack(side=tk.LEFT, padx=8)
        ttk.Button(box, text="Xuất file", command=self.export_report).pack(side=tk.LEFT, padx=4)

        self.report_text = tk.Text(self.tab_reports, height=18, font=("Times New Roman", 11))
        self.report_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.report_text.insert(tk.END, "Nhập khoảng ngày và bấm 'Xem báo cáo'.\n")
        self.report_text.config(state=tk.DISABLED)

    @staticmethod
    def validate_date(date_str: str) -> bool:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    @staticmethod
    def money(value: float) -> str:
        return f"{value:,.0f} VND".replace(",", ".")

    @staticmethod
    def parse_money_input(value: str) -> float:
        clean = value.strip().replace(".", "").replace(",", "")
        if not clean:
            return 0.0
        return float(clean)

    def ask_payment_or_debt(self, order):
        dialog = tk.Toplevel(self)
        dialog.title(f"Cập nhật thanh toán đơn #{order['id']}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        total_amount = float(order["total_amount"])
        current_paid = float(order["paid_amount"])
        current_debt = max(total_amount - current_paid, 0)

        paid_var = tk.StringVar()
        debt_var = tk.StringVar()
        result = {"ok": False, "paid": current_paid, "note_append": ""}

        body = ttk.Frame(dialog, padding=12)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text=f"Đơn #{order['id']} - {order['name']}").pack(anchor=tk.W)
        ttk.Label(body, text=f"Tổng tiền: {self.money(total_amount)}").pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(body, text=f"Đã thu hiện tại: {self.money(current_paid)}").pack(anchor=tk.W)
        ttk.Label(body, text=f"Còn nợ hiện tại: {self.money(current_debt)}").pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(
            body,
            text="Nhập một trong hai trường bên dưới (đã trả hoặc còn nợ):",
        ).pack(anchor=tk.W, pady=(0, 6))

        row1 = ttk.Frame(body)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Số tiền đã trả (tổng):", width=24).pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=paid_var, width=20).pack(side=tk.LEFT)

        row2 = ttk.Frame(body)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Số tiền còn nợ:", width=24).pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=debt_var, width=20).pack(side=tk.LEFT)

        def on_confirm():
            paid_text = paid_var.get().strip()
            debt_text = debt_var.get().strip()
            if not paid_text and not debt_text:
                messagebox.showerror("Lỗi", "Vui lòng nhập số tiền đã trả hoặc số tiền còn nợ.", parent=dialog)
                return
            try:
                paid_input = self.parse_money_input(paid_text) if paid_text else None
                debt_input = self.parse_money_input(debt_text) if debt_text else None
            except ValueError:
                messagebox.showerror("Lỗi", "Giá trị tiền không hợp lệ.", parent=dialog)
                return

            if paid_input is not None and paid_input < 0:
                messagebox.showerror("Lỗi", "Số tiền đã trả không được âm.", parent=dialog)
                return
            if debt_input is not None and debt_input < 0:
                messagebox.showerror("Lỗi", "Số tiền nợ không được âm.", parent=dialog)
                return

            if paid_input is not None and debt_input is not None:
                if abs((total_amount - paid_input) - debt_input) > 0.5:
                    messagebox.showerror(
                        "Lỗi",
                        "Dữ liệu chưa khớp: tổng tiền - đã trả phải bằng nợ.",
                        parent=dialog,
                    )
                    return
                final_paid = paid_input
                final_debt = debt_input
            elif paid_input is not None:
                final_paid = paid_input
                final_debt = total_amount - final_paid
            else:
                final_debt = debt_input
                final_paid = total_amount - final_debt

            if final_paid < 0 or final_debt < 0:
                messagebox.showerror("Lỗi", "Giá trị thanh toán vượt quá tổng tiền.", parent=dialog)
                return

            final_paid = min(final_paid, total_amount)
            final_debt = max(total_amount - final_paid, 0)

            result["ok"] = True
            result["paid"] = final_paid
            result["note_append"] = (
                f"Thanh toán khi trả đồ: đã thu {self.money(final_paid)}, còn nợ {self.money(final_debt)}"
            )
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_row = ttk.Frame(body)
        btn_row.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_row, text="Xác nhận", command=on_confirm).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Hủy", command=on_cancel).pack(side=tk.LEFT, padx=8)

        dialog.wait_window()
        if not result["ok"]:
            return None

        base_note = order["note"] or ""
        note = f"{base_note} | {result['note_append']}" if base_note else result["note_append"]
        return result["paid"], note

    def create_order(self):
        name = self.var_name.get().strip()
        phone = self.var_phone.get().strip()
        address = self.var_address.get().strip()
        service = self.var_service.get().strip()
        note = self.var_note.get().strip()
        status = self.var_status.get().strip()
        due_date = self.var_due.get().strip()

        if not name or not phone:
            messagebox.showerror("Lỗi", "Tên và số điện thoại không được để trống.")
            return
        if status not in STATUSES:
            messagebox.showerror("Lỗi", "Trạng thái không hợp lệ.")
            return
        if due_date and not self.validate_date(due_date):
            messagebox.showerror("Lỗi", "Ngày hẹn trả không đúng định dạng YYYY-MM-DD.")
            return

        try:
            weight = float(self.var_weight.get())
            price = float(self.var_price.get())
            paid = float(self.var_paid.get())
        except ValueError:
            messagebox.showerror("Lỗi", "Số kg, đơn giá, đã trả phải là số.")
            return

        if weight <= 0 or price < 0 or paid < 0:
            messagebox.showerror("Lỗi", "Giá trị tiền và khối lượng phải lớn hơn hoặc bằng 0.")
            return

        customer_id = self.db.upsert_customer(name, phone, address)
        order_id = self.db.create_order(
            customer_id=customer_id,
            service_type=service,
            weight_kg=weight,
            unit_price=price,
            paid_amount=paid,
            status=status,
            due_date=due_date,
            note=note,
        )
        messagebox.showinfo("Thành công", f"Đã tạo đơn #{order_id}.")
        self.status_var.set(f"Đã tạo đơn mới #{order_id} lúc {datetime.now().strftime('%H:%M:%S')}")
        self.reset_form()
        self.load_orders()

    def reset_form(self):
        self.var_name.set("")
        self.var_phone.set("")
        self.var_address.set("")
        self.var_service.set("Giặt thường")
        self.var_weight.set("1")
        self.var_price.set("15000")
        self.var_paid.set("0")
        self.var_status.set(STATUSES[0])
        self.var_due.set(str(date.today()))
        self.var_note.set("")

    def load_orders(self):
        keyword = self.var_search.get().strip()
        for item in self.table.get_children():
            self.table.delete(item)

        rows = self.db.list_orders(keyword)
        total_debt = 0.0
        debt_customers = set()
        for idx, row in enumerate(rows):
            tag = "even" if idx % 2 == 0 else "odd"
            debt_value = max(row["debt_amount"], 0)
            total_debt += debt_value
            if debt_value > 0:
                debt_customers.add(row["name"])
            self.table.insert(
                "",
                tk.END,
                values=(
                    row["id"],
                    row["name"],
                    row["phone"],
                    row["service_type"],
                    f"{row['weight_kg']:.2f}",
                    self.money(row["unit_price"]),
                    self.money(row["total_amount"]),
                    self.money(row["paid_amount"]),
                    self.money(debt_value),
                    row["status"],
                    row["due_date"] or "",
                    row["note"],
                    row["created_at"].replace("T", " "),
                ),
                tags=(tag,),
            )
        if keyword and (("nợ" in keyword.lower()) or ("khach no" in keyword.lower()) or ("khách nợ" in keyword.lower())):
            self.status_var.set(
                f"Tìm thấy {len(rows)} đơn nợ | {len(debt_customers)} khách nợ | Tổng nợ: {self.money(total_debt)}"
            )
        else:
            self.status_var.set(f"Đã tải {len(rows)} đơn hàng.")

    def on_select_order(self, _event=None):
        selected = self.table.selection()
        if not selected:
            return

        vals = self.table.item(selected[0], "values")
        self.var_edit_id.set(vals[0])
        self.var_edit_status.set(vals[9])
        paid_num = vals[7].replace(" VND", "").replace(".", "")
        self.var_edit_paid.set(paid_num or "0")
        self.var_edit_note.set(vals[11])
        self.var_quick_order_id.set(vals[0])
        self.var_quick_status.set(vals[9])

    def update_order(self):
        order_id = self.var_edit_id.get().strip()
        if not order_id:
            messagebox.showerror("Lỗi", "Hãy chọn một đơn cần cập nhật.")
            return

        status = self.var_edit_status.get().strip()
        note = self.var_edit_note.get().strip()
        order = self.db.get_order_detail(int(order_id))
        if not order:
            messagebox.showerror("Lỗi", "Không tìm thấy đơn hàng.")
            return
        try:
            paid = float(self.var_edit_paid.get().strip())
        except ValueError:
            messagebox.showerror("Lỗi", "Số tiền đã trả không hợp lệ.")
            return

        if paid < 0:
            messagebox.showerror("Lỗi", "Tiền đã trả không được âm.")
            return

        if status == "Đã trả" and order["status"] != "Đã trả":
            payment_result = self.ask_payment_or_debt(order)
            if payment_result is None:
                return
            paid, note = payment_result
            self.var_edit_paid.set(str(int(paid)))
            self.var_edit_note.set(note)

        self.db.update_order(int(order_id), status, paid, note)
        messagebox.showinfo("Thành công", f"Đã cập nhật đơn #{order_id}.")
        self.status_var.set(f"Đã cập nhật đơn #{order_id}.")
        self.load_orders()

    def update_status_quick(self):
        order_id = self.var_quick_order_id.get().strip()
        new_status = self.var_quick_status.get().strip()
        if not order_id:
            messagebox.showerror("Lỗi", "Vui lòng nhập mã đơn để cập nhật trạng thái.")
            return
        try:
            order_id_int = int(order_id)
        except ValueError:
            messagebox.showerror("Lỗi", "Mã đơn phải là số nguyên.")
            return
        if new_status not in STATUSES:
            messagebox.showerror("Lỗi", "Trạng thái không hợp lệ.")
            return

        order = self.db.get_order_detail(order_id_int)
        if not order:
            messagebox.showerror("Lỗi", "Không tìm thấy đơn hàng.")
            return

        paid_amount = order["paid_amount"]
        note = order["note"] or ""
        if new_status == "Đã trả":
            payment_result = self.ask_payment_or_debt(order)
            if payment_result is None:
                return
            paid_amount, note = payment_result

        self.db.update_order(
            order_id=order_id_int,
            status=new_status,
            paid_amount=paid_amount,
            note=note,
        )
        self.status_var.set(f"Đã cập nhật trạng thái đơn #{order_id} -> {new_status}.")
        messagebox.showinfo("Thành công", f"Đã cập nhật trạng thái đơn #{order_id}.")
        self.load_orders()

    def export_selected_order(self):
        order_id = self.var_edit_id.get().strip()
        if not order_id:
            messagebox.showerror("Lỗi", "Hãy chọn một đơn để export.")
            return

        order = self.db.get_order_detail(int(order_id))
        if not order:
            messagebox.showerror("Lỗi", "Không tìm thấy dữ liệu đơn hàng.")
            return

        return_time = order["due_date"] or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_amount = float(order["total_amount"])
        paid_amount = float(order["paid_amount"])
        debt_amount = max(total_amount - paid_amount, 0)
        save_path = filedialog.asksaveasfilename(
            title="Chọn nơi lưu đơn hàng",
            defaultextension=".html",
            initialfile=f"don_hang_{order['id']}.html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
        )
        if not save_path:
            return

        qr_export_name = self._ensure_qr_for_export(save_path)
        if not qr_export_name:
            messagebox.showerror("Lỗi", "Không có ảnh QR thanh toán. Vui lòng chọn ảnh QR trước khi export HTML.")
            return

        customer_name = html.escape(str(order["name"]))
        phone = html.escape(str(order["phone"]))
        service = html.escape(str(order["service_type"]))
        status = html.escape(str(order["status"]))
        note = html.escape(str(order["note"] or "Không có"))
        return_time_safe = html.escape(return_time)
        qr_src = f"{qr_export_name}?v={datetime.now().strftime('%Y%m%d%H%M%S')}"
        qr_block = (
            f"<img src='{qr_src}' "
            "alt='QR thanh toán' "
            "class='qr'/>"
        )

        content = f"""<!doctype html>
<html lang='vi'>
<head>
  <meta charset='utf-8'/>
  <title>Đơn hàng #{order['id']}</title>
  <style>
    @page {{
      size: 57mm 30mm;
      margin: 1.5mm;
    }}
    html, body {{
      width: 57mm;
      margin: 0;
      padding: 0;
      font-family: 'Times New Roman', serif;
      color: #111;
      background: #fff;
    }}
    .wrap {{
      width: 54mm;
      min-height: 27mm;
      margin: 0 auto;
      box-sizing: border-box;
      padding: 1mm 1.2mm 1mm 1.2mm;
      border: 0.2mm dashed #555;
    }}
    .title {{
      text-align: center;
      font-size: 8pt;
      font-weight: bold;
      line-height: 1.1;
      margin-bottom: 0.8mm;
    }}
    .meta {{
      font-size: 6.4pt;
      line-height: 1.1;
      margin-bottom: 0.3mm;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .split {{
      display: flex;
      gap: 1.2mm;
      margin-top: 0.5mm;
    }}
    .left {{
      flex: 1;
      min-width: 0;
    }}
    .right {{
      width: 13.5mm;
      text-align: center;
    }}
    .qr {{
      width: 12.5mm;
      height: 12.5mm;
      border: 0.2mm solid #333;
      padding: 0.3mm;
      box-sizing: border-box;
    }}
    .amount {{
      font-size: 6.2pt;
      font-weight: bold;
      margin-top: 0.4mm;
      line-height: 1.1;
    }}
    .divider {{
      border-top: 0.2mm dashed #333;
      margin: 0.6mm 0;
    }}
    .footer {{
      font-size: 5.8pt;
      text-align: center;
      line-height: 1.1;
      margin-top: 0.4mm;
    }}
    .print-btn {{
      margin-top: 1.2mm;
      width: 100%;
      background:#0b5ed7;
      color:#fff;
      border:none;
      border-radius:2mm;
      padding:1.6mm 0;
      font-family:'Times New Roman', serif;
      font-size:7pt;
      cursor:pointer;
    }}
    .print-btn {{
      display: none;
    }}
    @media screen {{
      body {{
        background: #f3f4f6;
        padding: 10px;
      }}
      .print-btn {{
        display: block;
      }}
    }}
    @media print {{
      .print-btn {{ display: none; }}
    }}
  </style>
</head>
<body>
  <div class='wrap'>
    <div class='title'>HÓA ĐƠN GIẶT LÀ</div>
    <div class='meta'>Mã đơn: #{order['id']}</div>
    <div class='meta'>Khách: {customer_name}</div>
    <div class='meta'>SĐT: {phone}</div>
    <div class='meta'>DV: {service} | {order['weight_kg']:.2f}kg</div>
    <div class='meta'>Tổng: {self.money(total_amount)}</div>
    <div class='meta'>Đã trả: {self.money(paid_amount)} | Nợ: {self.money(debt_amount)}</div>
    <div class='meta'>Trạng thái: {status}</div>
    <div class='meta'>Trả đồ: {return_time_safe}</div>
    <div class='divider'></div>
    <div class='split'>
      <div class='left'>
        <div class='meta'>Thanh toán QR</div>
        <div class='amount'>Số tiền: {self.money(total_amount)}</div>
      </div>
      <div class='right'>
        {qr_block}
      </div>
    </div>
    <div class='footer'>A software program authored by Cuongct</div>
    <button class='print-btn' onclick='window.print()'>In hóa đơn</button>
  </div>
</body>
</html>"""

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as exc:
            messagebox.showerror("Lỗi", f"Không thể ghi file: {exc}")
            return

        if save_path.lower().endswith(".html"):
            webbrowser.open(f"file:///{save_path.replace(os.sep, '/')}")
        messagebox.showinfo("Thành công", f"Đã export đơn hàng ra file:\n{save_path}")
        self.status_var.set(f"Đã export đơn #{order_id} ra file.")

    def _ensure_qr_for_export(self, save_path: str):
        qr_path = os.path.join(os.getcwd(), PAYMENT_QR_FILE)
        if not os.path.exists(qr_path):
            selected_path = filedialog.askopenfilename(
                title="Chọn ảnh QR thanh toán (PNG/JPG)",
                filetypes=[("Image files", "*.png;*.jpg;*.jpeg"), ("All files", "*.*")],
            )
            if not selected_path:
                return None
            try:
                shutil.copyfile(selected_path, qr_path)
            except OSError as exc:
                messagebox.showerror("Lỗi", f"Không thể lưu ảnh QR: {exc}")
                return None

        qr_export_name = "payment_qr.png"
        export_dir = os.path.dirname(save_path) or os.getcwd()
        export_qr_path = os.path.join(export_dir, qr_export_name)
        try:
            shutil.copyfile(qr_path, export_qr_path)
        except OSError as exc:
            messagebox.showerror("Lỗi", f"Không thể copy ảnh QR sang file export: {exc}")
            return None
        return qr_export_name

    def load_report(self):
        start = self.var_report_from.get().strip()
        end = self.var_report_to.get().strip()
        if not self.validate_date(start) or not self.validate_date(end):
            messagebox.showerror("Lỗi", "Ngày báo cáo phải theo định dạng YYYY-MM-DD.")
            return

        stats = self.db.revenue_between(start, end)
        total_orders = stats["total_orders"]
        gross = stats["gross_revenue"]
        paid = stats["paid_revenue"]
        unpaid = gross - paid
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report = (
            "BÁO CÁO GIẶT LÀ\n"
            f"Thời gian xuất: {created_at}\n"
            f"Khoảng ngày: {start} -> {end}\n"
            f"{'-' * 44}\n"
            f"Số đơn: {total_orders}\n"
            f"Tổng doanh thu: {self.money(gross)}\n"
            f"Đã thu: {self.money(paid)}\n"
            f"Còn nợ: {self.money(unpaid)}\n"
        )

        self.report_text.config(state=tk.NORMAL)
        self.report_text.delete("1.0", tk.END)
        self.report_text.insert(tk.END, report)
        self.report_text.config(state=tk.DISABLED)

    def export_report(self):
        content = self.report_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showerror("Lỗi", "Chưa có dữ liệu báo cáo để xuất file.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Chọn nơi lưu báo cáo",
            defaultextension=".txt",
            initialfile=f"bao_cao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content + "\n")
        except OSError as exc:
            messagebox.showerror("Lỗi", f"Không thể ghi file báo cáo: {exc}")
            return

        self.status_var.set(f"Đã xuất báo cáo: {file_path}")
        messagebox.showinfo("Thành công", f"Đã xuất báo cáo ra file:\n{file_path}")

    def on_closing(self):
        self.db.close()
        self.destroy()


def main():
    app = LaundryApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()

