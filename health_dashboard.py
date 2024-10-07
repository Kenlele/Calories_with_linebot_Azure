import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
from flask import session
import pandas as pd
import plotly.graph_objects as go
# from plotly.subplots import make_subplots
import datetime
from access_db import Userdata, Dailydata
import traceback

class HealthDashboard:
    def __init__(self, flask_app):
        self.dash_app = dash.Dash(
            server=flask_app,
            routes_pathname_prefix='/dashboard/',
            external_stylesheets=[dbc.themes.BOOTSTRAP, 'https://fonts.googleapis.com/css2?family=Comic+Neue&display=swap']
        )
        self.dash_app.layout = self.serve_layout()
        self.init_callbacks()

    def serve_layout(self):
        return html.Div([
            dcc.Location(id='url', refresh=False),
            html.Div(id='page-content')
        ])

    def init_callbacks(self):
        @self.dash_app.callback(
            Output('page-content', 'children'),
            Input('url', 'pathname'),
            State('url', 'search')
        )
        def display_page(pathname, search):
            user_id = session.get('user_id', '未知')
            return self.create_layout(user_id)

        @self.dash_app.callback(
            Output('calorie-trend-chart', 'figure'),
            Output('net-calories-trend-chart', 'figure'),
            Input('play-button', 'n_clicks'),
            Input('animation-interval', 'n_intervals'),
            State('url', 'pathname')
        )
        def update_charts(n_clicks, n_intervals, pathname):
            user_id = pathname.split('/')[-1]
            if n_clicks is None or n_intervals is None:
                days = 15  # 初始狀態顯示15天
            else:
                days = min(60, 15 + n_intervals)  # 從15天開始，最多到60天
            calorie_fig = self.create_calorie_trend_chart(user_id, days)
            net_calories_fig = self.create_net_calories_trend_chart(user_id, days)
            return calorie_fig, net_calories_fig

        @self.dash_app.callback(
            Output('animation-interval', 'disabled'),
            Input('play-button', 'n_clicks'),
            State('animation-interval', 'disabled')
        )
        def toggle_animation(n_clicks, current_state):
            if n_clicks is None:
                return True  # Initially disabled
            return not current_state

    def create_layout(self, user_id):
        user_info = self.get_user_info(user_id)
        today_data = self.get_today_data(user_id)
        
        layout = html.Div([
            html.H1("✨Lady卡卡閃亮登場！即將揭開您的健康祕密！✨", className="text-center mb-4"),
            html.H2(f"Hi, {user_info.get('name')} ！來看看今天的狀況吧！", className="text-center mb-4"),
            self.create_user_info_section(user_info, today_data),
            dbc.Row([
                dbc.Col(dcc.Graph(figure=self.create_calorie_pie_chart(today_data, user_info)), md=12)
            ], className="mb-4"),
            html.Div([
                dbc.Button("播放/暫停", id="play-button", color="primary", className="mb-3", style={
                'background-color': '#FFB6C1', 
                'border-color': '#FFB6C1'
                }),                  
                dcc.Graph(id='calorie-trend-chart', figure=self.create_calorie_trend_chart(user_id,15)),
                dcc.Graph(id='net-calories-trend-chart', figure=self.create_net_calories_trend_chart(user_id,15)),
            ]),
            dcc.Interval(
                id='animation-interval',
                interval=400,  # 更新速度
                n_intervals=0,
                max_intervals=45,  # 最多播放60天
                disabled=True
            ),
            html.Div(
                dbc.Button("🔙 Lady卡卡", href="line://oaMessage/@092livgd/", color="primary", className="text-center", style={
                'background-color': '#FFB6C1',  
                'border-color': '#FFB6C1',
                'color': 'white'
                }),
                style={
                    'position': 'fixed',
                    'bottom': '100px',
                    'right': '20px',
                    'zIndex': '1000',
                    'border-radius': '50%',
                    'width': '60px',
                    'height': '60px',
                    'text-align': 'center',
                    'font-size': '16px'
                }
            )
        ], className="container", style={'position': 'relative'})
        return layout

    def get_user_info(self, user_id):
        try:
            user_data = Userdata(user_id)
            user_info = user_data.search_data("u_id", user_id)
            if user_info:
                user_info['bmr'] = self.calculate_bmr(user_info)
                user_info['tdee'] = self.calculate_tdee(user_info['bmr'], user_info.get('activity_level', 1.2))
                user_info['target_weight'] = self.get_latest_target_weight(user_id, user_info.get('weight', 0))
                user_info['goal_achievement'] = self.calculate_goal_achievement(user_info['weight'], user_info['target_weight'])
            return user_info
        except Exception as e:
            print(f"Error in get_user_info: {str(e)}")
            traceback.print_exc()
            return {}

    def create_user_info_section(self, user_info, today_data):
        if not user_info:
            return html.Div("未找到用戶信息")
        
        total_calories = today_data['food_calories'].astype(float).sum() if not today_data.empty else 0
        total_exercise = today_data['exercise_duration'].astype(float).sum() if not today_data.empty else 0
        
        card = dbc.Card(
            dbc.CardBody([
                # html.H4("來看看今天的狀況吧！", className="card-title text-center"),
                # html.Hr(),
                dbc.Row([
                    dbc.Col([
                        html.P(f"身高: {user_info.get('height', '未知')} cm"),
                        html.P(f"基礎代謝率 (BMR): {user_info['bmr']:.2f} 大卡"),
                        html.P(f"基礎能量消耗: {user_info['tdee']:.2f} 大卡"),
                        html.P(f"今日熱量攝取: {total_calories:.2f} 大卡"),
                        html.P(f"今日運動時間: {total_exercise:.2f} 分鐘"),
                    ], md=6),
                    dbc.Col([
                        html.Div([
                            html.P(f"當前體重: {user_info.get('weight', '未知')} kg", style={'margin-bottom': '5px'}),
                            html.P(f"目標體重: {user_info['target_weight']} kg", style={'margin-bottom': '5px'}),
                            html.H6("達成率", className="text-center mt-2"),
                            self.create_progress_bar(user_info['goal_achievement'])
                        ], style={'height': '100%', 'display': 'flex', 'flexDirection': 'column', 'justifyContent': 'center'})
                    ], md=6),
                ]),
            ]),
            className="mb-4",
        )

        return card

    def create_progress_bar(self, achievement):
        return dbc.Progress(
            value=achievement,
            label=f"{achievement:.1f}%",
            style={"height": "20px"},
            className="mb-2",
            color="success" if achievement >= 80 else "warning" if achievement >= 50 else "danger",
            striped=True,
            animated=True
        )
    
    def create_calorie_pie_chart(self, data, user_info):
        if data.empty:
            return go.Figure()

        total_food_calories = data['food_calories'].astype(float).sum()
        total_exercise_calories = data['exercise_duration'].astype(float).sum() * 5
        bmr_calories = user_info['bmr']

        values = [total_food_calories, bmr_calories, total_exercise_calories]
        labels = ['食物攝入', '基礎能量消耗', '運動消耗']
        colors = ['#FFB3BA', '#BAFFC9', '#BAE1FF']

        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=.3,
            pull=[0.1, 0, 0],
            marker_colors=colors,
            textposition='outside',
            textinfo='label+percent',
            textfont_size=12,
        )])

        fig.update_layout(
            title="今天有好好運動嗎?😎",
            showlegend=False,
            height=400,
        )

        return fig

    def create_calorie_trend_chart(self, user_id, days=15):
        daily_data = self.get_sixty_day_data(user_id)
        if daily_data.empty:
            return go.Figure()

        daily_totals = daily_data.groupby('date').agg(
            total_food_calories=('food_calories', 'sum'),
            total_exercise_calories=('exercise_duration', 'sum'),
            TDEE=('TDEE', 'first'),
            bmr_target=('bmr_target', 'max')
        ).reset_index()

        daily_totals['date'] = pd.to_datetime(daily_totals['date'])
        daily_totals = daily_totals.sort_values('date').tail(days)
        daily_totals['total_exercise_calories'] *= 5

        # 計算食物攝入減去運動消耗的淨值
        daily_totals['net_calories'] = daily_totals['total_food_calories'] - daily_totals['total_exercise_calories']

        last_valid_bmr_target = None
        for i, row in daily_totals.iterrows():
            if row['bmr_target'] > 0:
                last_valid_bmr_target = row['bmr_target']
            daily_totals.at[i, 'calorie_expectation'] = last_valid_bmr_target if last_valid_bmr_target is not None else row['TDEE']

        fig = go.Figure()

        # 1. 食物攝入作為獨立的長條圖
        fig.add_trace(go.Bar(
            x=daily_totals['date'], 
            y=daily_totals['total_food_calories'], 
            name='食物攝入', 
            marker_color='rgba(255, 179, 186, 0.8)',
            offsetgroup=0
        ))

        # 2. TDEE 作為堆疊長條圖的底部
        fig.add_trace(go.Bar(
            x=daily_totals['date'], 
            y=daily_totals['TDEE'], 
            name='基礎能量消耗', 
            marker_color='rgba(186, 255, 201, 0.8)',
            offsetgroup=1
        ))

        # 3. 運動消耗堆疊在 TDEE 之上
        fig.add_trace(go.Bar(
            x=daily_totals['date'], 
            y=daily_totals['total_exercise_calories'], 
            name='運動消耗', 
            marker_color='rgba(186, 225, 255, 0.8)',
            offsetgroup=2
        ))

        # 保留熱量期望值作為比較
        fig.add_trace(go.Scatter(
            x=daily_totals['date'],
            y=daily_totals['calorie_expectation'],
            name='熱量期望值',
            line=dict(color='red', width=2, dash='dash')
        ))

        # 添加食物攝入減去運動消耗的淨值折線
        fig.add_trace(go.Scatter(
            x=daily_totals['date'],
            y=daily_totals['net_calories'],
            name='實際攝入熱量',
            line=dict(color='blue', width=2)
        ))

        fig.update_layout(
            title={
                'text':f'卡路里趨勢分析 (最近{days}天)',
                'font': {'size': 14}
            },
            xaxis_title={
                'text': '',
                'font': {'size': 12}  # 調整X軸標題字體大小
            },
                yaxis_title={
                'text': '卡路里',
                'font': {'size': 12}  # 調整Y軸標題字體大小
            },
            barmode='group',  # 使用 'group' 來創建群組直條圖
            height=500,
            legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5,font={'size': 10} )
        )

        return fig

    def create_net_calories_trend_chart(self, user_id, days=15):
        daily_data = self.get_sixty_day_data(user_id)
        if daily_data.empty:
            return go.Figure()

        daily_totals = daily_data.groupby('date').agg(
            total_food_calories=('food_calories', 'sum'),
            total_exercise_calories=('exercise_duration', 'sum'),
            TDEE=('TDEE', 'first'),
            bmr_target=('bmr_target', 'max')
        ).reset_index()

        daily_totals['date'] = pd.to_datetime(daily_totals['date'])
        daily_totals = daily_totals.sort_values('date').tail(days)
        daily_totals['total_exercise_calories'] *= 5

        last_valid_bmr_target = None
        for i, row in daily_totals.iterrows():
            if row['bmr_target'] > 0:
                last_valid_bmr_target = row['bmr_target']
            calorie_expectation = last_valid_bmr_target if last_valid_bmr_target is not None else row['TDEE']
            daily_totals.at[i, 'Net_Calories'] = row['total_food_calories'] - calorie_expectation - row['total_exercise_calories']

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=daily_totals['date'], 
            y=daily_totals['Net_Calories'], 
            name='每日淨卡路里', 
            line=dict(color='#FF5733', width=2)
        ))

        fig.add_trace(go.Scatter(
            x=daily_totals['date'],
            y=[0] * len(daily_totals),
            name='平衡線',
            line=dict(color='black', width=1, dash='dash')
        ))

        fig.update_layout(
            # title=f'淨卡路里消耗趨勢 (最近{days}天)',
            title={
                'text':f'淨卡路里消耗趨勢 (最近{days}天)',
                'font': {'size': 14}
            },
            # xaxis_title='',
            xaxis_title={
                'text': '',
                'font': {'size': 12}  # 調整X軸標題字體大小
            },
                yaxis_title={
                'text': '淨卡路里',
                'font': {'size': 12}  # 調整Y軸標題字體大小
            },
            # yaxis_title='淨卡路里',
            height=500,
            legend=dict(
            orientation="h",  # 水平排列圖例
            yanchor="top",  # 圖例在圖表下方
            y=-0.2,  # 將圖例移到圖表底部
            xanchor="center",  # 圖例居中
            x=0.5,  # X 軸上居中
            font={'size': 10}  # 調整圖例字體大小
    )
        )

        return fig

    def get_today_data(self, user_id):
        daily_data = Dailydata(user_id)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        all_data = daily_data.search_all_data("date", "1d")
        if not all_data:
            return pd.DataFrame()
        df = pd.DataFrame(all_data)
        return df[(df['date'] == today) & (df['u_id'] == user_id)]


                          
    def get_sixty_day_data(self, user_id):
        daily_data = Dailydata(user_id)
        all_data = daily_data.search_all_data("date", "60d")
        if not all_data:
            return pd.DataFrame()
        df = pd.DataFrame(all_data)
        df['date'] = pd.to_datetime(df['date'])
        
        user_info = self.get_user_info(user_id)
        
        df['TDEE'] = df.apply(lambda row: self.calculate_tdee(
            self.calculate_bmr(user_info),
            user_info.get('activity_level', 1.2)
        ), axis=1)
        
        if 'bmr_target' not in df.columns:
            df['bmr_target'] = 0.0
        
        return df[df['u_id'] == user_id].sort_values('date')

    @staticmethod
    def calculate_bmr(user_info):
        weight = user_info['weight']
        height = user_info['height']
        age = user_info['age']
        gender = user_info['gender']
        if gender == 1:  # 男性
            return 10 * weight + 6.25 * height - 5 * age + 5
        elif gender == 0:  # 女性
            return 10 * weight + 6.25 * height - 5 * age - 161
        else:
            return None

    @staticmethod
    def calculate_tdee(bmr, activity_level):
        return bmr * activity_level

    @staticmethod
    def calculate_goal_achievement(actual_weight, target_weight):
        return (target_weight / actual_weight) * 100 if actual_weight > 0 else 0

    @staticmethod
    def get_latest_target_weight(user_id, actual_weight):
        daily_data = Dailydata(user_id)
        all_data = daily_data.search_all_data("date", "60d")
        if all_data:
            df = pd.DataFrame(all_data)
            valid_target_weights = df[(df['u_id'] == user_id) & (df['weight_target'] > 0)]
            if not valid_target_weights.empty:
                latest_record = valid_target_weights.sort_values(by='date', ascending=False).iloc[0]
                return latest_record['weight_target']
        return actual_weight

    def render_dashboard(self, user_id):
        session['user_id'] = user_id
        return self.dash_app.index()