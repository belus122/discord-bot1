import discord
from discord.ext import commands, tasks
import sqlite3
from datetime import datetime
import pytz

import os

TOKEN = os.getenv("TOKEN")

KST = pytz.timezone("Asia/Seoul")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

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

conn.commit()

#  설정 명령어 
@bot.command()
@commands.has_permissions(administrator=True)
async def 출석설정(ctx, option=None, *args):

    if option == "채널":
        cursor.execute("""
        INSERT OR IGNORE INTO settings (guild_id)
        VALUES (?)
        """, (ctx.guild.id,))
        cursor.execute("""
        UPDATE settings SET channel_id=? WHERE guild_id=?
        """, (ctx.channel.id, ctx.guild.id))
        conn.commit()
        await ctx.send("설정 완료")

    elif option == "시간":
        if len(args) < 2:
            return await ctx.send("시간 형식: !출석설정 시간 8 30")

        hour = int(args[0])
        minute = int(args[1])

        cursor.execute("""
        INSERT OR IGNORE INTO settings (guild_id)
        VALUES (?)
        """, (ctx.guild.id,))
        cursor.execute("""
        UPDATE settings SET hour=?, minute=? WHERE guild_id=?
        """, (hour, minute, ctx.guild.id))
        conn.commit()
        await ctx.send("설정 완료")

    elif option == "메시지":
        message = " ".join(args)
        if not message:
            return await ctx.send("메시지를 입력하세요")

        cursor.execute("""
        INSERT OR IGNORE INTO settings (guild_id)
        VALUES (?)
        """, (ctx.guild.id,))
        cursor.execute("""
        UPDATE settings SET message=? WHERE guild_id=?
        """, (message, ctx.guild.id))
        conn.commit()
        await ctx.send("설정 완료")

    else:
        await ctx.send("출석설정 채널 / 시간 / 메시지")

# 자동 메시지 
@tasks.loop(minutes=1)
async def auto_attendance():
    now = datetime.now(KST)

    cursor.execute("SELECT * FROM settings")
    rows = cursor.fetchall()

    for guild_id, channel_id, hour, minute, message in rows:

        # 설정이 모두 되어있을 때만 실행
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

#  출석 
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

@bot.event
async def on_ready():
    auto_attendance.start()

bot.run(os.getenv("TOKEN"))
