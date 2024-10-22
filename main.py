# -*- coding: utf-8 -*-
import re
import requests
from bs4 import BeautifulSoup
from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext, mirai
from pkg.plugin.events import *

@register(name="StarRailCharacterFetcher", description="爬取崩坏：星穹铁道角色信息",
          version="1.0", author="BiFangKNT")
class StarRailCharacterPlugin(BasePlugin):

    def __init__(self, host: APIHost):
        super().__init__(host)
        self.base_url = "https://homdgcat.wiki/sr/char?lang=CH"

    # 异步初始化
    async def initialize(self):
        pass

    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def on_message(self, ctx: EventContext):
        message = ctx.event.query.message_chain.to_plain_text()
        match = re.match(r"爬取崩铁：(.{1,5})", message)
        if match:
            character_name = match.group(1)
            result = await self.fetch_character_info(character_name)
            if result:
                ctx.add_return('reply', [mirai.Plain(result)])
            else:
                ctx.add_return('reply', [mirai.Plain("未找到该角色信息。")])

    async def fetch_character_info(self, character_name):
        response = requests.get(self.base_url)
        soup = BeautifulSoup(response.content, 'html.parser')
        character_cards = soup.select('div.avatar-card.hover-shadow.rar-5')
        
        for card in character_cards:
            if character_name in card.select('p')[1].text:
                detail_url = "https://homdgcat.wiki" + card.select_one('a')['href']
                character_info = self.get_character_details(detail_url)
                return f"找到角色 {character_name} 的信息：\n{character_info}\n详情链接：{detail_url}"
        return None

    def get_character_details(self, url):
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 提取角色基本信息
        basic_info = soup.select_one('div.basic-info')
        info_text = ""
        if basic_info:
            for p in basic_info.select('p'):
                info_text += f"{p.text.strip()}\n"
        
        # 提取角色描述
        description = soup.select_one('div.description')
        if description:
            info_text += f"\n描述：{description.text.strip()}\n"
        
        # 提取技能信息（这里只提取技能名称作为示例）
        skills = soup.select('div.skill-item')
        if skills:
            info_text += "\n技能：\n"
            for skill in skills:
                skill_name = skill.select_one('div.skill-name')
                if skill_name:
                    info_text += f"- {skill_name.text.strip()}\n"
        
        return info_text.strip()
    
    def __del__(self):
        pass
