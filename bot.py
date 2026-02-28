import discord
from discord.ext import commands
from flask import Flask, request, jsonify
import threading
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import asyncio

load_dotenv()

TOKEN = os.getenv("TOKEN")
SEPAY_SECRET = os.getenv("SEPAY_SECRET")
MONGO_URI = os.getenv("MONGO_URI")
BANK_ACC = os.getenv("BANK_ACC")
BANK_CODE = os.getenv("BANK_CODE")
PANEL_CHANNEL_ID = int(os.getenv("PANEL_CHANNEL_ID"))

client = MongoClient(MONGO_URI)
db = client["shopbot"]
users = db["users"]
keys = db["keys"]
transactions = db["transactions"]
settings = db["settings"]

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

app = Flask(__name__)

# ================= WEBHOOK SEPAY =================

@app.route("/webhook", methods=["POST"])
def webhook():
    secret = request.headers.get("Authorization")
    if secret != SEPAY_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json

    if data.get("status") != "success":
        return jsonify({"message": "ignored"})

    transaction_id = data.get("transaction_id")
    amount = int(data.get("amount"))
    content = data.get("content").strip()

    # chống trùng giao dịch
    if transactions.find_one({"transaction_id": transaction_id}):
        return jsonify({"message": "duplicate"}), 200

    transactions.insert_one({
        "transaction_id": transaction_id,
        "amount": amount,
        "user_id": content
    })

    users.update_one(
        {"user_id": content},
        {"$inc": {"balance": amount}},
        upsert=True
    )

    asyncio.run_coroutine_threadsafe(
        send_notify(content, amount),
        bot.loop
    )

    return jsonify({"message": "ok"}), 200

async def send_notify(user_id, amount):
    user = await bot.fetch_user(int(user_id))
    if user:
        await user.send(f"✅ Nạp thành công {amount:,} VND")

# ================= VIEW =================

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💰 Nạp tiền", style=discord.ButtonStyle.green)
    async def nap(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NapModal())

    @discord.ui.button(label="💳 Số dư", style=discord.ButtonStyle.gray)
    async def balance(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = users.find_one({"user_id": str(interaction.user.id)})
        bal = user["balance"] if user else 0
        await interaction.response.send_message(f"Số dư: {bal:,} VND", ephemeral=True)

    @discord.ui.button(label="🛒 Mua key", style=discord.ButtonStyle.blurple)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Dùng lệnh:\n!buy day\n!buy week\n!buy month",
            ephemeral=True
        )

class NapModal(discord.ui.Modal, title="Nhập số tiền muốn nạp"):
    amount = discord.ui.TextInput(label="Số tiền")

    async def on_submit(self, interaction: discord.Interaction):
        amount = int(self.amount.value)
        user_id = str(interaction.user.id)

        qr_url = f"https://qr.sepay.vn/img?acc={BANK_ACC}&bank={BANK_CODE}&amount={amount}&des={user_id}"

        embed = discord.Embed(title="Quét QR để nạp tiền")
        embed.description = f"Số tiền: {amount:,} VND\nNội dung: `{user_id}`"
        embed.set_image(url=qr_url)

        await interaction.response.send_message(embed=embed, ephemeral=True)

# ================= BUY =================

@bot.command()
async def buy(ctx, type_key):
    product = keys.find_one({"type": type_key})
    if not product:
        await ctx.send("Không tồn tại sản phẩm")
        return

    if len(product.get("stock", [])) == 0:
        await ctx.send("Hết hàng")
        return

    user = users.find_one({"user_id": str(ctx.author.id)})
    balance = user["balance"] if user else 0

    if balance < product["price"]:
        await ctx.send("Không đủ tiền")
        return

    key = product["stock"].pop(0)

    users.update_one(
        {"user_id": str(ctx.author.id)},
        {"$inc": {"balance": -product["price"]}}
    )

    keys.update_one(
        {"type": type_key},
        {"$set": {"stock": product["stock"]}}
    )

    await ctx.author.send(f"🎉 Key của bạn: {key}")
    await ctx.send("Mua thành công! Check DM")

# ================= ADMIN ADD KEY =================

@bot.command()
async def addkey(ctx, type_key, price: int, *, key_value):
    if not ctx.author.guild_permissions.administrator:
        return

    keys.update_one(
        {"type": type_key},
        {
            "$setOnInsert": {"price": price},
            "$push": {"stock": key_value}
        },
        upsert=True
    )

    await ctx.send("Đã thêm key")

# ================= AUTO PANEL =================

async def send_panel():
    await bot.wait_until_ready()
    channel = bot.get_channel(PANEL_CHANNEL_ID)

    embed = discord.Embed(title="🛒 SHOP AUTO SEPAY")
    embed.description = "💰 Nạp tiền | 🛒 Mua key | 💳 Số dư"

    panel_data = settings.find_one({"type": "panel"})

    if not panel_data:
        msg = await channel.send(embed=embed, view=MainView())
        settings.insert_one({"type": "panel", "message_id": msg.id})
    else:
        try:
            await channel.fetch_message(panel_data["message_id"])
        except:
            msg = await channel.send(embed=embed, view=MainView())
            settings.update_one({"type": "panel"}, {"$set": {"message_id": msg.id}})

@bot.event
async def on_ready():
    print("Bot Online")
    bot.add_view(MainView())
    bot.loop.create_task(send_panel())

# ================= RUN =================

def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(TOKEN)
