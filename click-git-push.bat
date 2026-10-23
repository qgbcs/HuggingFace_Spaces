@echo on
setlocal
pushd "%~dp0"
set "PYTMP=%TEMP%\click_git_push_%RANDOM%.py"
copy /y "%~f0" "%PYTMP%" >nul
"C:\QGB\miniforge3\python.exe" -c "import sys;exec(sys.stdin.buffer.read().decode('utf-8').split('#'+'PYTHON_START',1)[1])" %* < "%PYTMP%"
set "RC=%ERRORLEVEL%"
del /q "%PYTMP%" >nul 2>nul
popd
if "%~1"=="" pause
exit /b %RC%
#PYTHON_START

import fnmatch
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

SRC = r"C:\test\github\multi_mqtt"
REPO = r"D:\test\github\HuggingFace_Spaces"
DST = os.path.join(REPO, "multi_mqtt")
GIT = r"C:\QGB\PortableGit\bin\git.exe"
PROXY = "socks5h://127.0.0.1:41080"
REPO_URL = "" # 推送/拉取使用的仓库地址；留空则自动使用仓库 .git/config 里的 origin
BRANCH = "main"
COMMIT_MSG = "chore: 同步最新 multi_mqtt 代码（client 子包、PTY/远程命令/socks5 测试、server_mqtt 与 rpc 更新）"
VERIFY_URL = "https://huggingface1q-q.hf.space/with%20open('multi_mqtt/server_mqtt.py','r')%20as%20f:r=f.read(-1)"
VERIFY_FILE = "server_mqtt.py"

SKIP_DIRS = {".git", ".stfolder", ".trae", "__pycache__", "venv", ".venv"}
SKIP_SUFFIX = (".db", ".db-shm", ".db-wal", ".pyc", ".pyo")
SKIP_NAMES = {"_poll.json",'.gitignore'}


def log(msg):
    print(msg, flush=True)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd, capture=False):
    if capture:
        p = subprocess.run(cmd, cwd=REPO, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, encoding="utf-8",
                           errors="replace")
        return p.returncode, (p.stdout or "").strip()
    p = subprocess.run(cmd, cwd=REPO)
    return p.returncode, ""


def git(*args, net=False, capture=False):
    cmd = [GIT]
    if net:
        cmd += ["-c", "http.proxy=" + PROXY, "-c", "http.version=HTTP/1.1",
                "-c", "protocol.version=0"]
    cmd += list(args)
    return run(cmd, capture=capture)


def load_ignore_rules():
    """收集源目录各级 .gitignore 规则（基目录、模式、是否取反、是否锚定）。"""
    rules = []
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if ".gitignore" not in files:
            continue
        rel = os.path.relpath(root, SRC)
        base = "" if rel == "." else rel.replace("\\", "/")
        with open(os.path.join(root, ".gitignore"), encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                negate = line.startswith("!")
                if negate:
                    line = line[1:]
                if line.endswith("/"):
                    continue  # 目录规则由 SKIP_DIRS 处理
                anchored = line.startswith("/") or "/" in line
                rules.append((base, line.lstrip("/"), negate, anchored))
    return rules


def is_ignored(rel_path, rules):
    ignored = False
    for base, pattern, negate, anchored in rules:
        if base:
            prefix = base + "/"
            if not rel_path.startswith(prefix):
                continue
            cand = rel_path[len(prefix):]
        else:
            cand = rel_path
        target = cand if anchored else cand.rsplit("/", 1)[-1]
        if fnmatch.fnmatchcase(target, pattern):
            ignored = not negate
    return ignored


def sync_files():
    rules = load_ignore_rules()
    copied = 0
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = os.path.relpath(root, SRC)
        out_dir = DST if rel == "." else os.path.join(DST, rel)
        os.makedirs(out_dir, exist_ok=True)
        for name in files:
            if name in SKIP_NAMES or name.endswith(SKIP_SUFFIX):
                continue
            rel_path = name if rel == "." else os.path.join(rel, name)
            rel_path = rel_path.replace("\\", "/")
            if is_ignored(rel_path, rules):
                continue
            src = os.path.join(root, name)
            dst = os.path.join(out_dir, name)
            if os.path.isfile(dst):
                try:
                    if os.path.getsize(src) == os.path.getsize(dst) and sha256_file(src) == sha256_file(dst):
                        continue
                except OSError:
                    pass
            shutil.copy2(src, dst)
            copied += 1
    return copied


def stage_all():
    git("add", "-A", "multi_mqtt", capture=True)
    git("reset", "-q", "--", "multi_mqtt/_poll.json", capture=True)
    rc, out = git("diff", "--cached", "--name-only", capture=True)
    return [x for x in out.splitlines() if x.strip()]


def commit_staged(files):
    rc, out = git("commit", "-m", COMMIT_MSG, "--", "multi_mqtt", capture=True)
    if rc != 0:
        raise RuntimeError("提交失败：" + out)
    log("  已提交 %d 个文件" % len(files))


def remote_status():
    rc, out = git("rev-list", "--left-right", "--count", "HEAD...origin/" + BRANCH, capture=True)
    if rc != 0:
        return 0, 0
    parts = out.split()
    return int(parts[0]), int(parts[1])


def net_target():
    return REPO_URL or "origin"


def masked(url):
    return re.sub(r"//[^/@]+@", "//***@", url)


def fetch_remote():
    last = ""
    target = net_target()
    refspec = ["+%s:refs/remotes/origin/%s" % (BRANCH, BRANCH)] if REPO_URL else [BRANCH]
    for _ in range(3):
        rc, out = git("fetch", target, *refspec, net=True, capture=True)
        if rc == 0:
            return
        last = out
        time.sleep(2)
    raise RuntimeError("拉取远端失败：" + last)


def resolve_rebase_conflicts():
    rc, out = git("diff", "--name-only", "--diff-filter=U", capture=True)
    if rc != 0 or not out.strip():
        return False
    log("  检测到 %d 个冲突，用源目录覆盖解决" % len(out.splitlines()))
    sync_files()
    stage_all()
    rc, out = git("-c", "core.editor=true", "rebase", "--continue", capture=True)
    return rc == 0


def sync_and_commit():
    log("[1/4] 同步源目录到 Space 仓库 ...")
    copied = sync_files()
    log("  复制/更新 %d 个文件" % copied)
    files = stage_all()
    if files:
        commit_staged(files)
    else:
        log("  无变更，跳过提交")
    return len(files)


def push():
    log("[2/4] 拉取并同步远端提交 ...")
    fetch_remote()
    ahead, behind = remote_status()
    if behind:
        rc, out = git("rebase", "origin/" + BRANCH, capture=True)
        if rc != 0:
            if not resolve_rebase_conflicts():
                git("rebase", "--abort", capture=True)
                raise RuntimeError("rebase 失败，已回滚：" + out)
    ahead, behind = remote_status()
    if ahead == 0 and behind == 0:
        log("  远端已是最新，无需推送")
        return False
    if behind:
        raise RuntimeError("本地仍落后远端 %d 个提交，请检查" % behind)
    log("[3/4] 推送 %d 个提交到 HuggingFace Space ..." % ahead)
    rc, out = git("push", net_target(), "HEAD:" + BRANCH, net=True, capture=True)
    if rc != 0:
        raise RuntimeError("推送失败：" + out)
    log("  " + (out.splitlines()[-1] if out else "推送完成"))
    return True


def http_get(url, proxy=None, timeout=30):
    curl = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "curl.exe")
    if not os.path.isfile(curl):
        curl = shutil.which("curl")
    if not curl:
        return None, 0
    tmp = os.path.join(REPO, ".verify_tmp.txt")
    cmd = [curl, "-sS", "-L", "--max-time", str(timeout), "-o", tmp, "-w", "%{http_code}"]
    if proxy:
        cmd += ["--proxy", proxy]
    cmd.append(url)
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        code = int((p.stdout or b"0").decode("ascii", "ignore").strip() or 0)
        body = None
        if os.path.isfile(tmp):
            with open(tmp, "rb") as f:
                body = f.read()
            os.remove(tmp)
        return body, code
    finally:
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def verify(timeout=420, interval=10):
    log("[4/4] 校验线上 multi_mqtt/server_mqtt.py 是否为最新 ...")
    want = sha256_file(os.path.join(SRC, VERIFY_FILE))
    deadline = time.time() + timeout
    last = ""
    while True:
        body, code = http_get(VERIFY_URL)
        if code != 200:
            body, code = http_get(VERIFY_URL, proxy=PROXY)
        if code == 200 and body is not None:
            got = sha256_bytes(body)
            if got == want:
                log("  校验通过：线上文件 sha256=%s（%d 字节）" % (got[:16], len(body)))
                return True
            last = "sha256=%s size=%d" % (got[:16], len(body))
        else:
            last = "HTTP %s" % code
        if time.time() >= deadline:
            log("  校验超时：线上内容仍为 %s，期望 %s" % (last, want[:16]))
            return False
        log("  等待 Space 生效（%s），%d 秒后重试 ..." % (last, interval))
        time.sleep(interval)


def main():
    for path in (SRC, REPO):
        if not os.path.isdir(path):
            raise RuntimeError("目录不存在：" + path)
    if not os.path.isfile(GIT):
        raise RuntimeError("git 不存在：" + GIT)
    log("同步源：%s" % SRC)
    log("目标仓：%s" % REPO)
    log("远端：%s" % (masked(REPO_URL) if REPO_URL else "origin（.git/config）"))
    sync_and_commit()
    push()
    ok = verify()
    if not ok:
        raise RuntimeError("线上代码校验未通过")
    log("全部完成。")


try:
    main()
except Exception as exc:
    log("错误：%s" % exc)
    sys.exit(1)
