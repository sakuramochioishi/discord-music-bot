import asyncio
import datetime
import os
import traceback
import discord
from discord.ext import commands
from dotenv import load_dotenv

# .env ファイルの読み込み
load_dotenv()
TOKEN = os.getenv("token")  # .env の記述に合わせて "DISCORD_TOKEN" 等に変更してください

intents = discord.Intents.default()
intents.message_content = True  # テキストコマンド読み取りに必須
intents.voice_states = True     # ボイスチャンネル接続に必須


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.remove_command("help")

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
        if isinstance(error, (commands.CommandNotFound, commands.MissingPermissions)):
            return

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] [ERROR] {ctx.author} failed: {error}")
        await ctx.send("❌ コマンドの実行中にエラーが発生しました。")

    async def on_ready(self):
        print(f"Logged in as {self.user.name} (ID: {self.user.id})")
        print("------")


bot = MyBot()


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