import requests
import json
from datetime import datetime, timedelta
import pytz
import os
from dotenv import load_dotenv
import time
import base64

# 加载本地的 .env 文件
print("正在加载环境变量...")
load_dotenv()

# 配置信息
WXPUSHER_TOKEN = os.getenv("WXPUSHER_TOKEN")
WXPUSHER_UIDS = [uid.strip() for uid in os.getenv("WXPUSHER_UID", "").split(",")]
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

# 更新长春朝阳区的精确经纬度
LONGITUDE = 125.2833  # 125°17'60" = 125.2833
LATITUDE = 43.8336    # 43°50'1" = 43.8336

# 检查配置
print("检查配置信息...")
if not all([WXPUSHER_TOKEN, WXPUSHER_UIDS, WEATHER_API_KEY]):
    raise ValueError("缺少必要的配置信息，请检查环境变量或.env文件")
print(f"已配置推送目标数量: {len(WXPUSHER_UIDS)}")

# API endpoints
WXPUSHER_API = "http://wxpusher.zjiecode.com/api/send/message"
CAIYUN_API_VERSION = "v2.6"
WEATHER_API_BASE = f"https://api.caiyunapp.com/{CAIYUN_API_VERSION}/{WEATHER_API_KEY}/{LONGITUDE},{LATITUDE}"
WEATHER_API_ALL = f"{WEATHER_API_BASE}/weather?alert=true&dailysteps=5&hourlysteps=24&unit=metric:v2"

def get_weather_description(skycon):
    """将天气代码转换为中文描述，按优先级排序"""
    weather_map = {
        # 降雪（优先级最高）
        'STORM_SNOW': '暴雪',
        'HEAVY_SNOW': '大雪',
        'MODERATE_SNOW': '中雪',
        'LIGHT_SNOW': '小雪',
        # 降雨
        'STORM_RAIN': '暴雨',
        'HEAVY_RAIN': '大雨',
        'MODERATE_RAIN': '中雨',
        'LIGHT_RAIN': '小雨',
        # 雾
        'FOG': '雾',
        # 沙尘
        'SAND': '沙尘暴',
        'DUST': '浮尘',
        # 雾霾
        'HEAVY_HAZE': '重度雾霾',
        'MODERATE_HAZE': '中度雾霾',
        'LIGHT_HAZE': '轻度雾霾',
        # 大风
        'WIND': '大风',
        # 阴晴
        'CLOUDY': '阴天',
        'PARTLY_CLOUDY_DAY': '多云',
        'PARTLY_CLOUDY_NIGHT': '多云',
        'CLEAR_DAY': '晴天',
        'CLEAR_NIGHT': '晴夜'
    }
    return weather_map.get(skycon, skycon)

def get_precipitation_description(precipitation):
    """根据降水量判断降水等级（使用 mm/h）"""
    if precipitation < 0.0606:
        return ""
    elif precipitation < 0.8989:
        return "小雨"
    elif precipitation < 2.8700:
        return "中雨"
    elif precipitation < 12.8638:
        return "大雨"
    else:
        return "暴雨"

def get_weather_icon(weather, precipitation=0):
    """根据天气现象和降水量返回对应的图标"""
    # 按优先级排序
    if "雪" in weather:
        if "暴" in weather:
            return "🌨️⚡"  # 暴雪
        elif "大" in weather:
            return "🌨️🌨️"  # 大雪
        elif "中" in weather:
            return "🌨️❄️"  # 中雪
        else:
            return "🌨️"    # 小雪
    elif "雨" in weather or precipitation >= 0.0606:
        if precipitation >= 12.8638:
            return "🌧️⚡"  # 暴雨
        elif precipitation >= 2.8700:
            return "🌧️🌧️"  # 大雨
        elif precipitation >= 0.8989:
            return "🌧️💧"  # 中雨
        else:
            return "🌧️"    # 小雨
    elif "雾" in weather:
        return "🌫️"
    elif "沙尘" in weather:
        return "⛔"
    elif "霾" in weather:
        if "重" in weather:
            return "😷😷"
        elif "中" in weather:
            return "😷"
        else:
            return "🌫️"
    elif "大风" in weather:
        return "🌪️"
    elif "阴" in weather:
        return "☁️"
    elif "多云" in weather:
        return "⛅"
    else:
        return "☀️"

def get_weather():
    """获取天气信息"""
    print("正在获取天气数据...")
    
    # 设置重试次数和超时时间
    max_retries = 3
    timeout_seconds = 30
    
    for attempt in range(max_retries):
        try:
            print(f"第 {attempt + 1} 次尝试请求天气API: {WEATHER_API_ALL}")
            
            # 使用 session 来设置重试和超时
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                max_retries=3,
                pool_connections=100,
                pool_maxsize=100
            )
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            
            response = session.get(
                WEATHER_API_ALL,
                timeout=(timeout_seconds, timeout_seconds)  # (连接超时, 读取超时)
            )
            
            print(f"天气API状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'ok':
                    result = data['result']
                    realtime = result['realtime']
                    hourly = result['hourly']
                    daily = result.get('daily', {})
                    alert = result.get('alert', {})
                    
                    # 处理预警信息
                    alerts = []
                    if 'content' in alert:
                        alerts = alert.get('content', [])
                    
                    # 处理24小时预报数据
                    forecast_list = []
                    for temp, skycon, precip in zip(hourly['temperature'], hourly['skycon'], hourly['precipitation']):
                        time_str = temp['datetime']
                        forecast_time = datetime.strptime(time_str, "%Y-%m-%dT%H:%M%z")
                        weather_desc = get_weather_description(skycon['value'])
                        
                        forecast_list.append({
                            'time': forecast_time.strftime("%H:00"),
                            'temp': round(temp['value'], 1),
                            'weather': weather_desc,
                            'precipitation': round(precip['value'], 2)
                        })

                    # 处理每日预报数据
                    daily_forecast = []
                    for temp, skycon in zip(daily['temperature'], daily['skycon']):
                        # 确保日期格式正确
                        date = datetime.strptime(skycon['date'].split('T')[0], "%Y-%m-%d")
                        
                        # 今天的温度区间应该使用实时温度和小时预报的最高温度
                        if date.date() == datetime.now(pytz.timezone('Asia/Shanghai')).date():
                            # 获取今天的最高温度（从小时预报中）
                            today_temps = [f['temp'] for f in forecast_list if datetime.strptime(f['time'], "%H:00").hour >= datetime.now().hour]
                            if today_temps:
                                max_temp = max(today_temps)
                                min_temp = min(today_temps)
                            else:
                                max_temp = temp['max']
                                min_temp = temp['min']
                        else:
                            max_temp = temp['max']
                            min_temp = temp['min']
                        
                        daily_forecast.append({
                            'date': date.strftime("%m-%d"),
                            'temp_min': round(min_temp, 1),
                            'temp_max': round(max_temp, 1),
                            'weather': get_weather_description(skycon['value'])
                        })
                    
                    return {
                        'current_temp': round(realtime['temperature'], 1),
                        'feels_like': round(realtime['apparent_temperature'], 1),
                        'weather': get_weather_description(realtime['skycon']),
                        'humidity': round(realtime['humidity'] * 100),
                        'visibility': round(realtime['visibility'], 1),
                        'wind_speed': round(realtime['wind']['speed'] * 3.6, 1),
                        'wind_direction': realtime['wind']['direction'],
                        'pressure': round(realtime['pressure'] / 100, 1),
                        'aqi': realtime['air_quality']['aqi'].get('chn', '未知'),
                        'pm25': round(realtime['air_quality']['pm25'], 1),
                        'forecast': forecast_list,
                        'alerts': alerts,
                        'comfort': realtime.get('life_index', {}).get('comfort', {}).get('desc', '未知'),
                        'ultraviolet': realtime.get('life_index', {}).get('ultraviolet', {}).get('desc', '未知'),
                        'daily_forecast': daily_forecast,
                    }
                else:
                    print(f"API返回状态错误: {data.get('status')}")
            else:
                print(f"请求失败，HTTP状态码: {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"第 {attempt + 1} 次请求超时")
        except requests.exceptions.RequestException as e:
            print(f"第 {attempt + 1} 次请求发生错误: {str(e)}")
        except Exception as e:
            print(f"第 {attempt + 1} 次请求发生未知错误: {str(e)}")
            import traceback
            print(f"错误堆栈: {traceback.format_exc()}")
        
        if attempt < max_retries - 1:
            wait_time = (attempt + 1) * 5  # 递增等待时间
            print(f"等待 {wait_time} 秒后重试...")
            time.sleep(wait_time)
    
    print("所有重试都失败了")
    return None

def format_weather_message(weather_data):
    """式化天气消息"""
    if not weather_data:
        return "获取天气信息失败"
    
    current_time = datetime.now(pytz.timezone('Asia/Shanghai')).strftime("%Y-%m-%d %H:%M:%S")
    
    # 获取风向的文字描述
    def get_wind_direction_text(degrees):
        directions = ['北', '东北', '东', '东南', '南', '西南', '西', '西北']
        index = round(((degrees + 22.5) % 360) / 45)
        return directions[index % 8]
    
    wind_direction_text = get_wind_direction_text(weather_data['wind_direction'])
    
    # 构建时天气信息
    message = f"""🌈 长春市朝阳区天气预报
━━━━━━━━━
📅 更新时间：{current_time}

🌡️ 实时天气
• 当前温度：{weather_data['current_temp']}°C
• 体感温度：{weather_data['feels_like']}°C
• 天气状况：{weather_data['weather']}

💨 环境指数
• 相对湿度：{weather_data['humidity']}%
• 气压：{weather_data['pressure']}hPa
• 见度：{weather_data['visibility']}km

🌪️ 风力状况
• 风向：{wind_direction_text}风 ({weather_data['wind_direction']}°)
• 风速：{weather_data['wind_speed']}km/h

🌫️ 空气质量
• AQI指数：{weather_data['aqi']}
• PM2.5：{weather_data['pm25']}μg/m³

👨‍👩‍👦 生活指数
• 舒适度：{weather_data['comfort']}
• 紫外线：{weather_data['ultraviolet']}"""

    # 添加预警信息（如果有）
    if weather_data['alerts']:
        message += "\n\n⚠️ 预警信息"
        message += "\n━━━━━━━━━━"
        for alert in weather_data['alerts']:
            message += f"\n{alert['title']}\n{alert['description']}"

    # 添加24小时预报，使用表格样式展示
    message += "\n\n⏰ 未来24小时预报"
    message += "\n━━━━━━━━━━"
    
    # 创建时间轴表头
    time_header = "\n时间  "
    temp_line = "\n温度  "
    weather_line = "\n天气  "
    
    # 每3小时显示一次，共显示8个时间点
    for i, forecast in enumerate(weather_data['forecast']):
        if i % 3 == 0 and i < 24:
            # 对齐处理
            time = forecast['time'].rjust(5)
            temp = f"{forecast['temp']}°C".rjust(5)
            
            # 选择天气图标
            if "雨" in forecast['weather']:
                weather_icon = "🌧"
            elif "雪" in forecast['weather']:
                weather_icon = "🌨"
            elif "阴" in forecast['weather']:
                weather_icon = "☁️"
            elif "多云" in forecast['weather']:
                weather_icon = "⛅"
            else:
                weather_icon = "☀️"
            
            # 添加降水量信息
            if forecast['precipitation'] > 0:
                weather_icon += f"({forecast['precipitation']}mm)"
            
            # 构建时间轴
            time_header += f"{time} "
            temp_line += f"{temp} "
            weather_line += f" {weather_icon}  "
    
    message += time_header
    message += "\n────────────────────────────────"
    message += temp_line
    message += "\n────────────────────────────────"
    message += weather_line

    # 添加温度变化趋势提示
    temp_trend = []
    for i in range(len(weather_data['forecast'])-1):
        if i % 3 == 0:
            current_temp = weather_data['forecast'][i]['temp']
            next_temp = weather_data['forecast'][i+1]['temp']
            if next_temp - current_temp >= 3:
                temp_trend.append("温度明显回升")
            elif current_temp - next_temp >= 3:
                temp_trend.append("温度明显下降")
    
    if temp_trend:
        message += f"\n\n📈 温度趋势：{'，'.join(temp_trend)}"

    # 添加数据来源说明
    message += "\n\n━━━━━━━━━━"
    message += "\n📊 数据来源：彩云天气"

    return message

def push_to_wxpusher(message):
    """推送消息到微信"""
    print("准备推送消息...")
    data = {
        "appToken": WXPUSHER_TOKEN,
        "content": message,
        "contentType": 3,  # 3表示Markdown格式，支持超链接
        "uids": WXPUSHER_UIDS,
        "summary": "天气预报详情"
    }
    
    try:
        print(f"推送消息内容: {message}")
        response = requests.post(WXPUSHER_API, json=data)
        result = response.json()
        print(f"推送响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
        
        if result['code'] == 1000:
            print(f"消息成功推送给 {len(WXPUSHER_UIDS)} 个用户")
            return True
        else:
            print(f"消息推送失败: {result['msg']}")
            return False
    except Exception as e:
        print(f"推送消息时发生错误: {str(e)}")
        return False

def generate_html_content(weather_data):
    """生成HTML格式的天气信息"""
    current_time = datetime.now(pytz.timezone('Asia/Shanghai')).strftime("%Y-%m-%d %H:%M:%S")
    
    def get_wind_direction_text(degrees):
        directions = ['北', '东北', '东', '东南', '南', '西南', '西', '西北']
        index = round(((degrees + 22.5) % 360) / 45)
        return directions[index % 8]
    
    wind_direction_text = get_wind_direction_text(weather_data['wind_direction'])
    
    html = f"""
    <!DOCTYPE html>
    <html lang="zh">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>长春市朝阳区天气预报</title>
        <style>
            * {{
                box-sizing: border-box;
                -webkit-tap-highlight-color: transparent;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                max-width: 100%;
                margin: 0;
                padding: 10px;
                background-color: #f5f5f5;
                color: #333;
                line-height: 1.6;
            }}
            
            @media (min-width: 768px) {{
                body {{
                    padding: 20px;
                    max-width: 800px;
                    margin: 0 auto;
                }}
            }}
            
            .container {{
                background: white;
                border-radius: 15px;
                padding: 15px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                margin-bottom: 15px;
            }}
            
            .header {{
                text-align: center;
                margin-bottom: 20px;
                padding: 10px;
                background: linear-gradient(135deg, #1a73e8, #4285f4);
                color: white;
                border-radius: 10px;
            }}
            
            .header h1 {{
                margin: 0;
                font-size: 1.5em;
                padding: 10px 0;
            }}
            
            .section {{
                margin: 15px 0;
                padding: 15px;
                background: #f8f9fa;
                border-radius: 12px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            }}
            
            .section h2 {{
                margin-top: 0;
                color: #1a73e8;
                font-size: 1.2em;
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            
            .current-weather {{
                display: flex;
                flex-direction: column;
                align-items: center;
                padding: 15px;
            }}
            
            .current-temp {{
                font-size: 3em;
                font-weight: bold;
                color: #1a73e8;
                margin: 10px 0;
            }}
            
            .weather-grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 10px;
                margin: 10px 0;
            }}
            
            .weather-item {{
                padding: 10px;
                background: white;
                border-radius: 8px;
                text-align: center;
            }}
            
            .forecast-scroll {{
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
                scrollbar-width: none;
                margin: 0 -15px;
                padding: 15px;
            }}
            
            .forecast-scroll::-webkit-scrollbar {{
                display: none;
            }}
            
            .forecast-container {{
                display: flex;
                gap: 12px;
                padding: 0 15px;
            }}
            
            .forecast-item {{
                flex: 0 0 100px;
                background: white;
                padding: 12px;
                border-radius: 12px;
                text-align: center;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }}
            
            .forecast-item .time {{
                font-weight: bold;
                color: #1a73e8;
            }}
            
            .weather-icon {{
                font-size: 2em;
                margin: 8px 0;
            }}
            
            .alert {{
                background: #fff3cd;
                border-left: 4px solid #ffc107;
                padding: 12px;
                margin: 10px 0;
                border-radius: 8px;
            }}
            
            .alert h3 {{
                margin: 0 0 8px 0;
                color: #856404;
            }}
            
            .scroll-hint {{
                text-align: center;
                color: #666;
                font-size: 0.9em;
                margin: 8px 0;
                opacity: 0.8;
            }}
            
            footer {{
                text-align: center;
                margin-top: 20px;
                padding: 15px;
                color: #666;
                font-size: 0.9em;
            }}
            
            .daily-forecast {{
                display: flex;
                gap: 12px;
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
                scrollbar-width: none;
                padding: 15px 0;
            }}
            
            .daily-forecast::-webkit-scrollbar {{
                display: none;
            }}
            
            .daily-item {{
                flex: 0 0 140px;
                background: white;
                padding: 12px;
                border-radius: 12px;
                text-align: center;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }}
            
            .daily-item .date {{
                font-weight: bold;
                color: #1a73e8;
            }}
            
            .daily-item .temp-range {{
                font-size: 1.1em;
                margin: 8px 0;
            }}
            
            @media (max-width: 480px) {{
                .weather-grid {{
                    grid-template-columns: 1fr;
                }}
                
                .forecast-item {{
                    flex: 0 0 90px;
                    padding: 10px;
                }}
                
                .daily-item {{
                    flex: 0 0 120px;
                }}
                
                .current-temp {{
                    font-size: 2.5em;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🌈 长春市朝阳区天气预报</h1>
                <div>{current_time}</div>
            </div>
"""

    # 添加五天天气预报部分
    html += """
            <div class="section">
                <h2>📅 五天天气预报</h2>
                <div class="scroll-hint">👈 左右滑动查看更多 👉</div>
                <div class="daily-forecast">
    """
    
    # 添加五天预报
    for forecast in weather_data['daily_forecast']:
        weather_icon = get_weather_icon(forecast['weather'])  # 使用统一的图标函数
        html += f"""
                    <div class="daily-item">
                        <div class="date">{forecast['date']}</div>
                        <div class="weather-icon">{weather_icon}</div>
                        <div class="weather">{forecast['weather']}</div>
                        <div class="temp-range">{forecast['temp_min']}° ~ {forecast['temp_max']}°</div>
                    </div>
        """
    
    html += """
                </div>
            </div>
    """

    # 添加24小时预报部分
    html += """
            <div class="section">
                <h2>⏰ 24小时预报</h2>
                <div class="scroll-hint">👈 左右滑动查看更多 👉</div>
                <div class="forecast-scroll">
                    <div class="forecast-container">
    """
    
    # 添加24小时预报
    for forecast in weather_data['forecast']:
        weather_icon = get_weather_icon(forecast['weather'], forecast['precipitation'])
        precipitation_info = f'<div class="precipitation">降水：{forecast["precipitation"]:.1f}mm/h</div>' if forecast["precipitation"] > 0.0606 else ''
        
        html += f"""
                        <div class="forecast-item">
                            <div class="time">{forecast['time']}</div>
                            <div class="weather-icon">{weather_icon}</div>
                            <div class="temp">{forecast['temp']}°C</div>
                            <div class="weather">{forecast['weather']}</div>
                            {precipitation_info}
                        </div>
        """

    html += """
                    </div>
                </div>
            </div>
    """

    # 添加预警信息
    if weather_data['alerts']:
        html += """
            <div class="section">
                <h2>⚠️ 气象预警</h2>
        """
        for alert in weather_data['alerts']:
            html += f"""
                <div class="alert">
                    <h3>{alert['title']}</h3>
                    <p>{alert['description']}</p>
                </div>
            """
        html += "</div>"

    # 在实时天气部分添加今日温区
    today_forecast = weather_data['daily_forecast'][0]
    today_temp_range = f"{today_forecast['temp_min']}°C ~ {today_forecast['temp_max']}°C"
    
    html += f"""
            <div class="section">
                <h2>📌 实时天气</h2>
                <div class="current-weather">
                    <div class="current-temp">{weather_data['current_temp']}°C</div>
                    <div>体感温度：{weather_data['feels_like']}°C</div>
                    <div>今日温区：{today_temp_range}</div>
                    <div>{weather_data['weather']}</div>
                </div>
            </div>
    """

    html += """
        </div>
        <footer>
            <p>数据来源：彩云天气</p>
            <p>更新时间：{datetime.now(pytz.timezone('Asia/Shanghai')).strftime("%Y-%m-%d %H:%M:%S")}</p>
        </footer>
    </body>
    </html>
    """
    return html

def upload_to_github(content):
    """上传HTML内容到GitHub Pages"""
    try:
        github_token = os.getenv("GH_TOKEN")
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # 准备文件内容
        current_time = datetime.now(pytz.timezone('Asia/Shanghai')).strftime("%Y-%m-%d %H:%M:%S")
        data = {
            "message": f"Update weather report at {current_time}",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": "gh-pages"
        }
        
        # 使用环境变量中的用户名
        repo_owner = os.getenv("GITHUB_USERNAME", "207279525")
        repo_name = "weather-push"  # 确保这是你的仓库名
        repo_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/index.html"
        
        # 获取现有文件的SHA（如果存在）
        response = requests.get(repo_url, headers=headers)
        if response.status_code == 200:
            data["sha"] = response.json()["sha"]
        
        # 更新文件
        response = requests.put(repo_url, headers=headers, json=data)
        if response.status_code in [200, 201]:
            print("成功更新 GitHub Pages")
            return True
        else:
            print(f"更新失败: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"上传到GitHub时发生错误: {str(e)}")
        import traceback
        print(f"错误堆栈: {traceback.format_exc()}")
        return False

def generate_short_message(weather_data):
    """生成简短的天气消息"""
    # 获取触发事件类型
    trigger_event = os.getenv("TRIGGER_EVENT", "")
    
    if not weather_data:
        return "获取天气信息失败"
    
    current_time = datetime.now(pytz.timezone('Asia/Shanghai')).strftime("%Y-%m-%d %H:%M:%S")
    
    # 获取风向的文字描述
    def get_wind_direction_text(degrees):
        directions = ['北', '东北', '东', '东南', '南', '西南', '西', '西北']
        index = round(((degrees + 22.5) % 360) / 45)
        return directions[index % 8]
    
    # 计算风向文字
    wind_direction_text = get_wind_direction_text(weather_data['wind_direction'])
    
    # 根据触发事件添加不同的标题
    if trigger_event == "watch":
        message = f"""🌟 感谢关注天气推送服务！
━━━━━━━━━━
📅 更新时间：{current_time}
"""
    else:
        message = f"""🌈 长春市朝阳区天气预报
━━━━━━━━━━
📅 更新时间：{current_time}
"""
    
    # 获取今天的温度区间
    today_forecast = weather_data['daily_forecast'][0]
    today_temp_range = f"{today_forecast['temp_min']}°C ~ {today_forecast['temp_max']}°C"
    
    # 分析天气趋势
    rain_hours = sum(1 for f in weather_data['forecast'][:24] if "雨" in f['weather'] or f['precipitation'] > 0.0606)
    snow_hours = sum(1 for f in weather_data['forecast'][:24] if "雪" in f['weather'])
    
    message += f"""
━━━━━━━━━━
📅 更新时间：{current_time}

🌡️ 实时天气
"""
    # 删除重复的时间显示部分
    message += f"""• 当前温度：{weather_data['current_temp']}°C
• 体感温度：{weather_data['feels_like']}°C
• 天气状况：{weather_data['weather']}
• 今日温区：{today_temp_range}
• 相对湿度：{weather_data['humidity']}%
"""

    # 添加五天预报
    for forecast in weather_data['daily_forecast']:
        weather_icon = get_weather_icon(forecast['weather'])
        message += f"\n• {forecast['date']} {weather_icon} {forecast['temp_min']}°C ~ {forecast['temp_max']}°C {forecast['weather']}"

    message += "\n\n【未来6小时天气】"

    # 添加未来6小时预报
    for i, forecast in enumerate(weather_data['forecast']):
        if i < 6:
            precip_desc = get_precipitation_description(forecast['precipitation'])
            weather_desc = forecast['weather'] if not precip_desc else precip_desc
            weather_icon = get_weather_icon(weather_desc, forecast['precipitation'])
            
            # 修改降水量显示格式
            precipitation = f" | 降水 {forecast['precipitation']:.1f}mm/h" if forecast['precipitation'] > 0.0606 else ""
            message += f"\n• {forecast['time']} {weather_icon} {forecast['temp']}°C {weather_desc}{precipitation}"

    # 添加天气提醒
    weather_tips = []
    if rain_hours > 0:
        weather_tips.append(f"未来24小时有{rain_hours}小时降雨")
    if snow_hours > 0:
        weather_tips.append(f"未来24小时有{snow_hours}小时降雪")
    if weather_data['humidity'] >= 80:
        weather_tips.append("湿度较大，注意防潮")
    if int(weather_data['pm25']) > 75:
        weather_tips.append("空气质量一般，建议戴口罩")

    if weather_tips:
        message += "\n\n⚠️ 天气提醒\n" + "\n".join(f"• {tip}" for tip in weather_tips)

    # 添加预警信息（如果有）
    if weather_data['alerts']:
        message += "\n\n🚨 预警信息"
        for alert in weather_data['alerts']:
            message += f"\n• {alert['title']}"

    # 使用环境变量中的用户名构建链接
    github_username = os.getenv("GITHUB_USERNAME", "207279525")
    message += f"\n\n📱 [点击查看详细天气预报](https://{github_username}.github.io/weather-push/)"
    message += "\n📍 [点击查询全国天气](https://xuyang-ruwen.fra1.zeabur.app/)"
    
    return message

def main():
    """主函数"""
    print("开始执行天气推送任务...")
    
    # 获取触发事件类型
    trigger_event = os.getenv("TRIGGER_EVENT", "")
    print(f"触发事件类型: {trigger_event}")
    
    weather_data = get_weather()
    if weather_data:
        # 只在定时任务和手动触发时更新 GitHub Pages
        if trigger_event in ["schedule", "workflow_dispatch"]:
            html_content = generate_html_content(weather_data)
            if upload_to_github(html_content):
                print("HTML内容已成功上传到GitHub Pages")
            else:
                print("上传HTML内容失败")
        
        # 生成并推送消息
        message = generate_short_message(weather_data)
        success = push_to_wxpusher(message)
        print(f"任务执行{'成功' if success else '失败'}")
    else:
        print("获取天气数据失败")

if __name__ == "__main__":
    main()
