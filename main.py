import telebot
import sqlite3
import time

BOT_TOKEN = '8192579751:AAGQBSu8I7i8vNgv_W4Xnh_w2FYcApLP9cU'
ADMIN_ID = 7489027229

bot = telebot.TeleBot(BOT_TOKEN)
db = sqlite3.connect('cards.db', check_same_thread=False)
cursor = db.cursor()

# --- Database Setup ---
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 0,
    referred_by INTEGER,
    discount_used INTEGER DEFAULT 0
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    info TEXT,
    price REAL,
    type TEXT
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    card_info TEXT,
    amount REAL,
    timestamp TEXT
)
''')
db.commit()

# --- Helper Functions ---
def get_balance(user_id):
    cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

def update_balance(user_id, amount):
    cursor.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
    db.commit()

def deduct_balance(user_id, amount):
    cursor.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, user_id))
    db.commit()

def save_order(user_id, card_info, amount):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO orders (user_id, card_info, amount, timestamp) VALUES (?, ?, ?, ?)",
                   (user_id, card_info, amount, timestamp))
    db.commit()

def apply_discount(user_id, price):
    cursor.execute("SELECT discount_used FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()
    if result and result[0] == 0:
        cursor.execute("UPDATE users SET discount_used = 1 WHERE id = ?", (user_id,))
        db.commit()
        return round(price * 0.85, 2)
    return price

# --- Commands ---
@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    user_id = message.chat.id
    cursor.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (user_id,))

    if len(args) > 1 and args[1].startswith("ref="):
        ref_id = int(args[1][4:])
        if ref_id != user_id:
            cursor.execute("UPDATE users SET referred_by = ? WHERE id = ? AND referred_by IS NULL", (ref_id, user_id))
            db.commit()

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('💰 Deposit', '💼 My Wallet')
    markup.row('🧾 Buy Prepaid Cards', '📘 View All CCs')
    markup.row('💳 Buy CCs - $15', '📦 My Orders')
    markup.row('📦 Preorder Balance')
    if user_id == ADMIN_ID:
        markup.row('🛠 Admin Panel')
    bot.send_message(user_id, f"👋 Welcome to Prepaid Haven!\nUse your referral link:\n"
                              f"https://t.me/PrepaidHavenCardBot?start=ref={user_id}", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == '💼 My Wallet')
def wallet(message):
    bal = get_balance(message.chat.id)
    bot.send_message(message.chat.id, f"💼 Your current balance: ${bal:.2f}")

@bot.message_handler(func=lambda m: m.text == '💰 Deposit')
def deposit(message):
    bot.send_message(message.chat.id, "💵 Send BTC or LTC to these addresses:\n\n"
                                      "BTC: `yourBTCwallet`\n"
                                      "LTC: `yourLTCwallet`\n\n"
                                      "Contact admin after sending to confirm.", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '🧾 Buy Prepaid Cards')
def buy_menu(message):
    markup = telebot.types.InlineKeyboardMarkup()
    for price in [50, 100, 150, 200, 250]:
        markup.add(telebot.types.InlineKeyboardButton(f"${price*2} Balance → Pay ${price}", callback_data=f'buy_{price}'))
    markup.add(telebot.types.InlineKeyboardButton("🎲 Gamble a Card ($5)", callback_data='gamble'))
    bot.send_message(message.chat.id, "💳 Choose an option:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == '📘 View All CCs')
def view_all(message):
    cursor.execute("SELECT * FROM cards WHERE type = 'fixed'")
    cards = cursor.fetchall()
    if not cards:
        bot.send_message(message.chat.id, "📭 No cards available.")
        return
    msg = "🗂 Available Cards:\n\n"
    for c in cards:
        msg += f"🆔 ID: {c[0]} - Price: ${c[2]}\n"
    bot.send_message(message.chat.id, msg)

@bot.message_handler(func=lambda m: m.text == '📦 My Orders')
def order_history(message):
    cursor.execute("SELECT card_info, amount, timestamp FROM orders WHERE user_id = ?", (message.chat.id,))
    orders = cursor.fetchall()
    if not orders:
        return bot.send_message(message.chat.id, "📦 No past orders.")
    msg = "🧾 Your Orders:\n\n"
    for o in orders:
        msg += f"{o[2]} - ${o[1]} → {o[0]}\n"
    bot.send_message(message.chat.id, msg)

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_') or call.data == 'gamble')
def handle_purchase(call):
    user_id = call.message.chat.id
    if call.data.startswith('buy_'):
        price = float(call.data.split('_')[1])
        cursor.execute("SELECT * FROM cards WHERE type = 'fixed' AND price = ? LIMIT 1", (price,))
        card = cursor.fetchone()
        if card:
            final_price = apply_discount(user_id, price)
            if get_balance(user_id) >= final_price:
                deduct_balance(user_id, final_price)
                cursor.execute("DELETE FROM cards WHERE id = ?", (card[0],))
                db.commit()
                save_order(user_id, card[1], final_price)
                cursor.execute("SELECT referred_by FROM users WHERE id = ?", (user_id,))
                ref = cursor.fetchone()
                if ref and ref[0]:
                    update_balance(ref[0], final_price * 0.15)
                bot.send_message(user_id, f"✅ Purchased:\n`{card[1]}`", parse_mode='Markdown')
            else:
                bot.send_message(user_id, "❌ Not enough balance.")
        else:
            bot.send_message(user_id, "❌ No cards left at that price.")
    elif call.data == 'gamble':
        price = 5
        cursor.execute("SELECT * FROM cards WHERE type = 'random' LIMIT 1")
        card = cursor.fetchone()
        if card and get_balance(user_id) >= price:
            deduct_balance(user_id, price)
            cursor.execute("DELETE FROM cards WHERE id = ?", (card[0],))
            db.commit()
            save_order(user_id, card[1], price)
            cursor.execute("SELECT referred_by FROM users WHERE id = ?", (user_id,))
            ref = cursor.fetchone()
            if ref and ref[0]:
                update_balance(ref[0], price * 0.15)
            bot.send_message(user_id, f"🎲 You got:\n`{card[1]}`", parse_mode='Markdown')
        else:
            bot.send_message(user_id, "❌ Not enough balance or no random cards.")

@bot.message_handler(func=lambda m: m.text == '🛠 Admin Panel' and m.chat.id == ADMIN_ID)
def admin_panel(message):
    bot.send_message(message.chat.id, "🛠 Admin Commands:\n"
                                      "/addcard fixed 100 4111111111111111|12|25|123\n"
                                      "/addcard random 4111111111111111|12|25|123\n"
                                      "/addbal USERID AMOUNT")

@bot.message_handler(commands=['addcard'])
def add_card(message):
    try:
        parts = message.text.split()
        ctype = parts[1]
        if ctype == 'fixed':
            price = float(parts[2])
            info = parts[3]
            cursor.execute("INSERT INTO cards (info, price, type) VALUES (?, ?, 'fixed')", (info, price))
        elif ctype == 'random':
            info = parts[2]
            cursor.execute("INSERT INTO cards (info, price, type) VALUES (?, 5, 'random')", (info,))
        db.commit()
        bot.send_message(message.chat.id, "✅ Card added.")
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Error: {e}")

@bot.message_handler(commands=['addbal'])
def add_balance(message):
    if message.chat.id != ADMIN_ID:
        return
    try:
        _, uid, amt = message.text.split()
        update_balance(int(uid), float(amt))
        bot.send_message(message.chat.id, "✅ Balance added.")
    except:
        bot.send_message(message.chat.id, "⚠️ Use format: /addbal USERID AMOUNT")

print("🤖 Bot is running...")
bot.infinity_polling()
