from langchain.schema import HumanMessage
from access_db import Userdata, Dailydata

class generate_plan:
    def __init__(self, llm_gemini, user_id, target_weight):
        self.llm_gemini = llm_gemini
        self.user_id = user_id
        self.target_weight = target_weight

    def fetch_user_data(self):
        """
        從資料庫中根據 user_id 獲取用戶的基本資料。
        返回包含年齡、體重、身高、性別等資料的字典。
        """
        user_data = Userdata(self.user_id)
        user_record = user_data.search_data('u_id', self.user_id)
        if not user_record:
            return None, "無法找到使用者資料，請先更新基本資料。"
        return user_record, None

    def generate_plan(self):
        """
        根據用戶資料和目標體重，生成個人化減肥計畫。
        返回個人化減肥建議以及計算出的標準（如 BMR 和每日卡路里需求）。
        """
        
        # 抓取用戶基本資料
        user_record, error_message = self.fetch_user_data()
        if error_message:
            return None, error_message

        # 提取用戶的基本資料
        name=user_record['name']
        age = user_record['age']
        gender = user_record['gender']
        weight = user_record['weight']
        height = user_record['height']
        activity_level = user_record.get('activity_level', 1.375)

        # 計算基礎代謝率（BMR），使用 Mifflin-St Jeor 方程
        if gender == 1:
            bmr = 10 * weight + 6.25 * height - 5 * age + 5
        else:
            bmr = 10 * weight + 6.25 * height - 5 * age - 161

        # 計算每日卡路里需求
        daily_calories = bmr * activity_level

        # 計算需要減少的體重
        weight_loss_needed = weight - self.target_weight

        # 設定減肥時間範圍
        if weight_loss_needed <= 5:
            weeks = 12  # 小於等於 5 公斤，設定 12 週計畫
        else:
            weeks = 25  # 超過 5 公斤，設定 25 週計畫

        # 計算每日熱量赤字
        total_calorie_deficit = weight_loss_needed * 7700
        daily_calorie_deficit = total_calorie_deficit / (weeks * 7)

        # 設置每日卡路里赤字的安全範圍
        if daily_calorie_deficit > 1000:
            daily_calorie_deficit = 1000
        elif daily_calorie_deficit < 500:
            daily_calorie_deficit = 500

        # 計算每日建議攝取的卡路里
        recommended_daily_calories = daily_calories - daily_calorie_deficit

        # 確保攝取熱量不低於最低安全值
        if gender == 1 and recommended_daily_calories < 1500:
            recommended_daily_calories = 1500
        elif gender == 0 and recommended_daily_calories < 1200:
            recommended_daily_calories = 1200

        #儲存recommended_daily_calories到資料庫BMR欄位
        daily_data = Dailydata(self.user_id)
        daily_data.add_data(
            food_name=None, 
            food_calories=0,  
            exercise_name=None,  
            exercise_duration=0,  
            weight_target=self.target_weight,  
            bmr_target=recommended_daily_calories,  
            calories_burned=0
            )  # 假设此处没有卡路里消耗)
        # 生成個性化減肥建議
        basic_plan = (
            f"根據您的資料，您的基礎代謝率（BMR）為 {bmr:.2f} 大卡。\n"
            f"為了在 {weeks} 週內達到目標體重，您每日應攝取約 {recommended_daily_calories:.2f} 大卡。\n"
            "請根據此建議進行減肥，並確保遵循健康的飲食和適當的運動。"
        )

        # 使用 Gemini 生成進一步的建議
        human_message = HumanMessage(content=f"""你是一個名字叫Lady卡卡的專業運動顧問以及減肥專家，請用溫暖和鼓勵的語氣，
                                為使用者 {name} 提供具體且實用的減肥建議，讓他們感覺減肥之路充滿動力。
                                根據以下資料，生成一個清晰、易讀、令人愉快的建議，並加入適當的鼓勵話語：
                                基礎代謝率（BMR）：{bmr:.2f} 大卡，目標體重需在 {weeks} 週內達成，
                                每日攝取 {recommended_daily_calories:.2f} 大卡。：\n{basic_plan}

                                回應絕對務必使用繁體中文，並控制在150字以內。
                                請不要使用「**」、「*」等符號，保持簡潔易讀。
                                    """)

        result = self.llm_gemini.invoke([human_message])
        refined_plan = result.content.strip()

        # 生成判斷標準
        standards = {
            'bmr': bmr,
            'daily_calories': daily_calories,
            'recommended_daily_calories': recommended_daily_calories,
            'weight_loss_needed': weight_loss_needed,
            'total_calorie_deficit': total_calorie_deficit,
            'daily_calorie_deficit': daily_calorie_deficit,
            'weeks': weeks
        }

        return refined_plan, standards