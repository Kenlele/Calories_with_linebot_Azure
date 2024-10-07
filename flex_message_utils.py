from linebot.models import (
    FlexSendMessage, BubbleContainer, BoxComponent, TextComponent, SeparatorComponent, CarouselContainer, ImageComponent
)
import random
import re
import configparser

config = configparser.ConfigParser()
config.read('config.ini')

website_url = config["ngrok"]["website_url"]

# 定義莫蘭迪色系的隨機顏色
morandi_colors = ['#A39E93', '#B7A99A', '#C7B8A5', '#D1B7A1', '#E0C9B0']
used_colors = []

# 定義圖片URL
image_urls = {
    "intro": f"{website_url}/static/sports/intro_image.jpg",
    "health": f"{website_url}/static/sports/health_image.jpg",
    
    "running_day": f"{website_url}/static/sports/running_day_image.jpg",
    "running_week": f"{website_url}/static/sports/running_week_image.jpg",
    "running_month": f"{website_url}/static/sports/running_month_image.jpg",
    
    "swimming_day": f"{website_url}/static/sports/swimming_day_image.jpg",
    "swimming_week": f"{website_url}/static/sports/swimming_week_image.jpg",
    "swimming_month": f"{website_url}/static/sports/swimming_month_image.jpg",
    
    "cycling_day": f"{website_url}/static/sports/cycling_day_image.jpg",
    "cycling_week": f"{website_url}/static/sports/cycling_week_image.jpg",
    "cycling_month": f"{website_url}/static/sports/cycling_month_image.jpg",

    "diet_plan": f"{website_url}/static/sports/diet_plan.jpg"
}

def get_morandi_color():
    """返回不重複的莫蘭迪色系，當所有顏色用過後重置"""
    global used_colors
    if len(used_colors) == len(morandi_colors):
        used_colors = []  # 重置使用過的顏色

    # 選擇一個新的顏色
    available_colors = list(set(morandi_colors) - set(used_colors))
    color = random.choice(available_colors)
    used_colors.append(color)
    return color

def parse_advice_to_sections(cleaned_response):
    """將 cleaned_response 切割為介紹、一天、一週、一個月、健康建議五個區塊"""
    sections = {}

    # 匹配「1天」之前的介紹部分
    intro_match = re.search(r'^(.*?)「1天」', cleaned_response, re.DOTALL)
    day_match = re.search(r'「1天」(.*?)「1週」', cleaned_response, re.DOTALL)
    week_match = re.search(r'「1週」(.*?)「1個月」', cleaned_response, re.DOTALL)
    month_match = re.search(r'「1個月」(.*?)「健康建議」', cleaned_response, re.DOTALL)

    # 查找「小貼士」、「小提醒」或「健康建議」
    reminder_section = find_reminder_section(cleaned_response)

    if intro_match:
        sections['介紹'] = intro_match.group(1).strip()
    if day_match:
        sections['一日建議'] = day_match.group(1).strip()
    if week_match:
        sections['一週建議'] = week_match.group(1).strip()
    if month_match:
        sections['一個月建議'] = month_match.group(1).strip()
    if reminder_section:
        sections['健康建議'] = reminder_section.strip()

    return sections

def find_reminder_section(advice_text):
    """找到隨機生成的小貼士/提醒/建議區塊"""
    reminder_keywords = ['小貼士', '小提醒', '健康建議']
    
    # 嘗試根據關鍵詞匹配區塊
    for keyword in reminder_keywords:
        match = re.search(rf'「{keyword}」(.*?)$', advice_text, re.DOTALL)
        if match:
            return match.group(1)  # 返回去掉標題的內容
    
    return None


def create_flex_message(title, content, image_url):
    """根據標題和內容生成動態 Flex Message，並加入背景圖片、顏色和分隔線"""
    if not content.strip():  # 確保內容不為空
        return None

    morandi_color = get_morandi_color()  # 獲取不重複的莫蘭迪色系

    bubble = BubbleContainer(
        hero=ImageComponent(
            url=image_url,  # 插入對應的圖片 URL
            size='full',
            aspect_ratio='20:13',  # 圖片比例
            aspect_mode='cover'
        ),
        styles={
            "body": {
                "backgroundColor":"#FFE4E1",  # 隨機選擇莫蘭迪色系背景顏色
                "borderColor": "#DDDDDD",  # 邊框顏色
                "borderWidth": "2px",
                "cornerRadius": "md",  # 圓角設置
                "shadowColor": "#BBBBBB",
                "shadowOffset": {"width": 0, "height": 4},
                "shadowOpacity": 0.5,
            }
        },
        body=BoxComponent(
            layout='vertical',
            contents=[
                TextComponent(
                    text=title, 
                    weight='bold', 
                    size='md',  # 調整標題大小
                    align='center',  # 讓標題居中
                    color='#000000'
                ),
                TextComponent(
                    text=content, 
                    wrap=True, 
                    size='sm',  # 調整內容的大小
                    color='#333333',  # 調整內容的顏色和大小
                    align='start'  # 內容靠左對齊
                )
            ],
            spacing='sm',  # 控制內容之間的距離
            padding_all='md',  # 調整padding讓框架變小
        )
    )
    return FlexSendMessage(alt_text=title, contents=bubble)

def generate_flex_messages(advice_text, activity):
    """根據解析出的區塊動態生成並排的 Flex Messages"""
    
    # 定義中英文對應字典
    activity_translation = {
        "游泳": "swimming",
        "跑步": "running",
        "騎腳踏車": "cycling"
    }

    # 將中文活動類型轉換為英文活動類型
    activity_english = activity_translation.get(activity, activity)  # 默認返回原本的 activity

    sections = parse_advice_to_sections(advice_text)

    bubbles = []
    for section_title, section_content in sections.items():
        if section_content.strip():
            # 根據區塊名稱進行標準化處理
            if section_title == "介紹":
                image_key = "intro"
            elif section_title == "健康建議":
                image_key = "health"
            elif section_title == "一日建議":
                image_key = f"{activity_english}_day"  # 使用轉換後的英文活動類型
            elif section_title == "一週建議":
                image_key = f"{activity_english}_week"  # 使用轉換後的英文活動類型
            elif section_title == "一個月建議":
                image_key = f"{activity_english}_month"  # 使用轉換後的英文活動類型
            else:
                image_key = f"{activity_english}_default"  # 如果有其他情況，使用預設圖片
            
            print("圖片key", image_key)  # 打印出正確的圖片key
            image_url = image_urls.get(image_key, f"{website_url}/static/sports/default_image.jpg")  # 預設圖片
            
            bubble = create_flex_message(section_title, section_content, image_url)
            if bubble:
                bubbles.append(bubble.contents)  # 只保存 Bubble 部分

    # 如果有超過一個 Bubble，使用 Carousel 來並排顯示
    if bubbles:
        carousel = CarouselContainer(contents=bubbles)
        return [FlexSendMessage(alt_text="運動建議", contents=carousel)]
    else:
        return []
    
def parse_diet_plan_to_sections(diet_plan):
    """將減肥計畫拆分為段落，以便生成Flex Messages"""
    sections = {}
    lines = diet_plan.split('\n')
    for idx, line in enumerate(lines):
        if line.strip():  # 確保不添加空行
            sections['減肥攻略'] = line.strip()
    return sections

def generate_diet_flex_messages(diet_plan):
    """根據解析出的減肥建議動態生成並排的 Flex Messages"""
    sections = parse_diet_plan_to_sections(diet_plan)

    bubbles = []
    for section_title, section_content in sections.items():
        if section_content.strip():
            # 根據不同建議來生成圖片，這裡也可以使用默認圖片或者根據需要調整
            image_key = "diet_plan"
            image_url = image_urls.get(image_key, f"{website_url}/static/sports/default_image.jpg")
            formatted_content = section_content.replace('，', '，\n')

            bubble = create_flex_message(section_title, formatted_content, image_url)
            if bubble:
                bubbles.append(bubble.contents)  # 只保存 Bubble 部分

    # 如果有超過一個 Bubble，使用 Carousel 來並排顯示
    if bubbles:
        carousel = CarouselContainer(contents=bubbles)
        return [FlexSendMessage(alt_text="減肥建議", contents=carousel)]
    else:
        return []