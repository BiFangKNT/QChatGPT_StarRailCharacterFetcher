import os
from datetime import datetime, timedelta
import math
from playwright.async_api import async_playwright
import traceback
from PIL import Image
import time  # 添加在文件开头的导入部分
from io import BytesIO
import base64
from pkg.plugin.context import mirai

class CharacterDataManager:
    def __init__(self):
        self.data = None
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.snapshot_dir = os.path.join(self.plugin_dir, 'snapshots')
        os.makedirs(self.snapshot_dir, exist_ok=True)

    def check_snapshot_exists(self, character_name, max_age_hours=24):
        """检查角色快照是否存在且未过期，并返回base64编码的图片"""
        snapshot_path = os.path.join(self.snapshot_dir, f'{character_name}.jpg')
        
        if not os.path.exists(snapshot_path):
            return None
            
        # 检查文件是否过期
        file_time = datetime.fromtimestamp(os.path.getmtime(snapshot_path))
        if datetime.now() - file_time > timedelta(hours=max_age_hours):
            return None
            
        # 读取文件并转换为base64
        try:
            with open(snapshot_path, 'rb') as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
                return mirai.Image(base64=image_base64)
        except Exception as e:
            print(f"读取图片文件失败: {e}")
            return None

    async def get_character_snapshot(self, character_id="1225", character_name=None):
        """获取角色页面快照，返回base64编码的图片"""
        # 先检查是否有未过期的快照
        if character_name:
            existing_snapshot = self.check_snapshot_exists(character_name)
            if existing_snapshot:
                print(f"找到有效的快照")
                return existing_snapshot
        
        start_time = time.time()  # 添加总计时器
        
        url = "https://homdgcat.wiki/sr/char"
        params = {
            "lang": "CH"
        }
        
        full_url = f"{url}?{'&'.join(f'{k}={v}' for k,v in params.items())}#_{character_id}"

        try:
            async with async_playwright() as p:
                browser_start = time.time()
                browser = await p.firefox.launch(  # 改用 firefox
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-gpu',
                        '--disable-dev-shm-usage'
                    ]
                )
                page = await browser.new_page()
                print(f"浏览器启动耗时: {time.time() - browser_start:.2f}秒")
                
                # 使用手机竖屏视口大小
                viewport_width = 600
                viewport_height = int(viewport_width * 16 / 9)
                await page.set_viewport_size({"width": viewport_width, "height": viewport_height})
                
                page_load_start = time.time()  # 页面加载计时
                print(f"正在加载页面: {full_url}")
                try:
                    # 先导航到页面，使用 domcontentloaded 而不是 networkidle
                    await page.goto(
                        full_url, 
                        wait_until='domcontentloaded',  # 改为更快的加载策略
                        timeout=60000  # 增加超时时间到60秒
                    )
                    
                    # 等待关键元素出现
                    print("等待页面内容加载...")
                    try:
                        await page.wait_for_selector('div.mon_body', 
                            state='visible', 
                            timeout=30000
                        )
                    except Exception as e:
                        print(f"等待内容超时，尝试继续执行: {e}")
                    
                    # 给页面一些额外的加载时间
                    await page.wait_for_timeout(5000)
                    
                    print(f"页面初始加载耗时: {time.time() - page_load_start:.2f}秒")
                except Exception as e:
                    print(f"页面加载超时: {e}")
                    
                # 只禁用一些不必要的资源
                await page.route("**/*.{woff,woff2,analytics.js}", lambda route: route.abort())
                
                # 添加性能优化的页面设置
                await page.set_extra_http_headers({"Accept-Language": "zh-CN,zh;q=0.9"})
                
                # 使用更精确的等待条件
                await page.wait_for_selector('div.mon_body', state='visible', timeout=15000)
                
                # 减少强制渲染等待时间，但确保内容加载完整
                await page.wait_for_timeout(3000)
                
                # 获取总高度和所有section
                sections_info = await page.evaluate('''() => {
                    const body = document.querySelector('div.mon_body');
                    const sections = Array.from(document.querySelectorAll('div.mon_body div.a_section'));
                    return {
                        height: body.scrollHeight,
                        sectionsCount: sections.length
                    };
                }''')
                
                total_height = sections_info['height']
                sections_count = sections_info['sectionsCount']
                print(f"计算得到总高度: {total_height}px, 共 {sections_count} 个区块")
                
                # 使用新的足够高的视窗重新加载页面
                browser = await p.firefox.launch(  # 这里也要改
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-gpu',
                        '--disable-dev-shm-usage'
                    ]
                )
                page = await browser.new_page()
                
                # 设置视窗大小
                await page.set_viewport_size({
                    "width": viewport_width,
                    "height": min(total_height + 1000, 15000)  # 限制最大高度为15000px
                })
                
                print("使用完整视窗重新加载页面...")
                await page.goto(full_url)
                await page.wait_for_selector('div.mon_body', timeout=30000)
                
                # 强制渲染所有section
                print("强制渲染所有内容...")
                await page.evaluate('''() => {
                    const sections = document.querySelectorAll('div.mon_body div.a_section');
                    sections.forEach((section, index) => {
                        section.style.transform = 'translateZ(0)';
                        section.style.willChange = 'transform';
                        section.style.contain = 'paint';
                    });
                    
                    const observer = new IntersectionObserver((entries) => {
                        entries.forEach(entry => {
                            if (!entry.isIntersecting) {
                                entry.target.style.visibility = 'hidden';
                                entry.target.style.visibility = 'visible';
                            }
                        });
                    }, {
                        root: null,
                        threshold: 0
                    });
                    
                    sections.forEach(section => {
                        observer.observe(section);
                    });
                    
                    document.body.offsetHeight;
                    
                    return new Promise(resolve => setTimeout(resolve, 2000));
                }''')
                
                # 等待渲染完成
                print("等待渲染完成...")
                await page.wait_for_timeout(5000)
                
                # 隐藏顶部返回按钮
                await page.evaluate('''() => {
                    const backSection = document.evaluate(
                        "/html/body/container/popbodyy/section[2]",
                        document,
                        null,
                        XPathResult.FIRST_ORDERED_NODE_TYPE,
                        null
                    ).singleNodeValue;
                    if (backSection) {
                        backSection.style.display = "none";
                    }
                }''')
                
                # 获取内容区域的实际位置和高度
                content_box = await page.evaluate('''() => {
                    const content = document.querySelector("div.mon_body");
                    const rect = content.getBoundingClientRect();
                    return {
                        y: rect.top,
                        height: rect.height
                    };
                }''')
                
                print(f"内容区域高度: {content_box['height']}px")
                
                # 获取完整截图
                print("开始截取完整页面...")
                full_screenshot = await page.screenshot(
                    clip={
                        "x": 0,
                        "y": content_box['y'],
                        "width": viewport_width,
                        "height": content_box['height']
                    }
                )
                
                # 计算需要分成几张图片
                slice_height = int(viewport_width * 16 / 9)  # 手机竖屏比例
                total_slices = math.ceil(content_box['height'] / (slice_height - 50))  # 留50px重叠区域
                
                print(f"需要切割成 {total_slices} 张图片")
                
                # 使用 PIL 直接处理内存中的图片数据
                with Image.open(BytesIO(full_screenshot)) as img:
                    # 创建一个新的空白图片
                    final_height = int((total_slices - 1) * (slice_height - 50) + 
                                     min(slice_height, content_box['height'] - (total_slices - 1) * (slice_height - 50)))
                    final_image = Image.new('RGB', (int(viewport_width), final_height), 'white')
                    
                    # 使用更大的缓冲区来提高处理速度
                    Image.MAX_IMAGE_PIXELS = None
                    
                    for i in range(total_slices):
                        start_y = int(i * (slice_height - 50))  # 每次减去重叠区域
                        end_y = int(min(start_y + slice_height, content_box['height']))
                        
                        # 裁剪当前切片
                        slice_img = img.crop((0, start_y, int(viewport_width), end_y))
                        
                        # 计算当前切片在最终图片中的位置
                        paste_y = int(i * (slice_height - 50))
                        
                        # 将切片粘贴到最终图片上
                        final_image.paste(slice_img, (0, paste_y))
                        print(f"已处理第 {i + 1}/{total_slices} 个切片")
                    
                    # 保存最终的完整图片，只使用角色名
                    final_path = os.path.join(
                        self.snapshot_dir,
                        f'{character_name}.jpg'  # 改用 jpg 格式
                    )
                    # 使用适中的压缩参数，保存为 JPEG
                    final_image.save(final_path, 
                                   format='JPEG',  # 明确指定格式
                                   quality=95,     # 保持较高质量
                                   optimize=True)  # 启用优化
                    print(f"已保存完整图片: {final_path}")
                    
                    # 读取并转换为base64
                    with open(final_path, 'rb') as f:
                        image_base64 = base64.b64encode(f.read()).decode('utf-8')
                        image_data = mirai.Image(base64=image_base64)
                
                await browser.close()
                total_time = time.time() - start_time
                print(f"\n总耗时: {total_time:.2f}秒")
                return image_data
            
        except Exception as e:
            total_time = time.time() - start_time
            print(f"执行出错，总耗时: {total_time:.2f}秒")
            print(f"获取快照时出错: {e}")
            traceback.print_exc()
            return None
    
    def clean_old_snapshots(self, max_age_days=7):
        """清理旧的快照文件"""
        try:
            now = datetime.now()
            for filename in os.listdir(self.snapshot_dir):
                filepath = os.path.join(self.snapshot_dir, filename)
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if now - file_time > timedelta(days=max_age_days):
                    os.remove(filepath)
                    print(f"已删除过期快照: {filename}")
        except Exception as e:
            print(f"清理快照时出错: {e}")

# 修改主函数为异步
async def main():
    total_start_time = time.time()
    manager = CharacterDataManager()
    
    # 清理旧快照
    manager.clean_old_snapshots()
    
    # 获取特定角色的快照
    character_ids = ["1225"]
    character_names = ["忘归人"]
    for char_id, character_name in zip(character_ids, character_names):
        snapshot_paths = await manager.get_character_snapshot(char_id, character_name)
        if snapshot_paths:
            print(f"角色 {char_id} 的快照已生成:")
            for i, path in enumerate(snapshot_paths, 1):
                print(f"第 {i} 张: {path}")
        else:
            print(f"角色 {char_id} 的快照生成失败")
    
    total_time = time.time() - total_start_time
    print(f"\n程序总耗时: {total_time:.2f}秒")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
