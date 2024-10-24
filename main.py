# -*- coding: utf-8 -*-
import re
import requests
import json
import asyncio
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext, mirai
from pkg.plugin.events import PersonNormalMessageReceived, GroupNormalMessageReceived
from .fetch_characters import CharacterDataManager
from playwright.async_api import async_playwright

@register(name="StarRailCharacterFetcher", description="爬取崩坏：星穹铁道角色信息",
          version="1.0", author="BiFangKNT")
class StarRailCharacterPlugin(BasePlugin):

    def __init__(self, host: APIHost):
        super().__init__(host)
        self.base_url = "https://homdgcat.wiki/sr/char?lang=CH"
        self.message_pattern = re.compile(r'^爬取崩铁：(.{1,5})|崩铁爬虫帮助$')
        self.char_manager = CharacterDataManager()  # 初始化角色管理器
        self.playwright_ready = False  # 标记 playwright 是否准备就绪
        self.executor = ThreadPoolExecutor(max_workers=1)
        # 启动异步初始化任务
        asyncio.create_task(self.initialize())

    async def initialize(self):
        """异步初始化 playwright"""
        try:
            self.ap.logger.info("开始安装 playwright webkit...")
            
            # 先安装 webkit 驱动
            result = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: subprocess.run(
                    #['playwright', 'install', 'webkit'],
                    ['playwright', 'install', 'firefox'],
                    capture_output=True,
                    text=True
                )
            )
            
            # 检查安装结果
            if result.returncode != 0:
                self.ap.logger.error(f"webkit 安装失败: {result.stderr}")
                return
                
            self.ap.logger.info("webkit 驱动安装成功")
            
            # 检查浏览器是否可用
            try:
                async with async_playwright() as p:
                    #browser = await p.webkit.launch(headless=True)
                    browser = await p.firefox.launch(headless=True)
                    await browser.close()
                    self.playwright_ready = True
                    self.ap.logger.info("firefox 浏览器测试成功")
            except Exception as e:
                self.ap.logger.error(f"firefox 浏览器测试失败: {e}")
                # 尝试安装系统依赖
                self.ap.logger.info("尝试安装系统依赖...")
                result = await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    lambda: subprocess.run(
                        ['playwright', 'install-deps', 'firefox'],
                        capture_output=True,
                        text=True
                    )
                )
                if result.returncode != 0:
                    self.ap.logger.error(f"系统依赖安装失败: {result.stderr}")
                else:
                    self.ap.logger.info("系统依赖安装成功")
                    self.playwright_ready = True
                    
        except Exception as e:
            self.ap.logger.error(f"初始化 playwright 时出错: {e}")

    async def get_character_id(self, character_name):
        """根据角色名从Avatar.js中获取角色ID"""
        try:
            response = requests.get("https://homdgcat.wiki/data/CH/Avatar.js")
            content = response.text
            
            # 定位 _avatar 变量的内容
            avatar_start = content.find("var _avatar = [")
            if avatar_start == -1:
                self.ap.logger.error("未找到 _avatar 变量")
                return None
                
            # 找到下一个变量定义的位置
            next_var = content.find("var _", avatar_start + 13)  # 跳过当前的 "var _avatar = ["
            if next_var == -1:
                self.ap.logger.error("未找到下一个变量定义")
                return None
                
            # 向前查找最后一个 "]"
            avatar_end = content.rfind("]", avatar_start, next_var)
            if avatar_end == -1:
                self.ap.logger.error("未找到 _avatar 数组的结束位置")
                return None
                
            # 提取 JSON 数组内容
            avatar_json = content[avatar_start + 13:avatar_end + 1]
            
            # 解析 JSON
            avatar_data = json.loads(avatar_json)
            
            # 查找匹配的角色
            for character in avatar_data:
                if character["Name"] == character_name:
                    return character["_id"]
                    
            self.ap.logger.info(f"未找到角色: {character_name}")
            return None
            
        except Exception as e:
            self.ap.logger.error(f"获取角色ID时出错: {e}")
            return None

    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def on_message(self, ctx: EventContext):
        if not self.playwright_ready:
            ctx.add_return('reply', [mirai.Plain("插件正在初始化中，请稍后再试...")])
            ctx.prevent_default()
            return
        
        message = ctx.event.text_message
        match = re.match(self.message_pattern, message)

        self.ap.logger.info(f"崩铁爬虫插件正在处理消息: {message}")

        if match:
            if match.group(0) == "崩铁爬虫帮助":
                await self.send_help(ctx)
            else:            
                character_name = match.group(1)
                # 获取角色ID
                char_id = await self.get_character_id(character_name)
                if not char_id:
                    ctx.add_return('reply', [mirai.Plain("未找到该角色ID。")])
                    ctx.prevent_default()
                    return

                # 获取角色快照
                image_data = await self.char_manager.get_character_snapshot(char_id, character_name)
                if image_data:
                    ctx.add_return('reply', [image_data])
                else:
                    ctx.add_return('reply', [mirai.Plain("获取角色快照失败。")])
                ctx.prevent_default()
        else:
            self.ap.logger.info("崩铁爬虫：消息不匹配，不进行处理")
            return

    async def send_help(self, ctx: EventContext):
        help_text = (
            "崩坏：星穹铁道角色信息查询插件使用说明：\n"
            "1. 输入 '爬取崩铁：角色名' 来查询角色信息。\n"
            "   例如：爬取崩铁：希儿\n"
            "2. 角色名应为1-5个字符。\n"
            "3. 信息包括角色基本信息、描述和技能列表。\n"
            "4. 输入 '崩铁爬虫帮助' 显示此帮助信息。"
        )
        ctx.add_return('reply', [mirai.Plain(help_text)])
        ctx.prevent_default()
    
    def __del__(self):
        pass
