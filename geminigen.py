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
        
        # 首次尝试时打印 Turnstile 内部结构
        if attempt == 0:
            try:
                structure = sb.execute_script('''
                    var container = document.querySelector('.cf-turnstile');
                    if (!container) return 'no .cf-turnstile';
                    var result = {tag: container.tagName, class: container.className, id: container.id, children: []};
                    function walk(el, depth) {
                        if (depth > 4) return;
                        var info = {tag: el.tagName, class: el.className, id: el.id, style: el.style.cssText.substring(0,100)};
                        if (el.tagName === 'IFRAME') info.src = (el.src || '').substring(0,100);
                        if (el.tagName === 'INPUT') { info.name = el.name; info.type = el.type; info.value_len = (el.value||'').length; }
                        result.children.push({'depth': depth, 'info': info});
                        for (var i = 0; i < el.children.length; i++) walk(el.children[i], depth+1);
                    }
                    for (var i = 0; i < container.children.length; i++) walk(container.children[i], 1);
                    return JSON.stringify(result);
                ''')
                print(f"  🔍 Turnstile 内部结构: {structure}")
            except Exception as e:
                print(f"  ⚠️ 获取 Turnstile 结构失败: {e}")
        
        # 方式A: 点击 cf-turnstile 容器
        try:
            if sb.is_element_visible('.cf-turnstile'):
                print(f"  🖱️ 点击 .cf-turnstile 容器（第 {attempt + 1} 次）")
                sb.click('.cf-turnstile')
                clicked = True
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
        
        # 方式C: 找 turnstile 相关的 label/checkbox 并点击
        if not clicked:
            try:
                result = sb.execute_script('''
                    var labels = document.querySelectorAll('label, [role="checkbox"]');
                    for (var i = 0; i < labels.length; i++) {
                        var parent = labels[i];
                        for (var j = 0; j < 5; j++) {
                            parent = parent.parentElement;
                            if (!parent) break;
                            if (parent.classList.contains('cf-turnstile') || parent.id.includes('turnstile'))
                                return labels[i];
                        }
                    }
                    return null;
                ''')
                if result:
                    print(f"  🖱️ 点击 Turnstile checkbox（第 {attempt + 1} 次）")
                    sb.click(result)
                    clicked = True
            except Exception:
                pass
        
        
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
#  账户登录模块 (100% 照搬 renew 的结构逻辑)
# ============================================================
def login(sb) -> bool:
    print(f"🌐 打开登录页面: {LOGIN_URL}")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
    time.sleep(4)
    # sb.save_screenshot("geminigen_01_page_loaded.png")
    # print("📸 截图: 页面加载完成")

    try:
        sb.wait_for_element('input[name="username"]', timeout=20)
    except Exception:
        print("❌ 页面未加载出登录表单")
        # sb.save_screenshot("geminigen_login_load_fail.png")
        return False

    # 调试：打印页面上所有 iframe 和 turnstile 相关元素
    try:
        iframes_info = sb.execute_script('''
            var result = [];
            document.querySelectorAll('iframe').forEach(function(f) {
                result.push({src: f.src, w: f.offsetWidth, h: f.offsetHeight, visible: f.offsetParent !== null});
            });
            return result;
        ''')
        print(f"🔍 页面 iframe 数量: {len(iframes_info)}")
        for i, info in enumerate(iframes_info):
            print(f"  iframe[{i}]: src={info.get('src','')[:80]}, size={info.get('w',0)}x{info.get('h',0)}, visible={info.get('visible',False)}")
    except Exception as e:
        print(f"⚠️ 获取 iframe 信息失败: {e}")

    try:
        turnstile_inputs = sb.execute_script('''
            var result = [];
            document.querySelectorAll('input').forEach(function(inp) {
                if (inp.name && (inp.name.includes('turnstile') || inp.name.includes('cf-')))
                    result.push({name: inp.name, value_len: (inp.value || '').length, type: inp.type});
            });
            return result;
        ''')
        print(f"🔍 Turnstile input 数量: {len(turnstile_inputs)}")
        for inp in turnstile_inputs:
            print(f"  input: name={inp.get('name')}, value_len={inp.get('value_len',0)}, type={inp.get('type')}")
    except Exception as e:
        print(f"⚠️ 获取 turnstile input 失败: {e}")

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
    time.sleep(1.5)

    # 检查 Turnstile：即使 input 存在也需要等 iframe 加载
    print("🛡️ 检查 Turnstile 验证...")
    
    # 等待 Turnstile iframe 加载，最多等 15 秒
    iframe_loaded = False
    for wait_i in range(15):
        time.sleep(1.5)
        try:
            iframe_count = sb.execute_script('''
                return document.querySelectorAll('iframe').length;
            ''')
            if iframe_count > 0:
                print(f"  ✅ 检测到 {iframe_count} 个 iframe（等待 {wait_i+1} 秒）")
                iframe_loaded = True
                time.sleep(2)  # iframe 加载后再等一会
                break
        except Exception:
            pass
    
    if not iframe_loaded:
        print("  ⚠️ 15 秒内未检测到 iframe，但 input 存在，仍尝试过盾")
    
    has_turnstile = False
    try:
        has_turnstile = sb.execute_script(_EXISTS_JS)
    except Exception:
        pass
    
    # 二次确认：检查 iframe 是否有 cloudflare 相关的
    if not has_turnstile:
        try:
            has_turnstile = sb.execute_script('''
                var iframes = document.querySelectorAll('iframe');
                for (var i = 0; i < iframes.length; i++) {
                    var src = iframes[i].src || '';
                    if (src.includes('cloudflare') || src.includes('turnstile') || src.includes('challenges'))
                        return true;
                }
                return false;
            ''')
        except Exception:
            pass
    
    # 三次确认：直接看 input 是否存在
    if not has_turnstile:
        try:
            has_turnstile = sb.execute_script('''
                return document.querySelector('input[name="cf-turnstile-response"]') !== null;
            ''')
        except Exception:
            pass
    
    # sb.save_screenshot("geminigen_02_before_turnstile.png")
    # print("📸 截图: 过盾前")
    
    if has_turnstile:
        print("🛡️ 检测到 Turnstile，开始处理...")
        if not handle_turnstile(sb):
            print("❌ 登录界面的 Turnstile 验证失败")
            # sb.save_screenshot("geminigen_login_turnstile_fail.png")
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
        time.sleep(3) # 等待弹窗加载
        try:
            # 优先点击“不再显示”
            if sb.is_element_visible('button:contains("不再显示")'):
                print("🖱️ 点击【不再显示】关闭弹窗")
                sb.click('button:contains("不再显示")')
                time.sleep(1.5)
            elif sb.is_element_visible('span.i-heroicons\\:x-mark-20-solid'):
                # 备用：点击 X 关闭按钮
                print("🖱️ 点击【X】关闭弹窗")
                sb.click('span.i-heroicons\\:x-mark-20-solid')
                time.sleep(1.5)
            else:
                print("ℹ️ 未检测到弹窗，进入主流程")
        except Exception as e:
            print(f"ℹ️ 弹窗处理跳过或未找到: {e}")
        
        return True
        
    print("❌ 登录失败，页面没有跳转。")
    # sb.save_screenshot("geminigen_login_failed.png")
    return False

# ============================================================
#  普通模式登录（headless2，不用 uc）
# ============================================================
def login_normal(sb) -> bool:
    print(f"🌐 打开登录页面: {LOGIN_URL}")
    sb.open(LOGIN_URL)
    time.sleep(4)
    # sb.save_screenshot("geminigen_01_page_loaded.png")
    # print("📸 截图: 页面加载完成")

    try:
        sb.wait_for_element('input[name="username"]', timeout=20)
    except Exception:
        print("❌ 页面未加载出登录表单")
        # sb.save_screenshot("geminigen_login_load_fail.png")
        return False

    # 调试 iframe
    try:
        iframes_info = sb.execute_script('''
            var result = [];
            document.querySelectorAll('iframe').forEach(function(f) {
                result.push({src: (f.src||'').substring(0,80), w: f.offsetWidth, h: f.offsetHeight});
            });
            return result;
        ''')
        print(f"🔍 页面 iframe 数量: {len(iframes_info)}")
        for i, info in enumerate(iframes_info):
            print(f"  iframe[{i}]: src={info.get('src','')}, size={info.get('w',0)}x{info.get('h',0)}")
    except Exception as e:
        print(f"⚠️ 获取 iframe 信息失败: {e}")

    print(f"📧 填写邮箱...")
    js_fill_input(sb, 'input[name="username"]', EMAIL)
    time.sleep(0.3)
    
    print("🔑 填写密码...")
    js_fill_input(sb, 'input[name="password"]', PASSWORD)
    time.sleep(1.5)

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
        has_turnstile = sb.execute_script('return document.querySelector("input[name=cf-turnstile-response]") !== null;')
    except Exception:
        pass
    
    # sb.save_screenshot("geminigen_02_before_turnstile.png")
    # print("📸 截图: 过盾前")
    
    if has_turnstile:
        print("🛡️ 检测到 Turnstile，开始处理...")
        if not handle_turnstile(sb):
            print("❌ 登录界面的 Turnstile 验证失败")
            # sb.save_screenshot("geminigen_login_turnstile_fail.png")
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
        time.sleep(3)
        return True
        
    print("❌ 登录失败，页面没有跳转。")
    # sb.save_screenshot("geminigen_login_failed.png")
    return False

# ============================================================
#  脚本执行入口
# ============================================================
def main():
    print("=" * 50)
    print("   GeminiGen 自动登录脚本 (Renew Mode)")
    print("=" * 50)
    
    # Github Action 无头环境专用参数
    sb_kwargs = {
        "uc": False,
        "headless": "new",
        "no_sandbox": True,
        "disable_gpu": True,
        "window_size": "1280,720",
        "disable_images": True,
        "incognito": True
    }
    print("🔧 使用 Github Action 无头环境配置")
    with SB(**sb_kwargs) as sb:
        print("✅ 浏览器已启动")
        if login(sb):
            print("🎉 登录完成，保存截图...")
            time.sleep(2)
            # sb.save_screenshot("geminigen_login_success.png")
            print("📸 截图已保存: geminigen_login_success.png")
        else:
            print("\n❌ 登录测试失败。")

if __name__ == "__main__":
    main()
