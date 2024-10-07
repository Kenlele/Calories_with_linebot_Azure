# sport_consultant.py
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage
import configparser
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
import re
# 初始化配置
config = configparser.ConfigParser()
config.read('config.ini')

# 初始化 Gemini API 客戶端
llm_gemini = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash-latest", 
    google_api_key=config["Gemini"]["API_KEY"]
)

# 使用一個字典來存儲每個用戶的對話歷史
user_histories = {}

def get_user_history(user_id: str):
    # 如果這個用戶的歷史不存在，為他創建一個新的
    if user_id not in user_histories:
        user_histories[user_id] = {
            'history': ChatMessageHistory(),
            'state': {'role': '專業運動顧問', 'activity': None}
        }
    return user_histories[user_id]['history']

def get_user_state(user_id: str):
    # 獲取用戶的狀態
    if user_id not in user_histories:
        user_histories[user_id] = {
            'history': ChatMessageHistory(),
            'state': {'role': '專業運動顧問', 'activity': None}
        }
    return user_histories[user_id]['state']

def set_user_state(user_id: str, role=None, activity=None):
    state = get_user_state(user_id)
    if role:
        state['role'] = role
    if activity:
        state['activity'] = activity
    print(f"狀態已更新 : {state}")

def generate_user_description(user_data):
    # 使用者的基本信息
    age = user_data.get('age')
    gender = user_data.get('gender')
    weight = user_data.get('weight')
    height = user_data.get('height')

    # 計算BMI
    bmi = weight / ((height / 100) ** 2)

    # 根據BMI值來判斷使用者的體型
    if bmi < 18.5:
        weight_status = "體重過輕"
    elif 18.5 <= bmi < 24.9:
        weight_status = "體重正常"
    elif 24.9 <= bmi < 29.9:
        weight_status = "體重過重"
    else:
        weight_status = "肥胖"

    # 根據性別和年齡生成描述
    if gender == 1:
        gender_description = "男性"
    else:
        gender_description = "女性"

    user_description = f"使用者的基本資料: {age}歲的{gender_description}，{weight_status}"
    return user_description

def replace_special_symbols(text):
    """處理文本中的特殊符號與引號冒號順序問題"""
    # 將所有成對的 ** 替換為「」
    replaced_text = re.sub(r'\*\*(.*?)\*\*', r'「\1」', text)
    # 將單個 * 替換為圓形符號
    replaced_text = replaced_text.replace('* ', '• ')
    # 修正引號和冒號的順序
    replaced_text = re.sub(r'「(.*?)」\s*:', r'「\1」:', replaced_text)
    return replaced_text

def validate_activity_time(activity, hours):
    # 設置不同運動類型的最大時數
    max_time_limits = {
        "跑步": 2,  # 跑步一天最多2小時
        "騎腳踏車": 4,  # 騎腳踏車最多4小時
        "游泳": 2,  # 游泳最多2小時
    }
    
    # 獲取運動類型的最大時數，默認最大為2小時
    max_hours = max_time_limits.get(activity, 2)
    
    # 確保 hours 是 float 類型
    try:
        hours = float(hours)
    except ValueError:
        return False, hours  # 如果轉換失敗，視為不合理輸入，保留原始輸入
    
    # 判斷是否超過最大時數
    if hours > max_hours:
        print("超過最大時數")
        return False, hours  # 返回 False 並保留用戶實際輸入的時間
    return True, hours

def generate_brtr_prompt(user_id, user_data, activity=None):
    background, request, tone, result = "", "", "", ""
    is_valid = True  # 初始化為 True
    # B: Background 背景
    state = get_user_state(user_id)
    advisor_role = state['role']
    
    background = f"""
    你是一個名字叫Lady卡卡，是一位{advisor_role}，根據使用者的健康資料和目標提供個性化的運動建議。
    """

    # R: Request 任務
    user_description = generate_user_description(user_data)
    print("使用者描述 : ", user_description)
    print("活動 : ", activity)
    if activity:
        try:
            activity_type, activity_duration = activity.split(" ")
            if "小時" in activity_duration:
                current_hours = float(activity_duration.replace("小時", ""))
                current_minutes = current_hours * 60  # 設定 current_minutes 以防稍後使用
            elif "分鐘" in activity_duration:
                current_minutes = float(activity_duration.replace("分鐘", ""))
                current_hours = current_minutes / 60  # 轉換為小時
            else:
                # 當活動時間格式不正確時，返回錯誤提示
                return False, "請確保格式正確，例如：'2小時' 或 '30分鐘'。"

            # 檢查是否超過最大時數
            is_valid, adjusted_hours = validate_activity_time(activity_type, current_hours)
            time_display = f"{current_hours:.1f} 小時" if current_hours >= 1 else f"{int(current_minutes)} 分鐘"  # 改成顯示小數點一位

            if not is_valid:
                print(f"返回提示：超過了最大時數，返回提示信息")
                # 如果時間不合理，返回 is_valid=False 和錯誤提示
                request = (
                    f"您選擇了進行 {activity_type} {time_display}。\n\n"
                    "雖然運動對健康很有幫助，但為了避免過度運動帶來的負擔，\n"
                    "我們建議您將時間分段，每段不超過 2 小時。\n\n"
                    "請記得保持充足的休息，這樣會讓您的運動效果更持久！"
                )
                return is_valid, request
        except ValueError:
            # 當解析失敗時，返回解析錯誤的提示
            return False, "無法解析活動和時間，請確保格式正確，例如：'2小時'。"
        
        print("時間邏輯不對不該往下繼續")
        # 如果時間合理，生成運動建議的請求文本
        request = f"""
        使用者 {user_description} 今天決定進行 {activity_type} 大約 {time_display}，請提供一個能幫助他達成健身目標的運動建議。
        """
        # T: Tone 語氣
        tone = """
        回覆應保持鼓勵和支持的語氣，讓使用者感受到運動的樂趣並保持動力。
        請使用標準的中文標點符號，例如「。」和「，」。
        請避免使用特殊符號來強調內容，如 * 或 #，確保語句通順自然，例如用「首先」、「特別要注意的是」等自然語言來描述。
        回應請使用繁體中文，總字數控制在250字以內，並可適當使用 emoji 來增加趣味性。
        """

        # R: Result 結果
        result = """
        請生成詳細的運動計畫，將其分成四個區塊：「1天」、「1週」、「1個月」的運動計畫和個性化的「健康建議」。

        每個區塊應包含：
        - 運動的時間安排、強度變化、以及必要的休息計畫；
        - 保持每個區塊的描述簡潔清楚，便於使用者理解並實施。

        在最後一個區塊提供個性化的「健康建議」區塊應排版整齊，使用清晰的項目符號或編號列出：
        1. 鼓勵使用者建立自信，保持積極的心態，讓他們相信自己能夠達到運動目標。
        2. 提供具體的飲食建議，如多攝取蛋白質以幫助恢復，保持良好的水分補充。
        3. 介紹良好的睡眠習慣如何提高運動表現，幫助身體更快恢復，並減少疲勞。
        4. 總字數請在90字以內

        確保這些建議具有可操作性，並使用簡單易懂的語言，避免過於複雜的專業術語。
        """
    else:
        print("沒有活動信息，返回通用的建議請求")
        # 如果沒有活動信息，返回通用的建議請求
        request = f"""
        使用者 {user_description} 還不確定要進行什麼運動，請根據其健康資料{user_description}提供一個能達到其健身目標的全面運動建議。
        """

    # 組合成最終的 BRTR prompt
    brtr_prompt = background + request + tone + result
    print("BRTR提示詞 : ", brtr_prompt)
    return is_valid, brtr_prompt  # 確保始終返回兩個值


def get_activity_advice(user_id, user_data, activity=None):
    print(f"收到的 activity: {activity}")
    
    # 使用 BRTR 原則生成 prompt，並同時獲取 is_valid 狀態
    is_valid, brtr_prompt = generate_brtr_prompt(user_id, user_data, activity)

    # 如果活動時間不合理，直接返回手動提示
    if not is_valid:
        print("運動時間超過限制或格式錯誤，直接返回手動提示。")
        return is_valid, brtr_prompt  # 返回手動提示和 is_valid=False

    # 如果活動時間合理，調用 Gemini API 獲取建議
    human_message = HumanMessage(content=brtr_prompt)
    
    try:
        gemini_response = llm_gemini.invoke([human_message])
        cleaned_response = replace_special_symbols(gemini_response.content)
        return True, cleaned_response  # 返回從 Gemini 生成的文本和 is_valid=True
    except Exception as e:
        print(f"Gemini API 錯誤: {e}")
        return False, "無法生成建議，請重試。"  # 返回錯誤時的手動提示
    

