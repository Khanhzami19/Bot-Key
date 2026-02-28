import discord
from discord.ext import commands
from discord import app_commands
import json
import qrcode
import os

TOKEN = "YOUR_BOT_TOKEN"
ADMIN_ID = 123456789  # đổi thành ID admin của bạn

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- LOAD DATA ----------------

def load_balance():
    with open("data.json", "r") as f:
        return json.load(f)

def save_balance(data):
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)

def load_keys():
    with open("keys.json", "r") as f:
        return json.load(f)

def save_keys(data):
    with open("keys.json", "w") as f:
        json.dump(data, f, indent=4)

# ---------------- QR FUNCTION ----------------

def generate_qr(user_id, amount):
    qr_data = f"PAY|USER:{user_id}|AMOUNT:{amount}"
    img = qrcode.make(qr_data)
    file_path = f"qr_{user_id}.png"
    img.save(file_path)
    return file_path

# ---------------- VIEW ----------------

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💰 Nạp tiền", style=discord.ButtonStyle.green)
    async def nap_tien(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NapModal())

    @discord.ui.button(label="💳 Số dư", style=discord.ButtonStyle.blurple)
    async def so_du(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_balance()
        bal = data.get(str(interaction.user.id), 0)
        await interaction.response.send_message(f"Số dư của bạn: {bal:,} VND", ephemeral=True)

class NapModal(discord.ui.Modal, title="Nhập số tiền muốn nạp"):
    amount = discord.ui.TextInput(label="Số tiền (VND)", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value)
        except:
            await interaction.response.send_message("Số tiền không hợp lệ!", ephemeral=True)
            return

        file_path = generate_qr(interaction.user.id, amount)
        file = discord.File(file_path)

        await interaction.response.send_message(
            f"Quét QR để nạp {amount:,} VND\n(Sau khi chuyển tiền admin dùng lệnh cộng tiền)",
            file=file,
            ephemeral=True
        )

# ---------------- ADMIN COMMAND ----------------

@bot.command()
async def addkey(ctx, type_key, *, key_value):
    if ctx.author.id != ADMIN_ID:
        return

    keys = load_keys()
    if type_key not in keys:
        await ctx.send("Loại key không tồn tại (day/week/month)")
        return

    keys[type_key]["stock"].append(key_value)
    save_keys(keys)
    await ctx.send(f"Đã thêm key vào {keys[type_key]['label']}")

@bot.command()
async def addmoney(ctx, user: discord.Member, amount: int):
    if ctx.author.id != ADMIN_ID:
        return

    data = load_balance()
    data[str(user.id)] = data.get(str(user.id), 0) + amount
    save_balance(data)
    await ctx.send(f"Đã cộng {amount:,} VND cho {user.mention}")

# ---------------- BUY COMMAND ----------------

@bot.command()
async def buy(ctx, type_key):
    keys = load_keys()
    data = load_balance()

    if type_key not in keys:
        await ctx.send("Loại sản phẩm không tồn tại")
        return

    price = keys[type_key]["price"]
    stock = keys[type_key]["stock"]

    user_balance = data.get(str(ctx.author.id), 0)

    if user_balance < price:
        await ctx.send("Bạn không đủ tiền!")
        return

    if len(stock) == 0:
        await ctx.send("Hết hàng!")
        return

    key = stock.pop(0)
    data[str(ctx.author.id)] -= price

    save_keys(keys)
    save_balance(data)

    await ctx.author.send(f"Bạn đã mua {keys[type_key]['label']}\nKey: {key}")
    await ctx.send("Mua thành công! Check DM")

# ---------------- START ----------------

@bot.event
async def on_ready():
    print("Bot đã online!")

@bot.command()
async def panel(ctx):
    embed = discord.Embed(title="HỆ THỐNG NẠP & MUA KEY")
    embed.description = "Chọn chức năng bên dưới"
    await ctx.send(embed=embed, view=MainView())

bot.run(TOKEN)
