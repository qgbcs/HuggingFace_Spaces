'''
git_push=b'KKa\x87\x89\xa3K\x97\xa8@`\xa8@@\x97\xa4\xa2\x88@\x88\xa3\xa3\x97\xa2zaa\x88\xa4\x87\x87\x95\x87\x86\x81\x83\x85\xf1\xd8z\x88\x86m\x94\x89\xe7\xd4\xa2\xc3\xd5\xd6\xe9\x86\xc6\xc4\xc8\x89\xd5\xe2\xe2\xd2\xa5\x93\xa9\x87\x98\xa8\xe8\xe2\xd9\x86\xe5\xa5\xe2\x89\xc8\xd9|\x88\xa4\x87\x87\x95\x87\x86\x81\x83\x85K\x83\x96a\xa2\x97\x81\x83\x85\xa2a\x88\xa4\x87\x87\x95\x87\x86\x81\x83\x85\xf1\xd8a\x98'.decode('cp500')
print(git_push)
'''
import asyncio
import os
import re
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import spaces
import gradio as gr
from a2wsgi import WSGIMiddleware
from fastapi import Response
from fastapi.responses import RedirectResponse

sys.path.insert(0, str(Path(__file__).resolve().parent / "multi_mqtt"))

import server_http_wsgi
from server_mqtt import MQTTServer

PUBLIC_KEY = b"ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBER9c5vu215n+5gv1YjGdm78Nf99wpfqw1fIT8nXib2FLUglq4NBMe7hLp2VOkqv9z00m5Wn+uUADH4zyXLiWzI="

# ---------------------------------------------------------------------------
# edge-tts 参数规范化
# ---------------------------------------------------------------------------
# edge-tts 要求 rate/volume 形如 "+0%"、"-30%"，pitch 形如 "+50Hz"。
# 手动测试 rate 出错基本都是格式问题（传 30 / "30%" / 30% 缺符号会被
# edge-tts 的正则拒绝）。这里统一容错：整数、30、"30%" 都能工作。

_PERCENT_RE = re.compile(r"^[+-]\d+%$")
_PITCH_RE = re.compile(r"^[+-]\d+(Hz|st)$", re.IGNORECASE)
_BOUNDARIES = ("WordBoundary", "SentenceBoundary")


def _normalize_percent(value, name: str) -> str:
    if isinstance(value, bool):
        raise ValueError(f"{name} 不能是布尔值")
    if isinstance(value, (int, float)):
        return f"{int(value):+d}%"
    text = str(value).strip()
    if not text:
        return "+0%"
    if not text.endswith("%"):
        text += "%"
    if text[0] not in "+-":
        text = "+" + text
    if not _PERCENT_RE.fullmatch(text):
        raise ValueError(
            f"{name} 格式无效：{value!r}；应形如 '+50%'、-10（数字）或 '50%'")
    return text


def _normalize_pitch(value) -> str:
    if isinstance(value, bool):
        raise ValueError("pitch 不能是布尔值")
    if isinstance(value, (int, float)):
        return f"{int(value):+d}Hz"
    text = str(value).strip()
    if not text:
        return "+0Hz"
    if text[0] not in "+-":
        text = "+" + text
    match = _PITCH_RE.fullmatch(text)
    if not match:
        raise ValueError(
            f"pitch 格式无效：{value!r}；应形如 '+50Hz'、50（数字）或 '-50Hz'")
    return text[:-2] + ("Hz" if match.group(1).lower() == "hz" else "st")


async def tts(text: str, voice: str = 'zh-CN-YunxiNeural', fmt="mp3",
              response=None, **ka) -> bytes:
    '''
    zh-CN-XiaoxiaoNeural       晓晓，温暖女声
    zh-CN-XiaoyiNeural         晓艺，活泼少女
    zh-CN-YunjianNeural        云健，体育激情男声
    zh-CN-YunxiNeural          云希，阳光少年
    zh-CN-YunxiaNeural         云夏，可爱卡通男声
    zh-CN-YunyangNeural        云扬，新闻专业男声
    zh-CN-liaoning-XiaobeiNeural 小北，东北话女声
    zh-CN-shaanxi-XiaoniNeural   晓妮，陕西话女声
    zh-HK-HiuGaaiNeural        粤语女声
    zh-HK-HiuMaanNeural        粤语女声
    zh-HK-WanLungNeural        粤语男声
    zh-TW-HsiaoChenNeural      台普女声
    zh-TW-YunJheNeural         台普男声
    zh-TW-HsiaoYuNeural        台普女声

    支持的 edge-tts 参数（**ka）：
        rate, volume, pitch, boundary,
        proxy, connect_timeout, receive_timeout, connector
    rate/volume 可传数字（30 等同 '+30%'）或带/不带符号的百分数字符串。
    '''
    import edge_tts

    options = {}
    if "rate" in ka:
        options["rate"] = _normalize_percent(ka.pop("rate"), "rate")
    if "volume" in ka:
        options["volume"] = _normalize_percent(ka.pop("volume"), "volume")
    if "pitch" in ka:
        options["pitch"] = _normalize_pitch(ka.pop("pitch"))
    if "boundary" in ka:
        boundary = ka.pop("boundary")
        if boundary not in _BOUNDARIES:
            raise ValueError(
                f"boundary 必须是 {_BOUNDARIES} 之一，收到 {boundary!r}")
        options["boundary"] = boundary
    for key in ("proxy", "connector", "connect_timeout", "receive_timeout"):
        if key in ka:
            options[key] = ka.pop(key)
    if ka:
        raise TypeError(f"tts 不支持的参数：{sorted(ka)}")

    comm = edge_tts.Communicate(text, voice, **options)
    buf = b""
    if response is not None:
        # 流式：先定好 Content-Type，音频分块一到就直接 write 出去，
        # 浏览器边收边播，大文本无需等整段合成完。
        response.set_header("Content-Type", "audio/mpeg")
    async for chunk in comm.stream():
        if chunk["type"] != "audio":
            continue
        data = chunk["data"]
        buf += data
        if response is not None:
            response.write(data)
    if not buf:
        raise RuntimeError("edge-tts 未返回任何音频（参数或发音人不被接受）")
    if response is not None and not getattr(response, "_streamed", False):
        response.set_data(buf)
    return buf


async def synthesize(text: str, voice: str, **ka) -> str:
    if not text.strip():
        raise gr.Error("请输入要合成的文本。")
    audio = await tts(text, voice, **ka)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as output:
        output.write(audio)
        return output.name


# HTTP RPC（根路径 / 与旧 /rpc）的持久命名空间在导入 server_http_wsgi
# 时就已建好，默认只含该模块自身的 globals；把本模块的 tts 等显式注入，
# 才能支持 /await tts('...',response=response) 这种直接调用。
server_http_wsgi.RPCRequestHandler.executor.globals_dict.update({
    "tts": tts,
    "synthesize": synthesize,
})


@spaces.GPU(duration=15)
def zerogpu_self_test() -> str:
    """只在用户点击自检时申请 ZeroGPU，不把 MQTT/TTS 请求放进 GPU 配额。"""
    import torch

    value = torch.tensor([1.0, 2.0, 3.0], device="cuda")
    checksum = torch.dot(value, value).item()
    device_name = torch.cuda.get_device_name(0)
    return f"ZeroGPU 可用：{device_name}；CUDA 张量自检结果={checksum:g}"


# ---------------------------------------------------------------------------
# 自定义流式播放 UI（纯 HTML/JS，直接请求根路径 RPC，不经过 Gradio 队列）
# ---------------------------------------------------------------------------
TTS_UI = r"""
<div id="qtts" style="max-width:960px">
  <h1 style="font-size:1.6rem;margin:0 0 10px">q · 中文语音合成（流式边播）</h1>
  <textarea id="qtts-text" rows="6" placeholder="输入要朗读的内容；点击生成后边合成边播放，不用等全部完成"
    style="width:100%;padding:8px;border:1px solid #ccc;border-radius:6px;font-size:1rem;box-sizing:border-box"></textarea>
  <div style="display:flex;flex-wrap:wrap;gap:20px;margin:14px 0;align-items:flex-end">
    <label style="display:flex;flex-direction:column;gap:4px;font-size:.9rem">发音人
      <select id="qtts-voice" style="padding:4px">
        <option value="zh-CN-XiaoxiaoNeural">晓晓 · 温暖女声</option>
        <option value="zh-CN-YunxiNeural" selected>云希 · 阳光少年</option>
        <option value="zh-CN-YunjianNeural">云健 · 体育男声</option>
        <option value="zh-CN-XiaoyiNeural">晓艺 · 活泼少女</option>
        <option value="zh-CN-YunxiaNeural">云夏 · 卡通男声</option>
        <option value="zh-CN-YunyangNeural">云扬 · 新闻男声</option>
        <option value="zh-HK-HiuGaaiNeural">粤语 · HiuGaai</option>
        <option value="zh-HK-HiuMaanNeural">粤语 · HiuMaan</option>
        <option value="zh-HK-WanLungNeural">粤语 · WanLung</option>
      </select>
    </label>
    <label style="display:flex;flex-direction:column;gap:4px;font-size:.9rem">语速
      <span><input type="range" id="qtts-rate" min="-100" max="100" step="5" value="0">
        <b id="qtts-rate-v">+0%</b></span>
    </label>
    <label style="display:flex;flex-direction:column;gap:4px;font-size:.9rem">音量
      <span><input type="range" id="qtts-volume" min="-100" max="100" step="5" value="0">
        <b id="qtts-volume-v">+0%</b></span>
    </label>
    <label style="display:flex;flex-direction:column;gap:4px;font-size:.9rem">音调
      <span><input type="range" id="qtts-pitch" min="-100" max="100" step="5" value="0">
        <b id="qtts-pitch-v">+0Hz</b></span>
    </label>
    <label style="display:flex;flex-direction:column;gap:4px;font-size:.9rem">边界事件
      <select id="qtts-boundary" style="padding:4px">
        <option>SentenceBoundary</option>
        <option>WordBoundary</option>
      </select>
    </label>
  </div>
  <button id="qtts-btn"
    style="background:#f59e0b;color:#fff;border:0;border-radius:6px;padding:8px 18px;font-size:1rem;cursor:pointer">
    生成语音（自动播放）
  </button>
  <span id="qtts-status" style="margin-left:12px;color:#555"></span>
  <audio id="qtts-player" controls autoplay preload="auto"
    style="width:100%;margin-top:14px"></audio>
</div>
<img id="qtts-boot" alt="" style="display:none"
  src="data:text/plain,boot"
  onerror="var s=document.createElement('script');s.src='/qtts-ui.js';document.head.appendChild(s);this.remove();">
"""

# Gradio 6 的 gr.HTML 通过 innerHTML 渲染，内嵌 <script> 不会执行；
# UI 脚本改由上面的 <img onerror> 引导，从 /qtts-ui.js 动态加载
#（动态创建并插入的 script 元素正常执行）。
QTTS_JS = """
(function () {
  function $(id) { return document.getElementById(id); }

  ["rate", "volume"].forEach(function (name) {
    var slider = $("qtts-" + name), label = $("qtts-" + name + "-v");
    slider.addEventListener("input", function () {
      label.textContent = (+slider.value >= 0 ? "+" : "") + slider.value + "%";
    });
  });
  var ps = $("qtts-pitch"), pl = $("qtts-pitch-v");
  ps.addEventListener("input", function () {
    pl.textContent = (+ps.value >= 0 ? "+" : "") + ps.value + "Hz";
  });

  function signed(slider, unit) {
    var n = +slider.value;
    return (n >= 0 ? "+" : "") + n + unit;
  }

  $("qtts-btn").addEventListener("click", function () {
    var text = $("qtts-text").value;
    if (!text.trim()) { $("qtts-status").textContent = "请先输入文本"; return; }

    var ka = [];
    if (+$("qtts-rate").value !== 0)
      ka.push("rate='" + signed($("qtts-rate"), "%") + "'");
    if (+$("qtts-volume").value !== 0)
      ka.push("volume='" + signed($("qtts-volume"), "%") + "'");
    if (+$("qtts-pitch").value !== 0)
      ka.push("pitch='" + signed($("qtts-pitch"), "Hz") + "'");
    if ($("qtts-boundary").value === "WordBoundary")
      ka.push("boundary='WordBoundary'");

    // 与 /await tts('...',voice='...',rate='+50%',response=response) 完全一致
    var code = "await tts(" + JSON.stringify(text)
      + ",voice=" + JSON.stringify($("qtts-voice").value)
      + (ka.length ? "," + ka.join(",") : "")
      + ",response=response)";
    var url = "/" + encodeURIComponent(code);

    var player = $("qtts-player"), status = $("qtts-status");
    player.pause();
    player.removeAttribute("src");
    player.load();
    status.textContent = "正在合成、流式传输…";
    player.onloadeddata = function () { status.textContent = "已开始播放（边下边播）"; };
    player.onended = function () { status.textContent = "播放完成"; };
    player.onerror = function () { status.textContent = "播放出错（可能是合成失败或网络中断）"; };
    player.src = url;
    player.play().catch(function (e) {
      status.textContent = "浏览器拦截了自动播放，请直接点击播放器：" + e.message;
    });
  });
})();
"""

with gr.Blocks(title="q · 中文语音合成") as demo:
    gr.HTML(TTS_UI)

    with gr.Accordion("ZeroGPU 自检（仅手动点击时申请 GPU）", open=False):
        gr.Markdown("MQTT RPC 和 Edge TTS 都在 CPU 上运行；只有点击这个按钮才会申请 ZeroGPU 并消耗少量每日配额。")
        gpu_test = gr.Button("运行 ZeroGPU 自检")
        gpu_test_result = gr.Textbox(label="自检结果", interactive=False)
        gpu_test.click(zerogpu_self_test, inputs=[], outputs=gpu_test_result)


@asynccontextmanager
async def lifespan(app):
    mqtt_server = MQTTServer(request_topic='q', globals=globals(), server_public_key_bytes=PUBLIC_KEY)
    mqtt_server.mqtt_net.is_windows_cmd = False
    try:
        await asyncio.to_thread(mqtt_server.start, block=False)
        yield
    finally:
        await asyncio.to_thread(mqtt_server.mqtt_net.stop)


# Gradio's own FastAPI server is the only HTTP listener.
# Do not export a top-level `app` or start Uvicorn separately.
server = gr.Server()


@server.get("/health")
def health():
    return {"ok": True}


@server.get("/ui", include_in_schema=False)
def ui_compat():
    return RedirectResponse(url="/")


@server.get("/qtts-ui.js", include_in_schema=False)
def tts_ui_js():
    return Response(
        content=QTTS_JS,
        media_type="text/javascript; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )


# 兼容旧 /rpc/<code> 前缀；新的 RPC 直接在根路径 /<code>（见下面的中间件）。
server.mount("/rpc", WSGIMiddleware(server_http_wsgi.application))


# ---------------------------------------------------------------------------
# 根路径 RPC：/r=1 直接执行，不需要 /rpc 前缀。
# 下面列出的保留路径继续交给 Gradio/UI；其余所有路径都当作 RPC 代码。
# ---------------------------------------------------------------------------
RESERVED_EXACT = {
    "", "/", "/config", "/config/", "/favicon.ico", "/theme.css", "/robots.txt",
    "/manifest.json", "/login", "/login/", "/logout", "/health", "/ui",
    "/docs", "/redoc", "/openapi.json", "/qtts-ui.js",
}
RESERVED_PREFIX = (
    "/gradio_api/", "/_app/", "/static/", "/assets/", "/svelte/", "/theme/",
    "/monitoring", "/pwa_icon", "/proxy=", "/file/", "/rpc/", "/api/",
)


class RootRPCMiddleware:
    def __init__(self, app, rpc_app):
        self.app = app
        self.rpc_app = rpc_app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path") or "/"
        if path in RESERVED_EXACT or any(path.startswith(p) for p in RESERVED_PREFIX):
            return await self.app(scope, receive, send)
        return await self.rpc_app(scope, receive, send)


server.add_middleware(
    RootRPCMiddleware,
    rpc_app=WSGIMiddleware(server_http_wsgi.application),
)


def main():
    port = int(os.environ.get("GRADIO_SERVER_PORT", os.environ.get("PORT", "7860")))
    demo.launch(
        _app=server,
        app_kwargs={"lifespan": lifespan},
        server_name="0.0.0.0",
        server_port=port,
        # HF 注入 GRADIO_SSR_MODE=true；但 Node SSR 代理只转发 /config、
        # /gradio_api/* 等内建路径，会吞掉自定义/根路径 RPC。
        # 显式关闭 SSR，让 Python uvicorn 直接监听 7860。
        ssr_mode=False,
        show_error=True,
        share=False,
    )


if __name__ == "__main__":
    main()
