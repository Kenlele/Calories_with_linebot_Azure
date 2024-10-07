import datetime
import sqlite3

class Userdata:
    DB_CONN = None
    USER_CURSOR = None
    db = ""
    table = "users"
    user_id = ""

    def open_db(self):
        self.DB_CONN = sqlite3.connect(self.db)
        self.USER_CURSOR = self.DB_CONN.cursor()

    def close_db(self):
        self.DB_CONN.commit()
        self.DB_CONN.close()

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.db = self.user_id+f".db"
        self.open_db()
        self.USER_CURSOR.execute('CREATE TABLE IF NOT EXISTS users('
                                 'u_id TEXT PRIMARY KEY NOT NULL, '
                                 'name TEXT, '
                                 'gender BOOLEAN, '
                                 'age INTEGER, '
                                 'weight FLOATING, '
                                 'height FLOATING, '
                                 'activity_level FLOATING)')
        self.close_db()

    def run_sql_comm(self, comm: str):
        self.open_db()
        self.USER_CURSOR.execute(comm)
        self.close_db()

    def get_sql_result(self, comm: str):
        self.open_db()
        result = self.USER_CURSOR.execute(comm).fetchone()
        self.close_db()
        return result

    def add_data(self, name: str = "test", gender: bool = True, age: float = 20,
                 weight: float = 60, height: float = 160, activity_level: float = 1.2):
        comm = (f"insert into {self.table} values(\'{str(self.user_id)}\', \'{str(name)}\', {bool(gender)},"
                f"{int(age)}, {float(weight)}, {float(height)}, {float(activity_level)})")
        if not self.search_data("u_id", self.user_id):
            self.run_sql_comm(comm=comm)
        return self.search_data("u_id", self.user_id)

    def search_data(self, field: str, data):
        comm = f"select * from {self.table} where {field}=\'{data}\'"
        search_result = self.get_sql_result(comm=comm)
        column_value = self.get_all_columns()
        if not search_result:
            return None
        return self.translate_to_dir(column_value, search_result)

    def update_data(self, field: str, data):
        if field == "name":
            comm = f"update {self.table} set {field}=\'{str(data)}\' where u_id=\'{str(self.user_id)}\'"
        elif field == "gender":
            comm = f"update {self.table} set {field}={bool(data)} where u_id=\'{str(self.user_id)}\'"
        else:
            comm = f"update {self.table} set {field}={float(data)} where u_id=\'{str(self.user_id)}\'"
        print(comm)
        if self.search_data("u_id", self.user_id):
            self.run_sql_comm(comm=comm)
        return self.search_data("u_id", self.user_id)

    def delete_data(self):
        comm = f"delete from {self.table} where u_id=\'{str(self.user_id)}\'"
        if self.search_data("u_id", self.user_id):
            self.run_sql_comm(comm=comm)
        return self.search_data("u_id", self.user_id)

    def get_all_columns(self):
        column_names = []
        self.open_db()
        result = self.USER_CURSOR.execute(f"PRAGMA table_info({self.table});").fetchall()
        self.close_db()
        for col in result:
            column_names.append(col[1])
        return column_names

    def translate_to_dir(self, column_value, data):
        dir_result = {}
        for key, value in zip(column_value, data):
            dir_result[key] = value
        return dir_result

class Dailydata:
    DB_CONN = None
    USER_CURSOR = None
    db = ""
    table = "daily_info"
    user_id = ""

    def open_db(self):
        self.DB_CONN = sqlite3.connect(self.db)
        self.USER_CURSOR = self.DB_CONN.cursor()

    def close_db(self):
        self.DB_CONN.commit()
        self.DB_CONN.close()

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.db = self.user_id+f".db"
        self.open_db()
        self.USER_CURSOR.execute(f'CREATE TABLE IF NOT EXISTS {self.table}('
                                 'date TEXT, ' 
                                 'time TEXT, '
                                 'u_id TEXT, '
                                 'food_name TEXT, '
                                 'food_calories FLOATING, '
                                 'exercise_name TEXT, '
                                 'exercise_duration FLOATING, '
                                 'weight_target FLOATING, '
                                 'bmr_target FLOATING, '
                                 'calories_burned FLOATING)')
        self.close_db()
        not_add_columns = ['weight_target', 'bmr_target', 'calories_burned']
        all_columns = self.get_all_columns()
        for add_columns in not_add_columns:
            if add_columns not in all_columns:
                comm = f"ALTER TABLE {self.table} ADD COLUMN {add_columns} FLOATING"
                self.run_sql_comm(comm=comm)

    def run_sql_comm(self, comm: str):
        self.open_db()
        self.USER_CURSOR.execute(comm)
        self.close_db()

    def get_sql_result(self, comm: str):
        self.open_db()
        result = self.USER_CURSOR.execute(comm).fetchone()
        self.close_db()
        return result

    def get_sql_all_result(self, comm: str):
        self.open_db()
        result = self.USER_CURSOR.execute(comm).fetchall()
        self.close_db()
        return result

    def add_data(self, food_name: str = None, food_calories: float = 0,
                 exercise_name: str = None, exercise_duration: float = 0, weight_target: float = 0,
                 bmr_target: float = 0, calories_burned: float = 0):
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        time = datetime.datetime.now().strftime("%H:%M:%S")
        comm = (f"insert into {self.table} values(\'{str(date)}\',\'{str(time)}\',"
                f"\'{str(self.user_id)}\',\'{str(food_name)}\', {float(food_calories)},"
                f" \'{str(exercise_name)}\',{float(exercise_duration)}, {float(weight_target)},"
                f"{float(bmr_target)} ,{float(calories_burned)})")
        self.run_sql_comm(comm=comm)
        return self.search_data("time", time)

    def search_data(self, field: str, data):
        comm = f"select * from {self.table} where {field}=\'{data}\'"
        action_result = self.get_sql_result(comm=comm)
        columns_value = self.get_all_columns()
        if not action_result:
            return None
        return self.trans_to_dir(action_result, columns_value, True)

    def summary_calories_data(self, field: str = "food_calories", data="1d"):
        if not (field == "food_calories" or field == "exercise_duration"):
            return
        before_day = datetime.datetime.now().strftime("%Y-%m-%d")
        if "d" in data:
            data_date = int(data[:-1])
            if data_date > 0:
                before_day = (datetime.datetime.now() -
                              datetime.timedelta(days=(int(data_date)))).strftime("%Y-%m-%d")
        comm = f"select sum({field}) from {self.table} where \'date\'>=\'{before_day}\'"
        action_result = self.get_sql_result(comm=comm)
        return action_result[0]

    def search_all_data(self, field: str, data):
        columns_value = action_result = comm = comm2 = None
        count_status = False
        if field == "date":
            if "d" in data:
                before_day = datetime.datetime.now().strftime("%Y-%m-%d")
                data = int(data[:-1])
                if data > 0:
                    before_day = (datetime.datetime.now() -
                                  datetime.timedelta(days=(int(data)))).strftime("%Y-%m-%d")
                comm = f"select * from {self.table} where {field} >= \'{before_day}\'"
                comm2 = f"select count(*) from {self.table} where {field} >= \'{before_day}\'"
            else:
                comm = f"select * from {self.table} where {field}=\'{data}\'"
                comm2 = f"select count(*) from {self.table} where {field}=\'{data}\'"
        else:
            comm = f"select * from {self.table} where {field}=\'{data}\'"
            comm2 = f"select count(*) from {self.table} where {field}=\'{data}\'"
        action_result = self.get_sql_all_result(comm=comm)
        if self.get_sql_result(comm=comm2)[0] <= 1:
            count_status = True
        columns_value = self.get_all_columns()
        if not action_result:
            return None
        return self.trans_to_dir(action_result, columns_value, count_status)

    def update_data(self, field: str, data):
        comm = f"update {self.table} set {field}={float(data)} where u_id=\'{str(self.user_id)}\'"
        self.run_sql_comm(comm=comm)
        return self.search_data("u_id", self.user_id)

    def delete_data(self, field: str, data: str):
        comm = f"delete from {self.table} where {field}=\'{str(data)}\'"
        if self.search_data(field, data):
            self.run_sql_comm(comm=comm)
        return self.search_data(field, data)

    def get_all_columns(self):
        column_names = []
        self.open_db()
        result = self.USER_CURSOR.execute(f"PRAGMA table_info({self.table});").fetchall()
        self.close_db()
        for col in result:
            column_names.append(col[1])
        return column_names

    def trans_to_dir(self, action_data, column_value, count_status: bool = False):
        dir_result = []
        if count_status:
            dir_result = {}
            for key, value in zip(column_value, action_data):
                dir_result[key] = value
            return dir_result
        else:
            for i in range(len(action_data)):
                create_dir = {}
                for j in range(len(column_value)):
                    create_dir[column_value[j]] = action_data[i][j]
                dir_result.append(create_dir)
        return dir_result

# def test_dailydata():
#     user_id = "U086caf6a13238183951b5f4aa41b965e"  # 使用實際的用戶 ID
#     daily_data = Dailydata(user_id)

#     # 測試獲取今天的數據
#     today = datetime.datetime.now().strftime("%Y-%m-%d")
#     today_data = daily_data.search_all_data("date", today)
#     print(f"Today's data ({today}):")
#     print(today_data)

#     # 測試獲取最近7天的數據
#     seven_days_data = daily_data.search_all_data("date", "1d")
#     print("\nLast 7 days data:")
#     print(seven_days_data)

#     # 測試獲取特定日期的數據
#     specific_date = "2024-09-22"  # 使用您知道存在數據的日期
#     specific_date_data = daily_data.search_all_data("date", specific_date)
#     print(f"\nData for specific date ({specific_date}):")
#     print(specific_date_data)

if __name__ == "__main__":
    user_id = "aa"
    daily_data = Dailydata(user_id)
    user_data = Userdata(user_id)
    user_data.update_data(field="name", data="ggg")
    # print(user_data.search_data(field="u_id", data=user_id))
    # print(daily_data.search_all_data("date", "0d"))
    # print(daily_data.search_all_data("date", "10d"))
    print(daily_data.search_all_data("date", "2024-09-22"))
    # print(daily_data.summary_calories_data("exercise_duration", "1d"))
    # print(daily_data.summary_calories_data("food_calories", "10d"))
    # print(daily_data.get_sql_result("select * from daily_info where date >= \"2024-09-04\""))
    # print(daily_data.search_data("u_id","gg"))
    # list = daily_data.search_data("u_id", "gg")
    # print(list[0]['date'])
    # test_dailydata()


