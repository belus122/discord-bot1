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

# 출석 설정
cursor.execute("""
CREATE TABLE IF NOT EXISTS settings (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    hour INTEGER,
    minute INTEGER,
    message TEXT
)
""")

# 출석 기록
cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    user_id INTEGER,
    guild_id INTEGER,
    date TEXT,
    PRIMARY KEY (user_id, guild_id, date)
)
""")

# 유저 스탯
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
# 레벨업 함수
# ==========================

def check_level_up(user_id, guild_id):
    cursor.execute("""
    SELECT points, level FROM users
    WHERE user_id=? AND guild_id=?
    """, (user_id, guild_id))

    points, level = cursor.fetchone()

    leveled_up = False

    while points >= level * 100:
        points -= level * 100
        level += 1
        leveled_up = True

    cursor.execute("""
    UPDATE users SET points=?, level=?
    WHERE user_id=? AND guild_id=?
    """, (points, level, user_id, guild_id))

    conn.commit()

    return leveled_up, level

# ==========================
# 출석 처리 함수
# ==========================

def process_attendance(user_id, guild_id):
    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")

    cursor.execute("""
    SELECT 1 FROM attendance
    WHERE user_id=? AND guild_id=? AND date=?
    """, (user_id, guild_id, today))

    if cursor.fetchone():
        return False, None

    # 출석 기록 저장
    cursor.execute("""
    INSERT INTO attendance (user_id, guild_id, date)
    VALUES (?, ?, ?)
    """, (user_id, guild_id, today))

    # 유저 없으면 생성
    cursor.execute("""
    INSERT OR IGNORE INTO users (user_id, guild_id)
    VALUES (?, ?)
    """, (user_id, guild_id))

    # 포인트 +100, 출석횟수 +1
    cursor.execute("""
    UPDATE users
    SET points = points + 100,
        attendance_count = attendance_count + 1
    WHERE user_id=? AND guild_id=?
    """, (user_id, guild_id))

    conn.commit()

    leveled_up, level = check_level_up(user_id, guild_id)

    return True, (leveled_up, level)

# ==========================
# ! 출석
# ==========================

@bot.command()
async def 출석(ctx):

    success, result = process_attendance(ctx.author.id, ctx.guild.id)

    if not success:
        return await ctx.send("이미 오늘 출석했습니다")

    leveled_up, level = result

    if leveled_up:
        await ctx.send(f"출석 완료! 🎉 레벨업! 현재 레벨: {level}")
    else:
        await ctx.send("출석 완료! +100포인트 지급")

# ==========================
# / 출석
# ==========================

@tree.command(name="출석", description="출석 체크")
async def slash_attendance(interaction: discord.Interaction):

    success, result = process_attendance(interaction.user.id, interaction.guild.id)

    if not success:
        return await interaction.response.send_message("이미 오늘 출석했습니다", ephemeral=True)

    leveled_up, level = result

    if leveled_up:
        await interaction.response.send_message(f"출석 완료! 🎉 레벨업! 현재 레벨: {level}")
    else:
        await interaction.response.send_message("출석 완료! +100포인트 지급")

# ==========================
# / 스탯
# ==========================

@tree.command(name="스탯", description="내 스탯 확인")
async def slash_stat(interaction: discord.Interaction):

    cursor.execute("""
    SELECT points, level, attendance_count
    FROM users
    WHERE user_id=? AND guild_id=?
    """, (interaction.user.id, interaction.guild.id))

    data = cursor.fetchone()

    if not data:
        return await interaction.response.send_message("데이터가 없습니다")

    points, level, count = data
    need = level * 100

    await interaction.response.send_message(
        f"""
📊 **{interaction.user.display_name}님의 스탯**

레벨: {level}
현재 포인트: {points}/{need}
총 출석 횟수: {count}
"""
    )

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
