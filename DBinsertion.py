import mysql.connector
import json

class DBInsertion:
    def __init__(self, host, user, password, database):
        self.conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database
        )
        self.cursor = self.conn.cursor()

    def create_user(self, name):
        email = f"{name.replace(' ', '').lower()}@autogen.com"
        password = "defaultpassword"
        role = "Worker"
        phone = ""
        self.cursor.execute(
            "INSERT INTO Users (name, email, password, role, phone) VALUES (%s, %s, %s, %s, %s)",
            (name, email, password, role, phone)
        )
        print(f"Created new user '{name}' with id {self.cursor.lastrowid}")
        return self.cursor.lastrowid

    def get_or_create_user_id_by_name(self, name):
        self.cursor.execute("SELECT id FROM Users WHERE name = %s", (name,))
        result = self.cursor.fetchone()
        if result:
            return result[0]
        else:
            return self.create_user(name)

    def get_menu_id_by_name(self, name):
        self.cursor.execute("SELECT id FROM Menu WHERE name = %s", (name,))
        result = self.cursor.fetchone()
        return result[0] if result else None

    def insert_order(self, customer_name, total_price, payment_method):
        user_id = self.get_or_create_user_id_by_name(customer_name)
        self.cursor.execute(
            "INSERT INTO Orders (user_id, total_price, payment_method) VALUES (%s, %s, %s)",
            (user_id, total_price, payment_method.capitalize())
        )
        order_id = self.cursor.lastrowid
        print(f"Inserted Order ID: {order_id}")
        return order_id

    def insert_order_items(self, order_id, ordered_items):
        for item in ordered_items:
            menu_id = self.get_menu_id_by_name(item["item_name"])
            if not menu_id:
                print(f"Menu item '{item['item_name']}' not found. Skipping.")
                continue
            self.cursor.execute(
                "INSERT INTO OrderItems (order_id, menu_id, quantity, special_request, item_name) VALUES (%s, %s, %s, %s, %s)",
                (order_id, menu_id, item["quantity"], item.get("special_instructions", ""), item["item_name"])
            )
            print(f"Inserted OrderItem for menu_id={menu_id}")

    def insert_reservation(self, customer_name, reservation_time, guests, table_number):
        user_id = self.get_or_create_user_id_by_name(customer_name)
        self.cursor.execute(
            "INSERT INTO Reservations (user_id, reservation_time, guests, table_number) VALUES (%s, %s, %s, %s)",
            (user_id, reservation_time, guests, table_number)
        )
        reservation_id = self.cursor.lastrowid
        print(f"Inserted Reservation ID: {reservation_id}")
        return reservation_id

    def commit_and_close(self):
        self.conn.commit()
        self.cursor.close()
        self.conn.close()
        print("Insertions completed.")

def main():
    tester = DBInsertion(
        host="localhost",
        user="root",
        password="Passw0rd!",
        database="CulinaryAI"
    )

    # Insert into Orders and OrderItems
    with open("order_test_data.json") as f:
        order_data = json.load(f)
    order_id = tester.insert_order(
        customer_name=order_data["customer_name"],
        total_price=order_data["total_price"],
        payment_method=order_data["payment_method"]
    )
    tester.insert_order_items(order_id, order_data["ordered_items"])

    # Insert into Reservations
    with open("reservation_test_data.json") as f:
        reservation_data = json.load(f)
    tester.insert_reservation(
        customer_name=reservation_data["customer_name"],
        reservation_time=reservation_data["reservation_time"],
        guests=reservation_data["guests"],
        table_number=reservation_data["table_number"]
    )

    tester.commit_and_close()

if __name__ == "__main__":
    main()