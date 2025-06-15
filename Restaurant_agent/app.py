from flask import Flask, render_template, request, redirect, url_for, jsonify
import mysql.connector
from flask import session  # Make sure session is imported
import json
from collections import defaultdict
app = Flask(__name__)

app.secret_key = "fh9ncv9^#12!!g8g@!@#"
transcripts = defaultdict(list)



@app.before_request
def make_session_permanent():
    session.permanent = True
# Helper function to get database connection
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Passw0rd!",
        database="CulinaryAI"
    )

# Route for Home Page
@app.route('/')
def home():
    return render_template('index.html')


## Twillio Api Calls

# Paths to the data files
ORDER_DATA_FILE = "/home/pc/LiveKit Voice AI/order_test_data.json"
RESERVATION_DATA_FILE = "/home/pc/LiveKit Voice AI/reservation_test_data.json"

@app.route('/orders_cardboard', methods=['GET', 'POST'])
def orders_and_reservations():
    with open(ORDER_DATA_FILE, 'r') as f:
        orders = json.load(f)
    with open(RESERVATION_DATA_FILE, 'r') as f:
        reservations = json.load(f)
    return render_template('orders_cardboard.html', orders=orders, reservations=reservations)





   


@app.route("/marketing_call",methods=['GET' ,'POST'])
def marketing_call():
  
       
    return render_template("marketing_call.html")



# Route for Signup Page
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    error = None
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        phone = request.form['phone']
        # Check if email already exists
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            error = "Email already exists! Please log in."
        else:
            # Insert new user into database
            cursor.execute("INSERT INTO Users (name, email, password, role, phone) VALUES (%s, %s, %s, %s, %s)",
                           (name, email, password, role, phone))
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('dashboard'))

    return render_template('admin_signup.html', error=error)

# Route for Login Page

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, role FROM Users WHERE email = %s AND password = %s", (username, password))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user:
            session['user_id'] = user['id']
            session['role'] = user['role']

            print("🔍 Debug: User ID ->", session.get('user_id'))
            print("🔍 Debug: User Role ->", session.get('role'))

            return redirect(url_for('dashboard'))
        else:
            error = "Invalid credentials, please try again."

    return render_template('login.html', error=error)

# Route for Dashboard Page
@app.route('/dashboard')
def dashboard():
    role = session.get('role', 'user').lower()  # Default to 'user' if not set
    #print("🔍 Debug: Dashboard Role ->", role)  # Debugging
    return render_template('admin_dashboard.html',role=role)

@app.route('/create_user')
def create_user():
    return render_template('signup.html')

@app.route('/feedback_get')
def feedback_form():
    return render_template('feedback_form.html')

# Route for Orders Page (Fetching data)
@app.route('/orders')
def orders():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""SELECT 
    o.id, 
    u.name, 
    o.status, 
    o.total_price, 
    o.payment_method, 
    GROUP_CONCAT(m.name SEPARATOR ', ') AS ordered_items
FROM Orders o
JOIN Users u ON o.user_id = u.id
JOIN OrderItems oi ON o.id = oi.order_id
JOIN Menu m ON oi.menu_id = m.id
GROUP BY o.id;
""")
    orders_data = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('orders.html', orders=orders_data)

# Route for Reservations Page (Fetching data)
@app.route('/reservations')
def reservations():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT r.id, u.name, r.reservation_time, r.guests, r.table_number, r.status FROM Reservations r JOIN Users u ON r.user_id = u.id")
    reservations_data = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('reservations.html', reservations=reservations_data)

# Route for Customers Page (Fetching data)
@app.route('/customers')
def customers():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT CustomerID, Name, PhoneNumber, DietaryConstraints, Allergy FROM Customers")
    customers_data = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('customers.html', customers=customers_data)

# Route for Feedback Page
@app.route('/feedback')
def feedback():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, order_id, customer_id, rating, comment, created_at FROM Feedback")
    feedback_data = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('feedback.html', feedbacks=feedback_data)

# Route for Menu Page (Fetching data)
@app.route('/menu')
def menu():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, description, price, category, availability FROM Menu")
    menu_data = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('menu.html', menu=menu_data)

# API for Dashboard Stats
@app.route('/api/dashboard/stats', methods=['GET'])
def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT
            (SELECT COUNT(*) FROM Orders) AS total_orders,
            (SELECT SUM(total_price) FROM Orders) AS total_revenue,
            (SELECT COUNT(*) FROM Reservations) AS total_reservations,
            (SELECT AVG(rating) FROM Feedback) AS average_rating;
    """)
    stats = cursor.fetchone()
    cursor.close()
    conn.close()
    return jsonify(stats)

# API for Sales Trends Graph
@app.route('/api/dashboard/sales-trends', methods=['GET'])
def get_sales_trends():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT
            DATE_FORMAT(created_at, '%Y-%m') AS month,
            SUM(total_price) AS total_sales
        FROM Orders
        GROUP BY DATE_FORMAT(created_at, '%Y-%m')
        ORDER BY month;
    """)
    sales_data = cursor.fetchall()
    labels = [row['month'] for row in sales_data]
    data = [row['total_sales'] for row in sales_data]
    cursor.close()
    conn.close()
    return jsonify({"labels": labels, "data": data})


@app.route('/add_item', methods=['POST'])
def add_item():
    # Get form data
    name = request.form.get('name')
    description = request.form.get('description')
    price = float(request.form.get('price'))
    category = request.form.get('category')
    availability = bool(int(request.form.get('availability')))

    # Insert new item into the database
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        INSERT INTO Menu (name, description, price, category, availability)
        VALUES (%s, %s, %s, %s, %s)
    """
    cursor.execute(query, (name, description, price, category, availability))
    conn.commit()
    cursor.close()
    conn.close()

    # Redirect back to the menu page
    return redirect(url_for('menu'))

# API for Recent Orders Table
@app.route('/api/dashboard/recent-orders', methods=['GET'])
def get_recent_orders():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
    SELECT 
    o.id, 
    u.name, 
    o.status, 
    o.total_price, 
    o.payment_method, 
    GROUP_CONCAT(m.name SEPARATOR ', ') AS ordered_items
FROM Orders o
JOIN Users u ON o.user_id = u.id
JOIN OrderItems oi ON o.id = oi.order_id
JOIN Menu m ON oi.menu_id = m.id
GROUP BY o.id;
""")
    recent_orders = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(recent_orders)


    

@app.route('/get-order', methods=['GET'])
def get_order():
    with open('orders.json', 'r') as file:
        order_data = json.load(file)
    return jsonify(order_data)
if __name__ == '__main__':
    app.run(debug=True)