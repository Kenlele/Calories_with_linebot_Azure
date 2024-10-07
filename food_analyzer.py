import configparser
import json
import re
from openai import AzureOpenAI
from access_db import Dailydata  # 匯入資料庫操作
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from flask import url_for

config = configparser.ConfigParser()
config.read('config.ini')

client = AzureOpenAI(
    api_key=config["AzureOpenAI"]["API_KEY"],
    api_version=config["AzureOpenAI"]["API_VERSION"],
    azure_endpoint=config["AzureOpenAI"]["API_BASE"],
)
def call_gemini_template():
        llm_gemini = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash-latest", 
            google_api_key=config["Gemini"]["API_KEY"]
        )

        return llm_gemini

def call_openai_template(message_text):
    completion = client.chat.completions.create(    
        model=config["AzureOpenAI"]["DEPLOYMENT_NAME_GPT4o"],
        messages=message_text,
        functions=None,
        max_tokens=800,
        top_p=0.0, # 降低隨機性，原本為0.85
        frequency_penalty=0,
        presence_penalty=0,
        stop=None,
    )
    return completion
def message_text_template():
    message_text = [
        {
            "role": "system",
            "content": "",
        },
        {   "role": "user", 
            "content": ""},
    ]
    return message_text
# 提取數字
def extract_numbers(input_string):
    numbers = re.findall(r'\d+', input_string)
    if len(numbers) == 1:
        return numbers[0]
    return numbers # 可能返回單值str或多值list

class FoodCalorieAnalyzer:
    def __init__(self, user_id):
        # Initialize user_id and config
        self.user_id = user_id
        self.daily_data = Dailydata(user_id)
        # Initialize Azure OpenAI Client

        # Initialize Google Gemini AI Client for image analysis
        # self.llm_gemini = ChatGoogleGenerativeAI(
        #     model="gemini-1.5-flash-latest", 
        #     google_api_key=self.config["Gemini"]["API_KEY"]
        # )
    # 圖片url -> 食物描述文字
    def _analyze_food_from_image_url(self, image_urls):

        user_messages = [
            {"type": "text", "text": """請幫我分析這張圖片中的食物，並告訴我食物名稱與份量。請提供具體的食物名稱和對應的份量，回覆格式:食物名稱為XXXXX，份量為XXX單位，並一律使用繁體中文回答。"""}
        ]
        for url in image_urls:
            user_messages.append({"type": "image_url", "image_url": url})
        human_messages = HumanMessage(content=user_messages)
        llm_gemini = call_gemini_template()
        response = llm_gemini.invoke([human_messages])  #我喝了一杯奶茶
        response =self.ensure_str_message(response)
        print(f"*********{response}********")
        return response


    # 文字 -> 食物json
    def _extract_food_info(self, user_input):
     # 圖片 URL 分析，獲取含有食物名稱、份量、卡路里的 JSON
        message_text = message_text_template()
        message_text[0]["content"] += """
                                        如果用戶輸入關於吃了什麼，提取用戶輸入的食物名和份量，
                                        並返回一個json，如果用戶輸入其他資訊就返回空json，
                                        如果用戶輸入不明確，就返回空json。
                                        """
        message_text[0]["content"] += "請一律用繁體中文回答。"
        message_text[0]["content"] = """
                                    範例一
                                    用戶輸入: "我吃了漢堡2個，水餃20顆，披薩2片" 
                                    返回:
                                    [
                                        {
                                            "food_name": "漢堡",
                                            "food_quantity": "2個",
                                            "tatal_calories": "700大卡",
                                            "serving_size_unit": "1個",
                                            "single_calories": "350大卡",
                                            "food_detail": "一個普通的漢堡大約含有250到500大卡的熱量。具體的熱量取決於漢堡的大小、配料和烹調方式。平均來說，可以估計 為350大卡。"
                                        },
                                        {
                                            "food_name": "水餃",
                                            "food_quantity": "20顆",
                                            "tatal_calories": "1000大卡",
                                            "serving_size_unit": "1顆"
                                            "single_calories": "50大卡",
                                            "food_detail": "一顆水餃的熱量大約在40至60大卡之間，具體數值會根據餡料和製作方法有所不同。平均來說，一顆水餃約為50大卡。"
                                        },
                                        {
                                            "food_name": "披薩",
                                            "food_quantity": "2片",
                                            "tatal_calories": "550大卡",
                                            "serving_size_unit": "1片(約100克)",
                                            "single_calories": "275大卡",
                                            "food_detail": "一片普通的披薩（約100克）大約含有250至300大卡的熱量。具體熱量會根據披薩的種類和配料有所不同。"
                                        }
                                    ]
                                    範例二
                                    用戶輸入: "今天天氣如何" 
                                    返回: None
                                    範例三
                                    用戶輸入: "我今天跑了10公里" 
                                    返回: None
                                    """
        message_text[1]["content"] = user_input

        print("type:kkkkkkkkkkkkkkkkkkkk",type(user_input))
        ### 調用OpenAI ###
        completion = call_openai_template(message_text)
        content = completion.choices[0].message.content
        try:
            json_info = json.loads(content)
            if not json_info:  # 如果返回的json為空
                return "請提供更清楚的食物描述或更清晰的圖片。"
            return json_info
        except json.JSONDecodeError:
            return "圖片有點不清楚～方便提供給我更清楚的圖片喔。"
        

    
    def _store_food_calories(self, json):
        daily_data = self.daily_data
        if json:
            food_name_portion_list = []
            food_calories_list = []
            total_calories_sum = 0
            for j in json:
                if 'food_name' not in j or 'food_quantity' not in j:
                    return "請提供食物名稱與份量，或更清楚的描述or圖片哦。"
                food_name = j['food_name']
                food_quantity = j['food_quantity']
                total_calories = int(extract_numbers(j['total_calories'])) # 提取數字
                food_name_portion = f"{food_quantity}{food_name}"
                food_name_portion_list.append(food_name_portion)
                food_calories_list.append(f"{food_name_portion} 含有 {total_calories} 大卡")
                total_calories_sum += total_calories
                try:
                    daily_data.add_data(
                        food_name=food_name_portion,
                        food_calories=total_calories,
                        exercise_name="",
                        exercise_duration=0,
                        calories_burned=0
                    )
                    print(f"已將 {food_name} 的熱量數據存入資料庫: {total_calories} 大卡")
                except Exception as e:
                    print(f"存入資料庫失敗: {e}")
                    
                # 顯示每個食物的熱量與總熱量
            food_details = ",".join(food_calories_list)
            return f"經過計算～{food_details}。總共含有 {total_calories_sum} 大卡，已幫您紀錄。"
        else:
            print("沒json可以存入資料庫。")
    # 使用以下兩個function!!!!!!!!!
    # 完整流程：圖片辨識出食物 -> 提取食物資訊 -> 存入資料庫
    def store_analyze_calories_from_image(self, image_urls):
        response = self._analyze_food_from_image_url(image_urls)
        if response in ["請提供更清楚的食物描述或更清晰的圖片。", "圖片有點不清楚～方便提供給我更清楚的圖片喔。"]:
            return response  # 返回失敗信息，不進行後續處理
        if response:
            print(f"*********** {response}kkkkkkkk")
            json = self._extract_food_info(response)
            if isinstance(json, str):  # 檢查是否是錯誤訊息
                return json
            message_text = self._store_food_calories(json)
            print(f"*********** {message_text}kkkkkkkk")
            return message_text
        else:
            return "無法從圖片中辨識到食物。"
        
    # 完整流程：提取食物資訊 -> 存入資料庫
    def store_analyze_calories_from_text(self, user_input):
        json = self._extract_food_info(user_input)
        if not json:  # 如果返回的結果為空
            return "無法辨識食物，請提供更清楚的描述。"
        message_text = self._store_food_calories(json)
        return message_text
        
    def ensure_str_message(self, response):
        if isinstance(response, str):
            return response
        elif hasattr(response, 'content'):
            return response.content  # 提取出 content 部分
        else:
            return str(response)  # 強制轉換成字串  


if __name__ == "__main__":
    user_id = "example_user"
    # user_input = "我今天吃了一碗拉麵"
    # user_input = "我吃了漢堡2個，水餃20顆，披薩2片"
    # user_input = "我吃了1碗白飯與喝了一碗湯"
    user_input = '我吃了蛋餅'
    
    analyzer = FoodCalorieAnalyzer(user_id)
    message_text = analyzer.store_analyze_calories_from_text(user_input)
    # json = analyzer._extract_food_info(user_input)
    print(message_text)
