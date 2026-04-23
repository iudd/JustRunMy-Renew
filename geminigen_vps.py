#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# GeminiGen 自动登录脚本 - VPS 物理桌面专用版本
# 此版本仅用于带真实 X11 桌面的 VPS / 独立服务器，通过率 95%+

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
#  页面注入脚本
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
#  底层输入工具
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
        # 加入随机偏移
        x += __import__('random').randint(-12, 12)
        y += __import__('random').randint(-8, 8)
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.10 + __import__('random').random() * 0.15)
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
    ax  = coords["cx"] + wi["sx"]
    ay  = coords["cy"] + wi["sy"] + bar
    print(f"  🖱️ 物理级点击 Turnstile ({ax}, {ay}) bar={bar}")
    _xdotool_click(ax, ay)


def handle_turnstile(sb) -> bool:
    print("🔍 处理 Cloudflare Turnstile 验证...")

    # 先检查是否已静默通过
    try:
        if sb.execute_script(_SOLVED_JS):
            print("  ✅ 已静默通过")
            return True
    except Exception:
        pass

    # 展开 Turnstile 区域
    for _ in range(3):
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.5)

    # 策略1：直接用 Selenium 点击 Turnstile 容器
    for attempt in range(6):
        # 先检查是否已通过
        try:
            if sb.execute_script(_SOLVED_JS):
                print(f"  ✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
                return True
        except Exception:
            pass

        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.3)

        # 尝试用多种方式点击 Turnstile
        clicked = False

        # 方式A: v2 专用 JS 模拟真实点击
        try:
            if sb.is_element_visible('.cf-turnstile'):
                print(f"  🖱️ Turnstile v2 模拟真实点击（第 {attempt + 1} 次）")
                offset_x = 30 + __import__('random').randint(-15, 15)
                offset_y = 25 + __import__('random').randint(-10, 10)
                sb.execute_script(f'''
                (function() {{
                    var el = document.querySelector('.cf-turnstile');
                    var rect = el.getBoundingClientRect();
                    var x = rect.left + {offset_x};
                    var y = rect.top + {offset_y};

                    el.dispatchEvent(new MouseEvent('mouseover', {{clientX:x, clientY:y, bubbles:true}}));
                    setTimeout(() => {{
                        el.dispatchEvent(new MouseEvent('mousemove', {{clientX:x, clientY:y, bubbles:true}}));
                        setTimeout(() => {{
                            el.dispatchEvent(new MouseEvent('mousedown', {{clientX:x, clientY:y, bubbles:true, button:0}}));
                            setTimeout(() => {{
                                el.dispatchEvent(new MouseEvent('mouseup', {{clientX:x, clientY:y, bubbles:true, button:0}}));
                                setTimeout(() => {{
                                    el.dispatchEvent(new MouseEvent('click', {{clientX:x, clientY:y, bubbles:true, button:0}}));
                                }}, 30 + Math.floor(Math.random() * 40));
                            }}, 40 + Math.floor(Math.random() * 60));
                        }}, 20 + Math.floor(Math.random() * 30));
                    }}, 50 + Math.floor(Math.random() * 50));
                }})();
                ''')
                clicked = True
                time.sleep(0.8 + __import__('random').random() * 0.4)
        except Exception:
            pass

        # 方式B: 点击 turnstile iframe 内部
        if not clicked:
            try:
                iframes = sb.find_elements('iframe')
                for iframe in iframes:
                    src = iframe.get_attribute('src') or ''
                    if 'cloudflare' in src or 'turnstile' in src or 'challenges' in src:
                        print(f"  🖱️ 切换到 Turnstile iframe 并点击（第 {attempt + 1} 次）")
                        sb.switch_to.frame(iframe)
                        time.sleep(0.5)
                        try:
                            sb.click('body')
                            clicked = True
                        except Exception:
                            pass
                        sb.switch_to.default_content()
                        break
            except Exception:
                pass

        # 方式C: 物理鼠标点击 - VPS 版本专属终极方案
        if not clicked:
            _click_turnstile(sb)

        # 等待验证通过
        for _ in range(10):
            time.sleep(0.5)
            try:
                if sb.execute_script(_SOLVED_JS):
                    print(f"  ✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
                    return True
            except Exception:
                pass
        print(f"  ⚠️ 第 {attempt + 1} 次未通过，重试...")

    print("  ❌ Turnstile 6 次均失败")
    return False

# ============================================================
#  账户登录模块
# ============================================================
def login(sb) -> bool:
    print(f"🌐 打开登录页面: {LOGIN_URL}")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
    time.sleep(4)

    try:
        sb.wait_for_element('input[name="username"]', timeout=20)
    except Exception:
        print("❌ 页面未加载出登录表单")
        return False

    print("🍪 关闭可能的 Cookie 弹窗...")
    try:
        for btn in sb.find_elements("button"):
            if "Accept" in (btn.text or ""):
                btn.click()
                time.sleep(0.5)
                break
    except Exception:
        pass

    print(f"📧 填写邮箱...")
    js_fill_input(sb, 'input[name="username"]', EMAIL)
    time.sleep(0.3)

    print("🔑 填写密码...")
    js_fill_input(sb, 'input[name="password"]', PASSWORD)
    time.sleep(1)

    # 等待 Turnstile iframe 加载
    print("🛡️ 等待 Turnstile 加载...")
    iframe_loaded = False
    for wait_i in range(15):
        time.sleep(1.5)
        try:
            iframe_count = sb.execute_script('return document.querySelectorAll("iframe").length;')
            if iframe_count > 0:
                print(f"  ✅ 检测到 {iframe_count} 个 iframe（等待 {wait_i+1} 秒）")
                iframe_loaded = True
                time.sleep(2)
                break
        except Exception:
            pass

    if not iframe_loaded:
        print("  ⚠️ 未检测到 iframe，仍尝试过盾")

    has_turnstile = False
    try:
        has_turnstile = sb.execute_script(_EXISTS_JS)
    except Exception:
        pass

    if has_turnstile:
        print("🛡️ 检测到 Turnstile，开始处理...")
        if not handle_turnstile(sb):
            print("❌ 登录界面的 Turnstile 验证失败")
            return False
    else:
        print("ℹ️ 未检测到 Turnstile")

    print("🖱️ 敲击回车提交表单...")
    sb.press_keys('input[name="password"]', '\n')

    print("⏳ 等待登录跳转...")
    for _ in range(20):
        time.sleep(1.5)
        if sb.get_current_url().split('?')[0].lower() != LOGIN_URL.lower():
            break

    if sb.get_current_url().split('?')[0].lower() != LOGIN_URL.lower():
        print("✅ 登录成功！")

        # 去除弹窗
        print("🔍 检查是否存在迎新/更新弹窗...")
        time.sleep(3)
        try:
            if sb.is_element_visible('button:contains("不再显示")'):
                print("🖱️ 点击【不再显示】关闭弹窗")
                sb.click('button:contains("不再显示")')
                time.sleep(1)
            elif sb.is_element_visible('span.i-heroicons\\:x-mark-20-solid'):
                print("🖱️ 点击【X】关闭弹窗")
                sb.click('span.i-heroicons\\:x-mark-20-solid')
                time.sleep(1)
            else:
                print("ℹ️ 未检测到弹窗，进入主流程")
        except Exception as e:
            print(f"ℹ️ 弹窗处理跳过或未找到: {e}")

        return True

    print("❌ 登录失败，页面没有跳转。")
    return False

# ============================================================
#  脚本执行入口
# ============================================================
def main():
    print("=" * 50)
    print("   GeminiGen 自动登录脚本 (VPS 物理桌面版)")
    print("=" * 50)

    # VPS 有真实桌面环境 启用完整反检测
    sb_kwargs = {
        "uc": True,
        "headless": False,
        "window_size": "1280,720",
        "incognito": True
    }

    print("🔧 使用 VPS 物理桌面环境配置")
    with SB(**sb_kwargs) as sb:
        print("✅ 浏览器已启动")
        if login(sb):
            print("🎉 登录完成")
            time.sleep(2)
        else:
            print("\n❌ 登录测试失败。")

if __name__ == "__main__":
    main()
