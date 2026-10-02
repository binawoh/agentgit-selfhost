# AgentGit Selfhost

[English](README.md) | 简体中文

一个小巧、无界面、单人使用的 AgentGit Hub，部署在你自己的 Linux VPS 上。它保存 Codex 和
Claude Code 的会话历史；配套客户端的 MCP 服务让这两个 agent 都能搜索、读取已经上传的会话。

这是独立的社区后端，不是 AgentGit 官方云服务，和 Einsia 没有关系；官方托管后端不开源。
本仓库的源码公开，但你部署的 Hub 和里面的会话仓库都是私有的，访问需要认证。

## 支持什么

- 私有 Git Smart HTTP 仓库：引用原子更新，版本标签不可篡改。
- Git LFS 附件存储，并校验内容哈希。
- 个人访问令牌（PAT）、会过期的访问令牌、轮换的刷新令牌，以及令牌吊销。
- 不用克隆仓库就能搜索会话、分段读取对话记录。
- 通过一次明确的本地操作，收集 Codex 已归档的会话和 Claude Code 的对话记录。
- 命令行管理、systemd 部署、HTTPS 反向代理，以及通过 npm 分发的原生 Linux 二进制。
- 可配置的存储配额、告警阈值、磁盘预留空间，并定期清理过期的临时上传文件。

没有网页管理后台，不能远程执行 agent，不会自动上传本机会话，也不会自动备份。已保存的会话和
上传完成的附件永远不会被自动删除，请另做备份。

一个 Hub 只服务一个所有者。要给别人用，就让每个人各自部署一个 Hub。

## 快速上手

需要准备：

- 一台 Linux x64 或 ARM64 服务器，装有 Git、npm（只在安装时用到）和 systemd；再准备一个你自己的
  域名，配好 HTTPS 反向代理。下面的例子用 `history.example.com`、nginx 和 Let's Encrypt 证书。
- 每台要保存会话的电脑：Git、Git LFS、Python 3.11 或更新版本，以及[配套客户端](#配套客户端)。

### 1. 安装并初始化 Hub

```sh
sudo apt-get update && sudo apt-get install -y git
sudo npm install --global --prefix /opt/agit-selfhost --ignore-scripts \
  --no-audit --no-fund @jooooesg/agit-selfhost@0.2.1
sudo useradd --system --home /var/lib/agit-selfhost --shell /usr/sbin/nologin agit-hub
sudo install -d -o agit-hub -g agit-hub -m 0700 /var/lib/agit-selfhost
sudo -u agit-hub /opt/agit-selfhost/bin/agit-selfhost --data /var/lib/agit-selfhost init \
  --owner YOUR_NAME --public-url https://history.example.com
```

`init` 会把第一个个人访问令牌（PAT）打印一次，之后不会再显示，请存进密码管理器。
`YOUR_NAME` 会成为仓库名里的所有者，比如 `YOUR_NAME/history`。`--public-url` 填客户端访问用的 HTTPS
地址。要改存储默认值，在 `init` 后面加上[存储策略](#选择存储策略)的参数。

### 2. 作为服务运行

```sh
sed 's#/usr/local/bin/agit-selfhost#/opt/agit-selfhost/bin/agit-selfhost#' \
  /opt/agit-selfhost/lib/node_modules/@jooooesg/agit-selfhost/deploy/agit-selfhost.service \
  | sudo tee /etc/systemd/system/agit-selfhost.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now agit-selfhost
curl --fail http://127.0.0.1:8177/api/health
```

服务只监听本机回环地址，不要把 8177 端口开放到公网。仓库的 Git 钩子会记下程序的安装路径，
所以以后升级要保持同一个 npm prefix 和包名。没有 systemd 的系统，用它自带的服务管理器运行 `serve`。

### 3. 通过 HTTPS 对外提供

把 `deploy/nginx.conf.example` 改成你的域名和证书路径；这个文件在安装好的包里也有。然后检查并
重载 nginx，再从外网验证：

```sh
sudo nginx -t && sudo systemctl reload nginx
curl --fail https://history.example.com/api/health
curl -s -o /dev/null -w '%{http_code}\n' https://history.example.com/api/agents
```

最后一条命令输出 `401` 就对了，说明没带令牌的请求会被拒绝。

### 4. 连接一台电脑

先装好[配套客户端](#配套客户端)，然后登录。可以用第一个 PAT，也可以用 `issue-token --label NAME`
给每台电脑单独发一个，这样能单独吊销（见[运维手册](selfhost/RUNBOOK.md#restore-maintain-and-back-up)）。

PowerShell：

```powershell
$env:AGIT_HOME = Join-Path $env:USERPROFILE 'agit-private'
$env:AGIT_USE_SYSTEM_GIT = '1'
$env:AGIT_TELEMETRY_DISABLED = '1'
$env:AGIT_HUB_URL = 'https://history.example.com'
agit login --hub $env:AGIT_HUB_URL --with-token
agit whoami --check
```

macOS 和 Linux：

```sh
export AGIT_HOME="$HOME/agit-private" AGIT_USE_SYSTEM_GIT=1 \
  AGIT_TELEMETRY_DISABLED=1 AGIT_HUB_URL=https://history.example.com
agit login --hub "$AGIT_HUB_URL" --with-token
agit whoami --check
```

`--with-token` 从标准输入读取 PAT，一直读到输入结束：粘贴后按 Ctrl-D（Windows 控制台里按 Ctrl-Z 再回车），
或者从密码管理器用管道传进来。不要把 PAT 写在命令行参数里。这几个环境变量要持久设置，比如设成
用户环境变量或写进 shell 配置文件，保证每个 agit 进程和 MCP 服务都用同一个 `AGIT_HOME` 和 Hub。
Windows 上 `AGIT_HOME` 的路径要短，路径太长时隐私保护会屏蔽内容。

### 5. 保存和搜索会话

在这台电脑上克隆本仓库，使用里面的收集脚本。第一条命令只列出将要上传的内容；第二条才真正导入，
并以私有方式发布：

```sh
python3 selfhost/collect.py --agit /path/to/agit --repo YOUR_NAME/history
python3 selfhost/collect.py --agit /path/to/agit --repo YOUR_NAME/history --apply --push
```

Windows 上用 `python -X utf8`，并传入 `agit.exe` 的路径。重复运行时，之前收集过的会话会把新的轮次发布上去。
然后给每个 agent 配上客户端的 MCP 服务，它们就能用 `search` 和 `read_remote` 读取已上传的会话：

```sh
claude mcp add --scope user agit -e AGIT_HOME="$HOME/agit-private" \
  -e AGIT_HUB_URL=https://history.example.com -e AGIT_USE_SYSTEM_GIT=1 \
  -e AGIT_TELEMETRY_DISABLED=1 -- /path/to/agit mcp
```

Codex 写在 `~/.codex/config.toml` 里：

```toml
[mcp_servers.agit]
command = "/path/to/agit"
args = ["mcp"]
env = { AGIT_HOME = "/home/you/agit-private", AGIT_HUB_URL = "https://history.example.com", AGIT_USE_SYSTEM_GIT = "1", AGIT_TELEMETRY_DISABLED = "1" }
```

MCP 只读取已经在 Hub 上的内容，不会上传当前对话。单个会话的导入、恢复、令牌管理、备份和
服务端升级，见[运维手册](selfhost/RUNBOOK.md)（英文）。

## 选择存储策略

例如，初始化时设 10 GiB 配额，用到 90% 时告警：

```sh
agit-selfhost --data /var/lib/agit-selfhost init --owner YOUR_OWNER \
  --public-url https://history.example.com --quota-mib 10240 --warn-percent 90
```

默认值：配额 5 GiB，80% 告警，磁盘预留 3 GiB，每天清理一次超过七天的临时文件。这五项都可以改：
已经在跑的实例，可以停机后用 `storage-configure` 修改，也可以在运行时通过需要认证的 HTTP API 修改。
`storage-status` 显示用量和告警。到达配额或磁盘预留线时，新的上传会暂停，已保存的数据仍然可读。
命令、告警方式和上传额度的限制，见[存储策略说明](selfhost/RUNBOOK.md#storage-policy-and-cleanup)。

## 编译

装好 Git，再通过 rustup 安装 Rust。工具链和依赖版本都已在仓库里固定。服务端运行时仍然需要 Git。

```sh
cargo build --locked --release
cargo test --locked
target/release/agit-selfhost --help
```

共用的 AgentGit 库从 [`binawoh/agent-git`](https://github.com/binawoh/agent-git) 拉取，版本是
`Cargo.toml` 里固定的那个提交，编译时不带命令行功能。编译服务端不需要在 VPS 上装 Codex、Claude Code
或 Node.js。

按[部署与运维手册](selfhost/RUNBOOK.md)创建服务账户、初始化认证、配置 HTTPS。私有数据不要放在
源码目录里，服务只绑定本机回环地址。

## 配套客户端

请使用 [`binawoh/agent-git`](https://github.com/binawoh/agent-git/tree/69e7489ddd069420cc9d2a569a45bfe0fe6123c6)
固定版本编译出来的客户端，它基于上游 AgentGit 0.2.6，比官方版多了：私有 Hub 的 `read_remote` MCP 工具、
已归档 Codex 会话的查找、原子发布，以及 Windows 凭据权限修复。官方客户端没有和这个 Hub 一起测过。

fork 的[配套版 Release](https://github.com/binawoh/agent-git/releases) 里有 Windows、macOS 和 Linux 的预编译客户端，
各平台对应哪个文件见[控制台 README](https://github.com/binawoh/agent-git/blob/remote-control/crates/agit-remote/README.md#connect-a-computer)。
也可以用 Git 和 [rustup](https://rustup.rs) 自己编译：仓库固定了 Rust 工具链，第一次编译时 rustup 会自动安装；
Windows 上要先装 Microsoft C++ Build Tools。

```sh
git clone https://github.com/binawoh/agent-git agit-companion
cd agit-companion
git checkout 69e7489ddd069420cc9d2a569a45bfe0fe6123c6
cargo build --release --locked --bin agit
```

编译出来的客户端在 `target/release/agit`（Windows 上是 `agit.exe`）。把它放进 `PATH`，并且排在
官方 `agit` 前面。`agit upgrade` 会向 Hub 询问最新版本，Hub 给出版本号时就装官方版；本 Hub 不回答这个问题，
所以配套客户端要从它的 Release 更新，或者重新编译。

配置 MCP 只是让 agent 能读到已上传的记录，不会上传当前对话。收集、导入、推送、恢复的具体命令见运维手册。

想在浏览器里操控各台电脑上的 agent，就在本 Hub 旁边运行 fork 里的
[agit-remote](https://github.com/binawoh/agent-git/blob/remote-control/crates/agit-remote/README.md) 网页控制台和中继。

## 验证

GitHub Actions 会在原生的 Ubuntu x64 和 ARM64 机器上，编译静态 musl 服务端和固定版本的配套客户端；
接着安装合并好的 npm 包，在 Ubuntu 上跑协议测试和存储测试，并在两种架构的 Debian、Alpine 容器里跑
存储测试。测试用的会话全部是合成数据。构建产物包括两种架构的二进制、带校验和与源码信息的 npm 包，
以及测试报告。

用你已经编译好的兼容客户端跑协议测试：

```sh
python3 selfhost/e2e.py --agit /path/to/agit --server target/release/agit-selfhost \
  --output selfhost/artifacts/e2e-linux.json
python3 selfhost/storage_e2e.py --server target/release/agit-selfhost
```

需要 Python 3.11 或更新版本。Windows 上用 `python -X utf8` 和 `.exe` 路径，并加上
`--state-parent "$env:USERPROFILE"`，作为测试的私有状态目录。

## npm 分发

[`@jooooesg/agit-selfhost`](https://www.npmjs.com/package/@jooooesg/agit-selfhost) 包含 Linux x64 和
ARM64 的原生静态服务端，安装时自动选择对应架构。npm 只托管安装包，不运行你的服务，也不保存你的会话。
详见[包说明](selfhost/npm/README.md)（英文）。

已发布的 `0.1.0` 是在本仓库拆分出来之前，从原来的 fork 编译的。它的源码出处仍是那个提交；
新建本仓库不会替换或重新发布任何 npm 版本。

## 许可证与来源

MIT，见 [LICENSE](LICENSE) 和 [NOTICE.md](NOTICE.md)。本后端通过固定版本的配套 fork，复用 MIT 许可的
[Einsia/agent-git](https://github.com/Einsia/agent-git) 核心代码。在这里提交的改动不会提交到上游项目。
