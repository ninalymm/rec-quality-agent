# 踩坑记录（Troubleshooting）

> 环境：macOS / Apple Silicon（arm64）· 2026-10-29 · 项目阶段 M0
>
> 用途：记录实际踩到的坑和验证过的解法，避免重复排查；同时作为 M6「失败案例」的素材来源。
> 自己代码里的缺陷另见 [bugs.md](bugs.md)。

## 1. github.com:443 概率性阻断，clone / push 随机超时

**现象**

同一个仓库、同一条命令、同一个 PyCharm 进程，10 分钟内一次成功、两次失败：

```
17:48:08  clone 开始 → 17:48:10  Receiving objects: 100% (11/11), done.   ← 2.4 秒成功
17:59:07  clone 开始 → 17:59:44  fatal: unable to access '...':
                                   Failed to connect to github.com port 443 after 36595 ms
18:01:22  clone 开始 → 18:01:59  fatal: ... after 36550 ms
```

**诊断**

```bash
# 反复探测 TCP 建连
for i in $(seq 1 15); do nc -z -G 2 -w 2 github.com 443; done   # 0/15
for i in $(seq 1 15); do nc -z -G 2 -w 2 github.com 22;  done   # 15/15

# 排除本地因素
git config --list --show-origin | grep -i proxy   # 无
cat /etc/gitconfig                                # 不存在
grep -i github /etc/hosts                         # 无
scutil --proxy                                    # HTTPEnable/HTTPSEnable/SOCKSEnable 全 0
nc -z 127.0.0.1 15236                             # 关闭（Clash Verge 未运行）
```

**根因**

`github.com:443` 的 TCP 建连被概率性丢包，成功率在 0%–12% 之间抖动；`22` 端口不受影响。

关键细节：探测到 443 端口能连通的下一秒，`git clone` 仍可能 36 秒后失败；再下一次又 2 秒成功。说明是**逐连接**的干扰，不是「端口封死」或「IP 被封」，因此换 IP、改 hosts 都无效。

**影响量化**：一次操作需要 n 次建连，成功率为 p，则整体成功率约 pⁿ。

- clone ≈ 2~3 次建连 → p=0.1 时约 0.1%
- push 需要更多往返 → 概率再降一个数量级

这解释了「偶尔能 clone 成功，push 却一直失败」。

**解法**

```bash
# 首选：改用 SSH（走 22 端口）
git remote set-url origin git@github.com:<user>/<repo>.git
```

备选：重试循环抢窗口（只对 clone 实用）、或开代理。

**预防**：新建仓库一律用 SSH 地址 clone；遇到 `Failed to connect ... port 443` 先看 `git remote -v` 是不是 https。

---

## 2. SSH key 登记得好好的，却报 Permission denied (publickey)

**现象**

```
$ ssh -T git@github.com
git@github.com: Permission denied (publickey).
```

但 GitHub → Settings → SSH keys 里能看到这把 key，指纹一致，`Last used within the last week`。

**诊断**

```bash
ssh-keygen -lf ~/.ssh/id_ed25519.pub          # 与网页显示指纹比对：一致
ssh-keygen -y -P "" -f ~/.ssh/id_ed25519      # 报错 → 私钥有口令
ssh-add -l                                    # The agent has no identities.
```

**根因**

私钥带口令，但 ssh-agent 里没有加载；测试时又用了 `BatchMode=yes`（禁止交互），无法输入口令 → ssh 直接放弃这把 key → 返回 `publickey denied`。

这个报错**位置具有误导性**：看起来像「key 没登记」，实际是本地 agent 空、口令没处输。

**解法**

```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519     # 输一次口令，存进钥匙串
```

```sshconfig
# ~/.ssh/config
Host github.com
  AddKeysToAgent yes
  UseKeychain yes
  IdentityFile ~/.ssh/id_ed25519
```

验证通过的标准输出：

```
Hi <user>! You've successfully authenticated, but GitHub does not provide shell access.
```

**预防**：判断 key 是否登记，先看 GitHub 页面的指纹和 `Last used`，不要只凭 `ssh` 的报错下结论。

---

## 3. HTTPS push 报 Password authentication is not supported

**现象**

```
Username for 'https://github.com': ninalymm
Password for 'https://ninalymm@github.com':
remote: Invalid username or token. Password authentication is not supported for Git operations.
fatal: Authentication failed for 'https://github.com/.../rec-quality-agent.git/'
```

**根因**

GitHub 自 2021-08-13 起取消 Git 操作的密码认证，只能用 Personal Access Token（当作密码）或 SSH key。与是否开启两步验证无关。

**注意区分**：这条报错是 **GitHub 服务器返回的**，说明当时网络是通的。如果是网络问题，会看到 `Failed to connect ... port 443`（见第 1 条），两者不要混为一谈。

**解法**：换 SSH（推荐）；或用 PAT 走 HTTPS（但在本项目环境下 443 不稳定，不推荐）。

---

## 4. pandas 导入失败：library load disallowed by system policy

**现象**

```
ImportError: dlopen(.../site-packages/pandas/_libs/join.cpython-38-darwin.so, 0x0002):
  ... library load disallowed by system policy
```

诡异之处：pytest 的 17 个用例全绿，但一旦 `import pandas` 就炸——因为那些用例没用到 pandas。

**诊断**

```bash
uname -m                                   # arm64
/opt/anaconda3/bin/python3 -V              # 3.8.12  ← x86_64（Rosetta）
file /opt/anaconda3/bin/python3            # Mach-O 64-bit executable x86_64
/usr/local/bin/python3.10 -V               # 3.10.0   ← arm64
```

**根因**

用 Anaconda 的 x86_64 解释器建了 venv，装到 x86_64 的 pandas wheel；在 arm64 机器上通过 Rosetta 加载这些未签名的 `.so` 时，被 macOS 的库校验拒绝。

**解法**

```bash
rm -rf .venv
/usr/local/bin/python3.10 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -c "import platform, pandas; print(platform.machine(), pandas.__version__)"
# 期望：arm64 2.3.3
```

**预防**：README 明确要求 Python 3.10+ 原生 arm64；建 venv 用绝对路径指定解释器，不依赖 `python3` 这个名字。

---

## 5. 终端提示符同时出现 (.venv) 和 (base)

**现象**

```
(.venv) (base) ninalym@Ninas-MacBook-Pro rec-quality-agent %
```

**根因**

两套机制叠加：`~/.zshrc` 里 conda 的 init 块会自动激活 `base`；PyCharm 终端又自动激活项目的 `.venv`。

venv 在 `PATH` 更前面，所以实际生效的是 `.venv`，但提示符会让人以为自己在 base 里。

**风险**：误在 base（3.8 / x86_64）里 `pip install`，就会触发第 4 条。

**解法**

```bash
conda config --set auto_activate_base false    # 重开终端生效
which python && python -V && echo $VIRTUAL_ENV # 随时确认
```

---

## 快速自查清单

| 症状 | 第一条命令 | 大概率原因 |
|---|---|---|
| `Failed to connect ... port 443` | `git remote -v` | 还在用 https（第 1 条） |
| `Permission denied (publickey)` | `ssh-add -l` | key 没加载到 agent（第 2 条） |
| `Password authentication is not supported` | `git remote -v` | 用了密码认证（第 3 条） |
| `ImportError: ... dlopen ... system policy` | `python -V` + `uname -m` | 解释器架构不对（第 4 条） |
| 提示符有 `(base)` | `echo $VIRTUAL_ENV` | conda 自动激活（第 5 条） |
| push 说 `Everything up-to-date` 但看不到改动 | `git ls-remote origin main` | 对比 hash，可能早已推上去 |
