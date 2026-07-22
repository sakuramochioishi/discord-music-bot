import asyncio
import discord
from discord.ext import commands
import yt_dlp
import random

# ストリーミング用の設定（ダウンロードしない）
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
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

    def play_next(self, ctx):
        """キュー内の次の曲を再生"""
        guild_id = ctx.guild.id
        if guild_id in self.queues and len(self.queues[guild_id]) > 0:
            current_item = self.queues[guild_id].pop(0)
            stream_url = current_item["url"]

            source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)

            def after_playing(error):
                if error:
                    print(f"[再生エラー]: {error}")

                # 無限再帰を防止するため、イベントループで安全に次の曲を呼び出し
                self.bot.loop.call_soon_threadsafe(self.play_next, ctx)

            ctx.voice_client.play(source, after=after_playing)
            asyncio.run_coroutine_threadsafe(
                ctx.send(f"🎵 **再生中** {current_item['title']}"), self.bot.loop
            )
        else:
            asyncio.run_coroutine_threadsafe(
                ctx.send("再生リストが空になりました。"), self.bot.loop
            )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """VC人数変化を検知して誰もいなくなったら自動切断"""
        if before.channel is not None:
            voice_client = member.guild.voice_client
            if voice_client and voice_client.channel.id == before.channel.id:
                human_members = [m for m in before.channel.members if not m.bot]
                if len(human_members) == 0:
                    guild_id = member.guild.id
                    if guild_id in self.queues:
                        self.queues[guild_id].clear()
                    await voice_client.disconnect()
                    print(f"[自動切断] {before.channel.name} に誰もいなくなったため自動切断しました。")

    @commands.command(name="join", aliases=["j"])
    async def join(self, ctx):
        """!j または !join でVCに接続（移動）"""
        if not ctx.author.voice:
            return await ctx.send("先にボイスチャンネルに入ってください！")

        channel = ctx.author.voice.channel

        # すでにどこかのVCに接続している場合
        if ctx.voice_client:
            if ctx.voice_client.channel.id == channel.id:
                return await ctx.send(f"すでに **{channel.name}** に接続しています。")
            await ctx.voice_client.move_to(channel)
            await ctx.send(f"🔊 **{channel.name}** に移動しました！")
        else:
            await channel.connect()
            await ctx.send(f"🔊 **{channel.name}** に接続しました！")

@commands.command(name="play", aliases=["p"])
async def play(self, ctx, *, query: str):
        """!p <URLまたはキーワード> [random] で再生"""
        if not ctx.author.voice:
            return await ctx.send("先にボイスチャンネルに入ってください！")

        # 未接続、または別チャンネルにいる場合は移動して接続
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        elif ctx.voice_client.channel.id != ctx.author.voice.channel.id:
            await ctx.voice_client.move_to(ctx.author.voice.channel)

        # 末尾に " random" がついているか判定
        is_random = False
        if query.lower().endswith(" random"):
            is_random = True
            query = query[:-7].strip() # URLや検索語句から " random" を除去

        await ctx.send("🔎 情報を取得中...")

        target = query if query.startswith("http") else f"ytsearch:{query}"

        loop = asyncio.get_running_loop()
        try:
            data = await loop.run_in_executor(
                None, lambda: ytdl.extract_info(target, download=False)
            )
        except Exception as e:
            return await ctx.send(f"動画の取得に失敗しました: {e}")

        guild_id = ctx.guild.id
        if guild_id not in self.queues:
            self.queues[guild_id] = []

        entries = data.get("entries") if "entries" in data else [data]

        # None要素を除外したリストを作成
        valid_entries = [e for e in entries if e]

        # random 指定があり、かつプレイリスト（複数曲）の場合はシャッフル
        if is_random and len(valid_entries) > 1:
            random.shuffle(valid_entries)

        added_count = 0
        for entry in valid_entries:
            item = {
                "title": entry.get("title", "Unknown Title"),
                "url": entry.get("url"),
            }
            self.queues[guild_id].append(item)
            added_count += 1

        if is_random and added_count > 1:
            await ctx.send(f"🔀 シャッフルして {added_count} 曲をキューに追加しました！")
        else:
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