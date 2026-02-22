import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
from datetime import datetime
import pytz
import os

# ==========================
# 기본 설정
# ==========================

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("TOKEN 환경변수가 설정되지 않았습니다")

KST = pytz.timezone("Asia/Seoul")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ==========================
# DB 설정
# ==========================

conn = sqlite3.connect("attendance.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS settings (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    hour INTEGER,
    minute INTEGER,
    message TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    user_id INTEGER,
    guild_id INTEGER,
    date TEXT,
    PRIMARY KEY (user_id, guild_id, date)
)
""")

conn.commit()

# ==========================
# ! 출석설정 (prefix)
# ==========================

@bot.command()
@commands.has_permissions(administrator=True)
async def 출석설정(ctx, option=None, *args):

    if not option:
        return await ctx.send("출석설정 채널 / 시간 / 메시지")

    cursor.execute("INSERT OR IGNORE INTO settings (guild_id) VALUES (?)", (ctx.guild.id,))

    if option == "채널":
        cursor.execute(
            "UPDATE settings SET channel_id=? WHERE guild_id=?",
            (ctx.channel.id, ctx.guild.id)
        )

    elif option == "시간":
        if len(args) < 2:
            return await ctx.send("형식: !출석설정 시간 9 30")

        hour = int(args[0])
        minute = int(args[1])

        cursor.execute(
            "UPDATE settings SET hour=?, minute=? WHERE guild_id=?",
            (hour, minute, ctx.guild.id)
        )

    elif option == "메시지":
        message = " ".join(args)
        if not message:
            return await ctx.send("메시지를 입력하세요")

        cursor.execute(
            "UPDATE settings SET message=? WHERE guild_id=?",
            (message, ctx.guild.id)
        )

    else:
        return await ctx.send("채널 / 시간 / 메시지 중 입력")

    conn.commit()
    await ctx.send("설정 완료")

# ==========================
# ! 출석 (prefix)
# ==========================

@bot.command()
async def 출석(ctx):

    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")

    cursor.execute("""
    SELECT 1 FROM attendance
    WHERE user_id=? AND guild_id=? AND date=?
    """, (ctx.author.id, ctx.guild.id, today))

    if cursor.fetchone():
        return await ctx.send("이미 출석")

    cursor.execute("""
    INSERT INTO attendance (user_id, guild_id, date)
    VALUES (?, ?, ?)
    """, (ctx.author.id, ctx.guild.id, today))

    conn.commit()
    await ctx.send("출석 완료")

# ==========================
# / 출석 (slash)
# ==========================

@tree.command(name="출석", description="출석 체크")
async def slash_attendance(interaction: discord.Interaction):

    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")

    cursor.execute("""
    SELECT 1 FROM attendance
    WHERE user_id=? AND guild_id=? AND date=?
    """, (interaction.user.id, interaction.guild.id, today))

    if cursor.fetchone():
        return await interaction.response.send_message("이미 출석", ephemeral=True)

    cursor.execute("""
    INSERT INTO attendance (user_id, guild_id, date)
    VALUES (?, ?, ?)
    """, (interaction.user.id, interaction.guild.id, today))

    conn.commit()
    await interaction.response.send_message("출석 완료")

# ==========================
# / 출석설정 (slash)
# ==========================

@tree.command(name="출석설정", description="출석 설정")
@app_commands.describe(
    옵션="채널 / 시간 / 메시지",
    값1="시간 또는 메시지",
    값2="분 (시간 설정시)"
)
async def slash_setting(
    interaction: discord.Interaction,
    옵션: str,
    값1: str = None,
    값2: str = None
):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("관리자만 사용 가능", ephemeral=True)

    guild_id = interaction.guild.id
    cursor.execute("INSERT OR IGNORE INTO settings (guild_id) VALUES (?)", (guild_id,))

    if 옵션 == "채널":
        cursor.execute(
            "UPDATE settings SET channel_id=? WHERE guild_id=?",
            (interaction.channel.id, guild_id)
        )

    elif 옵션 == "시간":
        if not 값1 or not 값2:
            return await interaction.response.send_message("예: 옵션=시간 값1=9 값2=30", ephemeral=True)

        hour = int(값1)
        minute = int(값2)

        cursor.execute(
            "UPDATE settings SET hour=?, minute=? WHERE guild_id=?",
            (hour, minute, guild_id)
        )

    elif 옵션 == "메시지":
        if not 값1:
            return await interaction.response.send_message("메시지를 입력하세요", ephemeral=True)

        cursor.execute(
            "UPDATE settings SET message=? WHERE guild_id=?",
            (값1, guild_id)
        )

    else:
        return await interaction.response.send_message("채널 / 시간 / 메시지 중 입력", ephemeral=True)

    conn.commit()
    await interaction.response.send_message("설정 완료")

# ==========================
# 자동 출석 메시지
# ==========================

@tasks.loop(minutes=1)
async def auto_attendance():

    now = datetime.now(KST)
    cursor.execute("SELECT * FROM settings")
    rows = cursor.fetchall()

    for guild_id, channel_id, hour, minute, message in rows:

        if not all([channel_id, hour is not None, minute is not None, message]):
            continue

        if now.hour == hour and now.minute == minute:
            guild = bot.get_guild(guild_id)
            if guild:
                channel = guild.get_channel(channel_id)
                if channel:
                    await channel.send(message)

@auto_attendance.before_loop
async def before_auto():
    await bot.wait_until_ready()

# ==========================
# 봇 준비
# ==========================

@bot.event
async def on_ready():
    auto_attendance.start()
    await tree.sync()
    print(f"{bot.user} 온라인!")

bot.run(TOKEN)
