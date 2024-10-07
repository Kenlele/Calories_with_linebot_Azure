import configparser
from access_db import Userdata, Dailydata  # 匯入資料庫操作
from openai import AzureOpenAI
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage
import json
import re


# # 初始化 Azure OpenAI
# client = AzureOpenAI(
#     api_key=config["AzureOpenAI"]["API_KEY"],
#     api_version=config["AzureOpenAI"]["API_VERSION"],
#     azure_endpoint=config["AzureOpenAI"]["API_BASE"],
# )

# 設定檔讀取
config = configparser.ConfigParser()
config.read("config.ini")

# 初始化 Gemini API
client = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash-latest",
    google_api_key=config["Gemini"]["API_KEY"]
)

class CalorieAnalyzer:
    def __init__(self, user_id):
        self.user_id = user_id

    def handle_user_input(self, user_input):
        """
        處理來自主程式的使用者輸入，檢查基本資料和運動時間，然後返回結果給主程式。
        """
        # 步驟 1: 從資料庫抓取使用者基本資料
        userdata = Userdata(self.user_id)
        user_record = userdata.search_data('u_id', self.user_id)

        # 無法取得使用者基本資料，使用預設值
        if not user_record:
            weight = 70  # 預設體重
            reply_message = "無法取得您的基本資料，使用預設體重 70 公斤計算。\n"
        else:
            weight = user_record.get('weight', 70)  # 從資料庫中取得體重，預設 70 公斤
            reply_message = f"使用您的體重 {weight} 公斤進行計算。\n"

        # 步驟 2: 使用手動提取的方式解析運動名稱、時間和距離
        exercise_name, duration_minutes, distance_km = self.extract_exercise_info(user_input)

        # 如果無法解析，返回錯誤提示並保留狀態
        if not exercise_name or not duration_minutes or not distance_km:
            return "請提供我完整的運動名稱、時間和距離，才能精確計算。"

        # 步驟 3: 手動計算卡路里並存入資料庫
        calories_burned = self.calculate_calories_burned(exercise_name, duration_minutes, weight)
        self.store_calorie_data(exercise_name, duration_minutes, calories_burned)

        # 步驟 4: 使用 Gemini API 生成最終回應
        result = self.gemini_generate_response(exercise_name, duration_minutes, distance_km, calories_burned)

        # 返回結果給主程式推送給使用者
        return result

    def extract_exercise_info(self, user_input):
        """
        手動提取運動名稱、持續時間、距離。
        """

        # 提取運動名稱 (例如 "跑步")
        exercise_match = re.search(r"(跑步|游泳|騎腳踏車)", user_input)
        exercise_name = exercise_match.group(1) if exercise_match else None

        # 提取運動時間（分鐘或小時）
        duration_match = re.search(r"(\d+)\s*(分鐘|小時)", user_input)
        if duration_match:
            duration_value = int(duration_match.group(1))
            duration_unit = duration_match.group(2)
            duration_minutes = duration_value if duration_unit == "分鐘" else duration_value * 60
        else:
            duration_minutes = None

        # 提取運動距離 (公里或公尺)
        distance_match = re.search(r"(\d+\.?\d*)\s*(公里|公尺)", user_input)
        if distance_match:
            distance_value = float(distance_match.group(1))
            distance_km = distance_value if distance_match.group(2) == "公里" else distance_value / 1000
        else:
            distance_km = None

        return exercise_name, duration_minutes, distance_km

    def calculate_calories_burned(self, exercise_name, duration_minutes, weight):
        """
        根據運動名稱、時間和使用者體重計算消耗的卡路里。
        """
        # 假設這裡有不同運動的 MET 值
        met_values = {
            "跑步": 9.8,
            "游泳": 8.0,
            "騎腳踏車": 7.5,
            "快走": 8.0,
            "爬山": 6.0,
            "瑜伽": 4.0,
            "舞蹈": 5.0,
            "籃球": 6.0,
            "足球": 7.0,
            "排球": 4.0,
            "羽毛球": 5.5,
            "乒乓球": 4.0,
            "壁球": 7.0,
            "高爾夫": 4.8,
            "滑雪": 7.0,
            "慢跑": 6.0,
            "健身": 6.0,
            "有氧運動": 7.0,
            "重訓": 8.0,
            "跳繩": 10.0,
            "拳擊": 8.0,
            "爬樓梯": 8.0,
            "慢跑": 6.0,
            "散步": 2.0,

        }
        met_value = met_values.get(exercise_name, 8.0)  # 預設一個MET值
        calories_burned = met_value * weight * (duration_minutes / 60)
        return int(calories_burned)

    def gemini_generate_response(self, exercise_name, duration_minutes, distance_km, calories_burned):
        """
        調用 Google Gemini 生成最終回應。
        """
        message_text =f"""
        你是一位專業的運動卡路里分析顧問，根據以下運動資訊生成鼓勵性的建議。請根據 BTRT 規則生成回應，並保持簡潔、清晰和鼓勵的語氣。生成大約 150 字的文本。

        **Background 背景**：
        使用者進行了以下運動，請根據這些資訊為他生成回應。
        運動名稱：{exercise_name}，持續時間：{duration_minutes} 分鐘，運動距離：{distance_km} 公里，消耗卡路里：{calories_burned} 卡路里。

        **Task 任務**：
        生成一段鼓勵的建議，告訴使用者他的努力對健康的積極影響，並引導他進行下一步的運動計劃。請保持鼓勵的語氣。

        **Tone 語氣**：
        保持正面、鼓勵，並多使用標點符號，使回應流暢自然。去掉**這類符號，保持段落清晰，語氣應充滿支持感。

        **Result 結果**：
        生成一個清晰、易讀的建議，包括鼓勵使用者繼續保持，並提出進一步的健康建議，讓他們保持動力。使用簡單的段落結構和友善的語氣。
        """

        try:
            human_message = HumanMessage(content=message_text)
            completion = client.invoke([human_message])

            # 處理 Gemini 的回應
            return completion.content  # 返回生成的文本
        except Exception as e:
            return f"處理輸入時發生錯誤：{e}"

    def store_calorie_data(self, exercise_name, duration_minutes, calories_burned):
        """
        將運動數據自動存入資料庫，無需使用者干預
        """
        daily_data = Dailydata(self.user_id)
        try:
            daily_data.add_data(
                food_name="",  # 運動記錄無需食物名稱
                food_calories=0,  # 食物卡路里為 0
                exercise_name=exercise_name,  # 運動名稱
                exercise_duration=duration_minutes,  # 運動持續時間
                calories_burned=calories_burned  # 消耗卡路里
            )
            print(f"已將運動數據存入資料庫：{exercise_name}，持續 {duration_minutes} 分鐘，消耗 {calories_burned} 卡路里")
        except Exception as e:
            print(f"存入資料庫失敗：{e}")



    # def azureopenai_calculate(self, user_input, weight):
    #     message_text = [
    #         {
    #             "role": "system",
    #             "content": "你是一位專業的運動卡路里分析顧問，會抓取用戶輸入的文字當中的運動名稱,運動時間、運動距離，並透過分析用戶前面提供的這些信息計算消耗的卡路里。",
    #         },
    #         {   
    #             "role": "user", 
    #             "content": f'使用者輸入：" {user_input} "，使用者體重：{weight} 公斤，運動距離：公尺或公里。'
    #         },
    #     ]
        
    #     functions = [{
    #         "name": "get_exercise_info",
    #         "description": "根據輸入提取運動名稱、持續時間、運動距離和消耗的卡路里，返回結果。",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "exercise_name": {"type": "string", "description": "運動名稱"},
    #                 "duration_minutes": {"type": "integer", "description": "運動持續時間，單位：分鐘或小時"},
    #                 "distance_km": {"type": "number", "description": "運動距離，單位可以是公里或公尺。支援的輸入例子包括 '100 公尺', '1 公里', '5 公里', '500 m', '1 km'。"},
    #                 "calories_burned": {"type": "integer", "description": "消耗的卡路里"}
    #             },
    #             "required": ["exercise_name", "duration_minutes", "calories_burned"]
    #         },
    #     }]

    #     try:
    #         ### 調用Azure OpenAI###
    #         completion = client.chat.completions.create(
    #             model=config["AzureOpenAI"]["DEPLOYMENT_NAME_GPT4o"],
    #             messages=message_text,
    #             functions=functions,
    #             max_tokens=800,
    #         )

    #         # 提取 function_call 结果
    #         completion_message = completion.choices[0].message

    #         if hasattr(completion_message, 'function_call') and completion_message.function_call is not None:
    #             # 使用 function_call 来提取数据
    #             this_arguments = json.loads(completion_message.function_call.arguments)
    #             exercise_name = this_arguments.get("exercise_name")
    #             duration_minutes = this_arguments.get("duration_minutes")
    #             distance_km = this_arguments.get("distance_km")
    #             calories_burned = this_arguments.get("calories_burned")

    #             # 如果沒有 duration_minutes 或 distance_km，則中斷程序並回傳提醒信息
    #             if not duration_minutes or not distance_km:
    #                 return "請提供我完整的距離與時間哦，才能精確計算。"
    #         else:
    #             return "請提供我完整的距離與時間哦，才能精確計算。"

    #         # 確保所有數據存在，才進行存儲
    #         if exercise_name and duration_minutes and calories_burned and distance_km:
    #             # 後端自動將提取到的數據存入資料庫
    #             self.store_calorie_data(exercise_name, duration_minutes, calories_burned)

    #             # 返回 Azure OpenAI 回應的結果
    #             return f"運動名稱：{exercise_name}，持續時間：{duration_minutes} 分鐘，運動距離：{distance_km} 公里，消耗卡路里：{calories_burned} 卡路里"
    #         else:
    #             return "請提供我完整的距離與時間哦，才能精確計算。"

    #     except Exception as e:
    #         return f"處理輸入時發生錯誤：{e}"
        

    # def store_calorie_data(self, exercise_name, duration_minutes, calories_burned):
    #     """
    #     將運動數據自動存入資料庫，無需使用者干預
    #     """
    #     daily_data = Dailydata(self.user_id)
    #     try:
    #         daily_data.add_data(
    #             food_name="",  # 運動記錄無需食物名稱
    #             food_calories=0,  # 食物卡路里為 0
    #             exercise_name=exercise_name,  # 運動名稱
    #             exercise_duration=duration_minutes,  # 運動持續時間
    #             calories_burned=calories_burned  # 消耗卡路里
    #         )
    #         print(f"已將運動數據存入資料庫：{exercise_name}，持續 {duration_minutes} 分鐘，消耗 {calories_burned} 卡路里")
    #     except Exception as e:
    #         print(f"存入資料庫失敗：{e}")

