

import logging
import random
from datetime import datetime
from dataclasses import dataclass, field
from typing import Annotated, Optional
from pydantic import Field
from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, AgentSession, RunContext
from livekit.agents.voice.room_io import RoomInputOptions
from livekit.plugins import deepgram, silero
from livekit.plugins.google import LLM
import mysql.connector
from DBinsertion import DBInsertion
from google.genai import types
logger = logging.getLogger("restaurant-agent")
logger.setLevel(logging.INFO)
load_dotenv()


# New menu and price structure
MENU_ITEMS = [
    "Chicken Biryani",
    "Zinger Burger",
    "Juice",
    "Fries",
]
MENU_PRICES = {
    "Chicken Biryani": 450.00,
    "Zinger Burger": 250.00,
    "Juice": 150.00,
    "Fries": 100.00,
}
MENU_STR = ", ".join(MENU_ITEMS)



@dataclass
class UserData:
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    reservation_time: Optional[str] = None
    delivery_address: Optional[str] = None
    order: Optional[list[dict]] = field(default_factory=list)  # [{item_name, quantity, special_instructions}]
    payment_method: Optional[str] = None  # 'credit' or 'cash'
    credit_card: Optional[str] = None
    total: Optional[float] = None
    guests: Optional[int] = None
    table_number: Optional[int] = None
    is_reservation: bool = False

    def summarize(self) -> str:
        return (
            f"Name: {self.customer_name or 'unknown'}, "
            f"Phone: {self.customer_phone or 'unknown'}, "
            f"Reservation time: {self.reservation_time or 'unknown'}, "
            f"Delivery address: {self.delivery_address or 'unknown'}, "
            f"Order: {self.order or 'none'}, "
            f"Payment: {self.payment_method or 'unknown'}, "
            f"Guests: {self.guests or 'unknown'}, Table: {self.table_number or 'unknown'}"
        )

RunContext_T = RunContext[UserData]



class RestaurantAgent(Agent):
    def _normalize_reservation_time(self, time_str):
        # Always return 'YYYY-MM-DD HH:MM:SS' format
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(time_str, fmt)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
        # fallback: now
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    DB_CONFIG = {
        "host": "localhost",
        "user": "root",
        "password": "Passw0rd!",
        "database": "CulinaryAI"
    }

    def __init__(self):
        super().__init__(
            instructions=(
                "You are a friendly, chatty restaurant assistant. You can provide menu information, take reservations, take orders for delivery or pickup, ask for delivery address if needed, and process payment. "
                f"Menu: {MENU_STR}. "
                "If the user asks for the menu, read it out. If they want to know the price of a menu item, answer with the price from {MENU_PRICES}. If they want to order, collect the items, ask if it's for delivery or pickup, and if delivery, ask for the address. "
                "Always confirm the customer name,total and payment method (credit or cash). "
                "Be conversational and confirm all details at the end always before finalizing. "
                "After confirming, insert the order or reservation into the database."
            ),
            llm=LLM(model="gemini-2.5-flash-preview-05-20", temperature=0.5, vertexai=True),
            tts=deepgram.TTS(),
        )

    def get_or_create_customer(self, phone_number, customer_name):
        try:
            conn = mysql.connector.connect(**self.DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM Customers WHERE phone = %s", (phone_number,))
            result = cursor.fetchone()
            if result:
                customer_id = result[0]
            else:
                cursor.execute("INSERT INTO Customers (name, phone) VALUES (%s, %s)", (customer_name, phone_number))
                customer_id = cursor.lastrowid
                conn.commit()
            cursor.close()
            conn.close()
            return customer_id
        except Exception as e:
            logger.error(f"DB error in get_or_create_customer: {e}")
            return None

    import random

    def _random_phone(self):
        # Generate a random 11-digit number starting with 030
        return "030" + "".join(str(random.randint(0, 9)) for _ in range(8))

    def insert_order_into_db(self, userdata: UserData):
        import json, os
        # Clean and format data for file and DB
        order_data = {
            "customer_name": userdata.customer_name,
            "customer_phone": self._random_phone(),
            "ordered_items": [
                {
                    "item_name": item.get("item_name"),
                    "quantity": int(item.get("quantity", 1)),
                    "special_instructions": item.get("special_instructions", "")
                } for item in (userdata.order or [])
            ],
            "total_price": str(int(userdata.total) if userdata.total is not None else 0),
            "payment_method": (userdata.payment_method or "").lower(),
            "delivery_address": userdata.delivery_address or ""
        }
        path = os.path.join(os.path.dirname(__file__), "order_test_data.json")
        try:
            # Read existing data
            if os.path.exists(path):
                with open(path, "r") as f:
                    try:
                        existing = json.load(f)
                        if not isinstance(existing, list):
                            existing = []
                    except Exception:
                        existing = []
            else:
                existing = []
            # Prepend new order
            new_data = [order_data] + existing
            with open(path, "w") as f:
                json.dump(new_data, f, indent=2)
            logger.info(f"Order data prepended to {path}")
        except Exception as e:
            logger.error(f"❌ Error saving order data to JSON: {e}")
            return False

        # Insert into DB using DBInsertion
        try:
            db = DBInsertion(**self.DB_CONFIG)
            order_id = db.insert_order(
                customer_name=order_data["customer_name"],
                total_price=order_data["total_price"],
                payment_method=order_data["payment_method"]
            )
            db.insert_order_items(order_id, order_data["ordered_items"])
            db.commit_and_close()
            logger.info("Order inserted into DB.")
            return True
        except Exception as e:
            logger.error(f"❌ Error inserting order into DB: {e}")
            return False

    def insert_reservation_into_db(self, userdata: UserData):
        import json, os
        reservation_data = {
            "customer_name": userdata.customer_name,
            "customer_phone": self._random_phone(),
            "reservation_time": self._normalize_reservation_time(userdata.reservation_time),
            "guests": int(userdata.guests) if userdata.guests is not None else 0,
            "table_number": int(userdata.table_number) if userdata.table_number is not None else 0
        }
        path = os.path.join(os.path.dirname(__file__), "reservation_test_data.json")
        try:
            # Read existing data
            if os.path.exists(path):
                with open(path, "r") as f:
                    try:
                        existing = json.load(f)
                        if not isinstance(existing, list):
                            existing = []
                    except Exception:
                        existing = []
            else:
                existing = []
            # Prepend new reservation
            new_data = [reservation_data] + existing
            with open(path, "w") as f:
                json.dump(new_data, f, indent=2)
            logger.info(f"Reservation data prepended to {path}")
        except Exception as e:
            logger.error(f"❌ Error saving reservation data to JSON: {e}")
            return False

        # Insert into DB using DBInsertion
        try:
            db = DBInsertion(**self.DB_CONFIG)
            db.insert_reservation(
                customer_name=reservation_data["customer_name"],
                reservation_time=reservation_data["reservation_time"],
                guests=reservation_data["guests"],
                table_number=reservation_data["table_number"]
            )
            db.commit_and_close()
            logger.info("Reservation inserted into DB.")
            return True
        except Exception as e:
            logger.error(f"❌ Error inserting reservation into DB: {e}")
            return False


    @function_tool()
    async def provide_menu(self, context: RunContext_T) -> str:
        """Provide the menu to the user in a friendly way."""
        return f"Here's our menu! {MENU_STR}. What would you like to order today?"

    @function_tool()
    async def get_menu_price(
        self,
        item_name: Annotated[str, Field(description="The menu item to get the price for")],
        context: RunContext_T,
    ) -> str:
        """Provide the price for a specific menu item."""
        price = MENU_PRICES.get(item_name.title())
        if price is not None:
            return f"The price of {item_name.title()} is Rs. {price:.2f}."
        else:
            return f"Sorry, {item_name} is not on our menu."



    @function_tool()
    async def make_reservation(
        self,
        time: Annotated[str, Field(description="The reservation time")],
        name: Annotated[str, Field(description="The customer's name")],
        phone: Annotated[str, Field(description="The customer's phone number")],
        guests: Annotated[int, Field(description="Number of guests")],
        table_number: Annotated[int, Field(description="Table number")],
        context: RunContext_T,
    ) -> str:
        """Take a reservation from the user and insert into DB."""
        userdata = context.userdata
        userdata.reservation_time = time
        userdata.customer_name = name
        userdata.customer_phone = phone
        userdata.guests = guests
        userdata.table_number = table_number
        userdata.is_reservation = True
        db_result = self.insert_reservation_into_db(userdata)
        if db_result:
            return f"Great! Your reservation is set for {name} at {time} for {guests} guests (table {table_number}). We'll reach you at {phone} if needed. Anything else I can help you with?"
        else:
            return "Sorry, there was a problem saving your reservation. Please try again."



    @function_tool()
    async def update_order(
        self,
        items: Annotated[list[dict], Field(description="The items of the order, each as a dict with item_name, quantity, special_instructions")],
        context: RunContext_T,
    ) -> str:
        """Take or update the user's order, and ask if it's for delivery or pickup. Insert into DB at the end."""
        userdata = context.userdata
        userdata.order = items
        total = 0
        not_found = []
        for item in items:
            price = MENU_PRICES.get(item["item_name"].title())
            if price:
                total += price * int(item.get("quantity", 1))
            else:
                not_found.append(item["item_name"])
        userdata.total = total
        if not_found:
            return f"I've added these items: {items}. Note: {not_found} are not on our menu. Your current total is ${total}. Is this order for delivery or pickup?"
        return f"Yum! I've added {items} to your order. Your total is ${total}. Is this for delivery or pickup?"

    @function_tool()
    async def set_delivery_address(
        self,
        address: Annotated[str, Field(description="The delivery address")],
        context: RunContext_T,
    ) -> str:
        """Save the delivery address if the user wants delivery."""
        userdata = context.userdata
        userdata.delivery_address = address
        return f"Thanks! We'll deliver to: {address}. How would you like to pay, credit or cash?"


    @function_tool()
    async def confirm_payment(
        self,
        method: Annotated[str, Field(description="Payment method: 'credit' or 'cash'")],
        context: RunContext_T,
    ) -> str:
        """Confirm payment method and collect info if needed. If delivery, confirm address."""
        userdata = context.userdata
        if not userdata.order or userdata.total is None:
            return "Please place your order first."
        if method.lower() not in ["credit", "cash"]:
            return "Please specify payment as 'credit' or 'cash'."
        userdata.payment_method = method.lower()
        if userdata.delivery_address:
            delivery_msg = f"Your order will be delivered to {userdata.delivery_address}. "
        else:
            delivery_msg = "Please pick up your order at the restaurant. "
        if userdata.payment_method == "credit":
            return delivery_msg + "How would you like to provide your credit card number?"
        else:
            return delivery_msg + f"You chose to pay by cash. Your total is ${userdata.total}. Please pay on delivery or at pickup."


    @function_tool()
    async def provide_credit_card(
        self,
        card_number: Annotated[str, Field(description="Credit card number")],
        context: RunContext_T,
    ) -> str:
        """Collect credit card number if user pays by credit, then confirm all details."""
        userdata = context.userdata
        if userdata.payment_method != "credit":
            return "You have not chosen to pay by credit."
        userdata.credit_card = card_number
        summary = self._confirmation_summary(userdata)
        return f"Thanks! Payment by credit card ending in {card_number[-4:]}. {summary}"


    @function_tool()
    async def confirm_all_details(self, context: RunContext_T) -> str:
        """Confirm all collected information with the user in a friendly way, and insert into DB."""
        userdata = context.userdata
        summary = self._confirmation_summary(userdata)
        if userdata.is_reservation:
            db_result = self.insert_reservation_into_db(userdata)
            if db_result:
                return summary + "\nReservation saved to our system!"
            else:
                return summary + "\nSorry, there was a problem saving your reservation."
        else:
            db_result = self.insert_order_into_db(userdata)
            if db_result:
                return summary + "\nOrder saved to our system!"
            else:
                return summary + "\nSorry, there was a problem saving your order."

    def _confirmation_summary(self, userdata: UserData) -> str:
        lines = [
            "Here's your order summary:",
            f"Name: {userdata.customer_name or 'unknown'}",
            f"Phone: {userdata.customer_phone or 'unknown'}",
        ]
        if userdata.reservation_time:
            lines.append(f"Reservation time: {userdata.reservation_time}")
        if userdata.order:
            # Format each order item as a string
            order_lines = []
            for item in userdata.order:
                if isinstance(item, dict):
                    name = item.get('item_name', 'unknown')
                    qty = item.get('quantity', 1)
                    special = item.get('special_instructions', '')
                    if special:
                        order_lines.append(f"{name} x{qty} (Special: {special})")
                    else:
                        order_lines.append(f"{name} x{qty}")
                else:
                    order_lines.append(str(item))
            lines.append(f"Order: {', '.join(order_lines)} (Total: ${userdata.total})")
        if userdata.delivery_address:
            lines.append(f"Delivery address: {userdata.delivery_address}")
        if userdata.payment_method:
            lines.append(f"Payment method: {userdata.payment_method}")
        if userdata.payment_method == "credit" and userdata.credit_card:
            lines.append(f"Credit card ending in {userdata.credit_card[-4:]}")
        lines.append("If everything looks good, your order/reservation is confirmed! Thank you for choosing us!")
        return "\n".join(lines)

    @function_tool()
    async def update_name(
        self,
        name: Annotated[str, Field(description="The customer's name")],
        context: RunContext_T,
    ) -> str:
        userdata = context.userdata
        userdata.customer_name = name
        return f"Name updated to {name}."

    @function_tool()
    async def update_phone(
        self,
        phone: Annotated[str, Field(description="The customer's phone number")],
        context: RunContext_T,
    ) -> str:
        userdata = context.userdata
        userdata.customer_phone = phone
        return f"Phone number updated to {phone}."

    @function_tool()
    async def summarize_user(self, context: RunContext_T) -> str:
        """Summarize the current user data."""
        return context.userdata.summarize()


async def entrypoint(ctx: JobContext):
    await ctx.connect()
    userdata = UserData()
    session = AgentSession[UserData](
        userdata=userdata,
        stt=deepgram.STT(),
        llm=LLM(model="gemini-2.5-flash-preview-05-20", temperature=0.3, vertexai=True,thinking_config=  types.ThinkingConfig(thinking_budget=0)),
        tts=deepgram.TTS(),
        vad=silero.VAD.load(),
        max_tool_steps=5,
    )
    await session.start(
        agent=RestaurantAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(),
    )
    await session.say("Welcome to our restaurant! How may I assist you today?")

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))