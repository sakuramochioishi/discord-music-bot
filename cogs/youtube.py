import asyncio
import os
import discord
from discord.ext import commands
import yt_dlp

DELETE_DELAY = 600  # 10分 (600秒)
DOWNLOAD_DIR = "./downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "extractaudio": True,
    "audioformat": "mp3",
    "outtmpl": f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
    "noplaylist": False,
    "quiet": True,
    "no_warnings": True,
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class YouTube(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}  # サーバーごとの再生キュー

    async def delayed_delete(self, file_path: str, delay: int):
        """再生完了から指定時間後にファイルを削除"""
        await asyncio.sleep(delay)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"[自動削除完了] {file_path}")
            except Exception as e:
                print(f"[削除エラー] {file_path}: {e}")

    def play_next(self, ctx):
        """キュー内の次の曲を再生"""
        guild_id = ctx.guild.id
        if guild_id in self.queues and len(self.queues[guild_id]) > 0:
            current_item = self.queues[guild_id].pop(0)
            file_path = current_item["file_path"]

            source = discord.FFmpegPCMAudio(file_path, **FFMPEG_OPTIONS)

            def after_playing(error):
                if error:
                    print(f"[再生エラー]: {error}")

                # 10分後自動削除タスクをバックグラウンドで開始
                asyncio.run_coroutine_threadsafe(
                    self.delayed_delete(file_path, DELETE_DELAY), self.bot.loop
                )
                # 次の曲へ
                self.play_next(ctx)

            ctx.voice_client.play(source, after=after_playing)
            asyncio.run_coroutine_threadsafe(
                ctx.send(f"🎵 **再生中** {current_item['title']}"), self.bot.loop
            )
        else:
            asyncio.run_coroutine_threadsafe(
                ctx.send("再生リストが空になりました。"), self.bot.loop
            )

    # 💡 VC人数変化を検知して誰もいなくなったら自動切断する処理
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel is not None:
            # 修正: member.guild_voice_client -> member.guild.voice_client
            voice_client = member.guild.voice_client
            if voice_client and voice_client.channel.id == before.channel.id:
                human_members = [m for m in before.channel.members if not m.bot]
                if len(human_members) == 0:
                    guild_id = member.guild.id
                    if guild_id in self.queues:
                        self.queues[guild_id].clear()
                    await voice_client.disconnect()
                    print(f"[自動切断] {before.channel.name} に誰もいなくなったため自動切断しました。")

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, query: str):
        """!p <URLまたはキーワード> で再生"""
        if not ctx.author.voice:
            return await ctx.send("先にボイスチャンネルに入ってください！")

        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()

        await ctx.send("🔎 情報を取得・ダウンロード中...")

        target = query if query.startswith("http") else f"ytsearch:{query}"

        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None, lambda: ytdl.extract_info(target, download=True)
            )
        except Exception as e:
            return await ctx.send(f"動画の取得に失敗しました: {e}")

        guild_id = ctx.guild.id
        if guild_id not in self.queues:
            self.queues[guild_id] = []

        entries = data.get("entries") if "entries" in data else [data]
        added_count = 0

        for entry in entries:
            if not entry:
                continue
            file_path = ytdl.prepare_filename(entry)
            item = {
                "title": entry.get("title", "Unknown Title"),
                "file_path": file_path,
            }
            self.queues[guild_id].append(item)
            added_count += 1

        await ctx.send(f"✅ {added_count} 曲をキューに追加しました！")

        if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
            self.play_next(ctx)

    @commands.command(name="skip", aliases=["s"])
    async def skip(self, ctx):
        """!s でスキップ"""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("⏭️ スキップしました。")
        else:
            await ctx.send("現在再生中の曲はありません。")

    @commands.command(name="stop")
    async def stop(self, ctx):
        """!stop で停止＆切断"""
        guild_id = ctx.guild.id
        if guild_id in self.queues:
            self.queues[guild_id].clear()

        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("⏹️ 停止して切断しました。")


async def setup(bot):
    await bot.add_cog(YouTube(bot)) 