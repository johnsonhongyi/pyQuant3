# InStock Docker 更新与外置数据操作手册

更新时间：2026-10-11

全系统职责、Git 发布、分层例外、镜像标识和无损回滚的总则见[全系统规范](../../docs/engineering/全系统职责与Docker发布持久化回滚规范.md)。本手册是 InStock 的操作细则，现存挂载路径和容器参数优先按现场 `docker inspect` 复核。

## 项目职责

- 本手册只负责 InStock 的 Python 选股、基本面/历史特征、候选数据及其 Web/API 和定时任务；不负责 TK/ATS 桌面运行，也不拥有 stock-strategy 的 Go 题材、热度和连板聚合。
- 全系统关注联动由 stock-strategy Go/Web 发起与汇总，桌面 JSON 网关和本地关注管理器负责 TK/ATS 消费；InStock 只提供候选和历史/基本面证据，不把盘后结果伪装成实时行情或交易指令。

## 核心约定

- 保持现有 Docker image、容器参数、网络、挂载点和挂载目录结构不变。功能代码更新通过容器内 Git 版本更新，或将本地审核通过的文件同步/替换到容器现有代码路径；**日常功能更新不重建 Docker image**。
- 本地开发仓库、既有外置代码目录和容器代码树的目录结构、文件相对路径保持不变；只更新审核过的代码内容，不移动、重命名、压平目录或增加代码挂载。
- 不改 Docker `run` 配置，不增删或重定向现有 bind mount，不更换容器名、端口、网络、重启策略或资源参数。执行代码更新前后都核对容器配置未变化。
- 数据库、日志、缓存、行情文件和运行状态保留在外置挂载目录。代码更新只触碰已审核的代码文件；禁止把数据文件、日志、缓存或运行产物写进 image。
- 现有 Docker stdout/stderr 使用 `json-file`，轮转上限为 `max-size=10m`、`max-file=2`，Docker 根目录是 `/var/lib/docker`。这是当前容器既有设置，最多占用约 20 MiB，更新时不改日志驱动或容器参数；应用自身的持久日志仍写在外置 `/data/InStock/instock/log`。
- 不用 `docker commit` 将运行容器做成新 image；常规代码和全系统联动功能更新均以审核过的 Git SHA 在既有运行代码路径中更新，不执行 `docker build`，不增加镜像层。只有基础运行环境/依赖必须变化，或用户明确要求隔离分层开发时，才允许从已核对的固定基础 image 建一个唯一候选层；记录构建理由、base digest、源码 SHA、tag、预期层数和回滚点。分层验收完成后不为每个普通修复继续叠层。
- Docker 主机系统盘容量小。发布前后分别记录 image size、容器 `SizeRw` 和 `SizeRootFs`；`docker ps -s` 的虚拟总大小约为 image 加可写层，不能误当成新 image 大小。禁止全局 prune 和批量删除；必须保留正在运行的 image 与可回撤版本。
- 单次代码同步导致的容器可写层净增长不得超过 64 MiB；超限先回撤本次代码并检查是否误写了缓存、日志或数据。该额度不允许写入任何持久数据，也不代表可以把代码发布成新 image。

## 远端管理入口

- PVE 主机为 `192.168.1.50`，Docker 服务运行在 PVE 的 LXC `102` 内；`pct` 命令只在 PVE 主机上执行。应用侧地址 `192.168.50.60` 属于 Docker 所在的 LXC，不是 PVE 管理节点。
- 从 Windows 管理时先 `ssh root@192.168.1.50`，再在 PVE 上执行 `pct enter 102` 进入 LXC；Docker、宿主挂载和容器管理命令在 LXC 102 内执行，应用代码/Git 命令通过 `docker exec inStock ...` 在 `inStock` 容器内执行。单条 LXC 命令可用 `pct exec 102 -- <命令>`。

```bash
ssh root@192.168.1.50
pct status 102
pct exec 102 -- docker ps --format '{{.Names}} {{.Image}} {{.Status}}'
```

## 现网已核对的 Docker 结构

当前容器名为 `inStock`，运行 image 为 `instock:johnson250103-sina-runtime-flatbase-20261007`，image ID 为 `sha256:4d85f9e9b4f605440373fe69975fc23f95680b6642ad4e70ebce4a927e86d124`，大小为 583,245,754 字节。现有四个 bind mount 如下，更新过程必须原样保留：

| 宿主机路径 | 容器路径 | 用途 |
| --- | --- | --- |
| `/mnt/4TB/dockerf/stock/instockcache` | `/data/InStock/instock/cache` | SQLite、行情缓存、锁和缓存数据 |
| `/mnt/4TB/dockerf/stock/instrategy` | `/data/InStock/instock/core/strategy` | 用户策略扩展及状态 |
| `/mnt/4TB/dockerf/stock/forwardp` | `/data/InStock/instock/forwardp` | TDX 日线文件 |
| `/mnt/4TB/dockerf/stock/log` | `/data/InStock/instock/log` | 应用日志 |

本次只读核对显示：容器内已安装 Git 2.30.2；`/data/InStock` 根目录**没有单独的 bind mount**，但表中四个子目录分别挂载到外置存储。Git 仓库位于容器现有 `/data/InStock` 路径，分支为 `master`，HEAD 短 SHA 为 `4cb74f8`，相对 `origin/master` 显示 ahead 4，工作区另有 12 个已修改/未提交路径。容器根文件系统当前可写，Docker 日志驱动为 `json-file`。更新代码时沿用这个 Git 工作树和现有目标路径，不新增或改动源码挂载：写入现有 bind mount 内的文件会落到对应外置存储；写入未挂载路径的代码或 Git 对象可能增加容器 `SizeRw`。两类更新都不改变 image 大小。若其他环境已有不同代码目录或挂载，以其 `docker inspect` 结果为准并原样保留。当前工作区和分支都需先对照本地开发版本再决定同步方向，不能直接 `pull` 或 `push`。

MariaDB 是独立容器；其数据目录沿用 `/mnt/mariadb-data/mariadb/data` 挂到 `/var/lib/mysql`。更新 InStock 代码不触碰 MariaDB 容器或数据目录。

2026-10-11 只读磁盘基线：Docker 根目录 `/var/lib/docker` 所在盘约 10.46 GB，已用约 5.41 GB、可用约 4.50 GB；Docker 有 27 个 image（合计约 2.27 GB）、7 个容器、11 个 volume，构建缓存为 0。`inStock` 当前 `SizeRw` 为 158,957,957 字节。`docker system df` 标出的可回收空间不等于可安全删除空间，必须先核对每个 image/container 与回撤用途。

## 更新前检查

在 Docker 主机上只读记录容器设置、代码版本、工作区状态、image 与可写层大小：

```bash
docker inspect --format '{{json .Mounts}}' inStock
docker inspect --format 'Image={{.Config.Image}} ReadonlyRootfs={{.HostConfig.ReadonlyRootfs}} LogDriver={{.HostConfig.LogConfig.Type}} Network={{.HostConfig.NetworkMode}} Restart={{.HostConfig.RestartPolicy.Name}}' inStock
docker exec inStock git -C /data/InStock rev-parse HEAD
docker exec inStock git -C /data/InStock status --short
docker inspect --size --format 'WritableLayer={{.SizeRw}} bytes' inStock
docker system df -v
```

当前容器已有未提交代码修改，不能直接执行 `git reset --hard`、`git clean` 或覆盖整个仓库。先对照线上分支和本地开发提交，逐项备份并确认这 12 个修改路径的归属；未确认内容不得被 Git 更新或文件同步覆盖。更新前在容器外的既有持久化存储中保存代码备份，不能把备份包留在容器可写层。

## 两种代码更新方式

### 默认发布流

```text
核验容器/镜像/挂载和当前 Git 状态
  → 外置保存旧代码与 SHA（有数据库迁移时另做数据快照）
  → 对齐经审核的目标 commit（联网 fast-forward 或 Git bundle）
  → 只在必要时替换代码并重启对应应用进程，不构建镜像、不重建容器
  → 核对目标 SHA、文件哈希、配置/挂载未变化、SizeRw 增量及只读健康接口
  → 记录 image digest + 代码 SHA + 外置数据状态 + 回滚命令
```

目标版本以明确 SHA 为准；先检查本地、远端、容器三方差异和未提交路径，再只允许审核后的 fast-forward。工作区有未提交修改时先在容器外备份并逐项确认归属，不能硬重置、清理或用整个目录覆盖。

### 方式 A：默认——容器内 Git 快进更新

适用于本地修改已审核并提交到既有 Git 仓库、容器 Git remote/branch 配置正确且未提交修改已妥善处理的情况。先比较本地目标 SHA、容器 HEAD 和 remote；确认工作区可安全更新后，显式获取目标版本并执行 `git merge --ff-only <remote>/<branch>` 或等价的目标 SHA 快进。不得强制重置或清理工作区。完成后核对 HEAD、`git status --short` 和目标文件哈希，再按既有应用控制方式重启/加载程序。远端不可达时使用经过校验的 Git bundle，不改用无版本记录的整仓覆盖。

可先执行以下只读比对：

```bash
docker exec inStock git -C /data/InStock status --short
docker exec inStock git -C /data/InStock rev-parse HEAD
docker exec inStock git -C /data/InStock remote -v
docker exec inStock git -C /data/InStock fetch origin
docker exec inStock git -C /data/InStock branch -vv
docker exec inStock git -C /data/InStock diff --name-status HEAD..origin/master
```

`remote -v` 可能包含私有仓库地址或凭据，不要把未脱敏输出贴入工单、公共日志或聊天记录。仓库工作区不干净时，先保存变更补丁到外置备份目录并人工合并，再执行版本更新。

### 方式 B：例外——已审核文件的紧急同步/替换

仅用于已审核但暂未推送的少量代码文件，不能替代默认 Git 版本更新。记录源文件清单、目标 SHA256 和临时补丁/提交；只替换容器现有 `/data/InStock/<相对路径>` 下列明的文件，不覆盖 `.git`、配置、数据目录或未审核文件。先把目标文件备份到现有外置发布备份目录，再原子替换；不得新增或调整挂载。之后应尽快把相同变更纳入 Git 并记录正式 commit。

两种方式一次发布只能选一种，避免 Git 与文件覆盖交叉修改。更新只包含代码时，image ID/标签/大小和 Docker 参数都应保持不变；容器 `SizeRw` 可能因代码写入增加，须符合 64 MiB 上限。只重启现有容器或应用进程，不删除并重建容器。`deploy/` 下历史 `build-*hotfix*.sh` 等构建脚本只保留作历史记录，不用于日常功能发布；执行前必须遵循本手册的 Git/逐文件同步流程。

## 回撤与磁盘控制

- 发布记录至少保存：当前 image ID、容器 inspect 配置、更新前 HEAD、更新目标 SHA/文件清单、代码备份路径及 SHA256、容器可写层更新前后大小。
- Git 更新回撤时，只有在工作区干净且目标提交确认后才按已审核的 Git 回退方案恢复记录的旧版本；文件同步回撤时，从容器外置备份按清单恢复文件。不得用 `docker commit` 或重建 image 回撤。
- 更新前后运行 `docker system df -v`、`docker inspect --size inStock` 和 `docker diff inStock`。`SizeRw`/`docker diff`反映容器可写层，不涵盖 bind mount 内文件变化；对外置挂载中的代码文件另按同步清单核对 SHA256 和对应外置目录用量。如果可写层出现日志、缓存、数据库或行情文件，立即停止后续更新并排查；不扩大或改造挂载来绕过检查。
- 同一次代码更新的容器 `SizeRw` 净增量上限为 67,108,864 字节（64 MiB），且 `docker diff` 中的新增/变更范围只能是本次位于未挂载路径的代码清单；超限立即回撤并停止发布。现有外置挂载内的代码更新仍须限于审核清单，不能覆盖数据或运行状态文件。
- 禁止 `docker system prune`、`docker image prune -a`、`docker volume prune` 和清理正在运行/可回撤版本的 image。Docker image 列表的大小含共享层，不可将各行直接相加；以 `docker system df -v` 查看实际占用。

## Image 说明提示

当前基础 image 没有 OCI labels（`docker image inspect` 返回 `Labels=null`）。Docker image 的说明属于不可变 image 元数据；给现有 image 追加 labels 会产生新的 image，因此**不为日常代码更新或补标签重建 image**。下次确需维护运行基础环境或获准生成隔离候选层时，再在该次构建中一次性补充以下说明标签：

- `org.opencontainers.image.title`：InStock 运行基础环境。
- `org.opencontainers.image.description`：包含固定运行环境和 Git；业务代码通过容器内 Git 或本地文件同步更新；SQLite、日志、缓存、行情和持久化状态使用既有外置挂载；更新功能代码不重建 image；不得改变现有挂载结构。
- `org.opencontainers.image.version` / `org.opencontainers.image.revision`：基础环境版本和镜像内实际包含的构建源码提交；容器内 Git 后续更新不会改变这两个标签。
- `io.instock.external-data-paths`：现有四个外置数据路径及其用途。
- `io.instock.image-size-policy`：基础 image 只在运行环境变化时维护；代码发布不产生新 image；保留当前与可回撤 image。

因此每次对外报告同时记录两种身份：Docker image tag/digest/labels 表示运行环境快照；`docker exec inStock git -C /data/InStock rev-parse HEAD` 表示当前应用源码版本。不得把 `docker ps -s` 的虚拟总大小写成镜像大小，也不得用 image revision 冒充运行中 Git HEAD。

`bash deploy/describe-instock-image.sh <image标签或ID>` 可查看现有 image 的 ID、大小和已嵌入标签；没有标签时脚本会明确提示它是未嵌入说明的现有基础 image，并给出本手册的更新策略。

## 当前待办

1. 先核对并备份容器 `/data/InStock` 下 12 个未提交路径；从正式开发 Git 仓库确认它们与本地开发提交的差异。
2. 补齐本地变更到线上同步/回撤清单，按 Git 快进或文件清单替换的单一路径做隔离验证。
3. 正式更新前再核验现有四个 InStock bind mount、容器网络/端口/重启策略、MariaDB 独立外置数据路径完全未变化。

以上是更新准备和手册约束；本轮未更新线上代码、未重启容器、未构建或删除 image。
