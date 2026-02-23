import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
from datetime import datetime
import pytz
import os

# ==========================
# 서버 ID 입력 (중요)
# ==========================
GUILD_ID = 1449765298918916240  # ← 여기에 서버 ID 숫자 넣기

TOKEN = os.getenv("TOKEN")

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
# PREFIX 출석
# ==========================

@bot.command()
async def 출석(ctx):

    success, result = process_attendance(ctx.author.id, ctx.guild.id)

    if not success:
        return await ctx.send("이미 오늘 출석했습니다")

    leveled_up, level = result

    if leveled_up:
        await ctx.send(f"🎉 레벨업! 현재 레벨: {level}")
    else:
        await ctx.send("출석 완료! +100포인트")

# ==========================
# SLASH 명령어 (서버 전용)
# ==========================

guild_obj = discord.Object(id=GUILD_ID)

@tree.command(name="출석", description="출석 체크", guild=guild_obj)
async def slash_attendance(interaction: discord.Interaction):

    success, result = process_attendance(interaction.user.id, interaction.guild.id)

    if not success:
        return await interaction.response.send_message("이미 오늘 출석했습니다", ephemeral=True)

    leveled_up, level = result

    if leveled_up:
        await interaction.response.send_message(f"🎉 레벨업! 현재 레벨: {level}")
    else:
        await interaction.response.send_message("출석 완료! +100포인트")

@tree.command(name="스탯", description="내 스탯 확인", guild=guild_obj)
async def slash_stat(interaction: discord.Interaction):

    cursor.execute(
        "SELECT points, level, attendance_count FROM users WHERE user_id=? AND guild_id=?",
        (interaction.user.id, interaction.guild.id)
    )

    data = cursor.fetchone()

    if not data:
        return await interaction.response.send_message("데이터가 없습니다", ephemeral=True)

    points, level, count = data
    need = level * 100

    await interaction.response.send_message(
        f"📊 레벨: {level}\n포인트: {points}/{need}\n총 출석: {count}"
    )

@tree.command(name="예시", description="출석 메시지 테스트", guild=guild_obj)
async def example(interaction: discord.Interaction):

    cursor.execute(
        "SELECT channel_id, message FROM settings WHERE guild_id=?",
        (interaction.guild.id,)
    )

    result = cursor.fetchone()

    if not result:
        return await interaction.response.send_message("출석설정이 없습니다", ephemeral=True)

    channel_id, message = result
    channel = interaction.guild.get_channel(channel_id)

    if channel:
        await channel.send(
            message,
            allowed_mentions=discord.AllowedMentions(everyone=True)
        )

    await interaction.response.send_message("테스트 메시지 전송 완료", ephemeral=True)

# ==========================
# READY
# ==========================

@bot.event
async def on_ready():

    auto = await tree.sync(guild=guild_obj)

    print(f"{len(auto)}개 서버 명령어 동기화 완료")
    print(f"{bot.user} 온라인")

bot.run(TOKEN)
