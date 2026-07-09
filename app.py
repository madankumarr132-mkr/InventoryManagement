

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
import config

from openpyxl import Workbook
from flask import send_file
import os

from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "zp_inventory_secret_key"

# ==========================
# Database Configuration
# ==========================
app.config["MYSQL_HOST"] = config.MYSQL_HOST
app.config["MYSQL_USER"] = config.MYSQL_USER
app.config["MYSQL_PASSWORD"] = config.MYSQL_PASSWORD
app.config["MYSQL_DB"] = config.MYSQL_DB
app.config["MYSQL_PORT"] = config.MYSQL_PORT



mysql = MySQL(app)

def log_activity(username, activity):

    cursor = mysql.connection.cursor()

    cursor.execute("""
        INSERT INTO activity_log(username, activity)
        VALUES(%s, %s)
    """, (username, activity))

    mysql.connection.commit()
    cursor.close()

# ==========================
# Home Page
# ==========================
@app.route("/")
def home():

    if "user_id" not in session:
        return redirect(url_for("login"))

    cursor = mysql.connection.cursor()

    # Total different items
    cursor.execute("SELECT COUNT(*) FROM items")
    total_items = cursor.fetchone()[0]

    # Total stock quantity
    cursor.execute("SELECT SUM(available_qty) FROM items")
    total_stock = cursor.fetchone()[0] or 0



    # Low stock items
    cursor.execute("""
        SELECT item_name, available_qty, minimum_qty
        FROM items
        WHERE available_qty <= minimum_qty
        ORDER BY available_qty ASC
    """)
    low_stock = cursor.fetchall()

    # Last 5 transactions
    cursor.execute("""
        SELECT
            i.item_name,
            t.person_name,
            t.department,
            t.quantity,
            t.transaction_date
        FROM transactions t
        JOIN items i ON t.item_id = i.id
        ORDER BY t.transaction_date DESC
        LIMIT 5
    """)
    recent_transactions = cursor.fetchall()

    cursor.close()

    return render_template(
        "index.html",
        total_items=total_items,
        total_stock=total_stock,
        low_stock=low_stock,
        recent_transactions=recent_transactions
    )

# ==========================
# Add Item
# ==========================
@app.route("/add-item", methods=["GET", "POST"])
def add_item():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":

        item_name = request.form["item_name"]
        category = request.form["category"]
        available_qty = request.form["available_qty"]
        minimum_qty = request.form["minimum_qty"]

        cursor = mysql.connection.cursor()

        cursor.execute("""
            INSERT INTO items
            (item_name, category, available_qty, minimum_qty)
            VALUES (%s, %s, %s, %s)
        """, (item_name, category, available_qty, minimum_qty))

        mysql.connection.commit()
        log_activity(
    session["username"],
    f"Added item: {item_name}"
)
        cursor.close()

        return redirect(url_for("home"))

    return render_template("add_item.html")

@app.route("/edit-item/<int:id>", methods=["GET", "POST"])
def edit_item(id):

    if "user_id" not in session:
        return redirect(url_for("login"))
    cursor = mysql.connection.cursor()

    if request.method == "POST":

        item_name = request.form["item_name"]
        category = request.form["category"]
        available_qty = request.form["available_qty"]
        minimum_qty = request.form["minimum_qty"]

        cursor.execute("""
            UPDATE items
            SET item_name=%s,
                category=%s,
                available_qty=%s,
                minimum_qty=%s
            WHERE id=%s
        """, (item_name, category, available_qty, minimum_qty, id))

        mysql.connection.commit()
        log_activity(
    session["username"],
    f"Edited item: {item_name}"
)
        cursor.close()

        return redirect(url_for("view_items"))

    cursor.execute("SELECT * FROM items WHERE id=%s", (id,))
    item = cursor.fetchone()

    cursor.close()

    return render_template("edit_item.html", item=item)

@app.route("/items")
def view_items():

    if "user_id" not in session:
        return redirect(url_for("login"))

    cursor = mysql.connection.cursor()

    search = request.args.get("search", "")
    category = request.args.get("category", "")
    page = request.args.get("page", 1, type=int)

    per_page = 10
    offset = (page - 1) * per_page

    # Load categories
    cursor.execute("SELECT DISTINCT category FROM items ORDER BY category")
    categories = cursor.fetchall()

    query = "SELECT * FROM items WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM items WHERE 1=1"

    params = []
    count_params = []

    if search:
        query += " AND item_name LIKE %s"
        count_query += " AND item_name LIKE %s"
        params.append("%" + search + "%")
        count_params.append("%" + search + "%")

    if category:
        query += " AND category=%s"
        count_query += " AND category=%s"
        params.append(category)
        count_params.append(category)

    query += " ORDER BY item_name LIMIT %s OFFSET %s"
    params.extend([per_page, offset])

    cursor.execute(query, tuple(params))
    items = cursor.fetchall()

    cursor.execute(count_query, tuple(count_params))
    total = cursor.fetchone()[0]

    total_pages = (total + per_page - 1) // per_page

    cursor.close()

    return render_template(
        "view_items.html",
        items=items,
        categories=categories,
        page=page,
        total_pages=total_pages
    )

@app.route("/delete-item/<int:id>")
def delete_item(id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    cursor = mysql.connection.cursor()

    cursor.execute(
        "SELECT item_name FROM items WHERE id=%s",
        (id,)
    )

    item = cursor.fetchone()

    cursor.execute(
        "DELETE FROM items WHERE id=%s",
        (id,)
    )

    mysql.connection.commit()

    log_activity(
        session["username"],
        f"Deleted item: {item[0]}"
    )

    cursor.close()

    return redirect(url_for("view_items"))

@app.route("/issue-stock", methods=["GET", "POST"])
@app.route("/issue-stock", methods=["GET", "POST"])
def issue_stock():

    if "user_id" not in session:
        return redirect(url_for("login"))

    cursor = mysql.connection.cursor()

    if request.method == "POST":

        item_id = request.form["item_id"]
        quantity = int(request.form["quantity"])
        person_name = request.form["person_name"]
        department = request.form["department"]
        remarks = request.form["remarks"]

        # Get item name and current stock
        cursor.execute(
            "SELECT item_name, available_qty FROM items WHERE id=%s",
            (item_id,)
        )

        result = cursor.fetchone()

        if result is None:
            cursor.close()
            return "Item not found!"

        item_name = result[0]
        current_stock = result[1]

        if quantity <= 0:
            cursor.close()
            return "Quantity must be greater than zero."

        if quantity > current_stock:
            cursor.close()
            return "Not enough stock available!"

        # Update stock
        new_stock = current_stock - quantity

        cursor.execute(
            "UPDATE items SET available_qty=%s WHERE id=%s",
            (new_stock, item_id)
        )

        # Save transaction
        cursor.execute("""
            INSERT INTO transactions
            (item_id, transaction_type, quantity, person_name, department, remarks)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            item_id,
            "ISSUE",
            quantity,
            person_name,
            department,
            remarks
        ))

        mysql.connection.commit()

        # Activity Log
        log_activity(
            session["username"],
            f"Issued {quantity} of {item_name} to {person_name} ({department})"
        )

        cursor.close()

        return redirect(url_for("view_items"))

    # GET Request
    cursor.execute("SELECT * FROM items")
    items = cursor.fetchall()

    cursor.execute("SELECT * FROM departments")
    departments = cursor.fetchall()

    cursor.close()

    return render_template(
        "issue_stock.html",
        items=items,
        departments=departments
    )

@app.route("/transactions")
def transactions():

    if "user_id" not in session:
        return redirect(url_for("login"))
    cursor = mysql.connection.cursor()

    department = request.args.get("department")

    if department:

        cursor.execute("""
            SELECT
                t.id,
                t.item_id,
                t.transaction_type,
                t.quantity,
                t.person_name,
                t.department,
                t.transaction_date,
                i.item_name
            FROM transactions t
            JOIN items i ON t.item_id = i.id
            WHERE t.department=%s
            ORDER BY t.transaction_date DESC
        """, (department,))

    else:

        cursor.execute("""
            SELECT
                t.id,
                t.item_id,
                t.transaction_type,
                t.quantity,
                t.person_name,
                t.department,
                t.transaction_date,
                i.item_name
            FROM transactions t
            JOIN items i ON t.item_id = i.id
            ORDER BY t.transaction_date DESC
        """)

    data = cursor.fetchall()

    # Load department list
    cursor.execute("SELECT * FROM departments")
    departments = cursor.fetchall()

    cursor.close()

    return render_template(
        "transactions.html",
        transactions=data,
        departments=departments
    )

@app.route("/export-transactions")
def export_transactions():

    if "user_id" not in session:
        return redirect(url_for("login"))
    cursor = mysql.connection.cursor()

    cursor.execute("""
        SELECT
            i.item_name,
            t.person_name,
            t.department,
            t.quantity,
            t.transaction_type,
            t.transaction_date
        FROM transactions t
        JOIN items i
        ON t.item_id = i.id
        ORDER BY t.transaction_date DESC
    """)

    data = cursor.fetchall()

    cursor.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"

    ws.append([
        "Item",
        "Person",
        "Department",
        "Quantity",
        "Type",
        "Date"
    ])

    for row in data:
        ws.append(row)

    filename = "transactions.xlsx"

    wb.save(filename)

    return send_file(
        filename,
        as_attachment=True
    )


@app.route("/item-history/<int:item_id>")
def item_history(item_id):

    if "user_id" not in session:
        return redirect(url_for("login"))
    cursor = mysql.connection.cursor()

    cursor.execute("""
        SELECT
            transaction_date,
            person_name,
            department,
            quantity,
            transaction_type,
            remarks
        FROM transactions
        WHERE item_id=%s
        ORDER BY transaction_date DESC
    """, (item_id,))

    history = cursor.fetchall()

    cursor.close()

    return render_template(
        "item_history.html",
        history=history
    )

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT id, username, role
            FROM users
            WHERE username=%s
            AND password=%s
        """, (username, password))

        user = cursor.fetchone()

        cursor.close()

        if user:

            session["user_id"] = user[0]
            session["username"] = user[1]
            session["role"] = user[2]

            log_activity(
    session["username"],
    "Logged into the system"
)

            return redirect(url_for("home"))

        flash("Invalid Username or Password")

    return render_template("login.html")

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))

@app.route("/change-password", methods=["GET", "POST"])
def change_password():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        current = request.form["current_password"]
        new = request.form["new_password"]

        cursor = mysql.connection.cursor()

        cursor.execute("""
            SELECT password
            FROM users
            WHERE id=%s
        """, (session["user_id"],))

        db_password = cursor.fetchone()[0]

        if current != db_password:
            cursor.close()
            return "Current password is incorrect."

        cursor.execute("""
            UPDATE users
            SET password=%s
            WHERE id=%s
        """, (new, session["user_id"]))

        mysql.connection.commit()
        log_activity(
    session["username"],
    "Changed password"
)
        cursor.close()

        flash("Password changed successfully.")

        return redirect(url_for("home"))

    return render_template("change_password.html")

@app.route("/stock-report")
def stock_report():

    if "user_id" not in session:
        return redirect(url_for("login"))

    cursor = mysql.connection.cursor()

    cursor.execute("""
        SELECT
            item_name,
            category,
            available_qty,
            minimum_qty
        FROM items
        ORDER BY item_name
    """)

    items = cursor.fetchall()

    cursor.close()

    return render_template(
        "stock_report.html",
        items=items
    )

@app.route("/activity-log")
def activity_log():

    if "user_id" not in session:
        return redirect(url_for("login"))

    cursor = mysql.connection.cursor()

    cursor.execute("""
        SELECT id, username, activity, activity_time
        FROM activity_log
        ORDER BY activity_time DESC
    """)

    logs = cursor.fetchall()

    cursor.close()

    return render_template(
        "activity_log.html",
        logs=logs
    )

@app.route("/stock-adjustment", methods=["GET", "POST"])
def stock_adjustment():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "Admin":
        return "Access Denied"

    cursor = mysql.connection.cursor()

    if request.method == "POST":

        item_id = request.form["item_id"]
        new_quantity = int(request.form["new_quantity"])
        reason = request.form["reason"]

        # Get item name
        cursor.execute(
            "SELECT item_name FROM items WHERE id=%s",
            (item_id,)
        )

        item = cursor.fetchone()

        if item is None:
            cursor.close()
            return "Item not found."

        item_name = item[0]

        # Update stock
        cursor.execute(
            "UPDATE items SET available_qty=%s WHERE id=%s",
            (new_quantity, item_id)
        )

        # Save transaction
        cursor.execute("""
            INSERT INTO transactions
            (item_id, transaction_type, quantity, person_name, department, remarks)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            item_id,
            "ADJUST",
            new_quantity,
            session["username"],
            "Stock Adjustment",
            reason
        ))

        mysql.connection.commit()

        log_activity(
            session["username"],
            f"Adjusted stock of {item_name} to {new_quantity}. Reason: {reason}"
        )

        cursor.close()

        return redirect(url_for("view_items"))

    cursor.execute("SELECT * FROM items ORDER BY item_name")
    items = cursor.fetchall()

    cursor.close()

    return render_template(
        "stock_adjustment.html",
        items=items
    )


print(app.url_map)
# ==========================
# Run Application
# ==========================
if __name__ == "__main__":
    app.run(debug=True)