from flask import Flask, request, abort, render_template, redirect, url_for, jsonify , send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, TemplateSendMessage,FlexSendMessage,
    ButtonsTemplate, PostbackAction, ImageMessage,
    QuickReply, QuickReplyButton, MessageAction, URIAction, PostbackEvent
)
import re
import requests
from configparser import ConfigParser
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage
import io
import base64
from PIL import Image
import threading
from datetime import datetime
from access_db import Userdata, Dailydata  # 資料庫操作
from health_dashboard import HealthDashboard  # 健康數據監控
from food_analyzer import FoodCalorieAnalyzer  # 食物熱量分析
from sport_caculate import CalorieAnalyzer
import os
from personalized_plan import generate_plan

from update_weight import WeightUpdater
from gemini_chat_handler import GeminiChatHandler
from monitoring import check_calories 
from Strava_ca import StravaAPI
from sport_consultant import get_activity_advice
from sport_consultant import get_activity_advice
from flex_message_utils import generate_diet_flex_messages, generate_flex_messages
class Lineca:
    def __init__(self):
        self.app = Flask(__name__) #開始Flask
        # 初始化日誌
        logging.basicConfig(level=logging.INFO)
        self.config = ConfigParser()
        self.config.read("config.ini")
        self.strava_api = StravaAPI(
            client_id=self.config['STRAVA']['CLIENT_ID'],
            client_secret=self.config['STRAVA']['CLIENT_SECRET'],
            redirect_uri= f"{self.config['ngrok']['website_url']}/strava_callback"
        )
        self.users_tokens = {} # 用戶的存取權杖和換發權杖
        # 記錄當天的卡路里累積數據
        self.calorie_tracker = {}

        self.channel_access_token = self.config["LineBot"]["CHANNEL_ACCESS_TOKEN"]
        self.channel_secret = self.config["LineBot"]["CHANNEL_SECRET"]
        self.flask_host = self.config["Flask"]["HOST"]
        self.flask_port = int(self.config["Flask"]["PORT"])
        self.app.secret_key = os.urandom(24)  # 設置一個隨機的 secret key for 數據圖表session抓取數字用
        channel_access_token = self.config['LineBot']['CHANNEL_ACCESS_TOKEN']
        channel_secret = self.config['LineBot']['CHANNEL_SECRET']
        self.line_bot_api = LineBotApi(self.channel_access_token)
        self.handler = WebhookHandler(self.channel_secret)
        self.llm_gemini = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash-latest",
            google_api_key=self.config["Gemini"]["API_KEY"],
            convert_system_message_to_human=True,
        )
    

        # 初始化 GeminiChatHandler
        self.gemini_chat_handler = GeminiChatHandler(self.line_bot_api, self.llm_gemini)


        #建立用戶的卡路里標準
        self.calorie_standards = {}

        # 初始化健康儀表板
        self.dashboard = HealthDashboard(self.app)

        # 設置 Rich Menu IDs
        self.rich_menu_ids = [
            "richmenu-94f3bf5f154159dfda9fd72465a8fae2",  # Rich Menu 1
            "richmenu-e2b9fa51177550d4c412aa12424257ec",  # Rich Menu 2
            "richmenu-e6a249c50cf34d0a73d0fbe364f6c299",  # Rich Menu 3
            "richmenu-40c68086b6010bdaa6165b1e30757938",  # Rich Menu 4
            "richmenu-3fcdd5d43a2a3ed17fd9e99fea2dabac",  # Rich Menu 5
        ]
       
        self.timers = {}
        self.user_states = {}
        self.monitoring_users = {}
        self.monitor_intervals = {
            "daily": 86400,  # 每天
            "hourly": 3600,  # 每小時
            "custom": None   # 用戶自定義（需要指定時間）
        }
        self.user_target_weights = {}


        # 設置路由和處理函數
        self.setup_routes()
    def setup_routes(self):

        # 設定 /callback 路由
        @self.app.route("/callback", methods=['POST'])
        def callback():
            signature = request.headers['X-Line-Signature']
            body = request.get_data(as_text=True)

            logging.info(f"Request body: {body}")

            try:
                self.handler.handle(body, signature)
            except InvalidSignatureError:
                logging.error("Invalid signature. Check your channel secret and access token.")
                abort(400)

            
            return 'OK'

        @self.app.route('/favicon.ico')
        def favicon():
            return send_from_directory(os.path.join(self.app.root_path, 'static'),
                                    'favicon.ico', mimetype='image/vnd.microsoft.icon')
        
        @self.app.route("/dashboard/<user_id>")
        def display_dashboard(user_id):
            # 使用 self.dashboard 渲染用戶的健康數據
            return self.dashboard.render_dashboard(user_id)


        @self.app.route('/strava_callback')
        def strava_callback():
            code = request.args.get('code')
            user_id = request.args.get('state')  # 通過 state 參數傳遞 user_id
            if code and user_id:
                try:
                    # 使用 StravaAPI 的方法交換授權碼以獲取 tokens
                    token_response = self.strava_api.get_strava_token(code)
                    
                    # 檢查 token_response 是否包含所需的 token 信息
                    if token_response and 'access_token' in token_response and 'refresh_token' in token_response:
                        # 保存 token 信息
                        self.strava_api.save_strava_tokens(user_id, token_response)
                        return "授權成功！您可以回到 LINE 應用並輸入 'strava' 查看運動數據。"
                    else:
                        logging.error("token_response 中缺少必要的 token 信息")
                        return "授權失敗，請重試。"
                except Exception as e:
                    logging.error(f"授權過程中發生錯誤: {e}")
                    return "授權失敗，請重試。"
            else:
                return "無效的授權碼！"
            
        @self.handler.add(MessageEvent, message=TextMessage)
        def handle_message(event):
            self.event = event
            user_id = self.event.source.user_id  # 獲取用戶的 user_id
            user_message = event.message.text.strip()
            reply_token = event.reply_token
            self.user_db = Userdata(user_id)  # 傳入 user_id
            self.daily_db = Dailydata(user_id)  # 傳入 user_id

            # 確保用戶狀態存在
            self.ensure_user_state(user_id)

            # 確保 current_state 被賦值
            current_state = self.user_states[user_id].get('state')
            
            # 定義功能關鍵字列表
            function_keywords = ['飲食打卡', '健康數據', 'AI減肥攻略', '燃脂打卡', '我的狀態', '運動建議']
            # 如果使用者正在輸入資料過程中，先檢查是否輸入了功能關鍵字
            if current_state in ['awaiting_nickname', 'awaiting_gender', 'awaiting_age', 'awaiting_height', 'awaiting_weight']:
                if user_message in function_keywords:
                    # 如果使用者輸入了功能關鍵字，則跳轉到該功能，並重置輸入狀態
                    logging.info(f"User {user_id} switched to function: {user_message}, exiting current input flow.")
                    self.user_states[user_id]['state'] = None  # 重置狀態

                    # 根據功能關鍵字執行對應操作
                    if user_message == '飲食打卡':
                        self.user_states[user_id]['state'] = 'awaiting_food'
                        self.line_bot_api.reply_message(reply_token, TextSendMessage(text="請輸入您今天吃了什麼。"))
                    elif user_message == '健康數據':
                        self.user_states[user_id]['state'] = 'awaiting_health_data'
                        return self.handle_health_data(user_id, reply_token)
                    elif user_message == 'AI減肥攻略':
                        self.user_states[user_id]['state'] = 'awaiting_target_weight'
                        self.line_bot_api.reply_message(reply_token, TextSendMessage(text="請輸入您想要達到的目標體重（公斤）："))
                    elif user_message == '燃脂打卡':
                        self.user_states[user_id]['state'] = 'awaiting_exercise'
                        self.line_bot_api.reply_message(reply_token, TextSendMessage(text="請輸入您做了什麼運動，請提供給我你的時間和距離 ："))
                    elif user_message == '我的狀態':
                        self.user_states[user_id]['state'] = None
                        self.line_bot_api.reply_message(reply_token, TextSendMessage(text="您可以查看您的狀態資料。"))
                    elif user_message == '運動建議':
                        self.line_bot_api.reply_message(reply_token, TextSendMessage(text="請問您想要什麼運動建議？"))
                        self.user_states[user_id]['state'] = 'awaiting_activity_advice'
                        return get_activity_advice(user_id, self.line_bot_api, reply_token)
                    

                else:
                    # 如果不是功能關鍵字，繼續資料輸入流程
                    if current_state == 'awaiting_nickname':
                        self.handle_nickname(user_message, reply_token)
                    elif current_state == 'awaiting_gender':
                        self.handle_gender(user_message, reply_token)
                    elif current_state == 'awaiting_age':
                        self.handle_age(user_message, reply_token)
                    elif current_state == 'awaiting_height':
                        self.handle_height(user_message, reply_token)
                    elif current_state == 'awaiting_weight':
                        self.handle_weight(user_message, reply_token)

                return  # 如果在等待資料輸入，不繼續執行後續邏輯
            
            # 確保當天的卡路里數據存在於字典中，使用當天日期作為鍵
            current_date = datetime.now().strftime('%Y-%m-%d')
            if user_id not in self.calorie_tracker:
                self.calorie_tracker[user_id] = {current_date: {'food_calories': 0, 'calories_burned': 0}}

            
            # 確認當前用戶狀態
            current_state = self.user_states.get(user_id, {}).get('state', None)

            # 當使用者進入 Line Bot 並按下「我的狀態」
            if user_message == '我的狀態':
                logging.info("Processing: 我的狀態")
                self.website_url = self.config["ngrok"]["website_url"]  # ngrok URL
                # QuickReply buttons for 更新基本資料 and 剩餘可攝取卡路里
                quick_reply_buttons = QuickReply(
                    items=[
                        QuickReplyButton(
                            action=MessageAction(label="我的基本資料", text="我的基本資料"),image_url=f"{self.website_url}/static/icons/data.jpeg"
                        ),
                        QuickReplyButton(
                            action=MessageAction(label="查看今日目標剩餘卡路里", text="查看今日目標剩餘卡路里"),image_url=f"{self.website_url}/static/icons/fire.jpeg"
                        )
                    ]
                )
                
                # 回應 quick reply buttons
                self.line_bot_api.reply_message(
                    reply_token,
                    TextSendMessage(
                        text="請選擇以下選項：",
                        quick_reply=quick_reply_buttons
                    )
                )
            
                return
            

            if user_message == '團隊介紹':
                logging.info("Processing: 團隊介紹")
                # 團隊成員資料
                self.website_url = self.config["ngrok"]["website_url"]  # ngrok URL
                team_members = [
                    {"name": "小賴", "role": "組長，前端，功能開發，系統整合", "image": f"{self.website_url}/static/images/member1.jpg"},
                    {"name": "威廉", "role": "功能開發", "image": f"{self.website_url}/static/images/member2.jpg"},
                    {"name": "JOJO", "role": "功能開發", "image": f"{self.website_url}/static/images/member3.jpg"},
                    {"name": "Vicky", "role": "功能開發", "image": f"{self.website_url}/static/images/member4.jpg"},
                    {"name": "Steven", "role": "資料庫開發", "image": f"{self.website_url}/static/images/member5.jpg"},
                    {"name": "James", "role": "資料庫開發", "image": f"{self.website_url}/static/images/member6.jpg"},
                    {"name": "肥羊", "role": "功能開發", "image": f"{self.website_url}/static/images/member7.jpg"},
                ]

                # 使用函數生成所有成員的 bubbles
                bubbles = [self.create_member_bubble(member["name"], member["role"], member["image"]) for member in team_members]

                # 建立 Flex Message
                flex_message = FlexSendMessage(
                    alt_text='團隊介紹',
                    contents={
                        "type": "carousel",
                        "contents": bubbles
                    }
                )

                # 發送 Flex Message
                self.line_bot_api.reply_message(reply_token, flex_message)

            # Step 2: 處理「更新基本資料」邏輯
            if user_message == '我的基本資料':
                logging.info("Processing: 更新基本資料")
                # 直接開始請求輸入綽號
                self.line_bot_api.reply_message(
                    reply_token,
                    TextSendMessage(text="請告訴我您的綽號。")
                )
                self.user_states[user_id]['state'] = 'awaiting_nickname'
                return
            # Step 3: 處理「查看剩餘卡路里」邏輯
            if user_message == '查看今日目標剩餘卡路里':
                logging.info("Processing: 查看剩餘卡路里")
                
                # 從 calorie_tracker 中計算剩餘卡路里
                current_date = datetime.now().strftime('%Y-%m-%d')
                if user_id in self.calorie_tracker and current_date in self.calorie_tracker[user_id]:
                    consumed_calories = self.calorie_tracker[user_id][current_date].get('food_calories', 0)
                    burned_calories = self.calorie_tracker[user_id][current_date].get('calories_burned', 0)
                    net_calories = consumed_calories - burned_calories
                    remaining_calories = self.calorie_standards.get(user_id, {}).get('recommended_daily_calories', 2000) - net_calories
                    
                    # 回覆剩餘卡路里量
                    self.website_url = self.config["ngrok"]["website_url"]  # ngrok URL
                    self.line_bot_api.reply_message(
                        reply_token,
                        TextSendMessage(
                            text=f"您今日剩餘可攝取卡路里量為：{remaining_calories} 卡。是否要記錄您的飲食或運動？",
                            quick_reply=QuickReply(
                                items=[
                                    QuickReplyButton(action=MessageAction(label="記錄飲食", text="飲食打卡"),image_url=f"{self.website_url}/static/icons/food.jpeg"),
                                    QuickReplyButton(action=MessageAction(label="記錄運動", text="燃脂打卡"),image_url=f"{self.website_url}/static/icons/exercise.jpeg"),
                                    QuickReplyButton(action=MessageAction(label="不需要", text="不需要"),image_url=f"{self.website_url}/static/icons/no.png"),
                                ]
                            )
                        )
                    )
                else:
                    # 沒有資料時的處理
                    self.line_bot_api.reply_message(
                        reply_token,
                        TextSendMessage(text="今日尚無卡路里數據，請先記錄飲食或運動。")
                    )
                return

            
                # 檢查是否包含體重變化關鍵字
            if any(keyword in user_message for keyword in ['瘦了', '胖了', '瘦了公斤','胖了公斤' ]):
                self.line_bot_api.reply_message(
                    reply_token,
                    TextSendMessage(text="請告訴我您的最新體重是多少公斤？")
                )
                self.user_states[user_id]['state'] = 'awaiting_weight_update'
                return
    
            # Step 1: 如果處於等待體重更新的狀態
            if self.user_states[user_id]['state'] == 'awaiting_weight_update':
                # 移除 "公斤" 等字眼，並檢查是否為數字
                cleaned_message = user_message.replace('公斤', '').replace('kg', '').strip()
                if cleaned_message.isdigit() or cleaned_message.replace('.', '', 1).isdigit():
                    new_weight = float(cleaned_message)
                    
                    # 使用 WeightUpdater 來更新體重
                    weight_updater = WeightUpdater(user_id)
                    update_result_message = weight_updater.update_weight(new_weight)

                    self.line_bot_api.reply_message(
                        reply_token,
                        TextSendMessage(text=update_result_message)
                    )

                # 重置狀態
                    self.user_states[user_id]['state'] = None
                else:
                    self.line_bot_api.reply_message(
                        reply_token,
                        TextSendMessage(text="請輸入有效的體重數字，例如 65 或 65.5 公斤。")
                    )
                return   
            # Step 1.2: 觸發“我的計畫”
            if user_message == "AI減肥攻略":
                logging.info("Processing: 我的計畫")

                user_data = self.get_user_data(user_id)
                if not user_data:
                    self.line_bot_api.reply_message(
                        reply_token,
                        TextSendMessage(text='請先更新您的基本資料（我的狀態->個人資料）, AI才能給您個人化減肥計畫')
                    )
                    return
                if 'target_weight' not in user_data:
                    self.line_bot_api.reply_message(
                        reply_token,
                        TextSendMessage(text='請於輸出列，輸入想要瘦到的目標體重（公斤）：')
                    )
                    self.user_states[user_id]['state'] = 'awaiting_target_weight'
                return  # 返回，避免進入其他處理邏輯
            
            if current_state == 'awaiting_target_weight':
                # 移除「公斤」單位，並檢查是否為數字
                cleaned_message = user_message.replace('公斤', '').strip()
                if cleaned_message.replace('.', '', 1).isdigit():
                    # 取得目標體重
                    target_weight = float(cleaned_message)
                    # 假設用戶的目標體重在weight_target欄位
                    daily_data = Dailydata(user_id)
                    daily_data.add_data(
                        food_name=None,  # 假设不需要存食物信息
                        food_calories=0,  # 假设此处没有食物热量
                        exercise_name=None,  # 假设此处没有运动信息
                        exercise_duration=0,  # 假设此处没有运动时长
                        weight_target=target_weight,  # 存储目标体重到 weight_target
                        bmr_target=0,  # 存储 BMR 到 bmr_target
                        calories_burned=0 
                        ) # 假设此处没有卡路里消耗'weight_target', target_weight)
                    
                    # 呼叫個性化減肥計畫生成器
                    personalized_plan = generate_plan(self.llm_gemini, user_id , target_weight)
                    diet_plan, standards = personalized_plan.generate_plan()

                    # 檢查是否成功生成減肥計畫
                    if not diet_plan:
                        self.line_bot_api.reply_message(
                            reply_token,
                            TextSendMessage(text=standards)  # 如果是錯誤訊息，直接回傳
                        )
                        return
                    
                    #使用flex message 顯示減肥計畫
                    flex_messages = generate_diet_flex_messages(diet_plan)
                      # 確保至少有一個訊息
                    if flex_messages:
                        self.line_bot_api.reply_message(reply_token, flex_messages)
                    else:
                        self.line_bot_api.reply_message(
                            reply_token,
                            TextSendMessage(text="無法生成減肥建議，請重試。")
                        )

                    # # 回覆減肥建議
                    # self.line_bot_api.reply_message(
                    #     reply_token,
                    #     TextSendMessage(text=f'您的減肥建議：\n{diet_plan}')
                    # )

                
                    # 將卡路里標準存到 calorie_standards 中
                    self.calorie_standards[user_id] = {
                        'recommended_daily_calories': standards.get('recommended_daily_calories'),
                    }
                    # 根據標準切換 Rich Menu
                    self.switch_rich_menu(user_id, self.calorie_standards[user_id])

                    # 開始監控用戶數據
                    self.line_bot_api.push_message(user_id, TextSendMessage(text="我們已開始監控您的健康數據，會定期提醒您！"))
                    return
                
            # Step 6: 處理 Strava 數據
            if user_message == 'authorize_strava':
                auth_url = self.strava_api.get_auth_url(user_id)
                self.line_bot_api.reply_message(
                    reply_token,
                    TextSendMessage(text=f"請點擊以下鏈接進行授權:\n{auth_url}")
                )
                return  # 確保不會執行後續的其他邏輯
            
            elif user_message == 'strava':
                # 使用 StravaAPI 的方法來獲取活動數據回覆
                message = self.strava_api.get_strava_reply(user_id)
                self.line_bot_api.reply_message(reply_token, TextSendMessage(text=message))
            
            # 初始化用戶卡路里數據

            if user_id not in self.calorie_tracker:
                self.calorie_tracker[user_id] = {current_date: {'food_calories': 0, 'calories_burned': 0}}

            # 記錄飲食
            if user_message == '飲食打卡':
                self.user_states[user_id]['state'] = 'awaiting_food'
                self.line_bot_api.reply_message(reply_token, TextSendMessage(text="請輸入您吃了什麼："))
                return

            # 記錄運動
            elif user_message == '燃脂打卡':
                self.user_states[user_id]['state'] = 'awaiting_exercise'
                self.line_bot_api.reply_message(reply_token, TextSendMessage(text="請輸入您做了什麼運動，請提供給我你的時間和距離 ："))
                return

            if self.user_states[user_id].get('state') == 'awaiting_food':
                food_analyzer = FoodCalorieAnalyzer(user_id)
                result_message = food_analyzer.store_analyze_calories_from_text(user_message)
                 # 如果返回錯誤消息，直接推送給用戶
                if user_message in ['健康數據', '燃脂打卡','我的狀態','運動建議','AI減肥攻略']:  # 假設有其他功能需要處理
                    self.user_states[user_id]['state'] = None  # 重置狀態
                    self.line_bot_api.reply_message(reply_token, TextSendMessage(text="已退出飲食紀錄。"))
                    return

                if "請提供" in result_message or "無法" in result_message:  # 根據回傳訊息判斷是否有錯誤
                    self.line_bot_api.reply_message(reply_token, TextSendMessage(text=result_message))
         
                # 只有在辨識成功後，才進行卡路里計算
                if "總共含有" in result_message:  # 檢查結果是否包含卡路里信息
                    try:
                        # 提取總卡路里
                        total_food_calories = int(re.search(r'總共含有 (\d+) 大卡', result_message).group(1))
                    except AttributeError:
                        total_food_calories = 0  # 找不到總卡路里資訊時設為 0
                    
                    # 將總卡路里累加到 calorie_tracker 中
                    self.calorie_tracker[user_id][current_date]['food_calories'] += total_food_calories
                    
                    # # 推播成功訊息
                    # self.line_bot_api.reply_message(reply_token, TextSendMessage(text=result_message))
                    # 計算剩餘卡路里
                    daily_limit = self.calorie_standards.get(user_id, {}).get('recommended_daily_calories', 2000)
                    food_calories = self.calorie_tracker[user_id][current_date]['food_calories']
                    calories_burned = self.calorie_tracker[user_id][current_date]['calories_burned']
                    net_calories = food_calories - calories_burned
                    remaining_calories = daily_limit - net_calories

                    # 推播剩餘可攝取的卡路里資訊
                    self.line_bot_api.reply_message(
                        reply_token,
                        TextSendMessage(text=f"{result_message}\n目前剩餘可攝入卡路里：{remaining_calories} 卡路里")
                    )
                    # 檢查是否超標
                    self.check_calorie_limit(user_id, current_date)

                    # 辨識成功後才退出等待狀態
                    self.user_states[user_id]['state'] = None
                return

            # 進入運動記錄狀態
            if self.user_states[user_id].get('state') == 'awaiting_exercise':
                calorie_analyzer =CalorieAnalyzer(user_id)
                result_message = calorie_analyzer.handle_user_input(user_message)
                if user_message in ['健康數據', '飲食打卡','我的狀態','運動建議','AI減肥攻略']:  # 假設有其他功能需要處理
                    self.user_states[user_id]['state'] = None  # 重置狀態
                    self.line_bot_api.reply_message(reply_token, TextSendMessage(text="已退出運動紀錄。"))
                    return
                
                # 如果輸入不完整，保持在運動記錄狀態並提示輸入完整數據
                if "請提供我完整的運動名稱、時間和距離，才能精確計算" in result_message:
                    self.line_bot_api.reply_message(reply_token, TextSendMessage(text=result_message))
                    # 明確保持狀態，繼續等待用戶輸入完整數據
                    self.user_states[user_id]['state'] = 'awaiting_exercise'
                    return

                # 記錄運動燃燒的卡路里
                exercise_calories = self.extract_calories(result_message)
                self.calorie_tracker[user_id][current_date]['calories_burned'] += exercise_calories

                # 獲取當天攝取的食物卡路里
                food_calories = self.calorie_tracker[user_id][current_date]['food_calories']

                # 計算每日卡路里限額
                daily_limit = self.calorie_standards.get(user_id, {}).get('recommended_daily_calories', 2000)

                # 計算淨卡路里（攝取的食物卡路里減去燃燒的運動卡路里）
                net_calories = food_calories - self.calorie_tracker[user_id][current_date]['calories_burned']

                # 計算剩餘可攝取的卡路里
                remaining_calories = daily_limit - net_calories

                # 推播剩餘可攝取的卡路里
                self.line_bot_api.reply_message(
                    reply_token,
                    TextSendMessage(text=f"{result_message}\n目前剩餘可攝入卡路里：{remaining_calories} 大卡。")
                )

                # 檢查是否超標
                self.check_calorie_limit(user_id, current_date)

                # 重置狀態
                self.user_states[user_id]['state'] = None
                return
            
            if user_message == '運動建議':
                self.website_url = self.config["ngrok"]["website_url"]  # ngrok URL
                self.user_states[user_id]['state'] = 'awaiting_activity_advice'
                quick_reply_buttons = QuickReply(
                    items=[
                        QuickReplyButton(action=MessageAction(label="跑步", text="我想要去跑步"),image_url=f"{self.website_url}/static/icons/running.png"),
                        QuickReplyButton(action=MessageAction(label="游泳", text="我想要去游泳"),image_url=f"{self.website_url}/static/icons/swimming.png"),
                        QuickReplyButton(action=MessageAction(label="騎自行車", text="我想要去騎腳踏車"),image_url=f"{self.website_url}/static/icons/bicycle.png"),
                        QuickReplyButton(action=MessageAction(label="請給我意見", text="我不知道該做什麼運動"),image_url=f"{self.website_url}/static/icons/sport_advisor.png")
                    ]
                )
                self.line_bot_api.reply_message(
                    reply_token,
                    TextSendMessage(
                        text="請選擇一個運動方式:",
                        quick_reply=quick_reply_buttons
                    )
                )
            
            elif user_message == '我想要去跑步':
                    self.line_bot_api.reply_message(
                        reply_token,
                        TextSendMessage(text="請告訴我您打算跑多久？")
                    )
                    self.user_states[user_id]['state'] = 'awaiting_running_duration'
                    return

            elif user_message == '我想要去游泳':
                self.line_bot_api.reply_message(
                    reply_token,
                    TextSendMessage(text="請告訴我您打算游多久？")
                )
                self.user_states[user_id]['state'] = 'awaiting_swimming_duration'
                return

            elif user_message == '我想要去騎腳踏車':
                self.line_bot_api.reply_message(
                    reply_token,
                    TextSendMessage(text="請告訴我您打算騎多久？")
                )
                self.user_states[user_id]['state'] = 'awaiting_cycling_duration'
                return

            elif self.user_states[user_id].get('state') == 'awaiting_running_duration':
                self.handle_activity_suggestion(user_id, reply_token, '跑步', user_message)
                # user_data = self.user_db.search_data('u_id', user_id)
                # if not user_data:
                #     self.line_bot_api.reply_message(
                #         reply_token,
                #         TextSendMessage(text="無法找到您的個人資料，請先更新基本資料。")
                #     )
                #     return

                # duration = user_message
                # gemini_advice = get_activity_advice(user_id, user_data, activity=f'跑步 {duration}')

                # self.line_bot_api.reply_message(
                #     reply_token,
                #     TextSendMessage(text=f"根據您的資料，運動顧問的建議是：\n{gemini_advice}")
                # )
                # self.user_states[user_id]['state'] = None
                # return

            elif self.user_states[user_id].get('state') == 'awaiting_swimming_duration':
                self.handle_activity_suggestion(user_id, reply_token, '游泳', user_message)
                # user_data = self.user_db.search_data('u_id', user_id)
                # if not user_data:
                #     self.line_bot_api.reply_message(
                #         reply_token,
                #         TextSendMessage(text="無法找到您的個人資料，請先更新基本資料。")
                #     )
                #     return

                # duration = user_message
                # gemini_advice = get_activity_advice(user_id, user_data, activity=f'游泳 {duration}')

                # self.line_bot_api.reply_message(
                #     reply_token,
                #     TextSendMessage(text=f"根據您的資料，運動顧問的建議是：\n{gemini_advice}")
                # )
                # self.user_states[user_id]['state'] = None
                # return

            elif self.user_states[user_id].get('state') == 'awaiting_cycling_duration':

                self.handle_activity_suggestion(user_id, reply_token, '騎腳踏車', user_message)
                # user_data = self.user_db.search_data('u_id', user_id)
                # duration = user_message
                # gemini_advice = get_activity_advice(user_id, user_data, activity=f'騎腳踏車 {duration}')
                # self.line_bot_api.reply_message(
                #     reply_token,
                #     TextSendMessage(text=f"根據您的資料，運動顧問的建議是：\n{gemini_advice}")
                # )
                # self.user_states[user_id]['state'] = None
                # return

            # 若用戶不確定要做什麼運動，提供建議
            elif user_message == '我不知道該做什麼運動':
                user_data = self.user_db.search_data('u_id', user_id)
                if not user_data:
                    self.line_bot_api.reply_message(
                        reply_token,
                        TextSendMessage(text="無法找到您的個人資料，請先更新基本資料。")
                    )
                    return
                else:
                    self.user_states[user_id]['state'] = 'gemini_chat'  # 切換到 gemini_chat 狀態
                    gemini_response = self.gemini_chat_handler.invoke_gemini(user_id,user_message)  # 啟動 Gemini chat
                    self.line_bot_api.reply_message(
                        reply_token,
                        TextSendMessage(text=f"根據您的資料，我的建議是：\n{gemini_response}")
                    )
                self.user_states[user_id]['state'] = 'gemini_chat'
                return
            if self.user_states[user_id].get('state') == 'gemini_chat':
                if user_message in ["掰掰", "結束對話", "bye", "再見"]: # 結束對話跳出狀態
                    self.line_bot_api.reply_message(
                        reply_token,
                        TextSendMessage(text="感謝您的詢問，有問題再來找卡卡喔！")
                    )
                    self.user_states[user_id]['state'] = None  # 重置狀態
                else:
                    # 否則，持續調用 Gemini 進行對話
                    gemini_response = self.gemini_chat_handler.invoke_gemini(user_id,user_message)
                    self.line_bot_api.reply_message(reply_token, TextSendMessage(text=gemini_response))
                return
           

            elif user_message == '我完成任務':
                logging.info("Processing: 我完成了任務")
                # 將 Rich Menu 切換回預設的第 0 張
                self.user_states[user_id]['current_rich_menu_index'] = 0
                rich_menu_id = self.rich_menu_ids[0]  # 預設為第 0 張 Rich Menu
                try:
                    # 切換 Rich Menu
                    self.line_bot_api.link_rich_menu_to_user(user_id, rich_menu_id)
                    logging.info(f"Switched Rich Menu for user {user_id} back to the default menu {rich_menu_id}")
                    
                    # 回應使用者
                    self.line_bot_api.reply_message(
                        reply_token,
                        TextSendMessage(text='太棒了！您已完成任務，請繼續保持！')
                    )
                except LineBotApiError as e:
                    logging.error(f"Error switching Rich Menu for user {user_id}: {e.message}")
                    self.line_bot_api.reply_message(
                        reply_token,
                        TextSendMessage(text='不能回歸滿血,請稍後再試。')
                    )

            #  "運動數據" 
            if user_message == '健康數據':
                logging.info("Processing: 健康數據")

                # Set user state to awaiting sport data
                self.user_states[user_id]['state'] = 'awaiting_sport_data'

            if self.user_states[user_id].get('state') == 'awaiting_sport_data':

                return self.handle_health_data(user_id, reply_token)
            
        # 處理 ImageMessage
        @self.handler.add(MessageEvent, message=ImageMessage)
        def handle_image_message(event):
                    user_id = event.source.user_id
                    current_date = datetime.now().strftime('%Y-%m-%d')
                    reply_token = event.reply_token
                    message_id = event.message.id
                    content_url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
                    headers = {"Authorization": f"Bearer {self.channel_access_token}"}
                    img_response = requests.get(content_url, headers=headers)
                    if event.source.user_id not in self.user_states:
                        self.user_states[event.source.user_id] = {'state': None}
                    if img_response.status_code == 200:
                        # 处理图片内容
                        img = Image.open(io.BytesIO(img_response.content))

                        # 保存图片到 static 文件夹，并生成一个URL
                        static_dir = os.path.join(os.getcwd(), 'static')
                        os.makedirs(static_dir, exist_ok=True)
                        image_filename = f"image_{message_id}.jpg"
                        image_path = os.path.join(static_dir, image_filename)
                        img.save(image_path, format='JPEG')

                        # 生成图片的URL
                        with self.app.app_context():
                            image_url = url_for('static', filename=image_filename, _external=True)

                        # 调用 food_analyzer 中的图片处理与热量分析功能
                        food_analyzer = FoodCalorieAnalyzer(event.source.user_id)
                        result_message = food_analyzer.store_analyze_calories_from_image([image_url])

                        if "請提供" in result_message or "無法" in result_message:  # 根據回傳訊息判斷是否有錯誤
                            self.line_bot_api.reply_message(reply_token, TextSendMessage(text=result_message))
                
                        # 只有在辨識成功後，才進行卡路里計算
                        if "總共含有" in result_message:  # 檢查結果是否包含卡路里信息
                            try:
                                # 提取總卡路里
                                total_food_calories = int(re.search(r'總共含有 (\d+) 大卡', result_message).group(1))
                            except AttributeError:
                                total_food_calories = 0  # 找不到總卡路里資訊時設為 0
                            
                            # 將總卡路里累加到 calorie_tracker 中
                            self.calorie_tracker[user_id][current_date]['food_calories'] += total_food_calories
                            
                            # 推播成功訊息
                            self.line_bot_api.reply_message(reply_token, TextSendMessage(text=result_message))
                            
                            # 檢查是否超標
                            self.check_calorie_limit(user_id, current_date)

                            # 辨識成功後才退出等待狀態
                            self.user_states[user_id]['state'] = None
                            return

                        # 回覆用戶結果並重置狀態
                        if result_message:
                            self.line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result_message))
                        else:
                            self.line_bot_api.reply_message(event.reply_token, TextSendMessage(text="無法識別圖片中的食物，請再提供更清晰的圖片"))

                        # 重置使用者狀態
                        self.user_states[event.source.user_id]['state'] = None
                    else:
                        logging.error("Failed to fetch image from LINE servers.")
                        self.line_bot_api.reply_message(event.reply_token, TextSendMessage(text="無法獲取圖片，請稍後再試。"))
    def start(self):
        self.app.run(host=self.flask_host, port=self.flask_port, debug=True)

    def get_user_data(self, user_id):
        """從資料庫中獲取用戶的基本資料"""
        user_data = Userdata(user_id)
        user_record = user_data.search_data('u_id', user_id)
        logging.info(f"獲取到的用戶資料：{user_record}")
        if user_record:
            return user_record  # 直接返回搜索到的用戶資料
        else:
            return None
               
    def create_member_bubble(self, name, role, image_url):
        # 定義 hero 部分
        hero_section = {
            "type": "image",
            "url": image_url,
            "size": "full",
            "aspectRatio": "1:1",
            "aspectMode": "cover"
        }

        # 定義 body 部分
        body_section = {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": name,
                    "weight": "bold",
                    "size": "xl",
                    "align": "center"
                },
                {
                    "type": "text",
                    "text": f"負責項目: {role}",
                    "size": "md",
                    "align": "center",
                    "color": "#666666",
                    "wrap": True
                }
            ]
        }

        # 返回整個 bubble 結構
        return {
            "type": "bubble",
            "size": "giga",
            "hero": hero_section,
            "body": body_section
        }
             
    def switch_rich_menu(self, user_id):
        """
        根據用戶狀態切換 Rich Menu 並每5分鐘自動切換下一張，直到最後一張
        """
        # 獲取當前用戶的 Rich Menu 索引
        current_rich_menu_index = self.user_states[user_id].get('current_rich_menu_index', 0)

        # 確認是否尚未達到最後一個 Rich Menu
        if current_rich_menu_index < len(self.rich_menu_ids) - 1:
            # 切換到下一個 Rich Menu
            current_rich_menu_index += 1
            self.user_states[user_id]['current_rich_menu_index'] = current_rich_menu_index
            rich_menu_id = self.rich_menu_ids[current_rich_menu_index]

            # 切換 Rich Menu
            self.line_bot_api.link_rich_menu_to_user(user_id, rich_menu_id)
            logging.info(f"Switched Rich Menu for user {user_id} to {rich_menu_id}")

            # 設置定時器每隔5分鐘切換一次，直到達到最後一張 Rich Menu
            timer = threading.Timer(10, self.switch_rich_menu, [user_id])
            self.timers[user_id] = timer
            timer.start()
        else:
            # 如果已經達到最後一個 Rich Menu，取消定時器
            logging.info(f"User {user_id} has reached the last Rich Menu.")
            if user_id in self.timers:
                self.timers[user_id].cancel()
                del self.timers[user_id]

    def get_current_calories(self,user_id):
        data_time = datetime.now().strftime('%Y-%m-%d')
        # 總攝取卡路里，檢查空值
        total_food_calories = self.daily_db.summary_calories_data("food_calories", "1d") or 0
        # 總消耗卡路里，檢查空值
        total_calories_burned = self.daily_db.summary_calories_data("calories_burned", "1d") or 0
        logging.info(f"Total food calories: {total_food_calories}, Total calories burned: {total_calories_burned}")
        return total_food_calories - total_calories_burned

    def ensure_user_state(self, user_id):
        """用戶狀態紀錄。"""
        if user_id not in self.user_states:
            self.user_states[user_id] = {
                'state': None,
                'in_gemini_chat': False,  # 默認為false
                'current_rich_menu_index': 0,
                'standards': {},
                'dashboard_url': None  # 默認為 None
            }

        # 在飲食或運動操作後，調用 check_calories 進行判斷
    def handle_food_or_exercise_update(self, user_id):

        """
        用戶在飲食或運動操作後觸發此邏輯。
        """
        exceeded = check_calories(self.user_states, user_id, self.calorie_standards, self.get_current_calories)

        if exceeded:
            # 切換 Rich Menu
            self.switch_rich_menu(user_id, self.user_states[user_id]['standards'])
        else:
            # 如果沒有超標，也可以回應用戶
            self.line_bot_api.push_message(
                user_id,
                TextSendMessage(text="您目前尚未超標每日的卡路里標準，繼續保持！")
            )

    def extract_calories(self, message):
        """
        從分析結果中提取卡路里或大卡數字
        """
        match = re.search(r'(\d+\.?\d*)\s*(?:大卡|卡|卡路里)', message)
        if match:
            return float(match.group(1))
        else:
            logging.error(f"無法從訊息中提取卡路里: {message}")
            return 0
    def check_calorie_limit(self, user_id, current_date):
        """
        檢查當天攝取和燃燒的卡路里是否超標
        """
        # 假設有每日推薦卡路里值
        daily_limit = self.calorie_standards.get(user_id, {}).get('recommended_daily_calories', 2000)
        
        # 獲取當天的卡路里數據
        food_calories = self.calorie_tracker[user_id][current_date]['food_calories']
        calories_burned = self.calorie_tracker[user_id][current_date]['calories_burned']
        logging.info(f"User {user_id} - Food calories added: {food_calories}, Total food: {self.calorie_tracker[user_id][current_date]['food_calories']}")
        logging.info(f"User {user_id} - Burned calories added: {calories_burned}, Total burned: {self.calorie_tracker[user_id][current_date]['calories_burned']}")
        net_calories = food_calories - calories_burned

        logging.info(f"User {user_id} - Total food: {food_calories}, Total burned: {calories_burned}, Net: {net_calories}")
        # 計算剩餘卡路里
        remaining_calories = daily_limit - net_calories
        # 如果淨攝取卡路里超標，則發送提醒並切換 Rich Menu
        if net_calories > daily_limit:
            logging.info(f"User {user_id} exceeded calorie limit: {net_calories} > {daily_limit}")
            # 依照超標的卡路里數量生成運動計畫
            calories_burn_plan = self.burn_calories_plan(remaining_calories, user_id)
            
            # 拼接卡路里提示和運動計畫成一個完整的消息
            calories_text = (
                f"「您今天的卡路里攝取已經超標 {abs(remaining_calories)} 大卡，現在是進行運動的好機會！💪」\n\n"
                f"「為了讓您保持健康的平衡，我準備了一份運動計畫，幫助您消耗多餘的卡路里，恢復活力。現在就開始吧！🏃‍♀️✨」\n\n"
                f"您需要進行以下運動來燃燒多餘的卡路里：\n\n"
                f"{calories_burn_plan}"
            )

            quick_reply_buttons = QuickReply(
                items=[
                    QuickReplyButton(action=MessageAction(label="我完成任務", text="我完成任務"),image_url=f"{self.website_url}/static/icons/finish.png"),
                    QuickReplyButton(action=MessageAction(label="我有空再做", text="我有空再做"),image_url=f"{self.website_url}/static/icons/couch.jpeg")
                ]
            )
                    
            self.line_bot_api.push_message(
                user_id,
                TextSendMessage(
                    text=calories_text,
                    quick_reply=quick_reply_buttons
                )
            )

            self.switch_rich_menu(user_id)

    # 發送請求使用者輸入綽號
    def ask_for_nickname(self,reply_token):
        user_id = self.event.source.user_id
        self.line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="請告訴我您的綽號。")
        )
        self.user_states[user_id]['state'] = 'awaiting_nickname'
    # 處理使用者回應的綽號
    def handle_nickname(self,user_message, reply_token):
        user_id = self.event.source.user_id 
        user_data=Userdata(user_id)    
        # 檢查用戶資料是否已存在，如果不存在則創建
        if not user_data.search_data('u_id', user_id):
            # 插入預設資料，只有user_id
            user_data.add_data(name='未設定', gender=True, age=20, weight=60.0, height=170.0, activity_level=1.2)  
        nickname = user_message  # 假設回應是綽號
        
        user_data.update_data('name', nickname)  # 將綽號儲存到資料庫
        # 提示選擇性別
        self.line_bot_api.reply_message(
            reply_token,
            TextSendMessage(
                text="請選擇您的性別。",
                quick_reply=QuickReply(
                    items=[
                        QuickReplyButton(action=MessageAction(label="男", text="男"),image_url=f"{self.website_url}/static/icons/men.png"),
                        QuickReplyButton(action=MessageAction(label="女", text="女"),image_url=f"{self.website_url}/static/icons/women.png"),
                    ]
                )
            )
        )
        self.user_states[user_id]['state'] = 'awaiting_gender'
    # 處理使用者回應的性別
    def handle_gender(self,user_message, reply_token):
        user_id = self.event.source.user_id
        user_data=Userdata(user_id)
        gender = user_message  # 存取使用者選擇的性別
        user_data.update_data('gender', gender)  # 儲存性別至資料庫
        self.line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="請告訴我您的年齡。")
        )
        self.user_states[user_id]['state'] = 'awaiting_age'
    # 處理使用者回應的年齡
    def handle_age(self,user_message, reply_token):
        user_id = self.event.source.user_id
        user_data=Userdata(user_id)
        try:
            age = int(user_message)  # 檢查是否為有效數字
            user_data.update_data('age', age)  # 儲存年齡
            self.line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text="請告訴我您的身高（cm）。")
            )
            self.user_states[user_id]['state'] = 'awaiting_height'
        except ValueError:
            self.line_bot_api.reply_message(reply_token, TextSendMessage(text="請提供有效的年齡數字。"))
    # 處理使用者回應的身高
    def handle_height(self,user_message, reply_token):
        user_id = self.event.source.user_id
        user_data=Userdata(user_id)
        try:
            height = int(user_message)  # 驗證身高
            user_data.update_data('height', height)  # 儲存身高
            self.line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text="請告訴我您的體重（kg）。")
            )
            self.user_states[user_id]['state'] = 'awaiting_weight'
        except ValueError:
            self.line_bot_api.reply_message(reply_token, TextSendMessage(text="請提供有效的身高數字。"))
    # 處理使用者回應的體重
    def handle_weight(self,user_message, reply_token):
        user_id = self.event.source.user_id
        user_data=Userdata(user_id)
        try:
            weight = float(user_message)  # 驗證體重
            user_data.update_data('weight', weight)  # 儲存體重
            self.line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text="資料更新成功！開始使用Lady 卡卡吧！")
            )
            self.user_states[user_id]['state'] = None  # 重置狀態
        except ValueError:
            self.line_bot_api.reply_message(reply_token, TextSendMessage(text="請提供有效的體重數字。"))

    def handle_health_data(self, user_id, reply_token):

        """
        處理當使用者按下「健康數據」後的行為，顯示 QuickReply 按鈕
        """
        # 確保狀態存在
        self.ensure_user_state(user_id)

        # 生成儀表板 URL（假設你已經有一個生成 URL 的邏輯）
        dashboard_url = url_for('display_dashboard', user_id=user_id, _external=True)
        self.website_url = self.config["ngrok"]["website_url"]  # ngrok URL
        # QuickReply buttons
        quick_reply_buttons = QuickReply(
            items=[
                QuickReplyButton(
                    action=URIAction(label="健康數據儀表板", uri=dashboard_url),image_url=f"{self.website_url}/static/icons/dashboard.png"  # 跳轉到儀表板 URL
                ),
                QuickReplyButton(
                    action=MessageAction(label="取消", text="取消"),image_url=f"{self.website_url}/static/icons/no.png"
                )
            ]
        )

        self.user_states[user_id]['state'] = None

        # 發送 QuickReply 選項給用戶
        self.line_bot_api.reply_message(
            reply_token,
            TextSendMessage(
                text="請選擇以下操作：",
                quick_reply=quick_reply_buttons
            )
        )


    def burn_calories_plan(self, remaining_calories, user_id):
        """
        根據超標的卡路里數量生成燃燒卡路里的運動計畫，並提供具體運動建議
        """
        # 定義常見運動的 MET 值
        activities = {
            '步行': 3.8,
            '跑步': 8.3,
            '跳繩': 12.0,
            '游泳': 7.0,
            '騎腳踏車': 7.5
        }

        # 初始化運動計畫
        calories_burn_plan = []

        # 根據每種運動計算燃燒多餘卡路里所需的時間
        user_data = Userdata(user_id)
        search_result = user_data.search_data(field="u_id", data=user_id)
        
        if search_result:
            user_weight = int(search_result['weight'])
        
        for activity, met in activities.items():
            # 計算消耗多餘卡路里所需的時間（小時)
            time_needed = abs(remaining_calories) / (met * user_weight)
            
            # 轉換成分鐘數
            minutes_needed = int(time_needed * 60)
            calories_burn_plan.append(f"{activity}: 約 {minutes_needed} 分鐘")
        
        if user_id in self.user_states:
            self.user_states[user_id]['state'] = None  # 或者將狀態設為初始狀態
        
        # 返回具體運動計畫作為字符串
        return (
            "您需要進行以下運動來燃燒多餘的卡路里：\n\n" +
            "\n".join(calories_burn_plan) +
            "\n\n每種運動的卡路里消耗量會根據您的體重和運動強度有所不同。"
        )
    
    def chinese_to_digit(self, chinese_str):
        """將中文數字轉換為阿拉伯數字"""
        chinese_digits = {'零': 0, '一': 1, '二': 2, '兩': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '半': 0.5}
        digit = 0
        if chinese_str == '半':
            return 0.5
        for char in chinese_str:
            if char in chinese_digits:
                digit += chinese_digits[char]
        return digit

    def parse_time_input(self, user_message):
        """解析用戶輸入的時間"""
        unit = ""
        original_message = user_message.strip().lower()
        print(f"原始用戶輸入時間：{original_message}")
        
        # 特別處理中文數字情況，例如 '半小時'，'兩個半小時' 等
        if '半' in original_message or any(c in original_message for c in '零一二三四五六七八九'):
            chinese_time_pattern = re.compile(r'([零一二三四五六七八九兩]+)?(個)?(半)?(小時|hr|h)')
            chinese_minute_pattern = re.compile(r'([零一二三四五六七八九兩]+)?(個)?(半)?(分鐘|min)')
            
            # 處理小時部分
            match = chinese_time_pattern.search(original_message)
            if match:
                hours_part = match.group(1)  # 數字部分
                half_part = match.group(3)   # 半部分
                total_hours = 0
                
                if hours_part:
                    total_hours = self.chinese_to_digit(hours_part)  # 轉換數字部分
                if half_part:
                    total_hours += 0.5  # 添加半小時
                
                print(f"解析結果: {total_hours} 小時")
                return total_hours
            
            # 處理分鐘部分
            match_minute = chinese_minute_pattern.search(original_message)
            if match_minute:
                minutes_part = match_minute.group(1)
                half_part = match_minute.group(3)
                total_minutes = 0
                
                if minutes_part:
                    total_minutes = self.chinese_to_digit(minutes_part)
                if half_part:
                    total_minutes += 0.5 * 60  # 半分鐘
                
                print(f"解析結果: {total_minutes} 分鐘")
                return total_minutes / 60  # 將分鐘轉為小時

        # 處理阿拉伯數字情況，支持小時(hr, h)和分鐘(min)
        time_pattern = re.compile(r'(\d+(\.\d+)?)(小時|hr|h|分鐘|min)')
        match = time_pattern.search(original_message)
        if match:
            time_value = float(match.group(1))
            unit = match.group(3)
            print(f"解析結果: {time_value} {unit}")
        
            if '小時' in unit or 'hr' in unit or 'h' in unit:
                return time_value
            elif '分鐘' in unit or 'min' in unit:
                return time_value / 60  # 將分鐘轉為小時
        
        # 如果無法解析，回傳錯誤並打印提示
        print(f"無法解析時間: {original_message}")
        return None
    def handle_activity_suggestion(self,user_id, reply_token, activity_type, user_message):
        # 使用 parse_time_input 來處理輸入的時間
        duration_in_hours = self.parse_time_input(user_message)
        
        if duration_in_hours is None:
            self.line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text="請確保格式正確，例如：'跑步 2小時'、'半小時' 或 '游泳 30分鐘'。")
            )
            return
        
        print(f"最終計算的時間：{duration_in_hours} 小時")
        
        # 調用運動建議生成邏輯
        is_valid, gemini_advice = get_activity_advice(user_id, self.user_db.search_data('u_id', user_id), f"{activity_type} {duration_in_hours}小時")
        
        if not is_valid:
            # 如果不符合要求，返回手動建議
            self.line_bot_api.reply_message(reply_token, TextSendMessage(text=gemini_advice))
        else:
            # 如果建議生成成功，使用 Flex Message 返回
            flex_messages = generate_flex_messages(gemini_advice, activity_type)
            # 確保最多只發送 5 條消息
            print("flex messages數量 : ",len(flex_messages))
            if len(flex_messages) > 5:
                flex_messages = flex_messages[:5]
            self.line_bot_api.reply_message(reply_token, flex_messages)

            self.user_states[user_id]['state'] = None
            return
    


if __name__ == "__main__":
    # 全局關閉資料庫連接
    bot_app = Lineca()
    bot_app.start()