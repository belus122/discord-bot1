import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
from datetime import datetime
import pytz
import os

# ==============================
# 서버 ID (반드시 수정)
# ==============================
GUILD_ID = 1449765298918916240

TOKEN = os.getenv("TOKEN")

KST = pytz.timezone("Asia/Seoul")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree
guild_obj = discord.Object(id=GUILD_ID)

# ==============================
# DB 설정
# ==============================
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

# ==============================
# 레벨 계산
# ==============================

def check_level_up(user_id, guild_id):

    cursor.execute(
        "SELECT points, level FROM users WHERE user_id=? AND guild_id=?",
        (user_id, guild_id)
    )
    points, level = cursor.fetchone()

    leveled = False

    while points >= level * 100:
        points -= level * 100
        level += 1
        leveled = True

    cursor.execute(
        "UPDATE users SET points=?, level=? WHERE user_id=? AND guild_id=?",
        (points, level, user_id, guild_id)
    )
    conn.commit()

    return leveled, level

# ==============================
# 출석 처리
# ==============================

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

# ==============================
# SLASH 명령어
# ==============================

@tree.command(name="출석", description="출석 체크", guild=guild_obj)
async def 출석(interaction: discord.Interaction):

    success, result = process_attendance(interaction.user.id, interaction.guild.id)

    if not success:
        return await interaction.response.send_message("이미 오늘 출석했습니다", ephemeral=True)

    leveled, level = result

    if leveled:
        await interaction.response.send_message(f"🎉 레벨업! 현재 레벨: {level}")
    else:
        await interaction.response.send_message("출석 완료! +100포인트")

@tree.command(name="스탯", description="내 정보 확인", guild=guild_obj)
async def 스탯(interaction: discord.Interaction):

    cursor.execute(
        "SELECT points, level, attendance_count FROM users WHERE user_id=? AND guild_id=?",
        (interaction.user.id, interaction.guild.id)
    )
    data = cursor.fetchone()

    if not data:
        return await interaction.response.send_message("데이터 없음", ephemeral=True)

    points, level, count = data
    need = level * 100

    await interaction.response.send_message(
        f"📊 레벨: {level}\n포인트: {points}/{need}\n총 출석: {count}"
    )

@tree.command(name="랭킹", description="출석 랭킹", guild=guild_obj)
async def 랭킹(interaction: discord.Interaction):

    cursor.execute(
        "SELECT user_id, attendance_count FROM users WHERE guild_id=? ORDER BY attendance_count DESC LIMIT 10",
        (interaction.guild.id,)
    )
    rows = cursor.fetchall()

    if not rows:
        return await interaction.response.send_message("랭킹 데이터 없음")

    text = "🏆 출석 랭킹 TOP10\n"

    for i, (user_id, count) in enumerate(rows, start=1):
        user = await bot.fetch_user(user_id)
        text += f"{i}. {user.name} - {count}회\n"

    await interaction.response.send_message(text)

@tree.command(name="출석설정", description="출석 설정", guild=guild_obj)
@app_commands.describe(
    채널="출석 메시지 보낼 채널",
    시간="시간 (0~23)",
    분="분 (0~59)",
    메시지="출석 안내 메시지"
)
async def 출석설정(
    interaction: discord.Interaction,
    채널: discord.TextChannel,
    시간: int,
    분: int,
    메시지: str
):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("관리자만 사용 가능", ephemeral=True)

    cursor.execute("""
    INSERT OR REPLACE INTO settings
    (guild_id, channel_id, hour, minute, message)
    VALUES (?, ?, ?, ?, ?)
    """, (
        interaction.guild.id,
        채널.id,
        시간,
        분,
        메시지
    ))

    conn.commit()

    await interaction.response.send_message("✅ 출석 설정 완료", ephemeral=True)

# ==============================
# 자동 출석 메시지
# ==============================

@tasks.loop(minutes=1)
async def auto_attendance():

    now = datetime.now(KST)

    cursor.execute("SELECT * FROM settings")
    rows = cursor.fetchall()

    for guild_id, channel_id, hour, minute, message in rows:

        if now.hour == hour and now.minute == minute:

            guild = bot.get_guild(guild_id)

            if guild:
                channel = guild.get_channel(channel_id)
                if channel:
                    await channel.send(
                        message,
                        allowed_mentions=discord.AllowedMentions(everyone=True)
                    )

@auto_attendance.before_loop
async def before_loop():
    await bot.wait_until_ready()

# ==============================
# READY
# ==============================

@bot.event
async def on_ready():

    auto_attendance.start()

    await tree.clear_commands(guild=guild_obj)
    synced = await tree.sync(guild=guild_obj)

    print(f"{len(synced)}개 명령어 동기화 완료")
    print(f"{bot.user} 온라인")

bot.run(TOKEN)
