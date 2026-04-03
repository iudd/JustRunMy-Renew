#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import subprocess
import requests
from seleniumbase import SB

LOGIN_URL = "https://justrunmy.app/id/Account/Login"
DOMAIN    = "justrunmy.app"

# ============================================================
# 1. 环境变量解析 (支持多账号)
# ============================================================
ACCOUNTS_STR = os.environ.get("ACCOUNTS")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID")

# 全局变量，用于动态保存网页上抓取到的应用名称
DYNAMIC_APP_NAME = "未知应用"

# ============================================================
# 2. Telegram 通知函数
# ============================================================
def send_tg_message(status_icon, status_text, time_left, account_email):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)
    text = (
        f"👤 账号: {account_email}\n"
        f"🖥 {DYNAMIC_APP_NAME}\n"
        f"{status_icon} {status_text}\n"
        f"⏱️ 剩余: {time_left}\n"
        f"时间: {current_time_str}"
    )
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
    except: pass
    
# ============================================================
# 3. 页面注入与验证码处理脚本
# ============================================================
_EXPAND_JS = """(function() { var ts = document.querySelector('input[name="cf-turnstile-response"]'); if (!ts) return 'no-turnstile'; var el = ts; for (var i = 0; i < 20; i++) { el = el.parentElement; if (!el) break; var s = window.getComputedStyle(el); if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden') el.style.overflow = 'visible'; el.style.minWidth = 'max-content'; } document.querySelectorAll('iframe').forEach(function(f){ if (f.src && f.src.includes('challenges.cloudflare.com')) { f.style.width = '300px'; f.style.height = '65px'; f.style.minWidth = '300px'; f.style.visibility = 'visible'; f.style.opacity = '1'; } }); return 'done'; })()"""
_EXISTS_JS = """(function(){ return document.querySelector('input[name="cf-turnstile-response"]') !== null; })()"""
_SOLVED_JS = """(function(){ var i = document.querySelector('input[name="cf-turnstile-response"]'); return !!(i && i.value && i.value.length > 20); })()"""
_COORDS_JS = """(function(){ var iframes = document.querySelectorAll('iframe'); for (var i = 0; i < iframes.length; i++) { var src = iframes[i].src || ''; if (src.includes('cloudflare') || src.includes('turnstile') || src.includes('challenges')) { var r = iframes[i].getBoundingClientRect(); if (r.width > 0 && r.height > 0) return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)}; } } var inp = document.querySelector('input[name="cf-turnstile-response"]'); if (inp) { var p = inp.parentElement; for (var j = 0; j < 5; j++) { if (!p) break; var r = p.getBoundingClientRect(); if (r.width > 100 && r.height > 30) return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)}; p = p.parentElement; } } return null; })()"""
_WININFO_JS = """(function(){ return { sx: window.screenX || 0, sy: window.screenY || 0, oh: window.outerHeight, ih: window.innerHeight }; })()"""

def js_fill_input(sb, selector, text):
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    sb.execute_script(f"""(function(){{ var el = document.querySelector('{selector}'); if (!el) return; var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set; if (setter) {{ setter.call(el, "{safe_text}"); }} else {{ el.value = "{safe_text}"; }} el.dispatchEvent(new Event('input', {{ bubbles: true }})); el.dispatchEvent(new Event('change', {{ bubbles: true }})); }})()""")

def _xdotool_click(x, y):
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], timeout=3)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2)
    except: pass

def handle_turnstile(sb):
    time.sleep(2)
    if sb.execute_script(_SOLVED_JS): return True
    for attempt in range(6):
        try: sb.execute_script(_EXPAND_JS)
        except: pass
        coords = sb.execute_script(_COORDS_JS)
        if coords:
            wi = sb.execute_script(_WININFO_JS) or {"sx":0, "sy":0, "oh":800, "ih":768}
            _xdotool_click(coords["cx"] + wi["sx"], coords["cy"] + wi["sy"] + (wi["oh"] - wi["ih"]))
        for _ in range(8):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS): return True
    return False

    
# ============================================================
# 4. 核心业务逻辑 (登录 + 续期)
# ============================================================
def login(sb, email, password):
    print(f"🌐 正在处理账号: {email}")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
    try:
        sb.wait_for_element('input[name="Email"]', timeout=15)
        js_fill_input(sb, 'input[name="Email"]', email)
        js_fill_input(sb, 'input[name="Password"]', password)
        if sb.execute_script(_EXISTS_JS): handle_turnstile(sb)
        sb.press_keys('input[name="Password"]', '\n')
        time.sleep(5)
        return sb.get_current_url().lower() != LOGIN_URL.lower()
    except: return False

def renew(sb, email):
    global DYNAMIC_APP_NAME
    sb.open("https://justrunmy.app/panel")
    try:
        sb.wait_for_element('h3.font-semibold', timeout=10)
        DYNAMIC_APP_NAME = sb.get_text('h3.font-semibold')
        sb.click('h3.font-semibold')
        time.sleep(2)
        sb.click('button.bg-amber-500.rounded-lg')
        if sb.execute_script(_EXISTS_JS): handle_turnstile(sb)
        sb.click('button:contains("Just Reset")')
        time.sleep(5)
        sb.refresh()
        timer_text = sb.get_text('span.font-mono.text-xl')
        print(f"✅ {email} 续期成功，剩余时间: {timer_text}")
        send_tg_message("✅", "续期完成", timer_text, email)
    except Exception as e:
        print(f"❌ {email} 续期过程中出错")
        send_tg_message("❌", f"续期失败: {str(e)}", "未知", email)

        # ============================================================
# 5. 程序入口
# ============================================================
def main():
    if not ACCOUNTS_STR:
        print("❌ 致命错误：未在 GitHub Secrets 中发现 ACCOUNTS 变量")
        return

    # 解析格式：邮箱1#密码1,邮箱2#密码2
    pairs = [p.split("#") for p in ACCOUNTS_STR.split(",") if "#" in p]
    print(f"🚀 检测到 {len(pairs)} 个账号，开始排队执行...")

    use_proxy = os.environ.get("USE_PROXY", "false").lower() == "true"
    sb_kwargs = {"uc": True, "test": True, "headless": False}
    if use_proxy: sb_kwargs["proxy"] = "http://127.0.0.1:8080"

    for email, password in pairs:
        email, password = email.strip(), password.strip()
        # 每个账号使用独立的浏览器实例，彻底隔离环境
        with SB(**sb_kwargs) as sb:
            if login(sb, email, password):
                renew(sb, email)
            else:
                print(f"❌ {email} 登录失败")
                send_tg_message("❌", "登录失败", "N/A", email)
        
        print(f"🏁 账号 {email} 处理完毕，冷却 15 秒...")
        time.sleep(15)

if __name__ == "__main__":
    main()

    

        

