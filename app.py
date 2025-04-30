import threading
import webview
import pyautogui as pag
import pygetwindow as gw
from flask import Flask, render_template, request ,jsonify , send_file , Response
import os
import signal
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
import time
import random
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from werkzeug.utils import secure_filename
import shutil
from selenium.webdriver.common.keys import Keys
import requests, os
import pyperclip
import sys
import re
from datetime import datetime, timezone 
from pynput import keyboard
import socket
import subprocess       
import openai
from queue import Queue, Empty





# Flask 앱 설정
app = Flask(__name__)


error_queue = Queue() 
stop_flag = False
driver = None
driver_ready = False
lock = threading.Lock()




SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}


EXPIRATION_DATE = datetime(2025, 4, 28, 23, 59, 59, tzinfo=timezone.utc)
date_messages= []
today = datetime.now(timezone.utc)


@app.route("/check", methods=["GET"])
def check():
    global date_messages,today,EXPIRATION_DATE
    

    if today > EXPIRATION_DATE:
        date_messages = {
            "expired": True,
            "date_messages": f"⚠️ 프로그램 사용 기한이 만료되었습니다!\n카카오 채널 통해 문의주세요."
        }
    else:
        remaining_days = (EXPIRATION_DATE - today).days
        print(remaining_days)
        date_messages = {
            "expired": False,
            "date_messages": f"✅ 프로그램은 2024-04-14(월)까지 사용 가능합니다. ({remaining_days}일 남음)\n🛠 지금은 테스트 버전입니다.\n🚀 다음주 월요일(4/28) 업데이트 예정입니다.\n💬 업데이트 문의: 채널톡으로 문의 바랍니다."
        }

    return jsonify(date_messages) 

@app.route("/check_date", methods=["POST"])
def check_date():
    global date_messages


    if date_messages["expired"]:  
        os.kill(os.getpid(), signal.SIGINT)

@app.route('/consent', methods=['POST'])
def consent():
    data = request.get_json()  # 요청에서 JSON 데이터 가져오기
    consent_value = data.get('consent')  # 'consent' 값 가져오기

    if consent_value is not None and not consent_value:
        
        print("동의하지 않았습니다. 프로그램을 종료합니다.")
        
        os.kill(os.getpid(), signal.SIGINT)  
        return jsonify({'status': 'failure', 'message': '동의하지 않음. 종료됩니다.'})
    
    # 동의한 경우에는 아무 처리 없이 종료
    return jsonify({'status': 'success', 'message': '동의가 확인되었습니다.'})




def get_hw_hash():
    uuid = subprocess.check_output("wmic csproduct get UUID", shell=True).decode().split("\n")[1].strip()
    return uuid





@app.route('/api/verify', methods=['POST'])
def verify():
    print("api/verify 들어왔습니다.")
    hw_hash = get_hw_hash()

    print(hw_hash)

    # 기기 + 프로그램 일치 시리얼 키 검색
    url = f"{SUPABASE_URL}/rest/v1/serial_keys?bound_hw_hash=eq.{hw_hash}&select=*"

    print(url)

    res = requests.get(url, headers=SUPABASE_HEADERS)
    
    keys = res.json()
   
        
    if keys:
        return jsonify({"status": "verified"})
    else:
        return jsonify({"status": "fail"})    

    


@app.route('/api/activate', methods=['POST'])
def activate():
    data = request.json
    serial_key = data.get('serial_key')
    hw_hash = get_hw_hash()

    # Supabase 시리얼 키 확인
    url = f"{SUPABASE_URL}/rest/v1/serial_keys?serial_key=eq.{serial_key}&select=*"
    res = requests.get(url, headers=SUPABASE_HEADERS)

    keys = res.json()
    if not keys:
        return jsonify({"status": "fail", "reason": "유효하지 않은 시리얼 키입니다"})

    key = keys[0]

    if key["used"]:
        return jsonify({"status": "fail", "reason": "이미 사용된 시리얼 키입니다"})

   
    # 시리얼 키 활성화 및 기기 바인딩
    patch_url = f"{SUPABASE_URL}/rest/v1/serial_keys?serial_key=eq.{serial_key}"
    requests.patch(patch_url, headers=SUPABASE_HEADERS, json={
        "used": True,
        "used_at": datetime.now(timezone.utc).isoformat(),
        "bound_hw_hash": hw_hash
    })

    return jsonify({
        "status": "success"
    })


def start_driver(hashtag_key=None, content_key=None, image_key=None, post_write=False, post_url=False):
    global driver, hashtags, contents, image_folders, navercafe_post_write, navercafe_post_url,driver_ready

    hashtags = []
    contents = []
    image_folders = []
    navercafe_post_write = []
    navercafe_post_url = []
    

    try:
        if driver is not None:
            driver.quit()
    except Exception as e:
        print("✅ 기존 드라이버 종료 중 오류 무시:", e)

    options = Options()
    options.add_argument('--disable-blink-features=AutomationControlled')  # 봇 감지 방지
    options.add_argument("--disable-gpu")  # GPU 비활성화
    options.add_argument("--no-sandbox")  # 샌드박스 비활성화
    options.add_argument("--disable-dev-shm-usage")  # 임시 파일 시스템 비활성화
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0 Safari/537.36')  # 봇 차단 방지, 사용자 에이전트 변경

    service = Service(ChromeDriverManager().install())
   
    driver = webdriver.Chrome(service=service, options=options)

    if hashtag_key:
        hashtags = read_hashtag_from_file(hashtag_key)
        print(f"✅ 해시태그 [{hashtag_key}]:", hashtags)

    if content_key:
        contents = read_content_from_file(content_key)
        print(f"✅ 콘텐츠 [{content_key}]:", contents)

    if image_key:
        image_folders = read_image_paths_from_file(image_key)
        print(f"✅ 이미지 경로 [{image_key}]:", image_folders)

       

    if post_write:
        navercafe_post_write = read_navercafe_post_write_from_file()
        print(f"✅ 카페 게시글 제목+내용:")

    if post_url:
        navercafe_post_url  = read_navercafe_post_url_from_file()
        print(f"✅ 카페 게시글 URL:")

    driver_ready = True    
    print("드라이버 상태")
    print(driver)
    
        
@app.route('/stop_driver', methods=['GET'])
def stop_driver():
    print("stop drvier옴")

    global driver, stop_flag,lock,lock
    print(driver)

    service = request.args.get('service')
    print(f"Received service: {service}")
    stop_flag = True

    print(stop_flag)
    

    with lock:
        if service == "stop_kakao_send":
            time.sleep(2)
            print_log("kakao_send","종료 되었습니다.")


        if driver is not None:
            print(service)

            stop_services = {
                'stop-instagram': 'instagram',
                'stop-naverblog' : 'naverblog',
                'stop-naverblog_api': 'naverblog_api',
                'stop-navercafe_comment': 'navercafe_comment',
                'stop-navercafe_post': 'navercafe_post',
                'stop-thread_following': 'thread_following',
                'stop-thread_unfollowing': 'thread_unfollowing',
                'stop_thread_comment': 'thread_comment',
                'stop_thread_post' : 'thread_post',
                'stop_thread_all' : 'thread_all'
                
            }

            if service in stop_services:
                service_name = stop_services[service]
                print_log(service_name, "종료중...")
                time.sleep(8)
                print_log(service_name, "종료되었습니다.")


            

        
            driver.quit()  
            driver = None

    return '', 204
       
      
       


log_messages = []

# 로그 메시지를 추가하는 함수
def print_log(program, *args):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = " ".join(str(arg) for arg in args)
    log_message = f"{program}: {now} {message}"
    log_messages.append(log_message)


def random_wait(min_time, max_time,type):
    wait_time = random.randint(min_time, max_time)
    
    log_types = {
    'instagram': 'instagram',
    'navercafe_comment': 'navercafe_comment',
    'navercafe_post': 'navercafe_post',
    'thread_following': 'thread_following',
    'thread_unfollowing': 'thread_unfollowing',
    'naverblog': 'naverblog',
    'naverblog_api': 'naverblog_api',
    'thread_post': 'thread_post',
    'thread_comment': 'thread_comment',
    'kakao_send' : 'kakao_send',
    'thread_all' : 'thread_all'
    }

    if type in log_types:
        print_log(log_types[type], "작동중...")     


    time.sleep(wait_time) 


@app.route('/download_logs', methods=['GET'])

def download_logs():
    global log_messages
    log_content = '\n'.join(log_messages)  
    

    return log_content


@app.route('/get_error')
def get_error():
    try:
        # timeout 짧게 줘서 없으면 바로 리턴
        msg = error_queue.get_nowait()
        return jsonify({'error': msg})
    except Empty:
        return jsonify({'error': None})
  

kakao_morningmessage = None
kakao_nightmessage = None 
user_ids = []  
hashtags = []  
contents = []  
image_folders = [] 
used_images = [] 
used_contents =[]
used_hashtags =[]
exception_count= 0
image_count = 0
insta_username =""   
hashtag_min_count = 0
hashtag_max_count = 0  
navercafe_post_write =[]
navercafe_post_url = []
instagram_tags = []
thread_post_hashtag = []
thread_comment_hashtag = []
wordpress_post_title = []
thread_all_hashtag = []
instagram_content = []
thread_post_detail = []
navercafe_comment_comment = []
thread_comment_detail = []
wordpress_post_content = []
thread_all_detail = []
image_folder = []
navercafe_post_image_folder = []
thread_post_image_folder = []
thread_comment_image_folder = []
wordpress_post_image_folder = []
thread_all_image_folder = []


def load_comment():
    # 사용자 홈 디렉토리 내 앱 댓글 폴더 경로
    user_home = os.path.expanduser('~')
    comment_folder = os.path.join(user_home, 'my_app_comments')
    file_path = os.path.join(comment_folder, 'comment.txt')

    # 저장된 댓글이 있다면 읽어오기
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        return "" 

# 홈 라우트: index.html을 렌더링



@app.route('/remember_chat_windows', methods=['GET'])
def get_chat_windows():
    global chat_windows
    return jsonify({'chat_windows': chat_windows})


@app.route('/remove_chat_windows', methods=['POST'])
def remove_chat_windows():
    global chat_windows
    to_remove = request.json.get('remove_list', [])
    chat_windows = [title for title in chat_windows if title not in to_remove]
    return jsonify({'status': 'success'})






@app.route('/')
def home():

    comment = load_comment()

    print("홈페이지 로딩 시작")
      
    response = render_template('index.html', comment=comment)
    return Response(response, content_type='text/html; charset=utf-8')

        




def remember_chat_windows():
    print("여기는오냐")
    global chat_windows
    active_window = gw.getActiveWindow() 
    print(active_window)
    
    if active_window and active_window.title not in [win.title for win in chat_windows]:
        print(f"채팅방 '{active_window.title}' 기억됨.")
        chat_windows.append(active_window.title)





def start_hotkey_listener():
    def on_activate():
        remember_chat_windows()

    def for_canonical(f):
        return lambda k: f(l.canonical(k))

    hotkey = keyboard.HotKey(
        keyboard.HotKey.parse('<alt>+c'),
        on_activate
    )

    l = keyboard.Listener(
        on_press=for_canonical(hotkey.press),
        on_release=for_canonical(hotkey.release)
    )
    l.start()

# ⭐ 백그라운드에서 단축키 리스너 실행
threading.Thread(target=start_hotkey_listener, daemon=True).start()





# 인스타그램 함수들 --------------------------------------------------------------


def search_web():
    global stop_flag,driver
    search_words = [
    "apple", "python", "selenium", "automation", "instagram", "facebook", "twitter", 
    "youtube", "java", "javascript", "html", "css", "react", "nodejs", "django", 
    "flask", "linux", "windows", "machine learning", "deep learning", "artificial intelligence", 
    "data science", "web development", "mobile app", "android", "ios", "cloud computing", 
    "cybersecurity", "database", "sql", "nosql", "github", "git", "api", "restful", "graphql", 
    "blockchain", "cryptocurrency", "ethereum", "bitcoin", "nft", "metaverse", "virtual reality", 
    "augmented reality", "gaming", "ecommerce", "digital marketing", "seo", "big data", "biotech", 
    "헬로", "사랑", "자동화", "기술", "인터넷", "웹개발", "인공지능", "소프트웨어", 
    "데이터분석", "미래기술", "빅데이터", "게임개발", "검색엔진", "디지털마케팅"]
    try:
        rword = random.choice(search_words)
        driver.get(f"https://www.google.com/search?q={rword}")
        random_wait(3,5,'insta')
        driver.get(f"https://search.daum.net/search?q={rword}")
        random_wait(3,5,'insta')
        driver.get(f"https://search.naver.com/search.naver?query={rword}")
        random_wait(3,5,'insta')
    except: 
        if not stop_flag:
            error_queue.put("❌ search_web 처리 중 예외 발생. 재실행 해주세요")
            try:
                driver.quit()
                stop_flag = True
            except:
                pass
        return False
            
def reset_browser(): # 오류처리 함수 
    global stop_flag
    if stop_flag:
        return
    driver.delete_all_cookies()
    driver.get("https://www.google.com/") 
    random_wait(3, 5,'insta')
    driver.get("https://www.instagram.com/")  
    random_wait(3, 5,'insta')


@app.route('/get_logs', methods=['GET'])
def get_logs():
    
    return jsonify(log_messages)   

# 파일 업로드 처리 라우트
@app.route('/upload', methods=['POST'])
def upload_file():

    user_home = os.path.expanduser('~')
    base_folder = os.path.join(user_home, 'my_app_uploads')
    os.makedirs(base_folder, exist_ok=True)


    print("업로드 파일 들어와짐")
    global image_folders,kakao_morningmessage, kakao_nightmessage

    morning_file = request.files.get('morning_messages')
    if morning_file:
        kakao_morningmessage = ""
        kakao_morningmessage = morning_file.read().decode('utf-8')  # 텍스트 파일 기준
        print("✅ 아침 메시지 저장 완료")
    
    night_file = request.files.get('night_messages')
    if night_file:
        kakao_nightmessage = ""
        kakao_nightmessage = night_file.read().decode('utf-8')  # 텍스트 파일 기준
        print("🌙 밤 메시지 저장 완료")

    
    for key in ['instagram-tags', 'thread_post_hashtag','thread_comment_hashtag','wordpress_post_title','thread_all_hashtag']:
        global instagram_tags, thread_post_hashtag, thread_comment_hashtag, wordpress_post_title, thread_all_hashtag
        if key in request.files:
            print(f"{key} 들어와짐")
            file = request.files[key]
            file_content = file.read().decode('utf-8')

            key_folder = os.path.join(base_folder, key)

            if os.path.exists(key_folder):
                shutil.rmtree(key_folder)
                print(f"기존 폴더 삭제됨: {key_folder}")

            os.makedirs(key_folder)
            print(f"새 폴더 생성됨: {key_folder}")

            filename = f"{key}_temp.txt"
            file_path = os.path.join(key_folder, filename)

            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(file_content)
                    lines = [item.strip() for item in file_content.split(',') if item.strip()]
                    if key == 'instagram-tags':
                        instagram_tags = lines
                    elif key == 'thread_post_hashtag':
                        thread_post_hashtag = lines
                    elif key == 'thread_comment_hashtag':
                        thread_comment_hashtag = lines
                    elif key == 'wordpress_post_title':
                        wordpress_post_title = lines
                    elif key == 'thread_all_hashtag':
                        thread_all_hashtag = lines
                print(f"{file_path}에 저장 완료됨.")
            except PermissionError:
                print(f"[오류] 쓰기 권한 없음: {file_path}")
        else:
            print(f"{key}에 해당하는 파일 없음.")


    for key in ['instagram-content', 'thread_post_detail', 'navercafe_comment_comment', 'thread_comment_detail', 'wordpress_post_content', 'thread_all_detail']:
        global instagram_content, thread_post_detail, navercafe_comment_comment, thread_comment_detail, wordpress_post_content, thread_all_detail
        if key in request.files:
            print(f"{key} 들어와짐")
            file = request.files[key]
            raw_data = file.read()
            file_content = raw_data.decode('utf-8', errors='ignore')

            key_folder = os.path.join(base_folder, key)
            if os.path.exists(key_folder):
                shutil.rmtree(key_folder)
                print(f"기존 폴더 삭제됨: {key_folder}")
            os.makedirs(key_folder)

            file_path = os.path.join(key_folder, f"{key}_temp.txt")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(file_content)
                lines = [item.strip() for item in file_content.split('/') if item.strip()]
                if key == 'instagram-content':
                    instagram_content = lines
                elif key == 'thread_post_detail':
                    thread_post_detail = lines
                elif key == 'navercafe_comment_comment':
                    navercafe_comment_comment = lines
                elif key == 'thread_comment_detail':
                    thread_comment_detail = lines
                elif key == 'wordpress_post_content':
                    wordpress_post_content = lines
                elif key == 'thread_all_detail':
                    thread_all_detail = lines

            print(f"{file_path}에 저장 완료됨.")  

      
    
    for key in ['image-folder', 'navercafe_post_image_folder', 'thread_post_image_folder',
            'thread_comment_image_folder', 'wordpress_post_image_folder', 'thread_all_image_folder']:
        global image_folder, navercafe_post_image_folder, thread_post_image_folder
        global thread_comment_image_folder, wordpress_post_image_folder, thread_all_image_folder
        if key in request.files:
            print(f"{key} 들어와짐")
            image_files = request.files.getlist(key)
            saved_paths = read_image(image_files, key)  # ✅ 저장된 경로 리스트 반환
            if key == 'image-folder':
                image_folder = saved_paths
            elif key == 'navercafe_post_image_folder':
                navercafe_post_image_folder = saved_paths
            elif key == 'thread_post_image_folder':
                thread_post_image_folder = saved_paths
            elif key == 'thread_comment_image_folder':
                thread_comment_image_folder = saved_paths
            elif key == 'wordpress_post_image_folder':
                wordpress_post_image_folder = saved_paths
            elif key == 'thread_all_image_folder':
                thread_all_image_folder = saved_paths
            break
             
            



    if 'navercafe_post_write' in request.files:
        print("제목,내용 들어옴")
        file = request.files['navercafe_post_write']
        raw_data = file.read()
        content = raw_data.decode('utf-8', errors='ignore')

        folder = os.path.join(base_folder, 'navercafe_post_write')
        os.makedirs(folder, exist_ok=True)
        file_path = os.path.join(folder, 'navercafe_post_write_temp.txt')
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"navercafe_post_write 저장 완료: {file_path}")

    # 4. navercafe_post_url 저장
    if 'navercafe_post_url' in request.files:
        print("URL 파일 들어옴")
        file = request.files['navercafe_post_url']
        content = file.read().decode('utf-8')

        folder = os.path.join(base_folder, 'navercafe_post_url')
        os.makedirs(folder, exist_ok=True)
        file_path = os.path.join(folder, 'navercafe_post_url_temp.txt')
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"navercafe_post_url 저장 완료: {file_path}")

          


    # 빈 응답 반환
    return '', 204

# 아이디와 비밀번호를 읽어오는 함수
def read_users(input_text):
    global user_ids
    try:
        user_ids = []
        lines = input_text.strip().split("\n")
        for line in lines:
            line = line.strip()  # 공백 제거
            if line:  # 비어있는 줄은 건너뛰기
                username, password = [x.strip() for x in line.split(',')]
                user_ids.append((username, password))

    
        print(user_ids)

    except Exception as e:
     
        print("아이디오류")

#해쉬태그 읽어오는 함수  
def read_hashtag_from_file(key):
    user_home = os.path.expanduser('~')
    file_path = os.path.join(user_home, 'my_app_uploads', key, f"{key}_temp.txt")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        hashtags = content.strip().split(',')
        hashtags = [tag.strip() for tag in hashtags if tag.strip()]
        return hashtags
    except Exception as e:
        print(f"[오류] 해시태그 파일 읽기 실패 ({key}): {e}")
        return []

def read_content_from_file(key):
    user_home = os.path.expanduser('~')
    file_path = os.path.join(user_home, 'my_app_uploads', key, f"{key}_temp.txt")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()

        content_items = file_content.strip().split('/')
        contents = [item.strip() for item in content_items if item.strip()]

        print(f"[{key}] 콘텐츠 불러오기 완료 ✅")
        print(contents)
        return contents

    except Exception as e:
        print(f"[오류] 콘텐츠 읽기 실패 ({key}): {e}")
        return []

def read_image(image_files, key):
    user_home = os.path.expanduser('~')
    image_folder_path = os.path.join(user_home, 'my_app_images', key)

    if os.path.exists(image_folder_path):
        shutil.rmtree(image_folder_path)
        print("📁 기존 이미지 폴더 삭제됨:", image_folder_path)

    os.makedirs(image_folder_path, exist_ok=True)
    print("📂 새로운 이미지 폴더 생성됨:", image_folder_path)

    saved_paths = []

    for image in image_files:
        filename = os.path.basename(image.filename)
        file_path = os.path.join(image_folder_path, filename)

        try:
            image.save(file_path)
        except Exception as e:
            print(f"❌ 파일 저장 실패: {file_path} | 이유: {e}")
            continue

        normalized_path = file_path.replace("\\", "/")
        saved_paths.append(normalized_path)

    # 경로 파일로 저장
    with open(os.path.join(image_folder_path, "image_paths.txt"), "w", encoding="utf-8") as f:
        for path in saved_paths:
            f.write(path + "\n")

    print("✅ 이미지 저장 완료:", saved_paths)
    return saved_paths

def read_image_paths_from_file(key):
   
    user_home = os.path.expanduser('~')
    path_file = os.path.join(user_home, 'my_app_images', key, 'image_paths.txt')

    try:
        with open(path_file, 'r', encoding='utf-8') as f:
            image_paths = [line.strip() for line in f if line.strip()]
        return image_paths
    except Exception as e:
        print(f"[오류] 이미지 경로 읽기 실패 ({key}): {e}")
        return []
    
    


def read_navercafe_post_write_from_file():
    user_home = os.path.expanduser('~')
    file_path = os.path.join(user_home, 'my_app_uploads', 'navercafe_post_write', 'navercafe_post_write_temp.txt')

    result = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()

        pairs = text.strip().split("//")
        for pair in pairs:
            if "$" in pair:
                result.append(tuple(pair.strip().split("$")))

        print("✅ 네이버 카페 포스트 write 읽기 완료")
        print(result)
        return result

    except Exception as e:
        print(f"[오류] navercafe_post_write 읽기 실패: {e}")
        return []

def read_navercafe_post_url_from_file():
    user_home = os.path.expanduser('~')
    file_path = os.path.join(user_home, 'my_app_uploads', 'navercafe_post_url', 'navercafe_post_url_temp.txt')

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        urls = [url.strip() for url in content.strip().split(",") if url.strip()]

        print("✅ 네이버 카페 포스트 URL 읽기 완료")
        print(urls)
        return urls

    except Exception as e:
        print(f"[오류] navercafe_post_url 읽기 실패: {e}")
        return []



# 실행하기 처리라우트
@app.route('/start', methods=['POST'])
def start():
    print("인스타시작")
    global image_count ,stop_flag,log_messages,hashtag_min_count,hashtag_max_count,used_contents,user_ids,driver_ready,driver,image_folders,exception_count
    stop_flag = False
    driver_ready = False
    exception_count = 0 
    post_count = int(request.form.get('post_count'))
    image_count = int(request.form.get('image_count'))
    insta_start_time = int(request.form.get('insta_start_time'))
    insta_end_time = int(request.form.get('insta_end_time'))
    instagram_id_value = request.form.get('instagram_id_value')
    read_users(instagram_id_value)
    print(user_ids)
    print(instagram_id_value)
    print(insta_start_time)
    print(insta_end_time)

    if request.form.get('hashtag_min_count'):
        
        hashtag_min_count = int(request.form.get('hashtag_min_count'))

    if request.form.get('hashtag_max_count'):
        
        hashtag_max_count = int(request.form.get('hashtag_max_count'))



    log_messages = []

    kwargs = {}

    # ✅ 1. 해시태그 리스트에 값이 있으면
    if instagram_tags:
        print("태그 있음 ✅")
        kwargs['hashtag_key'] = 'instagram-tags'

    # ✅ 2. 콘텐츠 리스트에 값이 있으면
    if instagram_content:
        print("콘텐츠 있음 ✅")
        kwargs['content_key'] = 'instagram-content'

    # ✅ 3. 이미지 경로 리스트에 값이 있으면
    if image_folder:
        print("이미지 있음 ✅")
        kwargs['image_key'] = 'image-folder'

    # ✅ 드라이버 실행
    threading.Thread(target=start_driver, kwargs=kwargs).start()


    random_wait(2,3,'insta')
    print(f"게시할 갯수: {post_count}")
    print(f"게시할 이미지 갯수: {image_count}")
    print(hashtag_min_count)
    print(hashtag_max_count)
    
 

    start_time = time.time()
    while not driver_ready:
        if time.time() - start_time > 30:  
            print_log('instagram', "연결 실패! 다시 시작해주세요.")
            error_queue.put("연결 실패! 크롬설치, 백신, 방화벽을 끄고 재실행 해주세요.")
            try:
                driver.quit()  # 드라이버 종료 시 예외 처리
            except Exception as e:
                print_log('instagram', f"드라이버 종료 중 오류 발생: {e}")
            stop_flag = True  # 프로그램 중단
            return  # 함수 종료
        time.sleep(1)  

    driver.get("https://www.instagram.com")

    
    

    random_wait(3,5,'insta')



    if is_logged_in():
        for _ in range(post_count):  
            for user in user_ids:  
                if stop_flag:
                    break
                login(user)
                if stop_flag == False:
                    print_log('instagram',"대기중...")
                    random_time(insta_start_time,insta_end_time)

    
    
    if stop_flag == False:
        print_log('instagram',"작업이 완료 되었습니다.")
    
    used_contents = []

    if stop_flag == False: 
        driver.quit()
        driver = None




    return '', 204


def is_logged_in():
    global exception_count, stop_flag, driver

    try:
        if stop_flag:
            return False
        
        if exception_count>3:
            error_queue.put("로그인 페이지를 찾지못했습니다 재실행 해주세요.")
            print_log("instagram","로그인 페이지를 찾지못했습니다 재실행 해주세요.")
            driver.quit()
            stop_flag = True
            return False

        print("로그인 유무 확인중...")

        try:
            login_button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "_acan"))
            )
        except Exception as e:
            if stop_flag:
                return False
            else:
                exception_count +=1
                try:
                    reset_browser()
                except:
                    if stop_flag:
                        return False  
                return is_logged_in()
            

        button_text = login_button.text.strip()

        if button_text == "로그인":
            exception_count = 0
            return True
        else:
            exception_count += 1
            try:
                reset_browser()
            except Exception as e:
                if  stop_flag:
                    return False
            return is_logged_in()

    except Exception as e:
        if not stop_flag:
            error_queue.put("오류 발생 프로그램 재실행 해주세요.")
            stop_flag = True
            try:
                driver.quit()
            except:
                pass
        return False
    
def login(user):
    global exception_count, stop_flag, insta_username

    try:
        if stop_flag:
            return False

        username, password = user
        print_log('instagram', f"로그인중 {username}")
        insta_username = username

        # 사용자 이름 입력
        try:
            username_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
        except Exception as e:
            if not stop_flag:
                error_queue.put("아이디 입력란을 찾을 수 없습니다. 프로그램을 재실행 해주세요.")
                try:
                    driver.quit()
                    stop_flag = True
                except:
                    pass
            return False

        username_field.clear()
        username_field.send_keys(username)
        random_wait(15, 30, 'instagram')

        if stop_flag:
            return False

        # 비밀번호 입력
        try:
            password_field = driver.find_element(By.NAME, "password")
        except Exception as e:
            if not stop_flag:
                error_queue.put("비밀번호 입력란을 찾을 수 없습니다. 프로그램을 재실행 해주세요.")
                try:
                    driver.quit()
                    stop_flag = True
                except:
                    pass
            return False

        password_field.clear()
        password_field.send_keys(password)

        # 로그인 버튼 클릭
        try:
            login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        except Exception as e:
            if not stop_flag:
                error_queue.put("로그인 버튼을 찾을 수 없습니다. 프로그램을 재실행 해주세요.")
                try:
                    driver.quit()
                    stop_flag = True
                except:
                    pass
            return False

        login_button.click()
        random_wait(13, 15, 'instagram')

        # 잘못된 비번 처리
        try:
            error_message = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(text(), '잘못된 비밀번호입니다. 다시 확인하세요.')]"))
            )
            if error_message:
                try:
                    print_log('instagram', "잘못된 아이디, 비밀번호입니다.")
                    driver.quit()
                    stop_flag = True
                except :
                    pass
                return False
        except:
            pass

        exception_count = 0

        click_post()
        return True

    except Exception as e:
        if not stop_flag:
            error_queue.put("로그인 도중 예기치 못한 오류가 발생했습니다. 프로그램을 재실행 해주세요.")
            try:
                driver.quit()
                stop_flag =True
            except:
                pass
        return False



def logout():
    global stop_flag, driver

    print_log('instagram', "로그아웃중...")
    random_wait(60, 80, 'instagram')

    try:
        if stop_flag:
            return False

        # '더 보기' 버튼 찾기
      
        more_button = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'svg[aria-label="설정"]'))
        )
        more_button.click()
        

        random_wait(5, 10, 'instagram')

        # '로그아웃' 버튼 찾기
       
        logout_button = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//span[text()="로그아웃"]'))
        )
        logout_button.click()
        

        random_wait(3, 5, 'instagram')

    
        search_web()

       
        driver.get("https://www.instagram.com/")
        

    except Exception as e:
        try:
            print_log("instagram","로그아웃 처리 중 예외 발생. 강제 초기화합니다.")
            driver.delete_all_cookies()
            driver.get("https://www.naver.com/")
            random_wait(2, 3, 'instagram')
            driver.get("https://www.instagram.com/")
        except Exception as e:
            if not stop_flag:
                error_queue.put("❌ 로그아웃 처리 중 예외 발생. 재실행 해주세요")
                try:
                    driver.quit()
                    stop_flag = True
                except:
                    pass
            return False
 

 


        

# 게시물 만들기 클릭 함수
def click_post():
    global stop_flag, insta_username

    try:
        if stop_flag:
            return False

        print_log('instagram', "게시물 클릭중...")

        # 닫기 버튼 먼저 시도
        try:
            close_buttons = driver.find_elements(By.CSS_SELECTOR, '[aria-label="닫기"]')
            if close_buttons:
                close_buttons[0].click()
        except Exception as e:
            if not stop_flag:
                error_queue.put("닫기 버튼 클릭 실패: 프로그램을 재실행 해주세요.")
                try:
                    driver.quit()
                    stop_flag = True
                except:
                    pass
            return False

        # 새 게시물 버튼
        try:
            post_button = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'svg[aria-label="새로운 게시물"]'))
            )
            random_wait(6, 7, 'instagram')
            post_button.click()
        except Exception as e:
            if not stop_flag:
                error_queue.put("새 게시물 버튼을 찾을 수 없습니다.")
                try:
                    driver.quit()
                    stop_flag =True
                except:
                    pass
            return False

        random_wait(3, 5, 'instagram')

        try:
            post_elements = driver.find_elements(By.XPATH, "//span[contains(text(),'게시물')]")
            if post_elements:
                post_elements[0].click()
        except Exception as e:
            if not stop_flag:
                error_queue.put("게시물 선택 항목을 찾을 수 없습니다.")
                try:
                    driver.quit()
                    stop_flag = True
                except:
                    pass
            return False

        random_wait(10, 20, 'instagram')

        try:
            select_button = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), '컴퓨터에서 선택')]"))
            )
            select_button.click()
        except Exception as e:
            if not stop_flag:
                error_queue.put("파일 선택 버튼을 찾을 수 없습니다.")
                try:
                    driver.quit()
                    stop_flag = True
                except:
                    pass
            return False

        random_wait(2, 3, 'instagram')

        # 이미지 업로드
        upload_images()
        return True

    except Exception as e:
        print_log('instagram', f"게시물 만들기 실패 {insta_username}")

        current_dir = os.path.dirname(os.path.abspath(__file__))
        error_folder = os.path.join(current_dir, "error")
        if not os.path.exists(error_folder):
            os.makedirs(error_folder)

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        screenshot_filename = f"screenshot_{insta_username}_{timestamp}.png"
        screenshot_path = os.path.join(error_folder, screenshot_filename)

        driver.get_screenshot_as_file(screenshot_path)
        if not stop_flag:
            error_queue.put("예기치 못한 오류로 게시물 생성에 실패했습니다.")
            try:
                driver.quit()
                stop_flag = True
            except:
                pass

        return False

def upload_images():
    global image_folders, image_count, stop_flag, driver

    try:
        if stop_flag:
            return False

        print_log('instagram', "이미지 업로드중...")
        print_log('instagram', f"선택한 이미지수 {image_count}")
        print(image_folders)

        all_images = [img for img in image_folders if img.lower().endswith(('jpg', 'jpeg', 'png'))]
        available_images = all_images

        if len(available_images) == 0:
            print_log('instagram', "현재 남은 이미지가 없습니다.")
            error_queue.put("현재 남은 이미지가 없습니다.")
            driver.quit()
            stop_flag = True
            return

        selected_images = available_images[:image_count]

        for idx, image_path in enumerate(selected_images):
            try:
                if idx == 0:
                    input_field = WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
                    )
                    random_wait(3, 5, 'instagram')
                    input_field.send_keys(image_path)

                elif idx == 1:
                    random_wait(2, 3, 'instagram')
                    add_button = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'div svg[aria-label="미디어 갤러리 열기"]'))
                    )
                    add_button.click()

                    random_wait(2, 3, 'instagram')
                    plus_button = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'div svg[aria-label="+ 아이콘"]'))
                    )
                    plus_button.click()

                    random_wait(2, 3, 'instagram')
                    input_field = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
                    )
                    input_field.send_keys(image_path)

                else:
                    random_wait(2, 3, 'instagram')
                    plus_button = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'div svg[aria-label="+ 아이콘"]'))
                    )
                    plus_button.click()

                    random_wait(2, 3, 'instagram')
                    input_field = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
                    )
                    input_field.send_keys(image_path)

            except Exception as e:
                if not stop_flag:
                    error_queue.put("이미지 업로드 중 오류가 발생했습니다. 프로그램을 재실행해주세요.")
                    try:
                        driver.quit()
                        stop_flag = True
                    except:
                        pass
                return False

            for window in gw.getWindowsWithTitle("열기") + gw.getWindowsWithTitle("Open"):
                random_wait(3, 5, 'instagram')
                window.close()

            random_wait(3, 5, 'instagram')

        for _ in range(2):
            try:
                random_wait(10, 40, 'instagram')
                next_button = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//*[text()='다음']"))
                )
                next_button.click()
            except Exception:
                if not stop_flag:
                    error_queue.put("게시물 작성 중 버튼 클릭 오류가 발생했습니다.")
                    print("다음버튼은 다누름")
                    try:
                        driver.quit()
                        stop_flag = True
                    except:
                        pass
                return False

        random_wait(2, 3, 'instagram')
        time.sleep(10)
        get_content()

    except Exception as e:
        if not stop_flag:
            error_queue.put("이미지 업로드중 오류가 발생했습니다.")
            try:
                driver.quit()
                stop_flag = True
            except:
                pass
        return False




    def get_content():
        global contents, stop_flag, driver

    try:
        if stop_flag:
            return False
        print("겟 콘텐트 들어옴")
        if not contents or len(contents) == 0:
            get_hashtag()
            return

        available_content = contents

        if len(available_content) == 0:
            print("사용할 컨텐츠가 없습니다.")
            print_log('instagram', "사용가능한 제목이 없습니다.")
            stop_flag = True
            return

        selected_content = random.choice(available_content)
        print(selected_content)
        print_log('instagram', "내용 입력중...")

        try:
            insert_text_box(selected_content)
        except Exception as e:
            if not stop_flag:
                error_queue.put("내용 입력 중 오류가 발생했습니다. 프로그램을 재실행해주세요.")
                try:
                    driver.quit()
                    stop_flag= True
                except:
                    pass
            return False

        get_hashtag()

    except Exception as e:
        if not stop_flag:
            error_queue.put("컨텐츠 로딩 중 오류가 발생했습니다. 프로그램을 재실행해주세요.")
            try:
                driver.quit()
                stop_flag = True
            except:
                pass
        return False
         


def get_hashtag():
    global hashtags, stop_flag, hashtag_max_count, hashtag_min_count, contents, driver

    try:
        if stop_flag:
            return False

        if not contents or len(contents) == 0:
            click_share_button()
            return

        print(hashtags)
        print(hashtag_max_count)
        print(hashtag_max_count)

        num_hashtags_select = random.randint(hashtag_min_count, hashtag_max_count)
        select_hashtag = random.sample(hashtags, num_hashtags_select)

        hashtag_text = ' '.join(select_hashtag)

        print("선택된 해시태그:", hashtag_text)
        print_log('instagram', "해쉬태그 입력중...")

        try:
            insert_text_box(hashtag_text)
        except Exception as e:
            if not stop_flag:
                error_queue.put("해시태그 입력 중 오류가 발생했습니다. 프로그램을 재실행해주세요.")
                try:
                    driver.quit()
                    stop_flag = True
                except:
                    pass
            return False

        click_share_button()

    except Exception as e:
        if not stop_flag:
            error_queue.put("해시태그 처리 중 오류가 발생했습니다. 프로그램을 재실행해주세요.")
            try:
                driver.quit()
                stop_flag = True
            except:
                pass
        return False


def insert_text_box(text):
    global stop_flag, driver

    try:
        if stop_flag:
            return False
        print("인서트 텍스트박스들어옴")
        if not text:
            print("입력할 텍스트가 없습니다.")
            return

        try:
            text_box = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[@aria-label='문구를 입력하세요...']"))
            )
        except Exception as e:
            if not stop_flag:
                error_queue.put("텍스트 입력창을 찾지 못했습니다. 프로그램을 재실행해주세요.")
                try:
                    driver.quit()
                    stop_flag = True
                except:
                    pass
            return False

        text_box.click()
        random_wait(2, 3, 'instagram')

        pyperclip.copy(text)
        random_wait(1, 3, 'instagram')

        text_box.send_keys(Keys.CONTROL, 'v')
        random_wait(1, 3, 'instagram')

        text_box.send_keys(Keys.ENTER)
        random_wait(20, 30, 'instagram')

        print("텍스트 입력 완료")

    except Exception as e:
        if not stop_flag:
            error_queue.put("텍스트 입력 중 오류가 발생했습니다. 프로그램을 재실행해주세요.")
            try:
                driver.quit()
                stop_flag = True
            except:
                pass
        return False



def click_share_button():
    global stop_flag, insta_username, driver

    try:
        if stop_flag:
            return False

        random_wait(2, 3, 'instagram')
        print_log('instagram', "공유중...")

        share_button_xpath = "//div[@role='button' and text()='공유하기']"

        try:
            share_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, share_button_xpath))
            )
        except Exception as e:
            if not stop_flag:
                error_queue.put("공유하기 버튼을 찾을 수 없습니다. 프로그램을 재실행해주세요.")
                try:
                    driver.quit()
                    stop_flag = True
                except:
                    pass
            return False

        share_button.click()
        print_log('instagram', f"공유하기 완료 {insta_username}")

        random_wait(10, 15, 'instagram')

        try:
            driver.refresh()
        except Exception as e:
            if not stop_flag:
                error_queue.put("드라이버 새로고침 중 오류가 발생했습니다.")
                try:
                    driver.quit()
                    stop_flag = True
                except:
                    pass
            return False

        random_wait(120, 300, 'instagram')

        logout()

    except Exception as e:
        if not stop_flag:
            error_queue.put("공유 과정에서 오류가 발생했습니다. 프로그램을 재실행해주세요.")
            try:
                driver.quit()
                stop_flag = True
            except:
                pass
        return False
       


# 인스타 종료 





def random_time(start_time,end_time):
    if not start_time or not end_time:
        return  
    wait_min = float(start_time) 
    wait_max = float(end_time) 
    
    wait_time = random.uniform(wait_min, wait_max)  # 사용자 지정 범위에서 랜덤 대기시간 생성
    print(wait_time)
    time.sleep(wait_time)


# 쓰레드 팔로잉 시작 

@app.route('/thread_following', methods=['POST'])   
def thread_following_start():
    global user_ids,log_messages,stop_flag,driver,driver_ready

    stop_flag = False
    driver_ready =False
    log_messages = []
  
    print(request.form.get('thread_following_start_time'))
    print(request.form.get('thread_following_end_time'))
    following_end_time = int(request.form.get('thread_following_end_time'))
    following_start_time = int(request.form.get('thread_following_start_time'))
    
    thread_following_id = request.form.get('thread_following_id')

    read_users(thread_following_id)

    threading.Thread(target=start_driver).start()

    print_log('thread_following',"작동중...")

    start_time = time.time()
    while not driver_ready:
        if time.time() - start_time > 30:  
            print_log('thread_following', "연결 실패! 다시 시작해주세요.")
            error_queue.put("연결 실패! 크롬설치, 백신, 방화벽을 끄고 재실행 해주세요.")
            try:
                driver.quit()  # 드라이버 종료 시 예외 처리
            except Exception as e:
                print_log('thread_following', f"드라이버 종료 중 오류 발생: {e}")
            stop_flag = True  # 프로그램 중단
            return  # 함수 종료
        time.sleep(1)  


    driver.get("https://www.threads.net/login?hl=ko")
    
    
    i = 0
    while i < len(user_ids):
        if stop_flag:
            break  
        user = user_ids[i]
        login_success = thread_login(user,"thread_following")
        user_ids.pop(i)
        if login_success:
            thread_search_click("thread_following")
            thread_following_click(following_start_time,following_end_time)
            thread_logout("thread_following")
            if stop_flag == False:
                
                print_log('thread_following',f"완료 {user}")
                print_log('thread_following',"대기중...")
                random_wait(90,120,"thread_following")
                
            
        else:
            if stop_flag == False:

                print_log("thread_following","로그인실패 계정을 확인해주세요")
                driver.quit()
                time.sleep(3)
                return thread_following_start()

    if stop_flag == False: 
        driver.quit()
        driver =None

    if stop_flag == False:
        print_log('thread_following',"[SF] 작업이 완료 되었습니다.")
    return '', 204

def thread_login(user, type):
    global stop_flag, driver
    print("쓰레드 로그인들어옴")
    print(user)
    if stop_flag:
        return  

    try:
        type_prefix_map = {
            "thread_following": "SF",
            "thread_post": "SU",
            "thread_comment": "SR",
            "thread_all": "SH",
            "thread_unfollowing": "SUF"
        }
        prefix = type_prefix_map.get(type, "")

        random_wait(5, 7, type)
        username, password = user
        print(username)
        print(password)
        random_wait(5,7,type)
        try:
            login_button = driver.find_element(By.XPATH, "//div[contains(text(), '로그인')]")
        except Exception:
            if not stop_flag:
                error_queue.put(f"[{prefix}] 로그인 버튼을 찾지 못했습니다. 프로그램을 재실행해주세요.")
                try:
                    print("로그인버튼을 못찾은겨????")
                    driver.quit()
                    stop_flag = True
                except:
                    pass
            return False

        print_log(type, f"[{prefix}] 로그인 중... {username}")

        if login_button:
            print("로그인버튼 if들어옴")
            try:
                input_id = driver.find_element(By.XPATH, "//input[@autocomplete='username']")
                input_id.click()
                random_wait(5, 7, type)
                input_id.send_keys(username)
                random_wait(5, 7, type)

                input_password = driver.find_element(By.XPATH, "//input[@placeholder='비밀번호']")
                input_password.click()
                random_wait(5, 7, type)
                input_password.send_keys(password)
                random_wait(5, 7, type)

                login_button.click()
                random_wait(10, 13, type)
            except Exception:
                if not stop_flag:
                    error_queue.put(f"[{prefix}] 로그인 입력 중 오류가 발생했습니다.")
                    print("입력중 오류인가?")
                    try:
                        driver.quit()
                        stop_flag = True
                    except:
                        pass
                return False

            try:
                next_button = driver.find_element(By.XPATH, "//div[@role='button'][span[contains(text(), '다음')]]")
                next_button.click()
                random_wait(5, 7, type)

                join_button = driver.find_element(By.XPATH, "//div[contains(text(), 'Threads 가입하기')]")
                random_wait(5, 7, type)
                join_button.click()
                random_wait(10, 15, type)

            except:
                print("넥스트버튼 없음")
                pass      

            try:
                random_wait(3, 5, type)
                login = driver.find_element(By.XPATH, "//button[.//div[contains(text(), '로그인')]]")
                if login:
                    print("로그인버튼있음")
                    return False
            except:
                pass

        print_log(type, "로그인 성공")
        return True

    except Exception as e:
        if not stop_flag:  
            print_log(type, "로그인 실패 로그아웃 합니다.")
            error_queue.put("로그인 중 오류가 발생했습니다. 프로그램을 재실행해주세요.")
            try:
                driver.quit()
                stop_flag = True
            except:
                pass
        return False
    

def thread_logout(type):
    global driver, stop_flag

    if stop_flag:
        return

    try:
        print("쓰레드 로그아웃 들어옴")
        print_log(type, "로그아웃 중...")

        
        more_button_svg = driver.find_element(By.CSS_SELECTOR, 'svg[aria-label="더 보기"]')
        random_wait(5, 7, type)
        

       
        more_button_div = more_button_svg.find_element(By.XPATH, '..')
        driver.execute_script("arguments[0].click();", more_button_div)
        random_wait(5, 7, type)
        

       
        logout_button = driver.find_element(By.XPATH, '//span[@dir="auto" and contains(text(), "로그아웃")]')
        driver.execute_script("arguments[0].click();", logout_button)
        print_log(type, "로그아웃 성공")
        random_wait(5, 7, type)
        

    except Exception:
        print_log(type, "로그아웃 실패: 강제 로그아웃 시도 중")
        error_queue.put("❌ 로그아웃 중 예외 발생. 브라우저 초기화합니다.")
        try:
            driver.delete_all_cookies()
            driver.get("https://www.threads.net/login?hl=ko")
        except:
            try:
                driver.quit()
                stop_flag = True
            except:
                pass


def thread_search_click(type):
    global driver, stop_flag

    if stop_flag:
        return 

    try:
        print("검색 클릭 들어옴")
        random_wait(5, 7, type)

        try:
            search_button = driver.find_element(By.XPATH, "//a[@role='link' and @href='/search']")
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 검색 버튼을 찾을 수 없습니다. 프로그램을 재시작 해주세요.")
                try:
                    driver.quit()
                    stop_flag= True
                except:
                    pass
            return

        random_wait(5, 7, type)
        print("서치버튼 찾음")

        try:
            search_button.click()
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 검색 버튼 클릭 중 오류 발생. 프로그램을 재시작 해주세요.")
                print("여기가 문제라고???")
                try:
                    driver.quit()
                    stop_flag = True
                except:
                    pass
            return

        random_wait(10, 13, type)

    except Exception as e:
        if not stop_flag:
            error_queue.put("❌ 검색 클릭 중 예기치 못한 오류가 발생했습니다.")
            try:
                driver.quit()
                stop_flag = True
            except:
                pass
        return False

def thread_following_click(following_start_time, following_end_time):
    global stop_flag

    if stop_flag:
        return
    
    try:
        while True:
            if stop_flag:
                return
            
            try:
                follow_buttons = driver.find_elements(By.XPATH, "//div[text()='팔로우']")
                visible_buttons = [btn for btn in follow_buttons if btn.is_displayed()]
            except Exception:
                if not stop_flag:
                    error_queue.put("❌ 팔로우 버튼 검색 중 오류가 발생했습니다.")
                    try:
                        driver.quit()
                        stop_flag = True
                    except:
                        pass
                return

            if not visible_buttons:
                print_log('thread_following', "화면에 보이는 팔로우 버튼이 없습니다. 종료합니다.")
                break

            while True:
                if stop_flag:
                    return
                
                random_wait(5, 7, 'thread_following')

                try:
                    follow_buttons = driver.find_elements(By.XPATH, "//div[text()='팔로우']")
                    visible_buttons = [btn for btn in follow_buttons if btn.is_displayed()]
                except Exception:
                    if not stop_flag:
                        error_queue.put("❌ 팔로우 버튼 재검색 중 오류가 발생했습니다.")
                        try:
                            driver.quit()
                            stop_flag = True
                        except:
                            pass
                    return

                if not visible_buttons:
                    break

                initial_length = len(visible_buttons)
                print("첫 팔로잉 크기:", initial_length)

                try:
                    button = visible_buttons[0]
                    driver.execute_script("arguments[0].scrollIntoView(true);", button)
                    random_wait(5, 8, 'thread_following')
                    driver.execute_script("arguments[0].click();", button)
                    print_log('thread_following', "팔로우 버튼 클릭")
                except Exception as e:
                    if not stop_flag:
                        error_queue.put("❌ 팔로우 버튼 클릭 실패. 프로그램을 재시작 해주세요.")
                        try:
                            driver.quit()
                            stop_flag = True
                        except:
                            pass
                    return

                random_wait(10, 13, 'thread_following')

                if stop_flag:
                    return

                try:
                    follow_buttons = driver.find_elements(By.XPATH, "//div[text()='팔로우']")
                    visible_buttons = [btn for btn in follow_buttons if btn.is_displayed()]
                except Exception:
                    if not stop_flag:
                        error_queue.put("❌ 팔로우 버튼 후처리 중 오류 발생.")
                        try:
                            driver.quit()
                            stop_flag = True
                        except:
                            pass
                    return

                if len(visible_buttons) == initial_length:
                    print_log('thread_following', "팔로우 실패")
                    return

                print_log("thread_following", "대기시간 대기중...")
                random_time(following_start_time, following_end_time)

            # 스크롤하여 새 버튼 로딩
            print("새로운 팔로우 버튼이 5개 이상 보일 때까지 스크롤합니다.")
            scroll_attempts = 0
            max_scroll_attempts = 20

            while True:
                if stop_flag:
                    return

                try:
                    follow_buttons = driver.find_elements(By.XPATH, "//div[text()='팔로우']")
                    visible_buttons = [btn for btn in follow_buttons if btn.is_displayed()]
                except Exception:
                    if not stop_flag:
                        error_queue.put("❌ 스크롤 중 버튼 확인 오류 발생.")
                        try:
                            driver.quit()
                            stop_flag = True
                        except:
                            pass
                    return

                if len(visible_buttons) >= 5:
                    print(f"새로운 팔로우 버튼 {len(visible_buttons)}개 확인됨")
                    break

                if scroll_attempts >= max_scroll_attempts:
                    print_log('thread_following', "최대 스크롤 시도 횟수 도달, 페이지 새로고침")
                    try:
                        driver.refresh()
                    except:
                        if not stop_flag:
                            error_queue.put("❌ 페이지 새로고침 중 오류 발생.")
                            try:
                                driver.quit()
                                stop_flag = True
                            except:
                                pass
                        return

                    random_wait(10, 13, 'thread_following')
                    break

                driver.execute_script("window.scrollBy(0, 100);")
                scroll_attempts += 1
                time.sleep(0.2)

    except Exception as e:
        if not stop_flag:
            error_queue.put("❌ 예기치 못한 오류가 발생했습니다. 프로그램을 재시작 해주세요.")
            try:
                driver.quit()
                stop_flag = True
            except:
                pass
        return
            

image_index = 0

# 쓰레드 게시물 업로드 시작 

successful_ids = []

@app.route('/thread_post_start', methods=['POST'])   
def thread_post_start():
    global user_ids,log_messages,stop_flag,hashtags,contents,image_folders,used_images,successful_ids,driver,driver_ready
    stop_flag = False
    driver_ready =False
    used_images = []
    thread_post_id = request.form.get('thread_post_id')
    read_users(thread_post_id)
    all_user_ids = user_ids.copy()    

    
    print(request.form.get('thread_post_start_time'))
    print(request.form.get('thread_post_end_time'))
    print(hashtags)
    print(contents)
    print(image_folders)

    thread_post_count = int(request.form.get('thread_post_count'))
    
    thread_post_image_count = int(request.form.get('thread_post_image_count') or 0)

    image_index =0
    log_messages = []

    time.sleep(3)

    print_log('thread_post',"작동중...")

    kwargs = {}

    # ✅ 1. 태그 파일 업로드 여부 확인
    if thread_post_hashtag:
        print("태그 파일 업로드 확인 ✅")
        kwargs['hashtag_key'] = 'thread_post_hashtag'
    else:
        print("태그 파일 없음 ❌")

    if thread_post_detail:
        print("내용 파일 업로드 확인 ✅")
        kwargs['content_key'] = 'thread_post_detail'
    else:
        print("내용 파일 없음 ❌")

    if thread_post_image_folder:
        print("이미지 폴더 업로드 확인 ✅")
        kwargs['image_key'] = 'thread_post_image_folder'
    else:
        print("이미지 폴더 없음 ❌")

    # ✅ 쓰레드 실행
    threading.Thread(target=start_driver, kwargs=kwargs).start()

    start_time = time.time()
    while not driver_ready:
        if time.time() - start_time > 30:  
            print_log('thread_post', "연결 실패! 다시 시작해주세요.")
            error_queue.put("연결 실패! 크롬설치, 백신, 방화벽을 끄고 재실행 해주세요.")
            try:
                driver.quit()  # 드라이버 종료 시 예외 처리
            except Exception as e:
                print_log('thread_post', f"드라이버 종료 중 오류 발생: {e}")
            stop_flag = True  # 프로그램 중단
            return  # 함수 종료
        time.sleep(1)

    driver.get("https://www.threads.net/login?hl=ko")

    
    for i in range(thread_post_count):
        successful_ids = []
        current_user_ids = [u for u in all_user_ids if u not in successful_ids]

        i = 0
        while i < len(current_user_ids):
            if stop_flag:
                break  

            user = current_user_ids[i]
            if stop_flag == False:
                login_success = thread_login(user,"thread_post")
            if login_success:
                    successful_ids.append(user)
                    post_success = thread_post_click(contents, hashtags)
                    if not post_success:
                        try:
                            thread_logout("thread_post")
                        except :
                            print("로그아웃실패")
                        i += 1
                        continue  
                    if thread_post_image_count > 0:
                        for j in range(thread_post_image_count):
                            if image_folders:  
                                thread_post_upload_image(image_folders[image_index],"thread_post")
                    thread_post_insert_click("thread_post")  
                    thread_logout("thread_post")
                    if stop_flag ==  False:
                        print_log('thread_post',f"완료 {user}")
                        print_log('thread_post',"대기중...")
                        random_wait(90,120,"thread_post")
                        random_time(request.form.get('thread_post_start_time'),request.form.get('thread_post_end_time'))
                        i += 1
            else:
                if stop_flag == False:
                    print("여길 왜 자꾸 오는거지?")
                    print(stop_flag)
                    print_log("thread_post","로그인실패 계정을 확인해주세요")
                    driver.quit()
                    time.sleep(3)
                    return thread_post_start()


    if stop_flag == False: 
        driver.quit()
        driver = None

    successful_ids = []
    if stop_flag == False:
        print_log('thread_post',"[SU] 작업이 완료 되었습니다.")


    return '', 204


def thread_post_click(contents, hashtags, refresh_attempt=0):
    global stop_flag, driver

    if stop_flag:
        return
    try:
        random_wait(5, 9, 'thread_post')
        print("쓰레드 포스트 들어옴")

        
        post_click_button = driver.find_element(By.CSS_SELECTOR, "div[role='button'][aria-label*='텍스트 필드가 비어 있습니다']")
        post_click_button.click()
        

        if hashtags:
            random_wait(3, 5, 'thread_post')
            print_log('thread_post', "태그 입력중...")
            random_hashtag = random.choice(hashtags)
            input_element = driver.find_element(By.CSS_SELECTOR, "input[placeholder='주제 추가']")
            pyperclip.copy(random_hashtag)
            input_element.click()
            random_wait(3, 5, 'thread_post')
            input_element.send_keys(Keys.CONTROL + "v")
            print_log('thread_post', f"태그 입력완료 {random_hashtag}")
            random_wait(3, 5, 'thread_post')

            first_li_xpath = '(//ul[@role="listbox"]/li)[1]'
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, first_li_xpath))
            ).click()

        if contents:
            random_content = random.choice(contents)
            print(random_content)
            random_wait(3, 5, 'thread_post')
            editable_div = driver.find_element(By.CSS_SELECTOR, "div[contenteditable='true'][aria-placeholder='새로운 소식이 있나요?']")
            pyperclip.copy(random_content)
            print_log('thread_post', "내용 입력중...")
            editable_div.click()
            random_wait(3, 5, 'thread_post')
            editable_div.send_keys(Keys.CONTROL + "v")
            print_log('thread_post', f"내용입력 완료 {random_content}")

        media_button = driver.find_element(By.CSS_SELECTOR, "div[role='button'] svg[aria-label='미디어 첨부']")
        parent_div = media_button.find_element(By.XPATH, './ancestor::div[1]')
        random_wait(3, 5, 'thread_post')
        print_log('thread_post', "사진 첨부중...")
        parent_div.click()

        random_wait(3, 5, 'thread_post')
        return True

    except Exception as e:
        if not stop_flag:
            if refresh_attempt < 3:
                print_log("thread_post", f"글쓰기 실패 {refresh_attempt + 1}회")
                try:
                    driver.refresh()
                except:
                    error_queue.put("새로고침 오류 재실행 해주세요")
                    try:
                        driver.quit()
                        stop_flag = True
                    except:
                        pass
                    return False
                random_wait(5, 7, "thread_post")
                thread_post_click(contents, hashtags, refresh_attempt + 1)
            else:
                print_log("thread_post", "게시글 작성 실패, 로그아웃합니다.")
                try:
                    driver.delete_all_cookies()
                    driver.get("https://www.threads.net/login?hl=ko")
                except:
                    error_queue.put("로그아웃중 오류발생 재실행 해주세요")
                    try:
                        driver.quit()
                        stop_flag = True
                    except:
                        pass
                    return False
        





def thread_post_upload_image(image_folder, type):
    global image_index, stop_flag, driver

    if stop_flag:
        return

    try:
        input_field = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
        )
        input_field.send_keys(image_folder)
        random_wait(1, 3, type)

        image_index += 1

    except Exception as e:
        if not stop_flag:
            error_queue.put("이미지 업로드 필드 탐색 또는 파일 첨부 실패. 프로그램을 재시작 해주세요.")
            try:
                driver.quit()
                stop_flag = True
            except:
                pass
        return False


def thread_post_insert_click(type):
    global stop_flag, driver

    if stop_flag:
        return

    try:
        print("인서트 클릭들어옴")
        random_wait(3, 5, type)

        try:
            for window in gw.getWindowsWithTitle("열기") + gw.getWindowsWithTitle("Open"):
                random_wait(1, 2, type)
                window.close()
        except Exception as e:
            if not stop_flag:
                error_queue.put("탐색기 창 닫기 중 오류가 발생했습니다.")
                try:
                    driver.quit()
                    stop_flag = True
                except:
                    pass
            return

        random_wait(3, 5, type)

        if type == "thread_post":
            try:
                post_buttons = driver.find_elements(By.XPATH, "//div[text()='게시' and @class='xc26acl x6s0dn4 x78zum5 xl56j7k x6ikm8r x10wlt62 x1swvt13 x1pi30zi xlyipyv xp07o12']")
                if not post_buttons:
                    raise Exception("게시 버튼을 찾을 수 없습니다.")
                print_log(type, "게시중...")
                last_button = post_buttons[-1]
                driver.execute_script("arguments[0].click();", last_button)
            except Exception as e:
                if not stop_flag:
                    error_queue.put("게시 버튼 클릭 실패. 프로그램을 재실행 해주세요.")
                    try:
                        driver.quit()
                        stop_flag = True
                    except:
                        pass
                return

        else:
            try:
                post_button = driver.find_element(By.XPATH, "//div[text()='게시' and @class='xc26acl x6s0dn4 x78zum5 xl56j7k x6ikm8r x10wlt62 x1swvt13 x1pi30zi xlyipyv xp07o12']")
                print_log(type, "게시중...")
                print("게시버튼 찾음")
                driver.execute_script("arguments[0].click();", post_button)
            except Exception as e:
                if not stop_flag:
                    error_queue.put("게시 버튼 클릭 실패. 프로그램을 재실행 해주세요.")
                    try:
                        driver.quit()
                        stop_flag = True
                    except:
                        pass
                return

        print("게시하기 클릭함")
        print_log(type, "게시 완료.")
        random_wait(8, 11, type)

    except Exception as e:
        if not stop_flag:
            error_queue.put("게시 중 알 수 없는 오류 발생.")
            try:
                driver.quit()
                stop_flag = True
            except:
                pass
        return


# 쓰레드 댓글 시작
@app.route('/thread_comment_start', methods=['POST'])   
def thread_comment_start():
    global user_ids,contents,stop_flag,log_messages,image_folders,hashtags,image_index,driver,driver_ready

    stop_flag = False
    driver_ready = False
    print(request.form.get('thread_comment_start_time'))
    print(request.form.get('thread_comment_end_time'))

    thread_comment_time = int(request.form.get('thread_comment_time'))
    thread_comment_id = request.form.get('thread_comment_id')

    read_users(thread_comment_id)

    if request.form.get('thread_comment_image_count'):
        thread_comment_image_count = int(request.form.get('thread_comment_image_count'))
        print(thread_comment_image_count)
    else: 
        thread_comment_image_count = 0    

    print(thread_comment_time)

    image_index = 0

    log_messages = []

    time.sleep(3)

    print_log('thread_comment',"작동중...")
    kwargs = {}
    
    if thread_comment_hashtag:
        print("태그 파일 업로드 확인 ✅")
        kwargs['hashtag_key'] = 'thread_comment_hashtag'
    else:
        print("태그 파일 없음 ❌")

    # ✅ 내용
    if thread_comment_detail:
        print("내용 파일 업로드 확인 ✅")
        kwargs['content_key'] = 'thread_comment_detail'
    else:
        print("내용 파일 없음 ❌")

    # ✅ 이미지
    if thread_comment_image_folder:
        print("이미지 폴더 업로드 확인 ✅")
        kwargs['image_key'] = 'thread_comment_image_folder'
    else:
        print("이미지 폴더 없음 ❌")

    # ✅ 쓰레드 실행
    threading.Thread(target=start_driver, kwargs=kwargs).start()

    start_time = time.time()
    while not driver_ready:
        if time.time() - start_time > 30:  
            print_log('thread_comment', "연결 실패! 다시 시작해주세요.")
            error_queue.put("연결 실패! 크롬설치, 백신, 방화벽을 끄고 재실행 해주세요.")
            try:
                driver.quit()  # 드라이버 종료 시 예외 처리
            except Exception as e:
                print_log('thread_comment', f"드라이버 종료 중 오류 발생: {e}")
            stop_flag = True  # 프로그램 중단
            return  # 함수 종료
        time.sleep(1)  
        

    driver.get("https://www.threads.net/login?hl=ko")

    
    i = 0
    while i < len(user_ids):
        if stop_flag:
            break  
        user = user_ids[i]
        login_success = thread_login(user,"thread_comment")
        user_ids.pop(i)

        print(login_success)
        if login_success:
                thread_search_click("thread_comment")
                thread_all_search(request.form.get('thread_comment_search_keword'),"extraction","thread_comment")
                if stop_flag == False:
                    driver.refresh()
                thread_comment_detail_insert(thread_comment_image_count,thread_comment_time,"thread_comment")
                thread_logout("thread_comment")
                if stop_flag == False:
                    print_log('thread_comment',f"완료 {user}")
                    random_wait(90,120,"thread_comment")
                    print_log('thread_comment',"대기중...")
                    random_time(request.form.get('thread_comment_start_time'),request.form.get('thread_comment_end_time'))
        else:
            if stop_flag == False:
                print_log("thread_comment","로그인실패 계정을 확인해주세요")
                driver.quit()
                time.sleep(3)
                return thread_comment_start()
            
        


    if stop_flag == False: 
        driver.quit()
        driver = None
        print_log('thread_comment',"[SR] 작업이 완료 되었습니다.")

    

    
    


    return '', 204

    
def thread_comment_detail_insert(thread_image_count, thread_comment_time, type):
    global image_folders, image_index, stop_flag, driver

    if stop_flag:
        return

    MAX_RETRIES = 3
    retries = 0

    while retries < MAX_RETRIES:
        try:
            random_wait(3, 5, "thread_comment")

          
            unique_post_container = driver.find_element(By.XPATH,
                "//div[contains(@class, 'xb57i2i') and contains(@class, 'x1q594ok') and "
                "contains(@class, 'x5lxg6s') and contains(@class, 'x78zum5') and contains(@class, 'xdt5ytf') and "
                "contains(@class, 'x1ja2u2z') and contains(@class, 'x1pq812k') and contains(@class, 'x1rohswg') and "
                "contains(@class, 'xfk6m8') and contains(@class, 'x1yqm8si') and contains(@class, 'xjx87ck') and "
                "contains(@class, 'xx8ngbg') and contains(@class, 'xwo3gff') and contains(@class, 'x1n2onr6') and "
                "contains(@class, 'x1oyok0e') and contains(@class, 'x1e4zzel') and contains(@class, 'x1plvlek') and "
                "contains(@class, 'xryxfnj')]")
            print("큰요소 찾음")

            prev_count = 0
            start_time = time.time()

            while True:
                if stop_flag:
                    return

                random_wait(3, 5, "thread_comment")


                posts = unique_post_container.find_elements(By.XPATH, ".//div[contains(@class, 'x78zum5') and contains(@class, 'xdt5ytf')]")
                
                if len(posts) == prev_count:
                    print_log("thread_comment", "해당 페이지에서 댓글을 다 달았습니다. 새로 받아옵니다.")
                    driver.refresh()
                    random_wait(3, 6, "thread_comment")
                    prev_count = 0
                    continue
                    

                for i in range(1, len(posts)):
                    if stop_flag:
                        return
                    post = posts[i]
                    try:
                        print_log("thread_comment", "댓글 작성중...")

                        elapsed_time = time.time() - start_time
                        if elapsed_time > thread_comment_time:
                            print_log("thread_comment", "설정 시간이 끝났습니다.")
                            return

                        random_wait(3, 6, "thread_comment")
                        svg_element = post.find_element(By.CSS_SELECTOR, "svg[aria-label='답글']")
                        parent_div = svg_element.find_element(By.XPATH, "..")
                        parent_div.click()
                        random_wait(3, 6, "thread_comment")

                        thread_comment_post(type)

                        if thread_image_count:
                            for _ in range(thread_image_count):
                                if stop_flag:
                                    return
                                thread_post_upload_image(image_folders[image_index], "thread_comment")

                        thread_post_insert_click("thread_comment")
                        print_log("thread_comment", "댓글 작성 완료")

                    except Exception:
                        if not stop_flag:
                            error_queue.put("❌ 댓글 작성 중 오류 발생.")
                            stop_flag = True
                            try:
                                driver.quit()
                                stop_flag = True
                            except:
                                pass
                        return

                if stop_flag:
                    return

                prev_count = len(posts)

                driver.execute_script("arguments[0].scrollTop += 500;", unique_post_container)

                random_wait(4, 7, "thread_comment")

        except Exception:
            if not stop_flag:
                retries += 1
                if retries <= MAX_RETRIES:
                    print_log("thread_comment", "댓글 쓰기 실패 재시도합니다.")
                    try:
                        driver.refresh()
                        random_wait(5, 7, "thread_comment")
                    except Exception:
                        if not stop_flag:
                            error_queue.put("❌ 재시도 중 페이지 새로고침 실패.")
                            try:
                                driver.quit()
                                stop_flag = True
                            except:
                                pass
                else:
                    error_queue.put("댓글 쓰기 실패 재실행 해주세요")
                    try:
                        driver.quit()
                        stop_flag = True
                    except:
                        pass
                return False    


        



def thread_comment_post(type):
    global hashtags, contents, stop_flag, driver

    if stop_flag:
        return

    print("쓰레드 코멘트 포스트 들어옴")
    print(hashtags)
    random_wait(8, 12, type)

    try:
        if hashtags:
            try:
                random_hashtag = random.choice(hashtags)
                pyperclip.copy(random_hashtag)
                print(random_hashtag)

                input_element = driver.find_element(By.CSS_SELECTOR, "input[placeholder='주제 추가']")
                print("주제추가 찾음")
                input_element.click()
                random_wait(3, 5, type)
                input_element.send_keys(Keys.CONTROL + "v")

                print_log(type, f"태그 입력완료 {random_hashtag}")
                time.sleep(5)

                first_li = driver.find_element(By.CSS_SELECTOR, 
                    "ul.xz401s1 li.html-li.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.xexx8yu.x4uap5.x18d9i69.xkhd6sd.x78zum5.xh8yej3")
                print("first_li 찾음")
                first_li.click()
                print("요소 클릭함")
            except Exception as e:
                if not  stop_flag:
                    error_queue.put("❌ 해시태그 입력 오류 발생.")
                    try:
                        driver.quit()
                        stop_flag = True
                    except:
                        pass
                return

        try:
            random_content = random.choice(contents)
            pyperclip.copy(random_content)

            comment_box = driver.find_element(By.CSS_SELECTOR, "div[contenteditable='true'][role='textbox']")
            comment_box.click()
            comment_box.send_keys(Keys.CONTROL + "v")

            print_log(type, f"내용 입력 완료 {random_content}")
        except Exception as e:
            if not stop_flag:
                error_queue.put("❌ 댓글 내용 입력 중 오류 발생.")
                stop_flag = True
                try:
                    driver.quit()
                except:
                    pass
            return

        try:
            media_button = driver.find_element(By.CSS_SELECTOR, "div[role='button'] svg[aria-label='미디어 첨부']")
            parent_div = media_button.find_element(By.XPATH, './ancestor::div[1]')
            random_wait(3, 5, type)
            parent_div.click()
            print("이미지 추가까지 누름")
        except Exception as e:
            if not stop_flag:
                error_queue.put("❌ 미디어 첨부 중 오류 발생.")
                stop_flag = True
                try:
                    driver.quit()
                except:
                    pass
            return

    except Exception as e:
        if not stop_flag:
            error_queue.put("❌ 댓글 작성 중 알 수 없는 오류 발생.")
            stop_flag = True
            try:
                driver.quit()
            except:
                pass
        return

# 쓰레드 언팔로잉 시작

@app.route('/thread_unfollowing', methods=['POST'])   
def thread_unfollowing_start():
    global user_ids,log_messages,stop_flag,driver,driver_ready

    stop_flag = False
    driver_ready = False
    log_messages = []

    thread_unfollowing_id = request.form.get('thread_unfollowing_id')

    read_users(thread_unfollowing_id)

    print(request.form.get('thread_unfollowing_start_time'))
    print(request.form.get('thread_unfollowing_end_time'))
    thread_unfollowing_count = int(request.form.get('thread_unfollowing_count'))
    print(thread_unfollowing_count)
    print("@@")
    

    threading.Thread(target=start_driver).start()

    print_log('thread_unfollowing',"작동중...")

    start_time = time.time()
    while not driver_ready:
        if time.time() - start_time > 30:  
            print_log('thread_unfollowing', "연결 실패! 다시 시작해주세요.")
            error_queue.put("연결 실패! 크롬설치, 백신, 방화벽을 끄고 재실행 해주세요.")
            try:
                driver.quit()  # 드라이버 종료 시 예외 처리
            except Exception as e:
                print_log('thread_unfollowing', f"드라이버 종료 중 오류 발생: {e}")
            stop_flag = True  # 프로그램 중단
            return  # 함수 종료
        time.sleep(1)  


    driver.get("https://www.threads.net/login?hl=ko")
    
    
    i = 0
    while i < len(user_ids):
        if stop_flag:
            break  
        user = user_ids[i]
        login_success = thread_login(user,"thread_unfollowing")
        user_ids.pop(i)
        if login_success:
            username , password = user
            thread_unfollowing_profile(username)
            thread_unfollowing_click(thread_unfollowing_count)
            thread_logout("thread_unfollowing")
            if stop_flag == False:
                print_log('thread_unfollowing',f"언팔로잉 완료 {username}")
                random_wait(90,120,"thread_unfollowing")
                print_log('thread_unfollowing',"대기중...")
                random_time(request.form.get('thread_unfollowing_start_time'),request.form.get('thread_unfollowing_end_time'))
        else:
            if stop_flag == False:
                print_log("thread_unfollowing","로그인실패 계정을 확인해주세요")
                driver.quit()
                time.sleep(3)
                return thread_unfollowing_start()

    if stop_flag == False: 
        driver.quit()
        driver = None
        print_log('thread_unfollowing',"[SUF] 작업이 완료 되었습니다.")
    
    return '', 204


def thread_unfollowing_profile(username):
    global stop_flag, driver

    if stop_flag:
        return

    try:
        time.sleep(3)
        print("프로필 클릭")
        url = f"https://www.threads.net/@{username}?hl=ko"
        driver.get(url)

        print_log('thread_unfollowing', "내 정보 접속")
        random_wait(3, 5, "thread_unfollowing")

        try:
            follower_element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//span[contains(text(), "팔로워")]'))
            )
            print("팔로워 찾음")
            follower_element.click()
            print("팔로워 클릭함")
            random_wait(1, 3, "thread_unfollowing")
        except Exception as e:
            if not stop_flag:
                error_queue.put("❌ 팔로워 요소를 찾을 수 없습니다.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

        try:
            following_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@role="button"][.//span[text()="팔로잉"]]'))
            )
            print("팔로잉 찾음")
            following_btn.click()
            random_wait(1, 3, "thread_unfollowing")
            print_log('thread_unfollowing', "팔로잉 확인 완료")
        except Exception as e:
            if not stop_flag:
                error_queue.put("❌ 팔로잉 버튼 클릭 중 오류가 발생했습니다.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

    except Exception as e:
        if not stop_flag:
            error_queue.put("❌ 프로필 접속 중 알 수 없는 오류 발생.")
            stop_flag = True
            try: driver.quit()
            except: pass
        return
   

def thread_unfollowing_click(thread_unfollowing_count):
    global stop_flag, driver

    if stop_flag:
        return

    random_wait(1, 3, "thread_unfollowing")

    target_class = ("x1i10hfl xjbqb8w x1ypdohk xdl72j9 x2lah0s xe8uvvx xdj266r x11i5rnm "
                    "xat24cr x1mh8g0r x2lwn1j xexx8yu x18d9i69 x1n2onr6 x16tdsg8 x1hl2dhg "
                    "xggy1nq x1ja2u2z x1t137rt x1q0g3np x1lku1pv x1a2a7pz x6s0dn4 x1a2cdl4 "
                    "xnhgr82 x1qt0ttw xgk8upj x9f619 x3nfvp2 x1s688f x90ne7k xl56j7k x193iq5w "
                    "x1swvt13 x1pi30zi x1g2r6go x12w9bfk x11xpdln xz4gly6 x87ps6o xuxw1ft "
                    "x19kf12q x6bh95i x1re03b8 x1hvtcl2 x3ug3ww x13fuv20 xu3j5b3 x1q0q8m5 "
                    "x26u7qi x178xt8z xm81vs4 xso031l xy80clv xu0ddkp xwsj4vy")

    print(thread_unfollowing_count)

    while True:
        if stop_flag:
            return

        try:
            following_containers = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((
                    By.XPATH,
                    '//div[contains(@class, "x78zum5") and contains(@class, "x1q0g3np") and contains(@class, "x1493c5g") and contains(@class, "x1ypdohk") and contains(@class, "x1w7i5hb")]'
                ))
            )
            print("총 팔로잉 컨테이너 갯수:", len(following_containers))

            if not following_containers:
                print_log("thread_unfollowing", "더 이상 팔로잉이 없습니다.")
                stop_flag = True
                break

            print_log("thread_unfollowing", f"총 {len(following_containers)}개 팔로잉 확인")

            for container in following_containers:
                if stop_flag:
                    return

                if thread_unfollowing_count <= 0:
                    print_log("thread_unfollowing", f"{thread_unfollowing_count}개 언팔로잉 작업을 완료했습니다.")
                    return

                try:
                    target_div = container.find_element(
                        By.XPATH,
                        f'.//div[@class="{target_class}"]'
                    )
                    driver.execute_script("arguments[0].scrollIntoView(true);", target_div)
                    random_wait(1, 3, "thread_unfollowing")
                    driver.execute_script("arguments[0].click();", target_div)
                    print_log("thread_unfollowing", "팔로잉 클릭")
                    random_wait(1, 2, "thread_unfollowing")

                    cancel_btn = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((
                            By.XPATH,
                            '//div[@role="button"]//span[text()="팔로우 취소"]'
                        ))
                    )
                    cancel_btn.click()
                    print_log("thread_unfollowing", "팔로우 취소 완료")

                    thread_unfollowing_count -= 1

                except Exception as e:
                    if not stop_flag:
                        error_queue.put("❌ 언팔로우 버튼을 찾거나 클릭하는 데 실패했습니다.")
                        stop_flag = True
                        try:
                            driver.quit()
                        except:
                            pass
                    return

        except Exception as e:
            if not stop_flag:
                error_queue.put("❌ 언팔로우 대상 목록을 불러오는 중 오류 발생.")
                stop_flag = True
                try:
                    driver.quit()
                except:
                    pass
            return
            
    
# 쓰레드 스하리 



current_count = 1
nickname = []
seen_ids = set() 
thread_content = []
thread_like = []
thread_extraction_comment= []
thread_retweet = []


@app.route('/thread_extraction_start', methods=['POST']) 
def thread_extraction_start():
    global user_ids,nickname,seen_ids,thread_content,thread_like,thread_extraction_comment,thread_retweet,stop_flag,driver_ready,log_messages
    print("extraction_start 들어옴")

    stop_flag = False
    driver_ready = False
    log_messages = []

    nickname = []
    seen_ids = set()
    thread_content =[]
    thread_like = []
    thread_extraction_comment= []
    thread_retweet = []

    thread_all_id = request.form.get('thread_all_id')

    read_users(thread_all_id)
    
    thread_all_search_keyword = request.form.get('thread_all_search_keyword')
    
    threading.Thread(target=start_driver).start()

    start_time = time.time()
    while not driver_ready:
        if time.time() - start_time > 30:  
            print_log('thread_all', "연결 실패! 다시 시작해주세요.")
            error_queue.put("연결 실패! 크롬설치, 백신, 방화벽을 끄고 재실행 해주세요.")
            try:
                driver.quit()  # 드라이버 종료 시 예외 처리
            except Exception as e:
                print_log('thread_all', f"드라이버 종료 중 오류 발생: {e}")
            stop_flag = True  # 프로그램 중단
            return  # 함수 종료
        time.sleep(1)  
    
    driver.get("https://www.threads.net/login?hl=ko")

    user = user_ids[0]

    print(user)

    thread_login(user,"thread_all")
    thread_search_click("thread_all")  
    thread_all_search(thread_all_search_keyword,"extraction","thread_all")
    if stop_flag == False:
        driver.refresh()
    thread_all_extraction()
    if stop_flag == False:
        print_log("thread_all","추출 완료!")

    if stop_flag == False:
        driver.quit()
        

    return '', 204



@app.route('/thread_update_table', methods=['POST'])
def thread_update_table():
    global stop_flag
    if stop_flag:
        if stop_flag:
            return jsonify({'stop': True})
    html = render_template("table.html",
                           nicknames=nickname,
                           contents=thread_content,
                           likes=thread_like,
                           comments=thread_extraction_comment,
                           retweets=thread_retweet)
    return jsonify({'stop': False, 'html': html})

    

def thread_all_search(thread_all_search_keyword, type, thread_type):
    global stop_flag, driver

    if stop_flag:
        return

    print_log(thread_type, "검색중...")

    try:
        # 검색 입력창 전체 컨테이너 찾기
        search_container = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.x6s0dn4.x78zum5.x1q0g3np.x1j85h84.x1yrsyyn"))
        )
    except Exception as e:
        if not stop_flag:
            error_queue.put("❌ 검색 입력창을 찾을 수 없습니다.")
            stop_flag = True
            try: driver.quit()
            except: pass
        return

    try:
        # 검색 입력 필드 클릭 및 입력
        thread_all_search_input = search_container.find_element(By.CSS_SELECTOR, 'input[type="search"]')
        pyperclip.copy(thread_all_search_keyword)
        thread_all_search_input.click()
        random_wait(1, 4, thread_type)
        thread_all_search_input.send_keys(Keys.CONTROL, 'v')
        print_log(thread_type, "검색어 입력완료")
        random_wait(1, 4, thread_type)
    except Exception as e:
        if not stop_flag:
            error_queue.put("❌ 검색어 입력 중 오류 발생.")
            stop_flag = True
            try: driver.quit()
            except: pass
        return

    # 검색 타입에 따라 동작
    if type == "extraction":
        try:
            thread_all_search_input.send_keys(Keys.ENTER)
        except Exception as e:
            if not stop_flag:
                error_queue.put("❌ 검색어 Enter 입력 중 오류 발생.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

    elif type == "all":
        try:
            li_elements = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "li.html-li.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.xexx8yu.x4uap5.x18d9i69.xkhd6sd.x78zum5.xh8yej3")
                )
            )
            first_li = li_elements[0]
            driver.execute_script("arguments[0].scrollIntoView(true);", first_li)
            first_li.click()
            print("✅ 첫 번째 li 클릭 완료")
        except Exception as e:
            if not stop_flag:
                error_queue.put("❌ 검색 결과 항목(li)을 클릭하는 데 실패했습니다.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

    random_wait(5, 7, thread_type)


def thread_all_extraction(target_count=50):
    global nickname, seen_ids, current_count, thread_content, thread_like, thread_extraction_comment, thread_retweet, stop_flag
    print("추출함수 들어옴")
    current_count = 1
    time.sleep(10)
    if stop_flag:
        return

    while current_count < target_count:
        if stop_flag:
            return

        try:
            unique_post_container = driver.find_element(By.XPATH, 
                "//div[contains(@class, 'xb57i2i') and contains(@class, 'x1q594ok') and "
                "contains(@class, 'x5lxg6s') and contains(@class, 'x78zum5') and contains(@class, 'xdt5ytf') and "
                "contains(@class, 'x1ja2u2z') and contains(@class, 'x1pq812k') and contains(@class, 'x1rohswg') and "
                "contains(@class, 'xfk6m8') and contains(@class, 'x1yqm8si') and contains(@class, 'xjx87ck') and "
                "contains(@class, 'xx8ngbg') and contains(@class, 'xwo3gff') and contains(@class, 'x1n2onr6') and "
                "contains(@class, 'x1oyok0e') and contains(@class, 'x1e4zzel') and contains(@class, 'x1plvlek') and "
                "contains(@class, 'xryxfnj')]"
            )
        except Exception as e:
            if not stop_flag:
                error_queue.put("❌ 게시글 컨테이너를 찾을 수 없습니다.")
                print("컨테이너를 못찾나?")
                stop_flag = True
                try:
                    driver.quit()
                except:
                    pass
            return

        try:
            posts = unique_post_container.find_elements(By.XPATH, ".//div[contains(@class, 'x78zum5') and contains(@class, 'xdt5ytf')]")
        except Exception as e:
            if not stop_flag:
                error_queue.put("❌ 게시글 요소 탐색 실패.")
                stop_flag = True
                try:
                    driver.quit()
                except:
                    pass
            return

        for post in posts[current_count:]:
            if stop_flag:
                return
            if current_count >= target_count:
                break

            try:
                id_span = WebDriverWait(post, 15).until(EC.presence_of_element_located(
                    (By.XPATH, ".//a[starts-with(@href, '/@')]/span/span[contains(@class, 'x1lliihq') and contains(@class, 'x193iq5w')]")
                ))
                id_text = id_span.get_attribute("innerText").strip()

                first_content_span = post.find_element(By.XPATH, ".//span[@class='x1lliihq x1plvlek xryxfnj x1n2onr6 x1ji0vk5 x18bv5gf xi7mnp6 x193iq5w xeuugli x1fj9vlw x13faqbe x1vvkbs x1s928wv xhkezso x1gmr53x x1cpjm7i x1fgarty x1943h6x x1i0vuye xjohtrz xo1l8bm xp07o12 x1yc453h xat24cr xdj266r']")
                content_text = first_content_span.get_attribute("innerText").strip()

                additional_content_spans = post.find_elements(By.XPATH, ".//span[@class='x1lliihq x1plvlek xryxfnj x1n2onr6 x1ji0vk5 x18bv5gf xi7mnp6 x193iq5w xeuugli x1fj9vlw x13faqbe x1vvkbs x1s928wv xhkezso x1gmr53x x1cpjm7i x1fgarty x1943h6x x1i0vuye xjohtrz xo1l8bm xp07o12 x1yc453h xat24cr x1anpbxc']")
                for span in additional_content_spans:
                    content_text += " " + span.get_attribute("innerText").strip().replace("\n", " ")

                content_text = re.sub(r'\s+', ' ', content_text)
                content_text = re.sub(r'[\u200b\u200c\u200d]', '', content_text).strip()

                divs = post.find_elements(By.XPATH, ".//div[contains(@class, 'x6s0dn4') and contains(@class, 'x78zum5') and contains(@class, 'xl56j7k') and contains(@class, 'xezivpi')]")

                like_count = divs[0].find_element(
                    By.XPATH, ".//span[contains(@class, 'x17qophe') and contains(@class, 'x10l6tqk') and contains(@class, 'x13vifvy')]"
                ).text.strip() if len(divs) > 0 else '0'

                comment_count = divs[1].find_element(
                    By.XPATH, ".//span[contains(@class, 'x17qophe') and contains(@class, 'x10l6tqk') and contains(@class, 'x13vifvy')]"
                ).text.strip() if len(divs) > 1 else '0'

                retweet_count = divs[2].find_element(
                    By.XPATH, ".//span[contains(@class, 'x17qophe') and contains(@class, 'x10l6tqk') and contains(@class, 'x13vifvy')]"
                ).text.strip() if len(divs) > 2 else '0'

                if id_text and id_text not in seen_ids:
                    seen_ids.add(id_text)
                    nickname.append(id_text)
                    thread_content.append(content_text)
                    thread_like.append(like_count)
                    thread_extraction_comment.append(comment_count)
                    thread_retweet.append(retweet_count)
                    current_count += 1

            except Exception as e:
                continue

        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception as e:
            if not stop_flag:
                error_queue.put("❌ 스크롤 중 오류 발생.")
                stop_flag = True
                try:
                    driver.quit()
                except:
                    pass
            return

        random_wait(5, 7, "thread_all")
    

   
    



@app.route('/thread_all_start', methods=['POST'])   
def thread_all_start():
    global user_ids,contents,stop_flag,log_messages,image_folders,hashtags,image_index,driver,driver_ready
    print("여기옴")
    stop_flag = False
    driver_ready = False
    log_messages = []
    
    thread_all_name = request.form.get('thread_all_id')
    read_users(thread_all_name)
    print("user_ids임")
    print(stop_flag)
    titles = request.form.getlist('selected_titles[]')
    ids = request.form.getlist('selected_ids[]')

    
    all_start_time = int(request.form.get('thread_all_start_time'))
    all_end_time = int(request.form.get('thread_all_end_time'))

    print("📌 아이디:", ids)
    print("📝 제목:", titles)
    
    
    


    if request.form.get('thread_all_image_count'):
        thread_all_image_count = int(request.form.get('thread_all_image_count'))
        print(thread_all_image_count)
    else: 
        thread_all_image_count = 0    

    print(thread_all_image_count)

    image_index = 0

    print_log('thread_all',"작동중...")
    kwargs = {}

    if thread_all_hashtag:
        print("태그 파일 업로드 확인 ✅")
        kwargs['hashtag_key'] = 'thread_all_hashtag'
    else:
        print("태그 파일 없음 ❌")

    # ✅ 내용
    if thread_all_detail:
        print("내용 파일 업로드 확인 ✅")
        kwargs['content_key'] = 'thread_all_detail'
    else:
        print("내용 파일 없음 ❌")

    # ✅ 이미지
    if thread_all_image_folder:
        print("이미지 폴더 업로드 확인 ✅")
        kwargs['image_key'] = 'thread_all_image_folder'
    else:
        print("이미지 폴더 없음 ❌")

    # ✅ 쓰레드 실행
    threading.Thread(target=start_driver, kwargs=kwargs).start()

    time.sleep(1)

    start_time = time.time()
    while not driver_ready:
        if time.time() - start_time > 30:  
            print_log('thread_all', "연결 실패! 다시 시작해주세요.")
            error_queue.put("연결 실패! 크롬설치, 백신, 방화벽을 끄고 재실행 해주세요.")
            try:
                driver.quit()  # 드라이버 종료 시 예외 처리
            except Exception as e:
                print_log('thread_all', f"드라이버 종료 중 오류 발생: {e}")
            stop_flag = True  # 프로그램 중단
            return  # 함수 종료
        time.sleep(1)  

    driver.get("https://www.threads.net/login?hl=ko")

    random_wait(3,5,"thread_all")
    print(stop_flag)
    print(len(user_ids))
    
    i = 0
    while i < len(user_ids):
        print("while 들어옴 아이디")
        if stop_flag:
            break  
        user = user_ids[i]
        print(user)
        login_success = thread_login(user,"thread_all")
        user_ids.pop(i)

        print(login_success)
        print(len(ids))
        if login_success:
            for j in range(len(ids)):
                print("for문들어옴 기본")
                print(len(ids))
                if stop_flag:
                    return '', 204 
                thread_search_click("thread_all") 
                thread_all_search(ids[j],"all","thread_all")
                if stop_flag == False:
                    driver.refresh()
                thread_all_following()
                thread_all_shhari(titles[j],thread_all_image_count)
                if stop_flag == False:
                    print_log("thread_all","대기중...")
                    random_time(all_start_time,all_end_time)
            thread_logout("thread_all")    
        else:
            if stop_flag == False:
                print_log("thread_all","로그인실패 계정을 확인해주세요")
                driver.quit()
                time.sleep(3)
                return thread_all_start()
            
        


    if stop_flag == False: 
        driver.quit()
        driver = None
        print_log('thread_all',"[SH] 작업이 완료 되었습니다.")


    return '', 204


def thread_all_following():
    global stop_flag
    if stop_flag:
        return
    try:
        wrapper_div = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.x1i10hfl.x1ypdohk.xe8uvvx.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.x2lwn1j.xeuugli.xexx8yu.x18d9i69.x1n2onr6.x16tdsg8.x1hl2dhg.xggy1nq.x1ja2u2z.x1t137rt.x1q0g3np.x1lku1pv.x1a2a7pz.x6s0dn4.x1a2cdl4.xnhgr82.x1qt0ttw.xgk8upj.x9f619.x3nfvp2.x1s688f.x90ne7k.xl56j7k.x193iq5w.x1swvt13.x1pi30zi.x1g2r6go.x12w9bfk.x11xpdln.xz4gly6.x87ps6o.xuxw1ft.x19kf12q.x111bo7f.x1vmvj1k.x45e8q.x3tjt7u.x35z2i1.x13fuv20.xu3j5b3.x1q0q8m5.x26u7qi.x178xt8z.xm81vs4.xso031l.xy80clv.xteu7em.x1l7klhg.x1iyjqo2.xs83m0k")
            )
        )

        follow_button = wrapper_div.find_element(By.CSS_SELECTOR, "div.x6ikm8r.x10wlt62.xlyipyv")
        button_text = follow_button.text.strip()

        if button_text == "팔로우":
            follow_button.click()
            print_log("thread_all", "팔로우 버튼 클릭완료")
        else:
            print_log("thread_all", "이미 팔로우 했습니다.")

    except:
        print_log("thread_all", "이미 팔로우 했습니다.")



def thread_all_shhari(title, thread_image_count):
    global image_folders, image_index, stop_flag
    if stop_flag:
        return

    prev_count = 1
    image_index = 0

    while True:
        if stop_flag:
            return
        try:
            unique_post_container = driver.find_element(By.XPATH, 
                "//div[contains(@class, 'xb57i2i') and contains(@class, 'x1q594ok') and "
                "contains(@class, 'x5lxg6s') and contains(@class, 'x78zum5') and contains(@class, 'xdt5ytf') and "
                "contains(@class, 'x1ja2u2z') and contains(@class, 'x1pq812k') and contains(@class, 'x1rohswg') and "
                "contains(@class, 'xfk6m8') and contains(@class, 'x1yqm8si') and contains(@class, 'xjx87ck') and "
                "contains(@class, 'xx8ngbg') and contains(@class, 'xwo3gff') and contains(@class, 'x1n2onr6') and "
                "contains(@class, 'x1oyok0e') and contains(@class, 'x1e4zzel') and contains(@class, 'x1plvlek') and "
                "contains(@class, 'xryxfnj')]"
            )
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 게시물 컨테이너를 찾을 수 없습니다.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

        try:
            posts = unique_post_container.find_elements(By.XPATH, ".//div[contains(@class, 'x78zum5') and contains(@class, 'xdt5ytf')]")
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 게시물 리스트를 가져오는 중 오류 발생.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

        if len(posts) == prev_count:
            print_log("해당 게시물을 찾을 수 없습니다.")
            return

        print_log("thread_all", "게시글 찾는 중...")

        for post in posts[prev_count:]:
            if stop_flag:
                return
            try:
                first_content_span = post.find_element(By.XPATH, ".//span[@class='x1lliihq x1plvlek xryxfnj x1n2onr6 x1ji0vk5 x18bv5gf xi7mnp6 x193iq5w xeuugli x1fj9vlw x13faqbe x1vvkbs x1s928wv xhkezso x1gmr53x x1cpjm7i x1fgarty x1943h6x x1i0vuye xjohtrz xo1l8bm xp07o12 x1yc453h xat24cr xdj266r']")
                content_text = first_content_span.get_attribute("innerText").strip()

                if re.sub(r'\s+', ' ', re.sub(r'[\u200b-\u200f\u202a-\u202e]', '', content_text)).strip() in re.sub(r'\s+', ' ', re.sub(r'[\u200b-\u200f\u202a-\u202e]', '', title)).strip():
                    print_log("thread_all", "게시글 확인")

                    like_svg = post.find_element(By.CSS_SELECTOR, "svg[aria-label='좋아요'], svg[aria-label='좋아요 취소']")
                    like_status = like_svg.get_attribute("aria-label")

                    if like_status == "좋아요":
                        like_div = like_svg.find_element(By.XPATH, "..")
                        like_div.click()
                        print_log("thread_all", "좋아요 클릭")

                        retweet_svg = post.find_element(By.CSS_SELECTOR, "svg[aria-label='리포스트']")
                        retweet_div = retweet_svg.find_element(By.XPATH, "..")
                        retweet_div.click()

                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, "//div[@role='button']//span[text()='리포스트']"))
                        )
                        confirm_button = driver.find_element(By.XPATH, "//div[@role='button']//span[text()='리포스트']")
                        driver.execute_script("arguments[0].click();", confirm_button)
                        print_log("thread_all", "리포스트 완료")

                        comment_element = post.find_element(By.CSS_SELECTOR, "svg[aria-label='답글']")
                        comment_div = comment_element.find_element(By.XPATH, "..")
                        comment_div.click()
                        thread_comment_post("thread_all")

                        if thread_image_count:
                            for i in range(thread_image_count):
                                if stop_flag:
                                    return
                                thread_post_upload_image(image_folders[image_index], "thread_all")

                        for window in gw.getWindowsWithTitle("열기") + gw.getWindowsWithTitle("Open"):
                            random_wait(1, 2, "thread_all")
                            window.close()

                        post_button = driver.find_element(By.XPATH, "//div[text()='게시' and @class='xc26acl x6s0dn4 x78zum5 xl56j7k x6ikm8r x10wlt62 x1swvt13 x1pi30zi xlyipyv xp07o12']")
                        post_button.click()
                        print_log("thread_all", "게시 완료")
                        return

                    else:
                        print_log("thread_all", "이미 스하리한 게시글입니다.")
                        return
                else:
                    continue

            except :
                continue
                

        prev_count = len(posts)
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 스크롤 중 오류 발생.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return
        random_wait(5, 7, "thread_all")
    



    



#@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@


# 네이버 시작 

naverblog_type = ""
secret_click = ""
comment = []
naver_neighbor_ment = ""

@app.route('/naverblogstart', methods=['POST'])
def naverblogtart():
    global log_messages,stop_flag,naverblog_type,secret_click,comment,naver_neighbor_ment,user_ids,driver,driver_ready
    naver_neighbor_ment = ""
    naverblog_type = "naverblog"
    log_messages = []
    stop_flag = False
    driver_ready = False
    
    threading.Thread(target=start_driver).start()
    time.sleep(5)

    naver_id = request.form.get('naver_id')

    read_users(naver_id)

    naver_neighbor_ment = request.form.get('naver_neighbor_ment')

    
    
  
    comment = request.form.get('comment')
    print(comment)
    secret_click = request.form.get('secret_click')

    

    save_comment(request)


    start_time = time.time()
    while not driver_ready:
        if time.time() - start_time > 30:  
            print_log(type, "연결 실패! 다시 시작해주세요.")
            error_queue.put("연결 실패! 크롬설치, 백신, 방화벽을 끄고 재실행 해주세요.")
            try:
                driver.quit()  # 드라이버 종료 시 예외 처리
            except Exception as e:
                print_log(type, f"드라이버 종료 중 오류 발생: {e}")
            stop_flag = True  # 프로그램 중단
            return  # 함수 종료
        time.sleep(1)  

    driver.get("https://nid.naver.com/nidlogin.login?mode=form&url=https://www.naver.com/")

    for user in user_ids:
        if stop_flag:
            break  
        login_success = naverlogin(user,"naverblog") 
        if login_success:
            keyword_search("naverblog",request.form.get('search_keword'))
            sort_option_click("naverblog",request.form.get('wr_2'))
            insert_blog("naverblog",int(request.form.get('naver_count')),request.form.get('neighbor_click'),request.form.get('start_time'),request.form.get('end_time'))
            if stop_flag== False:
                print_log(type,"대기중...")
                random_wait(100,300,"naverblog")
            


    
    

    

    if stop_flag == False: 
        driver.quit()
        driver =None
        print_log(type,"작업이 완료 되었습니다.")
   
    
    naverblog_type = ""
    secret_click = ""
    comment = []
    comment_index = 0
   
    
    return '', 204

def save_comment(request):
    print(request.form.get('comment'))
    # 사용자 홈 디렉토리 내 앱 이미지 폴더 경로
    user_home = os.path.expanduser('~')
    comment_folder = os.path.join(user_home, 'my_app_comments')

    # 기존 comment 폴더 삭제 후 재생성
    if os.path.exists(comment_folder):
        shutil.rmtree(comment_folder)
        print("기존 comment 폴더 삭제됨.")
    
    os.makedirs(comment_folder)  # 새로운 폴더 생성
    print("새로운 comment 폴더 생성됨.")

    # 'comment'가 요청에 포함되어 있는지 확인
    comment = request.form.get('comment')
    
    if comment:
        # comment 폴더 내에 comment.txt 파일을 생성하고 내용을 기록
        filename = "comment.txt"
        file_path = os.path.join(comment_folder, filename)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(comment)  # comment 값 저장
            print(f"댓글이 {file_path}에 저장됨.")
        except PermissionError:
            print(f"쓰기 권한이 없습니다. {file_path}에 저장할 수 없습니다.")
    else:
        print("comment 값이 없습니다.")








def naverlogin(user, type):
    global stop_flag
    try:
        if stop_flag:
            return '', 204
        
        time.sleep(3)
        random_wait(5, 7, type)
        username, password = user

        try:
            id = driver.find_element(By.CSS_SELECTOR, "#id")
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 네이버 ID 입력란을 찾을 수 없습니다.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return False

        print_log(type, f"로그인중... {username}")
        id.click()
        random_wait(5, 7, type)
        pyperclip.copy(username)
        id.send_keys(Keys.CONTROL, 'v')

        try:
            pw = driver.find_element(By.CSS_SELECTOR, "#pw")
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 네이버 PW 입력란을 찾을 수 없습니다.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return False

        random_wait(5, 7, type)
        pw.click()
        random_wait(5, 7, type)
        pyperclip.copy(password)
        pw.send_keys(Keys.CONTROL, 'v')

        try:
            login_btn = driver.find_element(By.CSS_SELECTOR, r"#log\.login")
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 로그인 버튼을 찾을 수 없습니다.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return False

        random_wait(5, 7, type)
        login_btn.click()
        random_wait(5, 7, type)

        # 비정상 활동 감지
        try:
            element = driver.find_element(By.CSS_SELECTOR, ".action_wrap .top_title")
            if "비정상적인 활동" in element.text:
                print_log(type, f"정지된 아이디입니다. 로그아웃 합니다. {username}")
                driver.delete_all_cookies()
                time.sleep(3)
                driver.get("https://nid.naver.com/nidlogin.login?mode=form&url=https://www.naver.com/")
                return False
        except:
            pass

        # 로그인 오류 메시지 감지
        try:
            if stop_flag:
                return
            error_message = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "error_message"))
            )
            if error_message:
                print_log(type, f"로그인 실패: 잘못된 아이디/비밀번호 {username}")
                driver.delete_all_cookies()
                time.sleep(3)
                driver.get("https://nid.naver.com/nidlogin.login?mode=form&url=https://www.naver.com/")
                return False
        except:
            return True

    except Exception as e:
        if not stop_flag:
            error_queue.put(f"❌ 네이버 로그인 중 오류 발생: {e}")
            stop_flag = True
            try: driver.quit()
            except: pass
        return False
    



    

def keyword_search(type, search_keword):
    global stop_flag
    try:
        if stop_flag:
            print_log(type, "작업이 중지되었습니다.")
            return '', 204

        print("keyword들어옴")
        print_log(type, f"블로그 검색중... {search_keword}")
        random_wait(5, 8, type)

        try:
            driver.get("https://section.blog.naver.com/BlogHome.naver?directoryNo=0&currentPage=1&groupId=0")
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 네이버 블로그 페이지 이동 실패")
                stop_flag = True
                try: driver.quit()
                except: pass
            return '', 204

        random_wait(5, 8, type)
        print_log(type, "작동중...")

        try:
            search_input = driver.find_element(By.CSS_SELECTOR, 'input[ng-model="navigationCtrl.searchWord"]')
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 검색 입력창을 찾을 수 없습니다.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return '', 204

        search_input.click()
        random_wait(5, 8, type)
        pyperclip.copy(search_keword)
        search_input.send_keys(Keys.CONTROL, 'v')

        random_wait(5, 8, type)
        print_log(type, "작동중...")

        try:
            search_button = driver.find_element(By.CSS_SELECTOR, 'a[ng-click="navigationCtrl.search()"]')
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 검색 버튼을 찾을 수 없습니다.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return '', 204

        search_button.click()
        random_wait(5, 8, type)
        print_log(type, "작동중...")

    except Exception as e:
        if not stop_flag:
            error_queue.put(f"❌ 블로그 검색 중 알 수 없는 오류 발생: {e}")
            stop_flag = True
            try: driver.quit()
            except: pass
        return '', 204




def sort_option_click(type, target_option):
    global stop_flag
    try:
        if stop_flag:
            print_log(type, "작업이 중지되었습니다.")
            return '', 204  

        if target_option == "최신순":
            try:
                latest_sort_option = driver.find_element(By.XPATH, '//span[contains(text(), "최신순")]')
                latest_sort_option.click()
                random_wait(5, 8, type)
                print_log(type, "정렬 옵션 '최신순' 클릭 완료")
            except Exception:
                if not stop_flag:
                    error_queue.put("❌ 정렬 옵션(최신순)을 찾거나 클릭하는 데 실패했습니다.")
                    stop_flag = True
                    try: driver.quit()
                    except: pass
                return '', 204

    except Exception as e:
        if not stop_flag:
            error_queue.put(f"❌ 정렬 옵션 처리 중 알 수 없는 오류 발생: {e}")
            stop_flag = True
            try: driver.quit()
            except: pass
        return '', 204


      


def insert_blog(type, naver_count, neighbor_click, start_time, end_time):
    global stop_flag, comment_index
    try:
        if stop_flag:
            print_log(type, "작업이 중지되었습니다.")
            return '', 204

        print("insert블로그 들어옴")
        attempts = naver_count
        current_page_number = 1

        while attempts > 0:
            if stop_flag:
                print_log(type, "작업이 중지되었습니다.")
                return '', 204

            if type == "naverblog_api":
                comment_index = 0
                get_naver_blog_titles()

            try:
                blog_elements = driver.find_elements(By.CSS_SELECTOR, 'div.list_search_post')
            except Exception as e:
                if not stop_flag:
                    error_queue.put(f"❌ 블로그 목록을 불러오는 데 실패했습니다: {e}")
                    stop_flag = True
                    try: driver.quit()
                    except: pass
                return

            current_page_blog_count = len(blog_elements)
            print_log(type, f"현재 블로그 갯수: {current_page_blog_count}")

            if current_page_blog_count == 0:
                print_log(type, "현재 페이지에 블로그가 없습니다.")
                return

            for i in range(current_page_blog_count):
                if stop_flag:
                    print_log(type, "작업이 중지되었습니다.")
                    return '', 204

                if attempts == 0:
                    print_log(type, "시행횟수가 모두 소진되었습니다.")
                    break

                try:
                    blog_link = blog_elements[i].find_element(By.CSS_SELECTOR, 'a.desc_inner')
                    blog_url = blog_link.get_attribute('href')
                    print_log(type, f"{i + 1}번째 블로그 링크 클릭: {blog_url}")
                    driver.get(blog_url)
                except Exception as e:
                    if not stop_flag:
                        error_queue.put(f"❌ 블로그 링크 이동 중 오류 발생: {e}")
                        stop_flag = True
                        try: driver.quit()
                        except: pass
                    return

                random_wait(10, 13, type)

                if neighbor_click:
                    click_neighbor()

                click_like()

                try:
                    driver.back()
                except Exception as e:
                    if not stop_flag:
                        error_queue.put(f"❌ 뒤로 가기 실패: {e}")
                        stop_flag = True
                        try: driver.quit()
                        except: pass
                    return

                random_wait(5, 8, type)
                attempts -= 1
                print_log(type, f"남은 시행횟수 {attempts} 회")
                random_time(int(start_time), int(end_time))

            if attempts == 0:
                print_log(type, "남은 시행횟수가 0입니다. 종료합니다.")
                try:
                    driver.delete_all_cookies()
                    random_wait(5, 8, type)
                    driver.get("https://nid.naver.com/nidlogin.login?mode=form&url=https://www.naver.com/")
                except Exception as e:
                    if not stop_flag:
                        error_queue.put(f"❌ 로그아웃 처리 중 오류: {e}")
                break

            if current_page_number % 10 == 0:
                try:
                    next_page_button = driver.find_element(By.CSS_SELECTOR, 'a.button_next')
                    next_page_button.click()
                    random_wait(5, 8, type)
                    current_page_number += 1
                except Exception as e:
                    if not stop_flag:
                        error_queue.put(f"❌ '다음' 페이지 버튼 클릭 실패: {e}")
                        stop_flag = True
                        try: driver.quit()
                        except: pass
                    return
            else:
                try:
                    page_link = driver.find_element(By.XPATH, f'//a[@aria-label="{current_page_number + 1}페이지"]')
                    page_link.click()
                    random_wait(5, 8, type)
                    current_page_number += 1
                except Exception as e:
                    if not stop_flag:
                        error_queue.put(f"❌ 다음 페이지 이동 실패: {e}")
                        stop_flag = True
                        try: driver.quit()
                        except: pass
                    return

    except Exception as e:
        if not stop_flag:
            error_queue.put(f"❌ 블로그 삽입 중 알 수 없는 오류 발생: {e}")
            stop_flag = True
            try: driver.quit()
            except: pass
        return

    finally:
        if not stop_flag:
            try:
                print_log(type, "작업 종료 후 로그아웃 처리")
                driver.delete_all_cookies()
                random_wait(5, 8, type)
                driver.get("https://nid.naver.com/nidlogin.login?mode=form&url=https://www.naver.com/")
            except Exception as e:
                if not stop_flag:
                    error_queue.put(f"❌ 최종 정리 중 오류: {e}")
                    stop_flag = True
                    driver.quit()


def click_neighbor():
    global stop_flag, naverblog_type, naver_neighbor_ment

    if stop_flag:
        return

    main_window = driver.current_window_handle

    try:
        print_log(naverblog_type, "이웃추가중...")

        # iframe 진입
        try:
            main_frame = driver.find_element(By.ID, "mainFrame")
            driver.switch_to.frame(main_frame)
        except Exception as e:
            if not stop_flag:
                error_queue.put(f"❌ iframe(mainFrame) 진입 실패: {e}")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

        # 이웃추가 버튼 클릭
        try:
            neighbor_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.btn_buddy.btn_addbuddy.pcol2._buddy_popup_btn._returnFalse._rosRestrictAll'))
            )
        except Exception as e:
            if not stop_flag:
                error_queue.put(f"❌ 이웃추가 버튼을 찾을 수 없습니다: {e}")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

        neighbor_text = neighbor_button.text.strip()

        if neighbor_text == "이웃추가":
            try:
                neighbor_button.click()
            except Exception as e:
                if not stop_flag:
                    error_queue.put(f"❌ 이웃추가 버튼 클릭 실패: {e}")
                    stop_flag = True
                    try: driver.quit()
                    except: pass
                return

            print_log(naverblog_type, "서로이웃추가중...")

            try:
                WebDriverWait(driver, 5).until(lambda d: len(d.window_handles) > 1)
            except Exception as e:
                if not stop_flag:
                    error_queue.put(f"❌ 새 창 열림 대기 중 오류 발생: {e}")
                    stop_flag = True
                    try: driver.quit()
                    except: pass
                return

            # 새 창 전환
            try:
                for handle in driver.window_handles:
                    if handle != main_window:
                        driver.switch_to.window(handle)
                        break
            except Exception as e:
                if not stop_flag:
                    error_queue.put(f"❌ 새 창 전환 실패: {e}")
                    stop_flag = True
                    try: driver.quit()
                    except: pass
                return

            try:
                WebDriverWait(driver, 3).until(EC.alert_is_present())
                driver.switch_to.alert.accept()
                print_log(naverblog_type, "블로거가 서로이웃 최대치입니다.")
                driver.switch_to.window(main_window)
                return
            except:
                pass

            try:
                each_buddy_add_label = driver.find_element(By.CSS_SELECTOR, "label[for='each_buddy_add']")
                each_buddy_add_input = driver.find_element(By.CSS_SELECTOR, "input#each_buddy_add")
            except Exception as e:
                error_queue.put(f"❌ 서로이웃 항목 로딩 실패: {e}")
                stop_flag = True
                try: driver.quit()
                except: pass
                return

            if "disabled" in each_buddy_add_input.get_attribute("outerHTML"):
                print_log(naverblog_type, "서로이웃 추가가 비활성화된 블로그입니다.")
                driver.close()
                driver.switch_to.window(main_window)
                return

            each_buddy_add_label.click()

            try:
                next_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.button_next._buddyAddNext'))
                )
                next_button.click()
            except Exception as e:
                if not stop_flag:
                    error_queue.put(f"❌ 첫 번째 '다음' 버튼 클릭 실패: {e}")
                    stop_flag = True
                    try: driver.quit()
                    except: pass
                return

            try:
                time.sleep(4)
                WebDriverWait(driver, 3).until(EC.alert_is_present())
                driver.switch_to.alert.accept()
                driver.close()
                driver.switch_to.window(main_window)
                print_log(naverblog_type, "이미 서로이웃 신청중입니다.")
                return
            except:
                pass

            try:
                WebDriverWait(driver, 5).until(lambda d: len(d.window_handles) > 1)
                for handle in driver.window_handles:
                    if handle != main_window:
                        driver.switch_to.window(handle)
                        break
            except Exception as e:
                if not stop_flag:
                    error_queue.put(f"❌ 두 번째 창 전환 실패: {e}")
                    stop_flag = True
                    try: driver.quit()
                    except: pass
                return

            try:
                message_textarea = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'textarea#message'))
                )
                message_textarea.click()
                pyperclip.copy(naver_neighbor_ment)
                time.sleep(1)
                message_textarea.send_keys(Keys.CONTROL, 'v')
                print("서이추멘트까지는 넣음")
            except Exception as e:
                if not stop_flag:
                    error_queue.put(f"❌ 메시지 입력창 오류: {e}")
                    stop_flag = True
                    try: driver.quit()
                    except: pass
                return
            random_wait(3,5,naverblog_type)
            try:
                next_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.button_next._addBothBuddy'))
                )
                next_button.click()
                print("닫기누름 마지막")
            except Exception as e:
                if not stop_flag:
                    error_queue.put(f"❌ 두 번째 '다음' 버튼 클릭 실패: {e}")
                    print("마지막을 못누른건가?")
                    stop_flag = True
                    try: driver.quit()
                    except: pass
                return

            driver.close()
            time.sleep(random.uniform(5, 8))
            driver.switch_to.window(main_window)
            print_log(naverblog_type, "서로이웃 추가 완료")

        else:
            print_log(naverblog_type, "이미 이웃입니다.")
            driver.switch_to.window(main_window)
            driver.switch_to.default_content()
            return

    except Exception as e:
        if not stop_flag:
            error_queue.put(f"❌ 이웃 추가 중 알 수 없는 오류 발생: {e}")
            stop_flag = True
            try: driver.quit()
            except: pass
        return

def click_like():
    global stop_flag, naverblog_type

    try:
        if stop_flag:  
            print_log(naverblog_type, "작업이 중지되었습니다.")
            return '', 204

        print_log(naverblog_type, "좋아요 누르는중...")

        time.sleep(random.uniform(5, 8))
        print_log(naverblog_type, "작동중...")

        try:
            main_frame = driver.find_element(By.ID, "mainFrame")
            driver.switch_to.frame(main_frame)
        except Exception as e:
            if not stop_flag:
                error_queue.put(f"❌ iframe(mainFrame) 진입 실패: {e}")
                print("메인프레임 못간거임?")
                stop_flag = True
                try: driver.quit()
                except: pass
            return '', 204

        scroll_count = 0

        while True:
            if stop_flag:
                print_log(naverblog_type, "작업이 중지되었습니다.")
                return '', 204

            try:
                print("좋아요 찾으러옴")
                like_button = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'a.u_likeit_list_btn._button[data-type="like"]'))
                )
                button_class = like_button.get_attribute('class')

                if 'off' in button_class:
                    try:
                        like_button.click()
                        print_log(naverblog_type, "좋아요 완료")
                        time.sleep(random.uniform(5, 8))
                        print_log(naverblog_type, "작동중...")
                        write_comment()
                        break
                    except Exception as e:
                        error_queue.put(f"❌ 좋아요 버튼 클릭 실패: {e}")

                elif 'on' in button_class:
                    time.sleep(random.uniform(5, 8))
                    print_log(naverblog_type, "작동중...")
                    break

            except Exception as e:
    
                driver.execute_script("window.scrollBy(0, 1000);")
               

                time.sleep(random.uniform(5, 8))
                print_log(naverblog_type, "좋아요 버튼을 찾을 수 없어 스크롤 내림.")
                scroll_count += 1

                if scroll_count >= 6:
                    if not stop_flag:
                        error_queue.put("❌ 좋아요 버튼을 찾을 수 없어 종료합니다.")
                        stop_flag = True
                        try: driver.quit()
                        except: pass
                    return '', 204

    except Exception as e:
        if not stop_flag:
            error_queue.put(f"❌ 좋아요 클릭 중 알 수 없는 오류 발생: {e}")
            print("설마 마지막 예외오는거임?")
            stop_flag = True
            try: driver.quit()
            except: pass
        return '', 204  




def write_comment():
    global stop_flag, secret_click, comment, naverblog_type, comment_index

    if stop_flag:
        print_log(naverblog_type, "작업이 중지되었습니다.")
        return

    print_log(naverblog_type, "댓글 쓰는중...")

    try:
        try:
            comment_button = driver.find_element(By.CSS_SELECTOR, 'a.btn_comment._cmtList')
            comment_button.click()
            random_wait(5, 8, naverblog_type)
        except Exception as e:
            if not stop_flag:
                error_queue.put(f"❌ 댓글 버튼 클릭 실패: {e}")
                stop_flag = True
                try: driver.quit()
                except: pass
            return '', 204

        try:
            comment_input = driver.find_element(By.CSS_SELECTOR, 'div.u_cbox_text.u_cbox_text_mention')
        except Exception as e:
            if not stop_flag:
                error_queue.put(f"❌ 댓글 입력창 로딩 실패: {e}")
                stop_flag = True
                try: driver.quit()
                except: pass
            return '', 204

        if secret_click:
            print_log(naverblog_type, "비밀댓글 실행중...")
            try:
                secret_checkbox_span = driver.find_element(By.CSS_SELECTOR, '.u_cbox_secret_tag')
                random_wait(5, 8, naverblog_type)
                secret_checkbox_span.click()
                random_wait(5, 8, naverblog_type)
            except Exception as e:
                if not stop_flag:
                    error_queue.put(f"❌ 비밀댓글 체크 실패: {e}")
                    stop_flag = True
                    try: driver.quit()
                    except: pass
                return '', 204

        try:
            driver.execute_script("arguments[0].focus();", comment_input)
            driver.execute_script("arguments[0].click();", comment_input)
            random_wait(5, 8, naverblog_type)
        except Exception as e:
            if not stop_flag:
                error_queue.put(f"❌ 댓글창 포커스 실패: {e}")
                stop_flag = True
                try: driver.quit()
                except: pass
            return '', 204

        if isinstance(comment, list):
            if comment_index < len(comment):
                current_comment = comment[comment_index]
                comment_index += 1
            else:
                print_log(naverblog_type, "더 이상 입력할 댓글이 없습니다.")
                return '', 204
        else:
            current_comment = comment

        print(current_comment)

        pyperclip.copy(current_comment)

        try:
            comment_input.send_keys(Keys.CONTROL, 'v')
        except Exception as e:
            if not stop_flag:
                error_queue.put(f"❌ 댓글 복사 붙여넣기 실패: {e}")
                stop_flag = True
                try: driver.quit()
                except: pass
            return '', 204

        random_wait(5, 8, naverblog_type)

        try:
            submit_button = driver.find_element(By.CSS_SELECTOR, 'button.u_cbox_btn_upload')
            driver.execute_script("arguments[0].click();", submit_button)
            print_log(naverblog_type, "댓글을 입력했습니다.")
        except Exception as e:
            if not stop_flag:
                error_queue.put(f"❌ 댓글 등록 버튼 클릭 실패: {e}")
                stop_flag = True
                try: driver.quit()
                except: pass
            return '', 204

        random_wait(5, 8, naverblog_type)

    except Exception as e:
        if not stop_flag:
            error_queue.put(f"❌ 댓글 작성 중 알 수 없는 오류 발생: {e}")
            stop_flag = True
            try: driver.quit()
            except: pass
        return '', 204               



# 네이버 서이추 gpt


@app.route('/naverblog_api_start', methods=['POST'])
def naverblog_api_start():
    global log_messages,stop_flag,user_ids,comment,naver_neighbor_ment,driver,driver_ready
    naver_neighbor_ment = ""
    log_messages = []
    naver_neighbor_ment = request.form.get('naver_api_neighbor_ment')
    stop_flag = False
    driver_ready = False
    
    print(request.form.get('api_search_keword'))
    print(request.form.get('ChatGPT_code'))
    print(request.form.get('api_secret_click'))
    print(request.form.get('target_option'))


    
    naverblog_api_id = request.form.get('naverblog_api_id')

    read_users(naverblog_api_id)
    
    random_wait(3,5,"naverblog_api")
    
    threading.Thread(target=start_driver).start()
    
    

    start_time = time.time()
    while not driver_ready:
        if time.time() - start_time > 30:  
            print_log('naverblog_api', "연결 실패! 다시 시작해주세요.")
            error_queue.put("연결 실패! 크롬설치, 백신, 방화벽을 끄고 재실행 해주세요.")
            try:
                driver.quit()  # 드라이버 종료 시 예외 처리
            except Exception as e:
                print_log('naverblog_api', f"드라이버 종료 중 오류 발생: {e}")
            stop_flag = True  # 프로그램 중단
            return  # 함수 종료
        time.sleep(1)  

    driver.get("https://nid.naver.com/nidlogin.login?mode=form&url=https://www.naver.com/")


    for user in user_ids:
        if stop_flag:
            break  
        login_success = naverlogin(user, "naverblog_api") 
        if login_success:
            keyword_search("naverblog_api",request.form.get('api_search_keword'))
            sort_option_click("naverblog_api",request.form.get('target_option'))
            insert_blog("naverblog_api",int(request.form.get('naver_api_count')),request.form.get('api_neighbor_click'),request.form.get('api_start_time'),request.form.get('api_end_time'))
            if stop_flag == False:
                print_log('naverblog_api',"대기중...")
                random_wait(100,300,"naverblog_api")
            

            
    
    

    if stop_flag == False: 
        driver.quit()
        driver = None
        print_log(type,"작업이 완료 되었습니다.")
   
    

    
    return '', 204


def get_naver_blog_titles():
    global comment, stop_flag

    try:
        blog_elements = driver.find_elements(By.CSS_SELECTOR, 'div.list_search_post')
    except Exception as e:
        if not stop_flag:
            error_queue.put(f"❌ 블로그 리스트 요소를 불러오는 중 오류 발생: {e}")
            stop_flag = True
            try: driver.quit()
            except: pass
        return

    titles = []
    for blog in blog_elements:
        try:
            title_element = blog.find_element(By.CSS_SELECTOR, 'span.title')
            titles.append(title_element.text)
            print(f"블로그 제목: {titles}")
        except Exception as e:
            if not stop_flag:
                error_queue.put(f"❌ 블로그 제목 추출 중 오류 발생: {e}")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

    try:
        generated_comments = call_gpt_api(titles)
        comment = generated_comments
    except Exception as e:
        if not stop_flag:
            error_queue.put(f"❌ ChatGPT API 호출 중 오류 발생: {e}")
            stop_flag = True
            try: driver.quit()
            except: pass
        return

def call_gpt_api(titles):
    # request.form.get('ChatGPT_code') 값으로 OpenAI API 키 설정
    openai.api_key = request.form.get('ChatGPT_code')
    
    # 프롬프트 구성: 각 제목에 따른 한 문장 댓글을 줄바꿈(\n)으로 구분해서 생성하도록 요청
    prompt = (
        "아래 블로그 제목들에 대해 각각 적절한 댓글을 한 문장씩 작성해줘. "
        "각 댓글은 순서대로 줄바꿈으로 구분되어야 해. 제목 목록은 다음과 같아:\n"
    )
    for title in titles:
        prompt += title + "\n"

    print("프롬트!@!!!!!")
    print(prompt)    
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", 
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.7
        )
    except openai.error.AuthenticationError as auth_err:
        print_log("naverblog_api","❌ 인증 실패: API 키 오류")
        return ["[오류] 유효하지 않은 OpenAI API 키입니다."]
    
    except openai.error.OpenAIError as api_err:
        print_log("naverblog_api","❌ OpenAI API 에러 발생:", api_err)
        return [f"[오류] GPT 호출 실패: {str(api_err)}"]
        
    except Exception as e:
        print("openai.ChatCompletion.create 호출 중 오류 발생:", e)
        
    
    # 응답 텍스트에서 댓글들을 추출
    generated_text = response['choices'][0]['message']['content'].strip()
    print("제너레이트 텍스트!!")
    print(generated_text)
    comments = []
    for line in generated_text.splitlines():
        line = line.strip()
        if line:
            comments.append(line)

    print("코멘츠임!!!")
    print(comments)
    
    return comments











# 네이버카페 댓글 시작 



@app.route('/navercafe_comment', methods=['POST'])
def navercafe_comment():
    global contents ,user_ids,log_messages,driver,driver_ready,stop_flag
    print("네이버카페 시작")
    stop_flag = False
    driver_ready = False
    log_messages = []
    
    comment_count = request.form.get('comment_count') 
    navercafe_url= request.form.get('navercafe_url') 
    navercafe_comment_start_time = int(request.form.get('navercafe_comment_start_time') )
    navercafe_comment_end_time = int(request.form.get('navercafe_comment_end_time') )
    navercafe_comment_id = request.form.get('navercafe_comment_id') 
    read_users(navercafe_comment_id)
    print(contents)
    print(user_ids)
    print(comment_count)
    print(navercafe_url)


    kwargs = {}

    # ✅ 내용 확인
    if navercafe_comment_comment:
        print("내용 파일 업로드 확인 ✅")
        kwargs['content_key'] = 'navercafe_comment_comment'
    else:
        print("내용 파일 없음 ❌")

    # ✅ 쓰레드 실행
    threading.Thread(target=start_driver, kwargs=kwargs).start()
    print("랜덤타임시작")
    
    start_time = time.time()
    while not driver_ready:
        if time.time() - start_time > 30:  
            print_log('navercafe_comment', "연결 실패! 다시 시작해주세요.")
            error_queue.put("연결 실패! 크롬설치, 백신, 방화벽을 끄고 재실행 해주세요.")
            try:
                driver.quit()  # 드라이버 종료 시 예외 처리
            except Exception as e:
                print_log('navercafe_comment', f"드라이버 종료 중 오류 발생: {e}")
            stop_flag = True  # 프로그램 중단
            return  # 함수 종료
        time.sleep(1)  

    driver.get("https://nid.naver.com/nidlogin.login?mode=form&url=https://www.naver.com/")


    
    for user in user_ids:
        if stop_flag:
            break  
        login_success = naverlogin(user,"navercafe_comment")
        time.sleep(3)
        if login_success:
            if stop_flag == False:
                print("여기는가지는건지")
                driver.get(navercafe_url)
            insert_cafe()
            if stop_flag == False:
                print_log('navercafe_comment',"대기중...")
                random_time(navercafe_comment_start_time,navercafe_comment_end_time)


    


    if stop_flag == False: 
        driver.quit()
        driver = None
        print_log('navercafe_comment',"작업이 완료 되었습니다.")



    return '', 204



def insert_cafe():
    global stop_flag
    try:
        if stop_flag:
            return False
        print("여기까지는 오냐?? 인설트 케이프")

    
        comment_count = int(request.form.get('comment_count'))
        print(comment_count)
      
       
        # driver.switch_to.frame("cafe_main")
        # print("케이프 메인 들어감")
      

        random_wait(5, 7, 'navercafe_comment')

        try:
            first_atag = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//tbody/tr[not(.//span[text()='공지'])]//a[contains(@class, 'article')]"))
            )
            first_atag.click()
        except Exception as e:
            if not stop_flag:
                error_queue.put(f"❌ 게시글 링크 클릭 중 오류 발생: {e}")
                print("게시글 못찾음")
                stop_flag = True
                try: driver.quit()
                except: pass
            return False

        while comment_count > 0:
            if stop_flag:
                return False

            random_wait(5, 7, 'navercafe_comment')

            try:
                click_naver_comment()
            except Exception as e:
                if not stop_flag:
                    error_queue.put(f"❌ 댓글 작성 중 오류 발생: {e}")
                    stop_flag = True
                    try: driver.quit()
                    except: pass
                return False

            comment_count -= 1

            try:
                click_navercafe_next_button()
            except Exception as e:
                if not stop_flag:
                    error_queue.put(f"❌ 다음 게시글 이동 중 오류 발생: {e}")
                    stop_flag = True
                    try: driver.quit()
                    except: pass
                return False

            print_log('navercafe_comment', f"남은 시행횟수 {comment_count}")
            print(comment_count)

        try:
            driver.delete_all_cookies()
            random_wait(5, 7, 'navercafe_comment')
            driver.get("https://nid.naver.com/nidlogin.login?mode=form&url=https://www.naver.com/")
        except Exception as e:
            if not stop_flag:
                error_queue.put(f"❌ 로그아웃 처리 중 오류 발생: {e}")
                stop_flag = True
                try: driver.quit()
                except: pass
            return False

    except Exception as e:
        if not stop_flag:
            error_queue.put(f"❌ insert_cafe 실행 중 알 수 없는 오류 발생: {e}")
            stop_flag = True
            try: driver.quit()
            except: pass
        return False
        

def click_naver_comment():
    global contents, used_contents, stop_flag

    print("클릭 네이버 코멘트 들어옴")

    try:
        if stop_flag:
            return False
        driver.switch_to.default_content()
        print("기보 프레임돌아옴")
      
        WebDriverWait(driver, 10).until(
                EC.frame_to_be_available_and_switch_to_it((By.NAME, "cafe_main"))
        )
        print("메인 카페 프레임 들어옴")

        try:
            print("댓글찾으러옴")
            comment_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'div.ArticleTool a.button_comment'))
            )
            print("댓글은 찾음")
            comment_button.click()
            print("댓글버튼 클릭함")
        except Exception as e:
            if not stop_flag:
                error_queue.put("❌ 댓글 버튼 클릭 실패.")
                print("댓글 버튼 클릭 실패")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

        print_log('navercafe_comment', "댓글 입력중...")

        try:
            comment_box = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.comment_inbox textarea"))
            )
        except Exception as e:
            if not stop_flag:
                error_queue.put("❌ 댓글 입력창 로딩 실패.")
                print("댓글 입력창 못찾음")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

        available_content = [content for content in contents if content not in used_contents]

        if not available_content:
            print_log('navercafe_comment', "모든 댓글을 다 사용했습니다.")
            stop_flag = True
            return

        select_contents = available_content[0]
        print(select_contents)

        try:
            comment_box.send_keys(select_contents)
        except Exception as e:
            if not stop_flag:
                error_queue.put("❌ 댓글 텍스트 입력 실패.")
                print("여기 의심 100%")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

        random_wait(5, 7, 'navercafe_comment')

        try:
            register_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a.button.btn_register.is_active"))
            )
            register_button.click()
        except Exception as e:
            if not stop_flag:
                error_queue.put("❌ 댓글 등록 버튼 클릭 실패.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

        random_wait(5, 7, 'navercafe_comment')

        used_contents.append(select_contents)

    except Exception as e:
        if not stop_flag:
            error_queue.put("❌ 댓글 입력 중 알 수 없는 오류 발생.")
            stop_flag = True
            try: driver.quit()
            except: pass
        return


def click_navercafe_next_button():
    global stop_flag

    if stop_flag:
        return False

    try:
        print("넥스트 버튼 들어옴")
        print_log('navercafe_comment', "다음 페이지 넘어가는중...")
        random_wait(5, 7, 'navercafe_comment')

        try:
            svg_element = driver.find_element(By.CSS_SELECTOR, "svg.BaseButton__icon.svg-icon.ico-post-top-323232")
            parent_a_tag = svg_element.find_element(By.XPATH, '..')
            driver.execute_script("arguments[0].click();", parent_a_tag)
            print("탑버튼누름")
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 상단으로 이동 버튼 클릭 실패.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

        random_wait(5, 7, 'navercafe_comment')

        try:
            next_button_svg = driver.find_element(By.CSS_SELECTOR, "a.BaseButton.btn_next svg.BaseButton__icon.svg-icon.ico-post-btn-arrow-up-323232")
            parent_a_tag = next_button_svg.find_element(By.XPATH, '..')
            driver.execute_script("arguments[0].click();", parent_a_tag)
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 다음 게시글 이동 버튼 클릭 실패.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

        random_wait(5, 7, 'navercafe_comment')

    except Exception as e:
        if not stop_flag:
            error_queue.put(f"❌ 다음 버튼 처리 중 알 수 없는 오류 발생: {e}")
            stop_flag = True
            try: driver.quit()
            except: pass
        return


# 네이버 카페 글쓰기 시작

@app.route('/navercafe_post', methods=['POST'])
def navercafe_post_start():
    global user_ids, image_folders, navercafe_post_write,navercafe_post_url,log_messages,stop_flag,driver,driver_ready
    
    log_messages = []
    stop_flag = False
    driver_ready = False

    kwargs = {}

    # ✅ 게시글 내용이 있을 경우
    if navercafe_post_write:
        print("게시글 내용 있음 ✅")
        kwargs['post_write'] = True
    else:
        print("게시글 내용 없음 ❌")

    # ✅ 게시글 URL이 있을 경우
    if navercafe_post_url:
        print("게시 대상 URL 있음 ✅")
        kwargs['post_url'] = True
    else:
        print("게시 대상 URL 없음 ❌")

    # ✅ 이미지 폴더가 있을 경우
    if navercafe_post_image_folder:
        print("이미지 폴더 업로드 확인 ✅")
        kwargs['image_key'] = 'navercafe_post_image_folder'
    else:
        print("이미지 폴더 없음 ❌")

    # ✅ 쓰레드 실행
    threading.Thread(target=start_driver, kwargs=kwargs).start()
    print("일단 여기옴")
    navercafe_post_id = request.form.get('navercafe_post_id')
    read_users(navercafe_post_id)
    print(image_folders)
    print(navercafe_post_write)
    print(navercafe_post_url)

    navercafe_post_start_time = int(request.form.get('navercafe_post_start_time'))
    navercafe_post_end_time = int(request.form.get('navercafe_post_end_time'))

    print_log('navercafe_post',"실행중...")

    

    start_time = time.time()
    while not driver_ready:
        if time.time() - start_time > 30:  
            print_log('navercafe_post', "연결 실패! 다시 시작해주세요.")
            error_queue.put("연결 실패! 크롬설치, 백신, 방화벽을 끄고 재실행 해주세요.")
            try:
                driver.quit()  # 드라이버 종료 시 예외 처리
            except Exception as e:
                print_log('navercafe_post', f"드라이버 종료 중 오류 발생: {e}")
            stop_flag = True  # 프로그램 중단
            return  # 함수 종료
        time.sleep(1)  
    

    driver.get("https://nid.naver.com/nidlogin.login?mode=form&url=https://www.naver.com/")

    random_wait(3,5,'navercafe_post')

    for user in user_ids:
        login_success= naverlogin(user, "navercafe_post") 
        time.sleep(4)
        if login_success: 
            for post_url, (title, content) in zip(navercafe_post_url, navercafe_post_write):
                if stop_flag == False:
                    driver.get(post_url)  # 카페 게시판 이동
                click_navercafe_write()  
                navercafe_write(title, content,image_folders)
                if stop_flag == False: 
                    print_log('navercafe_post',"대기중...") 
                    random_time(navercafe_post_start_time,navercafe_post_end_time)


            

    if stop_flag == False: 
        driver.quit()  
        driver = None
        print_log('navercafe_post',"작업이 완료 되었습니다.")  

    return '', 204

def click_navercafe_write():
    global stop_flag
    if stop_flag:
        return False
    try:
        time.sleep(7)
        print("클릭 네이버카페 롸이트 들어옴")

        try:
            cafe_write_button = driver.find_element(By.CSS_SELECTOR, ".cafe-write-btn a._rosRestrict")
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 네이버카페 글쓰기 버튼을 찾지 못했습니다.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

        print("카페 글쓰기 버튼 찾음")
        print_log('navercafe_post', "글쓰러 가는중...")

        try:
            cafe_write_button.click()
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 네이버카페 글쓰기 버튼 클릭 실패.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return

        print("카페 글쓰기 누름")
        random_wait(3, 5, 'navercafe_post')

    except Exception as e:
        if not stop_flag:
            error_queue.put(f"❌ 네이버카페 글쓰기 처리 중 알 수 없는 오류 발생: {e}")
            stop_flag = True
            try: driver.quit()
            except: pass
        return



def navercafe_write(title, content, image_folders):
    global stop_flag
    if stop_flag:
        return False  
    try:
        print("네이버카페 롸이트 들어옴")

        text_parts = split_content(content)
        image_index = 0

        original_window = driver.current_window_handle
        random_wait(3, 5, 'navercafe_post')

        new_window = None
        for handle in driver.window_handles:
            if handle != original_window:
                new_window = handle
                break

        random_wait(3, 5, 'navercafe_post')    

        if new_window:
            try:
                driver.switch_to.window(new_window)
            except Exception as e:
                if not stop_flag:
                    error_queue.put("❌ 새 창으로 전환 실패.")
                    stop_flag = True
                    try: driver.quit()
                    except: pass
                return False

        random_wait(5, 7, 'navercafe_post') 

        for i, text in enumerate(text_parts):
            if stop_flag:
                return False
            try:
                ActionChains(driver).send_keys(text).perform() 
                print_log('navercafe_post', "내용입력중...")
                random_wait(3, 5, 'navercafe_post') 
            except Exception as e:
                if not stop_flag:
                    error_queue.put("❌ 내용 입력 중 오류 발생.")
                    stop_flag = True
                    try: driver.quit()
                    except: pass
                return False

            if i < len(text_parts) - 1:
                if image_index < len(image_folders): 
                    try:
                        navercafe_post_upload_image(image_folders[image_index])  
                        image_index += 1
                    except Exception as e:
                        if not stop_flag:
                            error_queue.put("❌ 이미지 업로드 중 오류 발생.")
                            stop_flag = True
                            try: driver.quit()
                            except: pass
                        return False

        print("내용부터넣음")
        random_wait(5, 7, 'navercafe_post') 

        try:
            title_input = driver.find_element(By.CSS_SELECTOR, 'textarea.textarea_input')
            print("제목찾음")
            title_input.send_keys(title)
            random_wait(3, 5, 'navercafe_post')
            print("제목넣음")
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 제목 입력 실패.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return False

        try:
            submit_button = driver.find_element(By.CLASS_NAME, "BaseButton--skinGreen")
            submit_button.click()
            print("등록버튼누름")
            print_log('navercafe_post', "등록중...")
            random_wait(7, 9, 'navercafe_post')
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 등록 버튼 클릭 실패.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return False

        if stop_flag:
            return False

        try:
            driver.close()
            time.sleep(2)
            if stop_flag:
                return False
            driver.switch_to.window(original_window)
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 창 전환 또는 닫기 중 오류 발생.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return False

    except Exception as e:
        if not stop_flag:
            error_queue.put(f"❌ 네이버카페 글 작성 중 알 수 없는 오류 발생: {e}")
            stop_flag = True
            try: driver.quit()
            except: pass
        return False



def split_content(content):
    parts = content.split("(사진)")  
    text_parts = [part.strip() for part in parts if part.strip() or part == '']   
    print(text_parts)
    return text_parts 



def navercafe_post_upload_image(image_folder):
    global stop_flag
    if stop_flag:
        return False

    try:
        print("업로드 이미지 들어옴")
        print(image_folder)
        random_wait(3, 5, 'navercafe_post')

        try:
            image_button = driver.find_element(By.CLASS_NAME, "se-image-toolbar-button")
            image_button.click()
            print_log('navercafe_post', "이미지 추가중...")
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 이미지 버튼을 찾거나 클릭하는 데 실패했습니다.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return False

        random_wait(2, 4, 'navercafe_post')

        try:
            input_field = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
            )
            input_field.send_keys(image_folder)
            print_log('navercafe_post', "이미지 추가 완료")
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 파일 입력 필드를 찾거나 이미지 업로드에 실패했습니다.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return False

        random_wait(3, 5, 'navercafe_post')

        try:
            for window in gw.getWindowsWithTitle("열기") + gw.getWindowsWithTitle("Open"):
                print(f"탐색기 창 찾음: {window.title}")
                time.sleep(2)
                window.close()
                print("창닫음")
                random_wait(3, 5, 'navercafe_post')
        except Exception:
            if not stop_flag:
                error_queue.put("❌ 탐색기 창 종료 중 오류 발생.")
                stop_flag = True
                try: driver.quit()
                except: pass
            return False

    except Exception as e:
        if not stop_flag:
            error_queue.put(f"❌ 이미지 업로드 중 알 수 없는 오류 발생: {e}")
            stop_flag = True
            try: driver.quit()
            except: pass
        return False

    

#카카오 시작 
@app.route('/pause', methods=['POST'])
def pause_macro():
    global pause
    pause = not pause  # 현재 상태의 반대로 전환

    print_log("kakao_send",f"{' 일시정지' if pause else '재개'} 상태로 전환됨.")
    return {'pause': pause} 


selected_chatting_list = []
chat_windows = []

pause =False

@app.route('/kakaotalk_send_form', methods=['POST'])
def kakaotalk_send_form():
    global selected_chatting_list,stop_flag,log_messages,kakao_morningmessage,kakao_nightmessage
    
    stop_flag = False
    log_messages =[]
    selected_chatting_list =[]
    # 선택한 채팅방 가져오기
    for key in request.form:
        if key.startswith('select_chatting_'):
            selected_chatting_list.extend(request.form.getlist(key))

    # 폼 데이터 가져오기 (문자열 → 정수 변환)
    night_start = request.form.get('night_start')
    night_end = request.form.get('night_end')
    night_messages = kakao_nightmessage
    morning_messages = kakao_morningmessage
    print(night_messages)
    print("으아아아악")
    
    night_interval = int(request.form.get('night_next_interval', 0) or 0)
    morning_interval = int(request.form.get('morning_interval', 0) or 0)
    night_min_interval = int(request.form.get('night_min_interval', 0) or 0)
    night_max_interval = int(request.form.get('night_max_interval', 0) or 0)
    morning_min_interval = int(request.form.get('morning_min_interval', 0) or 0)
    morning_max_interval = int(request.form.get('morning_max_interval', 0) or 0)

    # 데이터 출력 (테스트용)
    print(f"밤 시작 시간: {night_start}")
    print(f"밤 종료 시간: {night_end}")
    print(f"밤 메시지: {night_messages}")
    print(f"낮 메시지: {morning_messages}")
    print(f"밤 대기시간: {night_interval}")
    print(f"낮 대기시간: {morning_interval}")
    print(f"밤 최소 대기시간: {night_min_interval}")
    print(f"밤 최대 대기시간: {night_max_interval}")
    print(f"낮 최소 대기시간: {morning_min_interval}")
    print(f"낮 최대 대기시간: {morning_max_interval}")

    def is_night_time():
        """밤 시간인지 확인"""
        now = datetime.now().time()
        start_time = datetime.strptime(night_start, "%H:%M").time()
        end_time = datetime.strptime(night_end, "%H:%M").time()

        if start_time < end_time:
            return start_time <= now <= end_time  # ✅ 같은 날
        else:
            return now >= start_time or now <= end_time  # ✅ 다음 날 포함


    def send_messages():
        global stop_flag, pause
        cycle_count = 0 

        while True:
            if stop_flag:
                return
            is_night_check = ""
            while pause:
                time.sleep(1)
                print("정지중")
                
            random_wait(4,7,"kakao_send")
            try:
                if is_night_time():
                    message = night_messages
                    interval = night_interval
                    is_night_check ="night"
                    print_log("kakao_send","밤 설정으로 실행중...")
                    
                else:
                    message = morning_messages
                    interval = morning_interval
                    is_night_check ="morning"
                    print_log("kakao_send","낮 설정으로 실행중...")

                if not message:
                    print_log("kakao_send"," 메시지가 입력되지 않았습니다. 전송을 중단합니다.")
                    return
                if not selected_chatting_list:
                    print_log("kakao_send"," 선택된 채팅방이 없습니다. 전송을 중단합니다.")
                    return

                for chat_title in selected_chatting_list:
                    if stop_flag:
                        print("🛑 중단 신호 감지. 루프 종료.")
                        return
                    while pause:
                        print(f"⏸️ 일시정지 상태 - '{chat_title}' 전송 대기 중...")
                        time.sleep(1)

                    chat_window = gw.getWindowsWithTitle(chat_title)
                    if not chat_window:
                        print(f"⚠️ 채팅방 '{chat_title}'을 찾을 수 없습니다. 건너뜁니다.")
                        continue
                    
                    random_wait(5,7,"kakao_send")
                    chat_window[0].activate()  # 창 활성화
                    

                    pyperclip.copy(message)
                    pag.hotkey("ctrl", "v")
                    pag.press("enter")
                    print_log("kakao_send",f" 채팅방 '{chat_title}' 메시지 전송 완료.")

                    if stop_flag:
                        print("🛑 중단 신호 감지. 전송 중단.")
                        return
                    while pause:
                        print(f"⏸️ 일시정지 상태 - 다음 채팅까지 대기 중...")
                        time.sleep(1)

                    print_log("kakao_send",f"{interval}초 대기중...")
                    time.sleep(interval)
                    

                cycle_count += 1
                print_log("kakao_send",f" 사이클 {cycle_count}회 완료")


                if is_night_check == "night":
                    print_log("kakao_send", f"{night_min_interval}분 ~ {night_max_interval}분 사이 랜덤 대기 중...")
                    random_time(night_min_interval,night_max_interval)
                    
                else:
                    print_log("kakao_send", f"{morning_min_interval}분 ~ {morning_max_interval}분 사이 랜덤 대기 중...")
                    random_time(morning_min_interval, morning_max_interval)
                    
                
            except Exception as e:
                print(f"❌ 오류 발생: {str(e)}")
                time.sleep(300)  # 오류 발생 시 5분 대기 후 재시작

    # ✅ 스레드로 실행하여 Flask 응답 차단 방지
    threading.Thread(target=send_messages, daemon=True).start()

    return '', 204
    



#  워드프레스 블로그 게시물  시작

def wait_for_login_by_url(driver, expected_url_part='home', timeout=900):
    print_log("wordpress", f"로그인 대기 중... 최대 {timeout}초")
    start_time = time.time()

    while time.time() - start_time < timeout:
        current_url = driver.current_url
        if expected_url_part in current_url:
            print_log("wordpress", "로그인완료")
            return True
        time.sleep(1)

    return False

@app.route('/wordpress_post', methods=['POST'])   
def wordpress_post_start():
    print("워드프레스왔따!")
    
    global log_messages,stop_flag,hashtags,contents,image_folders
    stop_flag = False
    used_images = []

   
    print(request.form.get('wordpress_post_start_time'))
    print(request.form.get('wordpress_post_end_time'))
    print(hashtags)
    print(contents)
    print(image_folders)

    wordpress_post_count = int(request.form.get('wordpress_post_count'))
    
    wordpress_post_image_count = int(request.form.get('wordpress_post_image_count') or 0)

    print(wordpress_post_count)

    print(wordpress_post_image_count)

    image_index =0
    log_messages = []

    time.sleep(3)

    print_log('wordpress_post',"작동중...")

    kwargs = {}

    # ✅ 제목(해시태그) 확인
    if wordpress_post_title:
        print("제목(태그) 파일 업로드 확인 ✅")
        kwargs['hashtag_key'] = 'wordpress_post_title'
    else:
        print("제목(태그) 없음 ❌")

    # ✅ 본문 내용 확인
    if wordpress_post_content:
        print("본문 내용 파일 업로드 확인 ✅")
        kwargs['content_key'] = 'wordpress_post_content'
    else:
        print("본문 내용 없음 ❌")

    # ✅ 이미지 폴더 확인
    if wordpress_post_image_folder:
        print("이미지 폴더 업로드 확인 ✅")
        kwargs['image_key'] = 'wordpress_post_image_folder'
    else:
        print("이미지 폴더 없음 ❌")

    # ✅ 드라이버 실행
    threading.Thread(target=start_driver, kwargs=kwargs).start()

    start_time = time.time()
    while driver is None:
        if time.time() - start_time > 30:  
            print_log('wordpress',"연결 실패! 다시 시작해주세요.")
        time.sleep(1)  

    driver.get("https://wordpress.com/log-in/ko")
    

    if not wait_for_login_by_url(driver, expected_url_part="home", timeout=900):
        print_log("wordpress", "로그인 실패 또는 시간 초과되었습니다.")
        driver.quit()
        return '', 204  

    wordpress_post_insert()
    
    for i in range(wordpress_post_count):
        wordpress_post_send_title(hashtags[i])
        wordpress_post_send_content(contents[i])
        time.sleep(100)
        

        

    if stop_flag == False: 
        driver.quit()

   
    print_log('wordpress_post',"작업이 완료 되었습니다.")


    return '', 204



def wordpress_post_insert():
    try:
        menu_button = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, "//a[contains(@class, 'sidebar__heading') and contains(., '글')]"))
                        )
        menu_button.click()


        add_post_button = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.page-title-action"))
                            )
        add_post_button.click()


        try:
            close_button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[aria-label="닫기"]'))
            )
            close_button.click()
            
        except :
            print("닫기버튼없음")

        random_wait(5,7,"wordpress_post")
    except:
        print("글쓰기 못들어감")




def wordpress_post_send_title(title):
    try:
        block_button = WebDriverWait(driver, 15).until(
           EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='블록 삽입기']"))
        )
        block_button.click()
        # 이거 editor-cavnos 밖에있음 


        WebDriverWait(driver, 10).until(
           EC.frame_to_be_available_and_switch_to_it((By.NAME, "editor-canvas"))
        )

        pyperclip.copy(title)

        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        random_wait(3,5,"wordpress_post")
    except:
        print("제목 쓰기 실패")
    


def wordpress_post_send_content(content):
    global image_folders
    image_count = 0
    # (사진)을 기준으로 내용 분리
    parts = content.split('(사진)')
    

    for i, part in enumerate(parts):
        print(f"for문 들어옴, {i+1}번째 반복 시작")
        
        if i == 0:
            # 첫 번째 반복: 초기 포커스를 위해 'appender' 블록을 클릭
            starter_p = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "p.block-editor-default-block-appender__content"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", starter_p)
            starter_p.click()
            print("starter_p 클릭 완료 (초기 블록 선택)")
            
            # 첫 번째 분리 요소가 공백이면 -> 사진 업로드, 아니면 텍스트 붙여넣기
            if not part.strip():  # 공백이면 이미지 업로드
                wordpress_post_upload_image(image_folders[image_count])
                image_count += 1 
            else:  # 공백이 아니면 텍스트 붙여넣기
                pyperclip.copy(part)
                ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                print_log("wordpress_post", f"1번째 문단 입력 완료: {part}")
               
        else:
            
            if part.strip():
                wordpress_post_upload_image(image_folders[image_count])
                image_count += 1 
            else:
                pyperclip.copy(part)
                ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                print_log("wordpress_post", f"{i+1}번째 문단 입력 완료: {part}")
                

        # 마지막 분리 요소가 아니라면 ENTER로 새 문단 생성
        if i < len(parts) - 1:
            print("ENTER 누르기 전, 새 문단 생성 시도")
            # stale element 방지를 위해 새로 찾기 (현재 포커스된 문단)
            selected_p = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "p.block-editor-rich-text__editable.is-selected[contenteditable='true']")
                )
            )
            selected_p.send_keys(Keys.ENTER)
            print_log("wordpress_post", f"{i+1}번째 문단 입력 후 ENTER 눌러 새 문단 생성")





def wordpress_post_upload_image(image_folder):
    print("이미지 들어옴 ")
    time.sleep(2)
    image_button = driver.find_element_by_id(":r2r:")

    print("이미지버튼 찾음")
    image_button.click()  
    # 이거 이후에 다시 editor-canvos인가 거기로 가서 올리기 눌러야함

    driver.switch_to.default_content()
    print("frame전환")

    button = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='블록 추가']"))
    )
    print("블록 버튼 찾음")
    button.click()
    time.sleep(10)

    WebDriverWait(driver, 10).until(
        EC.frame_to_be_available_and_switch_to_it((By.NAME, "editor-canvas"))
    )
    print("또 프레임전환...")

    time.sleep(5)

    image_button = driver.find_element(By.XPATH, "//button[.//span[text()='이미지']]")
    print("이미지 버튼찾음")
    image_button.click()
    print("이미지 버튼 클릭함")

    time.sleep(3)

    driver.switch_to.default_content()
    print("frame전환")

    time.sleep(4)
    upload_button = driver.find_element(By.CLASS_NAME, "block-editor-media-placeholder__upload-button")
    print("올리기버튼 찾음")
    upload_button.click()
    print("올리기버튼 클릭")
    time.sleep(3)

    file_input = driver.find_element(By.CSS_SELECTOR, 'input[type="file"]')
    time.sleep(2)
    print("이미지업로드함")
    file_input.send_keys(image_folder)

    for window in gw.getWindowsWithTitle("열기") + gw.getWindowsWithTitle("Open"):
                    print(f"탐색기 창 찾음: {window.title}")
                    time.sleep(2)
                    window.close()

                    
    print("창닫기끝")


    figures = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "figure.wp-block-image"))
    )
    print("피거스 찾음")

    last_figure = figures[-1]
    # figure 요소의 크기를 가져옴
    fig_size = last_figure.size
    # figure의 중앙 아래쪽, 예를 들어 높이 + 20픽셀 정도 아래에 클릭하도록 오프셋 계산
    x_offset = fig_size['width'] / 2
    y_offset = fig_size['height'] + 20
    
    # figure 요소를 기준으로 오프셋 위치에 마우스 이동 후 클릭
    ActionChains(driver).move_to_element_with_offset(last_figure, x_offset, y_offset).click().perform()
    print_log("wordpress_post", "figure 바로 아래 클릭 완료, 새 문단 생성 시도")





    WebDriverWait(driver, 10).until(
        EC.frame_to_be_available_and_switch_to_it((By.NAME, "editor-canvas"))
    )

    print("프레임전환?")


    new_appender = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "p.block-editor-default-block-appender__content"))
    )
    driver.execute_script("arguments[0].scrollIntoView(true);", new_appender)
    new_appender.click()

    print("먼지기억안남")


    print("클릭함")
    time.sleep(100)

   






def find_free_port(start_port=5000, max_tries=10):
    """사용 가능한 포트를 찾아서 반환하는 함수"""
    port = start_port
    while max_tries > 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            result = s.connect_ex(('127.0.0.1', port))  # 포트에 연결을 시도
            if result != 0:  
                return port  
            port += 1  
            max_tries -= 1
    raise Exception("No available port found")


# Flask 서버 실행 함수
def run_flask(port):
   app.run(debug=True, use_reloader=False, host='0.0.0.0', port=port)
   
  

# PyWebView 실행 함수
def create_webview(port):
    # PyWebView로 웹 페이지를 띄울 때 창 크기를 설정
    webview.create_window('CEO Portal 프로그램', f'http://127.0.0.1:{port}/', width=1920, height=1080)
    webview.create_window('CEO Portal', 'https://ceoportal.co.kr/',  width=1200, height=800)
    
    # 웹 페이지 표시
    webview.start()
    
# Flask 서버 종료 함수
def stop_flask_server():
    # Flask 서버 종료 시그널을 보내기
    print("flask 서버종료")
    os.kill(os.getpid(), signal.SIGINT)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          
if __name__ == '__main__':
    # Flask를 백그라운드에서 실행
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        free_port = find_free_port(start_port=5000)
        print(f"사용 가능한 포트 발견: {free_port}")
        
        # Flask를 백그라운드에서 실행
        flask_thread = threading.Thread(target=run_flask, args=(free_port,))
        flask_thread.daemon = True  # 백그라운드에서 실행되도록 설정
        flask_thread.start()
        
        # Flask 서버가 실행될 때까지 잠시 대기
        time.sleep(3)  # 서버 시작에 충분한 시간을 둡니다
        
        try:
            # PyWebView 실행
            create_webview(free_port)
        except Exception as e:
            print(f"Error while displaying webview: {e}")
        finally:
            # 웹뷰 창이 닫히면 Flask 서버를 종료``
            stop_flask_server()
    except Exception as e:
        print("포트실패")
