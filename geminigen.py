#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import subprocess
import requests
from seleniumbase import SB

LOGIN_URL = "https://geminigen.ai/auth/login"

# ============================================================
#  环境变量与全局变量
# ============================================================
EMAIL        = os.environ.get("GEMINIGEN_EMAIL")
PASSWORD     = os.environ.get("GEMINIGEN_PASSWORD")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID")

if not EMAIL or not PASSWORD:
    print("❌ 致命错误：未找到账号密码")
    sys.exit(1)


# ============================================================
#  页面注入脚本 (完全照搬 renew)
# ============================================================
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

# ============================================================
#  底层输入工具 (完全照搬 renew)
# ============================================================
def js_fill_input(sb, selector: str, text: str):
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    sb.execute_script(f"""
    (function(){{
        var el = document.querySelector('{selector}');
        if (!el) return;
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        if (nativeInputValueSetter) {{
            nativeInputValueSetter.call(el, "{safe_text}");
        }} else {{
            el.value = "{safe_text}";
        }}
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
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"], timeout=3, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _xdotool_click(x: int, y: int):
    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
    except Exception:
        os.system(f"xdotool mousemove {x} {y} click 1 2>/dev/null")

def _click_turnstile(sb):
    try:
        coords = sb.execute_script(_COORDS_JS)
    except Exception as e:
        print(f"  ⚠️ 获取 Turnstile 坐标失败: {e}")
        return
    if not coords:
        print("  ⚠️ 无法定位 Turnstile 坐标")
        return
    try:
        wi = sb.execute_script(_WININFO_JS)
    except Exception:
        wi = {"sx": 0, "sy": 0, "oh": 800, "ih": 768}
        
    bar = wi["oh"] - wi["ih"]
    if bar < 0 or bar > 200:
        bar = 135 # 猜测的浏览器顶部系统栏加地址栏高度
        
    ax  = coords["cx"] + wi["sx"]
    ay  = coords["cy"] + wi["sy"] + bar
    print(f"  🖱️ 物理级点击 Turnstile ({ax}, {ay})")
    _xdotool_click(ax, ay)

def handle_turnstile(sb) -> bool:
    print("🔍 处理 Cloudflare Turnstile 验证...")
    time.sleep(2)
    
    if sb.execute_script(_SOLVED_JS):
        print("  ✅ 已静默通过")
        return True

    for _ in range(3):
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.5)

    for attempt in range(6):
        if sb.execute_script(_SOLVED_JS):
            print(f"  ✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
            return True
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.3)
        
        _click_turnstile(sb)
        
        for _ in range(8):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS):
                print(f"  ✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
                return True
        print(f"  ⚠️ 第 {attempt + 1} 次未通过，重试...")

    print("  ❌ Turnstile 6 次均失败")
    return False

# ============================================================
#  账户登录模块 (100% 照搬 renew 的结构逻辑)
# ============================================================
def login(sb) -> bool:
    print(f"🌐 打开登录页面: {LOGIN_URL}")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
    time.sleep(4)

    # 查盾
    if sb.execute_script(_EXISTS_JS):
        if not handle_turnstile(sb):
            print("❌ 进入前的界面的 Turnstile 验证可能未通过")

    # 提取出的输入框元素
    email_selector = 'input[name="username"]'
    password_selector = 'input[name="password"]'
    
    try:
        sb.wait_for_element(email_selector, timeout=20)
    except Exception:
        print("❌ 页面未加载出登录表单")
        sb.save_screenshot("geminigen_login_load_fail.png")
        return False

    print(f"📧 填写邮箱...")
    js_fill_input(sb, email_selector, EMAIL)
    time.sleep(0.5)
    
    print("🔑 填写密码...")
    js_fill_input(sb, password_selector, PASSWORD)
    time.sleep(1)

    # 看看填写账号密码的时候有没有跳出盾
    if sb.execute_script(_EXISTS_JS):
        print("🛡️ 检测到登录界面的 CF 验证...")
        if not handle_turnstile(sb):
            print("❌ 登录界面的 Turnstile 验证可能未通过")
            sb.save_screenshot("geminigen_login_turnstile_fail.png")

    print("🖱️ 敲击回车提交表单...")
    sb.press_keys(password_selector, '\n')

    print("⏳ 等待登录跳转...")
    for _ in range(12):
        time.sleep(1)
        if sb.get_current_url().split('?')[0].lower() != LOGIN_URL.lower():
            break

    if sb.get_current_url().split('?')[0].lower() != LOGIN_URL.lower():
        print("✅ 登录成功！")
        
        # 去除弹窗
        print("🔍 检查是否存在迎新/更新弹窗...")
        time.sleep(3) # 等待弹窗加载
        try:
            # 优先点击“不再显示”
            if sb.is_element_visible('button:contains("不再显示")'):
                print("🖱️ 点击【不再显示】关闭弹窗")
                sb.click('button:contains("不再显示")')
                time.sleep(1)
            elif sb.is_element_visible('span.i-heroicons\\:x-mark-20-solid'):
                # 备用：点击 X 关闭按钮
                print("🖱️ 点击【X】关闭弹窗")
                sb.click('span.i-heroicons\\:x-mark-20-solid')
                time.sleep(1)
            else:
                print("ℹ️ 未检测到弹窗，进入主流程")
        except Exception as e:
            print(f"ℹ️ 弹窗处理跳过或未找到: {e}")
        
        return True
        
    print("❌ 登录失败，页面没有跳转。")
    sb.save_screenshot("geminigen_login_failed.png")
    return False

# ============================================================
#  脚本执行入口
# ============================================================
def main():
    print("=" * 50)
    print("   GeminiGen 自动登录脚本 (Renew Mode)")
    print("=" * 50)
    
    sb_kwargs = {"uc": True, "test": True, "headless": False}
    with SB(**sb_kwargs) as sb:
        print("✅ 浏览器已启动")
        if login(sb):
            print("🎉 登录完成。")
        else:
            print("\n❌ 登录测试失败。")

if __name__ == "__main__":
    main()
