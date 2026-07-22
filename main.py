import asyncio
import datetime
import os
import sys
import traceback
import discord
from discord.ext import commands
from dotenv import load_dotenv

# .env ファイルの読み込み
load_dotenv()
TOKEN = os.getenv("token")

intents = discord.Intents.default()
intents.message_content = True  # テキストコマンド読み取りに必須
intents.voice_states = True     # ボイスチャンネル接続に必須


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None) # デフォルトhelpを完全に無効化

    async def setup_hook(self):
        # cogs フォルダ内のファイルを自動ロード
        cogs_dir = "./cogs"
        if os.path.exists(cogs_dir):
            for filename in os.listdir(cogs_dir):
                if filename.endswith(".py"):
                    cog_name = f"cogs.{filename[:-3]}"
                    try:
                        await self.load_extension(cog_name)
                        print(f"✅ Loaded Cog: {filename[:-3]}")
                    except Exception as e:
                        print(f"❌ Failed to load Cog {filename[:-3]}: {e}")

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # コマンド実行時の簡易ログ
        if message.content.startswith("!"):
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{now}] [COMMAND] {message.author}: {message.content}")

        await self.process_commands(message)

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, (commands.CommandNotFound, commands.MissingPermissions, commands.NotOwner)):
            return

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] [ERROR] {ctx.author} failed: {error}")
        await ctx.send("❌ コマンドの実行中にエラーが発生しました。")

    async def on_ready(self):
        print(f"Logged in as {self.user.name} (ID: {self.user.id})")
        print("------")


bot = MyBot()


# --- 一般コマンド ---

@bot.command(name="help")
async def custom_help(ctx: commands.Context):
    """!sm 以外の一般コマンドの説明一覧を表示"""
    embed = discord.Embed(
        title="📖 コマンド一覧",
        description="利用可能なコマンド一覧です。",
        color=discord.Color.blue()
    )

    # 管理用(!sm_) と help 自身を除外して取得
    commands_to_show = [
        cmd for cmd in bot.commands 
        if not cmd.hidden and not cmd.name.startswith("sm_") and cmd.name != "help"
    ]

    if not commands_to_show:
        embed.add_field(name="お知らせ", value="現在利用可能なコマンドはありません。", inline=False)
    else:
        for cmd in commands_to_show:
            aliases_str = f" (エイリアス: {', '.join(f'!{a}' for a in cmd.aliases)})" if cmd.aliases else ""
            doc_str = cmd.help if cmd.help else "（説明はありません）"
            embed.add_field(
                name=f"`!{cmd.name}`{aliases_str}",
                value=doc_str,
                inline=False
            )

    await ctx.send(embed=embed)


# --- オーナー管理用コマンド (!sm_) ---

@bot.command(name="sm_servers")
@commands.is_owner()
async def sm_servers(ctx: commands.Context):
    """【オーナー限定】所属しているサーバー一覧とメンバー数を表示"""
    guilds = bot.guilds
    if not guilds:
        return await ctx.send("現在どのサーバーにも参加していません。")

    embed = discord.Embed(
        title=f"🌐 参加サーバー一覧 (計 {len(guilds)} サーバー)",
        color=discord.Color.green()
    )

    guild_list_str = ""
    for guild in guilds:
        guild_list_str += f"・**{guild.name}** (ID: `{guild.id}`) - メンバー数: {guild.member_count}人\n"

    if len(guild_list_str) > 4000:
        guild_list_str = guild_list_str[:3900] + "\n...（省略されました）"

    embed.description = guild_list_str
    await ctx.send(embed=embed)


@bot.command(name="sm_restart")
@commands.is_owner()
async def sm_restart(ctx: commands.Context):
    """【オーナー限定】VCを切断した上でBotのプロセスを終了（再起動処理）"""
    await ctx.send("🔄 **再起動処理を実行中 (VCを切断してプロセスを終了します)**")
    print("[SYSTEM] Disconnecting from VCs and exiting process...")

    for vc in bot.voice_clients:
        try:
            await vc.disconnect()
        except Exception as e:
            print(f"[VC切断エラー]: {e}")

    await bot.close()
    sys.exit(0)


# --- 起動処理 ---

async def main():
    if not TOKEN:
        print("エラー: .env からトークンが読み込めませんでした。")
        return

    try:
        async with bot:
            await bot.start(TOKEN)
    except Exception as e:
        with open("error_log.txt", "w", encoding="utf-8") as f:
            f.write("⚠️ 起動エラーが発生しました:\n")
            f.write(traceback.format_exc())
        raise e


if __name__ == "__main__":
    asyncio.run(main())