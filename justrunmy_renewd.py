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

ACCOUNTS_STR = os.environ.get("ACCOUNTS")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID")

EMAIL = ""
PASSWORD = ""
DYNAMIC_APP_NAME = "未知应用"

if not ACCOUNTS_STR:
    print("❌ 致命错误：未找到 ACCOUNTS 环境变量！")
    sys.exit(1)

def send_tg_message(status_icon, status_text, time_left):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)
    text = (
        f"👤 账号: {EMAIL}\n"
        f"🖥 {DYNAMIC_APP_NAME}\n"
        f"{status_icon} {status_text}\n"
        f"⏱️ 剩余: {time_left}\n"
        f"时间: {current_time_str}"
    )
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
    except:
        pass
        _EXPAND_JS = """
(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (!ts) return 'no-turnstile';
    var el = ts;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var s = window.getComputedStyle(el);
        if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden')
            el.style.overflow = 'visible';
        el.style.minWidth = 'max-content';
    }
    document.querySelectorAll('iframe').forEach(function(f){
        if (f.src && f.src.includes('challenges.cloudflare.com')) {
            f.style.width = '300px'; f.style.height = '65px';
            f.style.minWidth = '300px';
            f.style.visibility = 'visible'; f.style.opacity = '1';
        }
    });
    return 'done';
})()
"""

_EXISTS_JS = """
(function(){
    return document.querySelector('input[name="cf-turnstile-response"]') !== null;
})()
"""

_SOLVED_JS = """
(function(){
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    return !!(i && i.value && i.value.length > 20);
})()
"""

_COORDS_JS = """
(function(){
    var iframes = document.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i++) {
        var src = iframes[i].src || '';
        if (src.includes('cloudflare') || src.includes('turnstile') || src.includes('challenges')) {
            var r = iframes[i].getBoundingClientRect();
            if (r.width > 0 && r.height > 0)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
        }
    }
    var inp = document.querySelector('input[name="cf-turnstile-response"]');
    if (inp) {
        var p = inp.parentElement;
        for (var j = 0; j < 5; j++) {
            if (!p) break;
            var r = p.getBoundingClientRect();
            if (r.width > 100 && r.height > 30)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
            p = p.parentElement;
        }
    }
    return null;
})()
"""

_WININFO_JS = """
(function(){
    return {
        sx: window.screenX || 0,
        sy: window.screenY || 0,
        oh: window.outerHeight,
        ih: window.innerHeight
    };
})()
"""
def js_fill_input(sb, selector: str, text: str):
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    sb.execute_script(f"""
    (function(){{
        var el = document.querySelector('{selector}');
        if (!el) return;
        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        if (setter) {{ setter.call(el, "{safe_text}"); }} else {{ el.value = "{safe_text}"; }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }})()
    """)

def _activate_window():
    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls], capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]], timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception: pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"], timeout=3, stderr=subprocess.DEVNULL)
    except Exception: pass

def _xdotool_click(x: int, y: int):
    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
    except Exception:
        os.system(f"xdotool mousemove {x} {y} click 1 2>/dev/null")

def _click_turnstile(sb):
    try: coords = sb.execute_script(_COORDS_JS)
    except Exception: return
    if not coords: return
    try: wi = sb.execute_script(_WININFO_JS)
    except Exception: wi = {"sx": 0, "sy": 0, "oh": 800, "ih": 768}
    bar = wi["oh"] - wi["ih"]
    _xdotool_click(coords["cx"] + wi["sx"], coords["cy"] + wi["sy"] + bar)

def handle_turnstile(sb) -> bool:
    time.sleep(2)
    if sb.execute_script(_SOLVED_JS): return True
    for _ in range(3):
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.5)
    for attempt in range(6):
        if sb.execute_script(_SOLVED_JS): return True
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.3)
        _click_turnstile(sb)
        for _ in range(8):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS): return True
    return False
    def login(sb) -> bool:
        print(f"🌐 打开登录页面: {LOGIN_URL}")
        sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
        time.sleep(4)

        try: sb.wait_for_element('input[name="Email"]', timeout=15)
        except Exception:
            sb.save_screenshot("login_load_fail.png")
            return False

    try:
        for btn in sb.find_elements("button"):
            if "Accept" in (btn.text or ""):
                btn.click()
                time.sleep(0.5)
                break
    except Exception: pass

    js_fill_input(sb, 'input[name="Email"]', EMAIL)
    time.sleep(0.3)
    js_fill_input(sb, 'input[name="Password"]', PASSWORD)
    time.sleep(1)

    if sb.execute_script(_EXISTS_JS):
        if not handle_turnstile(sb):
            sb.save_screenshot("login_turnstile_fail.png")
            return False

    sb.press_keys('input[name="Password"]', '\n')
    for _ in range(12):
        time.sleep(1)
        if sb.get_current_url().split('?')[0].lower() != LOGIN_URL.lower(): break

    if sb.get_current_url().split('?')[0].lower() != LOGIN_URL.lower(): return True
    sb.save_screenshot("login_failed.png")
    return False
    def main():
    global EMAIL, PASSWORD
    
    pairs = [p.split("#") for p in ACCOUNTS_STR.split(",") if "#" in p]
    use_proxy = os.environ.get("USE_PROXY", "false").lower() == "true"
    sb_kwargs = {"uc": True, "test": True, "headless": False}
    
    if use_proxy:
        sb_kwargs["proxy"] = "http://127.0.0.1:8080"

    for email_str, pwd_str in pairs:
        EMAIL = email_str.strip()
        PASSWORD = pwd_str.strip()
        
        print(f"\n▶️ 开始处理账号: {EMAIL}")
        
        with SB(**sb_kwargs) as sb:
            try:
                sb.open("https://api.ipify.org/?format=json")
                print(f"🌐 IP: {sb.get_text('body')}")
            except Exception: pass

            if login(sb):
                renew(sb)
            else:
                print(f"\n❌ {EMAIL} 登录环节失败。")
                send_tg_message("❌", "登录失败", "未知")
                
        print(f"🏁 冷却 15 秒...")
        time.sleep(15)

if __name__ == "__main__":
    main()
    
