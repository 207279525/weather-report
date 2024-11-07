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

# 长春朝阳区的经纬度
LONGITUDE = 125.5358
LATITUDE = 43.8330

# 检查配置
print("检查配置信息...")
if not all([WXPUSHER_TOKEN, WXPUSHER_UIDS, WEATHER_API_KEY]):
    raise ValueError("缺少必要的配置信息，请检查环境变量或.env文件")
print(f"已配置推送目标数量: {len(WXPUSHER_UIDS)}")

# API endpoints
WXPUSHER_API = "http://wxpusher.zjiecode.com/api/send/message"
CAIYUN_API_VERSION = "v2.6"
WEATHER_API_BASE = f"https://api.caiyunapp.com/{CAIYUN_API_VERSION}/{WEATHER_API_KEY}/{LONGITUDE},{LATITUDE}"
WEATHER_API_ALL = f"{WEATHER_API_BASE}/weather?alert=true&dailysteps=1&hourlysteps=24"

def get_weather_description(skycon):
    """将天气代码转换为中文描述"""
    weather_map = {
        'CLEAR_DAY': '晴天',
        'CLEAR_NIGHT': '晴夜',
        'PARTLY_CLOUDY_DAY': '多云',
        'PARTLY_CLOUDY_NIGHT': '多云',
        'CLOUDY': '阴',
        'LIGHT_RAIN': '小雨',
        'MODERATE_RAIN': '中雨',
        'HEAVY_RAIN': '大雨',
        'STORM_RAIN': '暴雨',
        'LIGHT_SNOW': '小雪',
        'MODERATE_SNOW': '中雪',
        'HEAVY_SNOW': '大雪',
        'STORM_SNOW': '暴雪',
        'DUST': '浮尘',
        'SAND': '沙尘',
        'WIND': '大风',
        'FOG': '雾',
        'HAZE': '霾',
        'LIGHT_HAZE': '轻度霾',
        'MODERATE_HAZE': '中度霾',
        'HEAVY_HAZE': '重度霾'
    }
    return weather_map.get(skycon, skycon)

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
                    # 其余代码保持不变...
                    result = data['result']
                    realtime = result['realtime']
                    hourly = result['hourly']
                    daily = result.get('daily', {})
                    alert = result.get('alert', {})
                    
                    # 处理24小时预报数据...
                    forecast_list = []
                    base_time = datetime.now(pytz.timezone('Asia/Shanghai'))
                    
                    for temp, skycon in zip(hourly['temperature'], hourly['skycon']):
                        # 转换时间字符串为时间戳
                        time_str = temp['datetime']
                        forecast_time = datetime.strptime(time_str, "%Y-%m-%dT%H:%M%z")
                        weather_desc = get_weather_description(skycon['value'])
                        
                        # 修改降水量获取方式
                        precipitation = next((p['value'] for p in hourly['precipitation'] 
                                           if p['datetime'] == time_str), 0)
                        
                        forecast_list.append({
                            'time': forecast_time.strftime("%H:00"),
                            'temp': round(temp['value'], 1),
                            'weather': weather_desc,
                            'precipitation': precipitation
                        })

                    # 处理预警信息...
                    alerts = []
                    if 'content' in alert:
                        for warning in alert['content']:
                            alerts.append({
                                'title': warning.get('title', '未知预警'),
                                'description': warning.get('description', '')
                            })
                    
                    return {
                        'current_temp': round(realtime['temperature'], 1),
                        'feels_like': round(realtime['apparent_temperature'], 1),
                        'weather': get_weather_description(realtime['skycon']),
                        'humidity': round(realtime['humidity'] * 100),
                        'visibility': round(realtime['visibility'], 1),
                        'wind_speed': round(realtime['wind']['speed'], 1),
                        'wind_direction': realtime['wind']['direction'],
                        'pressure': round(realtime['pressure'] / 100, 1),
                        'aqi': realtime['air_quality']['aqi'].get('chn', '未知'),
                        'pm25': realtime['air_quality']['pm25'],
                        'forecast': forecast_list,
                        'alerts': alerts,
                        'comfort': realtime.get('life_index', {}).get('comfort', {}).get('desc', '未知'),
                        'ultraviolet': realtime.get('life_index', {}).get('ultraviolet', {}).get('desc', '未知'),
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

def generate_html_content(weather_data):
    """生成HTML格式的天气信息"""
    current_time = datetime.now(pytz.timezone('Asia/Shanghai')).strftime("%Y-%m-%d %H:%M:%S")
    
    html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>长春市朝阳区天气预报</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 20px auto;
                padding: 0 20px;
                background-color: #f0f2f5;
            }}
            .container {{
                background: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }}
            .header {{
                text-align: center;
                color: #1a73e8;
                margin-bottom: 20px;
            }}
            .section {{
                margin: 15px 0;
                padding: 15px;
                border-radius: 8px;
                background: #f8f9fa;
            }}
            .forecast-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
                gap: 10px;
                margin: 15px 0;
            }}
            .forecast-item {{
                text-align: center;
                padding: 10px;
                background: white;
                border-radius: 8px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }}
            .warning {{
                background: #fff3cd;
                color: #856404;
                padding: 10px;
                border-radius: 5px;
                margin: 10px 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🌈 长春市朝阳区天气预报</h1>
                <p>更新时间：{current_time}</p>
            </div>
            
            <div class="section">
                <h2>🌡️ 实时天气</h2>
                <p>当前温度：{weather_data['current_temp']}°C</p>
                <p>体感温度：{weather_data['feels_like']}°C</p>
                <p>天气状况：{weather_data['weather']}</p>
            </div>

            <div class="section">
                <h2>💨 环境指数</h2>
                <p>相对湿度：{weather_data['humidity']}%</p>
                <p>气压：{weather_data['pressure']}hPa</p>
                <p>能见度：{weather_data['visibility']}km</p>
            </div>

            <div class="section">
                <h2>🌫️ 空气质量</h2>
                <p>AQI指数：{weather_data['aqi']}</p>
                <p>PM2.5：{weather_data['pm25']}μg/m³</p>
            </div>

            <div class="section">
                <h2>⏰ 24小时预报</h2>
                <div class="forecast-grid">
    """
    
    # 添加24小时预报
    for forecast in weather_data['forecast']:
        weather_icon = "🌧" if "雨" in forecast['weather'] else "🌨" if "雪" in forecast['weather'] \
                      else "☁️" if "阴" in forecast['weather'] else "⛅" if "多云" in forecast['weather'] else "☀️"
        
        html += f"""
            <div class="forecast-item">
                <div>{forecast['time']}</div>
                <div style="font-size: 24px">{weather_icon}</div>
                <div>{forecast['temp']}°C</div>
                <div>{forecast['weather']}</div>
                {f"<div>降水: {forecast['precipitation']}mm</div>" if forecast['precipitation'] > 0 else ""}
            </div>
        """
    
    html += """
                </div>
            </div>
    """
    
    # 添加预警信息
    if weather_data['alerts']:
        html += """
            <div class="section">
                <h2>⚠️ 预警信息</h2>
        """
        for alert in weather_data['alerts']:
            html += f"""
                <div class="warning">
                    <h3>{alert['title']}</h3>
                    <p>{alert['description']}</p>
                </div>
            """
        html += "</div>"
    
    html += """
        </div>
    </body>
    </html>
    """
    return html

def upload_to_github_pages(content):
    """上传内容到GitHub Pages并返回链接"""
    try:
        github_token = os.getenv("GITHUB_TOKEN")
        github_username = "你的GitHub用户名"  # 需要替换为你的GitHub用户名
        repo_name = "weather-report"  # 你可以修改为其他名称
        
        # 创建或更新仓库
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # 检查仓库是否存在
        repo_url = f"https://api.github.com/repos/{github_username}/{repo_name}"
        repo_response = requests.get(repo_url, headers=headers)
        
        if repo_response.status_code == 404:
            # 创建仓库
            create_repo_data = {
                "name": repo_name,
                "auto_init": True,
                "private": False,
                "description": "Weather Report Page"
            }
            requests.post("https://api.github.com/user/repos", headers=headers, json=create_repo_data)
        
        # 更新文件
        file_path = "index.html"
        update_file_data = {
            "message": f"Update weather report at {datetime.now()}",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": "main"
        }
        
        # 检查文件是否存在
        file_url = f"https://api.github.com/repos/{github_username}/{repo_name}/contents/{file_path}"
        file_response = requests.get(file_url, headers=headers)
        
        if file_response.status_code == 200:
            # 文件存在，需要提供 sha
            update_file_data["sha"] = file_response.json()["sha"]
        
        # 更新或创建文件
        response = requests.put(file_url, headers=headers, json=update_file_data)
        
        if response.status_code in [200, 201]:
            # 返回GitHub Pages 链接
            return f"https://{github_username}.github.io/{repo_name}"
        
        print(f"上传文件失败: {response.status_code} - {response.text}")
        return None
        
    except Exception as e:
        print(f"上传到GitHub Pages时发生错误: {str(e)}")
        return None

def format_weather_message(weather_data):
    """格式化天气消息"""
    if not weather_data:
        return "获取天气信息失败"
    
    # 生成HTML内容
    html_content = generate_html_content(weather_data)
    
    # 上传到GitHub Pages并获取链接
    detailed_link = upload_to_github_pages(html_content)
    
    # 生成简短的消息版本
    message = generate_short_message(weather_data)
    
    # 添加详细信息链接
    if detailed_link:
        message += f"\n\n📱 查看详细天气信息：{detailed_link}"
    
    return message

def push_to_wxpusher(message):
    """推送消息到微信"""
    print("准备推送消息...")
    data = {
        "appToken": WXPUSHER_TOKEN,
        "content": message,
        "contentType": 3,  # 3表示Markdown格式
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

def generate_short_message(weather_data):
    """生成简短的天气消息"""
    if not weather_data:
        return "获取天气信息失败"
    
    current_time = datetime.now(pytz.timezone('Asia/Shanghai')).strftime("%Y-%m-%d %H:%M:%S")
    
    # 获取风向的文字描述
    def get_wind_direction_text(degrees):
        directions = ['北', '东北', '东', '东南', '南', '西南', '西', '西北']
        index = round(((degrees + 22.5) % 360) / 45)
        return directions[index % 8]
    
    wind_direction_text = get_wind_direction_text(weather_data['wind_direction'])
    
    # 构建简短消息
    message = f"""🌈 长春市朝阳区天气预报
-------------------
📅 更新时间：{current_time}

🌡️ 实时天气
• 当前温度：{weather_data['current_temp']}°C
• 体感温度：{weather_data['feels_like']}°C
• 天气状况：{weather_data['weather']}
• 相对湿度：{weather_data['humidity']}%

🌫️ 空气质量
• AQI指数：{weather_data['aqi']}
• PM2.5：{weather_data['pm25']}μg/m³

🌪️ 风力状况
• 风向：{wind_direction_text}风
• 风速：{weather_data['wind_speed']}m/s

⏰ 未来6小时预报"""

    # 添加未来6小时预报
    for i, forecast in enumerate(weather_data['forecast']):
        if i < 6:  # 只显示未来6小时
            weather_icon = "🌧" if "雨" in forecast['weather'] else "🌨" if "雪" in forecast['weather'] \
                          else "☁️" if "阴" in forecast['weather'] else "⛅" if "多云" in forecast['weather'] else "☀️"
            
            precipitation_info = f"降水:{forecast['precipitation']}mm" if forecast['precipitation'] > 0 else ""
            message += f"\n{forecast['time']} {forecast['temp']}°C {weather_icon}{forecast['weather']} {precipitation_info}"

    # 添加预警信息（如果有）
    if weather_data['alerts']:
        message += "\n\n⚠️ 预警信息"
        for alert in weather_data['alerts']:
            message += f"\n• {alert['title']}"

    return message

def main():
    """主函数"""
    print("开始执行天气推送任务...")
    weather_data = get_weather()
    message = format_weather_message(weather_data)
    success = push_to_wxpusher(message)
    print(f"任务执行{'成功' if success else '失败'}")

if __name__ == "__main__":
    main()
