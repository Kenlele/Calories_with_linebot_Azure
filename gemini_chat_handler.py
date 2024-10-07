import logging
from linebot.models import TextSendMessage
from langchain.schema import HumanMessage
from linebot.exceptions import LineBotApiError
from access_db import Userdata
class GeminiChatHandler:
    def __init__(self, line_bot_api, llm_gemini):
        self.line_bot_api = line_bot_api
        self.llm_gemini = llm_gemini
        self.historical_messages = []

    def start_gemini_chat(self, user_states, user_id, reply_token):
        # 開始 Gemini 對話
        user_states[user_id]['in_gemini_chat'] = True
        self.line_bot_api.reply_message(reply_token, TextSendMessage(text="已進入客服小幫手對話，請輸入問題。"))

    def stop_gemini_chat(self, user_states, user_id, reply_token):
        # 結束 Gemini 對話
        user_states[user_id]['in_gemini_chat'] = False
        self.line_bot_api.reply_message(reply_token, TextSendMessage(text="已退出客服小幫手對話。"))

    def handle_gemini_chat(self, user_states, user_id, user_message, reply_token):
        # 檢查用戶是否處於 Gemini 對話模式
    # Check if the user is in Gemini chat mode
        if user_states.get(user_id, {}).get('in_gemini_chat', False):
            try:
                logging.info(f"Gemini對話模式中: {user_message}")
                # Invoke Gemini with the motivational prompt
                response_text = self.invoke_gemini(user_message)
                self.line_bot_api.reply_message(reply_token, TextSendMessage(text=response_text))
            except LineBotApiError as e:
                logging.error(f"Error occurred: {e.message}")
                self.line_bot_api.reply_message(reply_token, TextSendMessage(text='處理您的請求時發生錯誤，請稍後再試。'))
            return True  # Indicates that Gemini chat was handled
        return False  # Indicates that it was not a Gemini chat interaction

        
    
    def invoke_gemini(self,user_id,user_message):
        # 處理與 Gemini 的對話邏輯
    # 抓取使用者的資料
        user_data = Userdata(user_id)
        user_record = user_data.search_data('u_id', user_id)
        
        if not user_record or 'name' not in user_record:
            nickname = "使用者"  # 若無法取得資料，則使用預設稱呼
        else:
            nickname = user_record['name']
        motivational_prompt = f"""
        回應請使用繁體中文，並控制在150字以內
        你是一位熱情的運動顧問，專門幫助人們保持動力並達成健身目標。使用者的名字是 {nickname}，請使用輕鬆愉快的語氣回覆以下問題，
        請先詢問使用者：「您喜歡戶外運動還是室內運動呢？」根據他們的回應，給出適合的運動建議。
        針對使用者問題:{user_message}給予積極的建議，回覆前參考使用者輸入對話的歷史紀錄:{self.historical_messages}並讓用戶感覺到信心十足：
        請不要在回答中使用「**」、「*」、「-」等特殊符號來強調或分隔項目，
        直接使用完整的句子和段落，並在需要強調的地方使用自然語言描述，
        如「首先」、「接著」等來組織內容。

        排版請保持簡潔整齊，使用適當的段落間距來分隔不同部分。
        如果可以，請加一些 emoji 來增加面板的趣味性和吸引力。
        另外，並且如果使用者提問的問題不明確，請給予適當的回答。
        使用者如果告訴違反常規的運動方式，請給予適當的建議。
        例如：說要騎腳踏車五十小時(50hr)，跑步跑三百小時(300hr)等。
        如果使用者給予關心，請給予適當的回答。 
        —— Lady 卡卡      
        """
    
        self.historical_messages.append(user_message)
        human_message = HumanMessage(content=motivational_prompt + "\n" + user_message)
        result = self.llm_gemini.invoke([human_message])
        return result.content.strip()