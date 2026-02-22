import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
from datetime import datetime
import pytz
import os

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("TOKEN 환경변수가 설정되지 않았습니다")

KST = pytz.timezone("Asia/Seoul")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# DB
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER,
    guild_id INTEGER,
    points INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    attendance_count INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, guild_id)
)
""")

conn.commit()

# ==========================
# PREFIX 출석설정 (!출석설정)
# ==========================

@bot.command()
@commands.has_permissions(administrator=True)
async def 출석설정(ctx, 옵션=None, 값1=None, 값2=None):

    if not 옵션:
        return await ctx.send("사용법: !출석설정 채널 / 시간 9 30 / 메시지 내용")

    guild_id = ctx.guild.id

    cursor.execute(
        "INSERT OR IGNORE INTO settings (guild_id) VALUES (?)",
        (guild_id,)
    )

    if 옵션 == "채널":

        cursor.execute(
            "UPDATE settings SET channel_id=? WHERE guild_id=?",
            (ctx.channel.id, guild_id)
        )

        await ctx.send("출석 채널 설정 완료")

    elif 옵션 == "시간":

        if not 값1 or not 값2:
            return await ctx.send("예: !출석설정 시간 9 30")

        cursor.execute(
            "UPDATE settings SET hour=?, minute=? WHERE guild_id=?",
            (int(값1), int(값2), guild_id)
        )

        await ctx.send("출석 시간 설정 완료")

    elif 옵션 == "메시지":

        message = f"{값1} {값2}" if 값2 else 값1

        cursor.execute(
            "UPDATE settings SET message=? WHERE guild_id=?",
            (message, guild_id)
        )

        await ctx.send("출석 메시지 설정 완료")

    else:
        await ctx.send("옵션: 채널 / 시간 / 메시지")

    conn.commit()

# ==========================
# SLASH 출석설정 (/출석설정)
# ==========================

@tree.command(name="출석설정", description="출석 설정")
@app_commands.describe(
    옵션="채널 / 시간 / 메시지",
    값1="시간 또는 메시지",
    값2="분 (시간 설정시)"
)
async def slash_setting(interaction: discord.Interaction,
                        옵션: str,
                        값1: str = None,
                        값2: str = None):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "관리자만 사용 가능",
            ephemeral=True
        )

    guild_id = interaction.guild.id

    cursor.execute(
        "INSERT OR IGNORE INTO settings (guild_id) VALUES (?)",
        (guild_id,)
    )

    if 옵션 == "채널":

        cursor.execute(
            "UPDATE settings SET channel_id=? WHERE guild_id=?",
            (interaction.channel.id, guild_id)
        )

        msg = "출석 채널 설정 완료"

    elif 옵션 == "시간":

        if not 값1 or not 값2:
            return await interaction.response.send_message(
                "예: 옵션=시간 값1=9 값2=30",
                ephemeral=True
            )

        cursor.execute(
            "UPDATE settings SET hour=?, minute=? WHERE guild_id=?",
            (int(값1), int(값2), guild_id)
        )

        msg = "출석 시간 설정 완료"

    elif 옵션 == "메시지":

        cursor.execute(
            "UPDATE settings SET message=? WHERE guild_id=?",
            (값1, guild_id)
        )

        msg = "출석 메시지 설정 완료"

    else:
        msg = "옵션 오류"

    conn.commit()

    await interaction.response.send_message(msg, ephemeral=True)

# ==========================
# 레벨 처리
# ==========================

def check_level_up(user_id, guild_id):

    cursor.execute(
        "SELECT points, level FROM users WHERE user_id=? AND guild_id=?",
        (user_id, guild_id)
    )

    points, level = cursor.fetchone()

    leveled_up = False

    while points >= level * 100:
        points -= level * 100
        level += 1
        leveled_up = True

    cursor.execute(
        "UPDATE users SET points=?, level=? WHERE user_id=? AND guild_id=?",
        (points, level, user_id, guild_id)
    )

    conn.commit()

    return leveled_up, level

# ==========================
# 출석 처리
# ==========================

def process_attendance(user_id, guild_id):

    today = datetime.now(KST).strftime("%Y-%m-%d")

    cursor.execute(
        "SELECT 1 FROM attendance WHERE user_id=? AND guild_id=? AND date=?",
        (user_id, guild_id, today)
    )

    if cursor.fetchone():
        return False, None

    cursor.execute(
        "INSERT INTO attendance VALUES (?, ?, ?)",
        (user_id, guild_id, today)
    )

    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, guild_id) VALUES (?, ?)",
        (user_id, guild_id)
    )

    cursor.execute(
        "UPDATE users SET points=points+100, attendance_count=attendance_count+1 WHERE user_id=? AND guild_id=?",
        (user_id, guild_id)
    )

    conn.commit()

    return True, check_level_up(user_id, guild_id)

# ==========================
# 출석 명령어
# ==========================

@bot.command()
async def 출석(ctx):

    success, result = process_attendance(ctx.author.id, ctx.guild.id)

    if not success:
        return await ctx.send("이미 출석했습니다")

    leveled_up, level = result

    if leveled_up:
        await ctx.send(f"레벨업! 현재 레벨: {level}")
    else:
        await ctx.send("출석 완료! +100포인트")

@tree.command(name="출석")
async def slash_attendance(interaction: discord.Interaction):

    success, result = process_attendance(interaction.user.id, interaction.guild.id)

    if not success:
        return await interaction.response.send_message("이미 출석했습니다")

    leveled_up, level = result

    if leveled_up:
        await interaction.response.send_message(f"레벨업! 현재 레벨: {level}")
    else:
        await interaction.response.send_message("출석 완료! +100포인트")

# ==========================
# 자동 메시지
# ==========================

@tasks.loop(minutes=1)
async def auto_attendance():

    now = datetime.now(KST)

    cursor.execute("SELECT * FROM settings")
    rows = cursor.fetchall()

    for guild_id, channel_id, hour, minute, message in rows:

        if channel_id and message and now.hour == hour and now.minute == minute:

            guild = bot.get_guild(guild_id)

            if guild:

                channel = guild.get_channel(channel_id)

                if channel:

                    await channel.send(
                        message,
                        allowed_mentions=discord.AllowedMentions(everyone=True)
                    )

@auto_attendance.before_loop
async def before_auto():
    await bot.wait_until_ready()

# ==========================
# READY
# ==========================

@bot.event
async def on_ready():

    auto_attendance.start()

    await tree.sync()

    print(f"{bot.user} 온라인")

bot.run(TOKEN)
