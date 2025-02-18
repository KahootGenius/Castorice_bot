# -*- coding: utf-8 -*-
import asyncio
import os
import random
from datetime import datetime, timedelta
import pytz
from requests import get

from mcstatus import JavaServer
import socket

import botpy
from botpy import logging
from botpy.ext.cog_yaml import read
from botpy.ext.command_util import Commands
from botpy.message import GroupMessage, Message

test_config = read(os.path.join(os.path.dirname(__file__), "config.yaml"))
_log = logging.get_logger()

class MyClient(botpy.Client):
    def __init__(self, intents):
        super().__init__(intents=intents)
        self.game_status = {}
        self.player_cards = {}
        self.bot_cards = {}
        self.sleep_records = {}
        self.tz = pytz.timezone('Asia/Shanghai')
        self.epic_subscribers = set()
        self.epic_task = None
        self.now = []
        self.soon = []
        self.mc_servers = {}
        self.social_credits = {}
        self.group_members = {}

    async def on_ready(self):
        _log.info(f"robot 「{self.robot.name}」 on_ready!")
        self.epic_task = asyncio.create_task(self.schedule_epic_push())

    # Epic游戏相关函数
    def _get_title(self, item):
        s = item.get("title", "")
        lst = s.strip("《").split("》")
        return "".join(lst)

    def _get_original_price(self, item):
        details = item.get("price", {}).get("totalPrice", {})
        return int(details.get("originalPrice", 0))

    def _get_time(self, item):
        if item.get("promotions", None) is not None:
            if len(item["promotions"]["promotionalOffers"]) != 0:
                startDate = item["promotions"]["promotionalOffers"][0]['promotionalOffers'][0]['startDate'].split("T")[0]
                endDate = item["promotions"]["promotionalOffers"][0]['promotionalOffers'][0]['endDate'].split("T")[0]
                return f"{startDate}——{endDate}"
            elif len(item["promotions"]['upcomingPromotionalOffers']) != 0:
                startDate = item["promotions"]["upcomingPromotionalOffers"][0]['promotionalOffers'][0]['startDate'].split("T")[0]
                endDate = item["promotions"]["upcomingPromotionalOffers"][0]['promotionalOffers'][0]['endDate'].split("T")[0]
                return f"{startDate}——{endDate}"
        return ""

    def _is_free(self, item):
        if self._get_original_price(item) == 0:
            return False

        if item.get("promotions", None) is not None:
            if len(item["promotions"]["promotionalOffers"]) != 0:
                if item["promotions"]["promotionalOffers"][0]["promotionalOffers"][0]["discountSetting"]["discountPercentage"] == 0:
                    self.now.append(f"{self._get_title(item)} - {(self._get_original_price(item) / 100)}元 - {self._get_time(item)}")
                    return True
            elif len(item["promotions"]['upcomingPromotionalOffers']) != 0:
                if item["promotions"]['upcomingPromotionalOffers'][0]["promotionalOffers"][0]["discountSetting"]["discountPercentage"] == 0:
                    self.soon.append(f"{self._get_title(item)} - {(self._get_original_price(item) / 100)}元 - {self._get_time(item)}")
                    return True
        return False

    async def get_epic_free_games(self):
        url = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions?locale=zh-CN&country=CN&allowCountries=CN"
        response = await asyncio.get_event_loop().run_in_executor(None, get, url)
        hashMap = response.json()
        ls = hashMap["data"]["Catalog"]["searchStore"]["elements"]
        self.now = []  # Reset lists before processing
        self.soon = []

        for item in ls:
            if self._is_free(item):
                continue

        message = "Epic免费游戏推送\n"
        if self.now:  # Use self.now instead of now
            message += "\n当前免费：\n"
            for item in self.now:
                message += f"{item}\n"
        
        if self.soon:  # Use self.soon instead of soon
            message += "\n即将推出：\n"
            for item in self.soon:
                message += f"{item}\n"
        
        return message

    async def schedule_epic_push(self):
        while True:
            now = datetime.now(self.tz)
            # 计算距离下一个中午12点的时间
            next_run = now.replace(hour=12, minute=0, second=0, microsecond=0)
            if now >= next_run:
                next_run += timedelta(days=1)
            
            await asyncio.sleep((next_run - now).seconds)
            
            # 获取并推送信息
            message = await self.get_epic_free_games()
            for group_id in self.epic_subscribers:
                await self.api.post_group_message(
                    group_openid=group_id,
                    msg_type=1,
                    content=message
                )

    async def handle_epic(self, message):
        if "/epicfree" in message.content:
            message_content = await self.get_epic_free_games()
            await message.reply(content=message_content)
            return True
        if "订阅epic" in message.content:
                self.epic_subscribers.add(message.group_openid)
                await message.reply(content="已订阅Epic免费游戏推送，将在每天中午12点推送信息。")

                return True
        if "epicTD" in message.content:
            self.epic_subscribers.discard(message.group_openid)
            await message.reply(content="已取消订阅Epic免费游戏推送。")
            return True
        return False


    
    # DeepSeek 相关函数
    async def handle_deepseek(self, message):
        if "/deepseek" in message.content:
            await message.reply(content="正在思考中...")
            await asyncio.sleep(5)  # 等待5秒
            
            pic_url = 'https://img.zcool.cn/community/01bb815b4c8b5ca80121ade02bfb4f.jpg'  # 替换为您的图片URL
            
            try:
                upload_media = await self.api.post_group_file(
                    group_openid=message.group_openid,
                    file_type=1,
                    url=pic_url
                )
                
                await message.reply(
                    msg_type=7,
                    media=upload_media,
                    msg_seq=2
                )
                return True
            except Exception as e:
                await message.reply(content=f"发送图片失败：{str(e)}")
                return True
        return False

    #mcstatus相关函数
    async def handle_minecraft(self, message):
        if "/mc绑定" in message.content:
            # 从消息中提取服务器地址
            try:
                server_address = message.content.split()[1]  # 获取第二个参数作为服务器地址
                self.mc_servers[message.group_openid] = server_address
                await message.reply(content=f"已绑定Minecraft服务器")
                return True
            except IndexError:
                await message.reply(content="请提供服务器地址，格式：/mc绑定 域名或IP:端口")
                return True

        elif "/mc解绑" in message.content:
            if message.group_openid in self.mc_servers:
                del self.mc_servers[message.group_openid]
                await message.reply(content="已解除 Minecraft 服务器绑定")
            else:
                await message.reply(content="当前群组未绑定任何服务器")
            return True

        elif "/mc状态" in message.content:
            if message.group_openid not in self.mc_servers:
                await message.reply(content="请先使用 /mc绑定 命令绑定服务器地址")
                return True

            try:
                server = JavaServer.lookup(self.mc_servers[message.group_openid])
                status = await asyncio.get_event_loop().run_in_executor(None, server.status)
                
                # 构建在线玩家列表
                players = "无" if not status.players.sample else "\n".join([p.name for p in status.players.sample])
                
                response = (
                    f"服务器状态：在线\n"
                    f"延迟：{status.latency:.1f}ms\n"
                    f"在线人数：{status.players.online}/{status.players.max}\n"
                    f"在线玩家：\n{players}"
                )
                await message.reply(content=response)
                return True

            except (socket.timeout, ConnectionRefusedError, ConnectionError):
                await message.reply(content="无法连接到服务器，请检查服务器地址是否正确或服务器是否在线")
                return True
            except Exception as e:
                await message.reply(content=f"查询失败：{str(e)}")
                return True

        return False

    # 21点游戏相关函数
    def calculate_points(self, cards):
        points = 0
        ace_count = 0
        for card in cards:
            if card == 'A':
                ace_count += 1
            elif card in ['J', 'Q', 'K']:
                points += 10
            else:
                points += int(card)
        
        for _ in range(ace_count):
            if points + 11 <= 21:
                points += 11
            else:
                points += 1
        return points

    async def handle_blackjack(self, message):
        if "/21点" in message.content:
            return await self._start_game(message)
        elif "/抽卡" in message.content and self.game_status.get(message.group_openid):
            return await self._draw_card(message)
        elif "/停止" in message.content and self.game_status.get(message.group_openid):
            return await self._stop_game(message)
        return False

    async def _start_game(self, message):
        self.game_status[message.group_openid] = True
        self.player_cards[message.group_openid] = []
        self.bot_cards[message.group_openid] = []
        cards = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
        
        self.player_cards[message.group_openid].append(random.choice(cards))
        self.bot_cards[message.group_openid].append(random.choice(cards))
        
        player_points = self.calculate_points(self.player_cards[message.group_openid])
        await message.reply(content=f"游戏开始！\n你的手牌: {', '.join(self.player_cards[message.group_openid])} (点数: {player_points})\n机器人的明牌: {self.bot_cards[message.group_openid][0]}\n你可以输入 /抽卡 继续要牌，或输入 /停止 停止要牌")

        return True

    async def _draw_card(self, message):
        cards = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
        self.player_cards[message.group_openid].append(random.choice(cards))
        player_points = self.calculate_points(self.player_cards[message.group_openid])
        
        if player_points > 21:
            self.game_status[message.group_openid] = False
            await message.reply(content=f"你的手牌: {', '.join(self.player_cards[message.group_openid])} (点数: {player_points})\n爆牌了！你输了！")
        else:
            await message.reply(content=f"你的手牌: {', '.join(self.player_cards[message.group_openid])} (点数: {player_points})\n机器人的明牌: {self.bot_cards[message.group_openid][0]}")
        return True

    async def _stop_game(self, message):
        cards = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
        while self.calculate_points(self.bot_cards[message.group_openid]) < 17:
            self.bot_cards[message.group_openid].append(random.choice(cards))
        
        player_points = self.calculate_points(self.player_cards[message.group_openid])
        bot_points = self.calculate_points(self.bot_cards[message.group_openid])
        
        result = f"游戏结束！\n你的手牌: {', '.join(self.player_cards[message.group_openid])} (点数: {player_points})\n"
        result += f"机器人的手牌: {', '.join(self.bot_cards[message.group_openid])} (点数: {bot_points})\n"
        
        if bot_points > 21:
            result += "机器人爆牌了！你赢了！"
        elif player_points > bot_points:
            result += "恭喜你赢了！"
        elif player_points < bot_points:
            result += "很遗憾，你输了！"
        else:
            result += "平局！"
        
        await message.reply(content=result)
        self.game_status[message.group_openid] = False
        return True

    # 睡眠记录相关函数
    async def clear_sleep_record(self, user_id):
        await asyncio.sleep(24 * 3600)
        if user_id in self.sleep_records:
            del self.sleep_records[user_id]

    async def handle_sleep(self, message):
        if "/晚安" in message.content:
            return await self._record_sleep(message)
        elif "/早安" in message.content:
            return await self._record_wake(message)
        return False

    async def _record_sleep(self, message):
        current_time = datetime.now(self.tz)
        user_id = f"{message.group_openid}_{message.author.member_openid}"
        self.sleep_records[user_id] = {
            'sleep_time': current_time,
            'timer': asyncio.create_task(self.clear_sleep_record(user_id))
        }
        formatted_time = current_time.strftime("%H:%M")
        await message.reply(content=f"晚安！现在是{formatted_time}，祝你好梦~ 🌙")
        return True

    async def _record_wake(self, message):
        user_id = f"{message.group_openid}_{message.author.member_openid}"
        if user_id in self.sleep_records:
            wake_time = datetime.now(self.tz)
            sleep_time = self.sleep_records[user_id]['sleep_time']
            
            self.sleep_records[user_id]['timer'].cancel()
            
            sleep_duration = wake_time - sleep_time
            hours = sleep_duration.seconds // 3600
            minutes = (sleep_duration.seconds % 3600) // 60
            
            del self.sleep_records[user_id]
            
            formatted_wake_time = wake_time.strftime("%H:%M")
            await message.reply(
                content=f"早安！现在是{formatted_wake_time}。\n"
                       f"你睡了{hours}小时{minutes}分钟。\n"
                       f"{'要注意休息哦！' if hours < 6 else '睡眠时间刚刚好！' if hours <= 8 else '睡得有点久哦！'}"
            )
        else:
            await message.reply(content="你还没有记录睡眠时间呢，请先使用 /晚安 指令~")
        return True

    # 主消息处理函数
    async def on_group_at_message_create(self, message: GroupMessage):
        _log.info(f"Author info: {message.author.__dict__}")

        # 处理21点游戏
        if await self.handle_blackjack(message):
            return
        
        # 处理Epic免费游戏推送
        if await self.handle_epic(message):
            return

        # 处理睡眠记录
        if await self.handle_sleep(message):
            return
        
        # 处理Minecraft服务器查询
        if await self.handle_minecraft(message):
            return
        
        # 处理Social Credit系统
        if await self.handle_social_credit(message):
            return
        
        # 处理deepseek命令
        if await self.handle_deepseek(message):
            return

        # 处理骰子
        if "/摇骰子" in message.content:
            dice_number = random.randint(1, 6)
            await message.reply(content=f"你投出了: {dice_number} 点 ")

        _log.info(f"User member_openid: {message.author.member_openid}")

if __name__ == "__main__":
    intents = botpy.Intents(public_messages=True)
    client = MyClient(intents=intents)
    client.run(appid=test_config["appid"], secret=test_config["secret"])






