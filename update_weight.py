import logging
from access_db import Userdata

class WeightUpdater:
    def __init__(self, user_id):
        self.user_db = Userdata(user_id)

    def update_weight(self, new_weight):
        try:
            # 使用 search_data 方法檢查用戶是否存在
            user_record = self.user_db.search_data('u_id', self.user_db.user_id)
            
            if not user_record:
                logging.error(f"用戶 {self.user_db.user_id} 的資料未找到。")
                return "用戶資料未找到，請先更新您的基本資料。"

            # 更新體重
            self.user_db.update_data('weight', new_weight)

            logging.info(f"用戶 {self.user_db.user_id} 的體重已更新為 {new_weight} 公斤。")
            return f"體重已成功更新為 {new_weight} 公斤,請去按下我的計畫重新生成減肥建議。"

        except Exception as e:
            logging.error(f"更新體重時發生錯誤: {e}")
            return "更新體重時發生錯誤，請稍後再試。"

if __name__ == "__main__":
    # 測試體重更新功能
    updater = WeightUpdater("test_user")
    result = updater.update_weight(75)
    print(result)