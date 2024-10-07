import logging

def check_calories(user_states, user_id, calorie_standards, get_current_calories):
    """
    在卡路里變化時進行檢查，判斷是否超標。

    參數：
    - user_states: 用戶狀態字典
    - user_id: 用戶 ID
    - calorie_standards: 用戶的卡路里標準
    - get_current_calories: 用來計算當前卡路里的函數
    """
    # 獲取用戶的標準
    standards = user_states.get(user_id, {}).get('standards', None)
    if not standards:
        logging.error(f"No standards found for user {user_id}")
        return False  # 沒有標準則返回 False

    # 設置 daily_calorie_limit
    if 'recommended_daily_calories' in calorie_standards.get(user_id, {}):
        user_states[user_id]['daily_calorie_limit'] = calorie_standards[user_id]['recommended_daily_calories']

    daily_calorie_limit = user_states[user_id]['daily_calorie_limit']
    current_calories = get_current_calories(user_id)

    # 檢查用戶的攝取卡路里是否超標
    if current_calories > daily_calorie_limit:
        logging.info(f"User {user_id} has exceeded the daily calorie limit.")
        return True  # 如果超標返回 True
    else:
        logging.info(f"User {user_id} is within the daily calorie limit.")
        return False  # 沒有超標則返回 False