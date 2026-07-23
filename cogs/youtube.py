import asyncio
import discord
from discord.ext import commands
import yt_dlp
import random

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ★ 高速化に最適化した YTDL 設定（ニコニコ用ヘッダー追加）
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "extract_flat": "in_playlist",
    "skip_download": True,
    "source_address": "0.0.0.0",
    "lazy_playlist": True,
    "ignoreerrors": True,
    "http_headers": {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.nicovideo.jp/",
    },
}

# ★ ニコニコ動画のブロックを回避するための FFmpeg オプション（User-Agent + Referer）
FFMPEG_OPTIONS = {
    "before_options": (
        f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
        f'-user_agent "{USER_AGENT}" '
        f'-headers "Referer: https://www.nicovideo.jp/\r\n"'
    ),
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


# --- キューのページネーション用 UI (ボタン) ---
class QueuePaginator(discord.ui.View):
    def __init__(self, queue: list, author: discord.Member, per_page: int = 10):
        super().__init__(timeout=60)
        self.queue = queue
        self.author = author
        self.per_page = per_page
        self.current_page = 0
        self.max_pages = (len(queue) - 1) // per_page + 1
        self.message = None
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.max_pages - 1

    def create_embed(self) -> discord.Embed:
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_items = self.queue[start:end]

        embed = discord.Embed(
            title="📋 再生キュー一覧",
            color=discord.Color.blue()
        )

        description = ""
        for idx, item in enumerate(page_items, start=start + 1):
            description += f"**{idx}.** {item['title']}\n"

        embed.description = description
        embed.set_footer(
            text=f"ページ {self.current_page + 1} / {self.max_pages} (合計 {len(self.queue)} 曲)"
        )
        return embed

    @discord.ui.button(label="◀ 前へ", style=discord.ButtonStyle.secondary, custom_id="prev")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("コマンドを実行したユーザーのみ操作できます。", ephemeral=True)

        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="次へ ▶", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("コマンドを実行したユーザーのみ操作できます。", ephemeral=True)

        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class YouTube(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}

    def play_next(self, ctx):
        """キュー内の次の曲を再生"""
        guild_id = ctx.guild.id
        if guild_id in self.queues and len(self.queues[guild_id]) > 0:
            current_item = self.queues[guild_id].pop(0)
            target_url = current_item["url"]
            stream_url = target_url

            # 最新の音声ストリームURLを取得（ヘッダー付きで取得）
            try:
                single_opts = {
                    "format": "bestaudio/best",
                    "quiet": True,
                    "http_headers": {
                        "User-Agent": USER_AGENT,
                        "Referer": "https://www.nicovideo.jp/",
                    },
                }
                with yt_dlp.YoutubeDL(single_opts) as ytdl_single:
                    info = ytdl_single.extract_info(target_url, download=False)
                    stream_url = info.get("url", target_url)
            except Exception as e:
                print(f"[ストリーム取得エラー]: {e}")

            source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)

            def after_playing(error):
                if error:
                    print(f"[再生エラー]: {error}")
                self.bot.loop.call_soon_threadsafe(self.play_next, ctx)

            if ctx.voice_client:
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
        if not ctx.author.voice:
            return await ctx.send("先にボイスチャンネルに入ってください！")

        channel = ctx.author.voice.channel

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
        if not ctx.author.voice:
            return await ctx.send("先にボイスチャンネルに入ってください！")

        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        elif ctx.voice_client.channel.id != ctx.author.voice.channel.id:
            await ctx.voice_client.move_to(ctx.author.voice.channel)

        is_random = False
        if query.lower().endswith(" random"):
            is_random = True
            query = query[:-7].strip()

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
        valid_entries = [e for e in entries if e]

        if is_random and len(valid_entries) > 1:
            random.shuffle(valid_entries)

        added_count = 0
        for entry in valid_entries:
            video_url = entry.get("webpage_url") or entry.get("url")
            if not video_url and entry.get("id"):
                video_url = f"https://www.youtube.com/watch?v={entry.get('id')}"

            item = {
                "title": entry.get("title", "Unknown Title"),
                "url": video_url,
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
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("⏭️ スキップしました。")
        else:
            await ctx.send("現在再生中の曲はありません。")

    @commands.command(name="stop")
    async def stop(self, ctx):
        guild_id = ctx.guild.id
        if guild_id in self.queues:
            self.queues[guild_id].clear()

        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("⏹️ 停止して切断しました。")

    @commands.command(name="view", aliases=["v", "q", "queue"])
    async def view(self, ctx):
        guild_id = ctx.guild.id
        queue = self.queues.get(guild_id, [])

        if not queue:
            return await ctx.send("📋 キューは現在空です。")

        paginator = QueuePaginator(queue, ctx.author, per_page=10)
        embed = paginator.create_embed()

        if paginator.max_pages > 1:
            paginator.message = await ctx.send(embed=embed, view=paginator)
        else:
            await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(YouTube(bot))