# 沙箱镜像：agent 写的 Python 代码在容器里跑，边界由容器强制。
#
# 构建（在仓库根执行）：
#     docker build -f docker/sandbox.Dockerfile -t biopilot-sandbox:latest .
#
# 默认走阿里云 PyPI 镜像；换源加参数覆盖（手动 docker build 不读 compose 的变量）：
#     docker build -f docker/sandbox.Dockerfile -t biopilot-sandbox:latest \
#         --build-arg PIP_INDEX_URL=https://pypi.org/simple .
#
# 容器启动参数由 biopilot/core/security/services/sandbox.py 决定（断网、根只读、
# 丢 capability、禁提权、资源上限、非 root、论文库只读挂载、临时目录可写）。
# 本镜像只负责「里面有什么」——Python 与数据/生信分析常备库。
# 改这个清单后必须重建镜像（沙箱缺库时脚本会以 ImportError 失败）。
FROM python:3.12-slim

# 用 http 镜像时才需要同时给 PIP_TRUSTED_HOST。
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_TRUSTED_HOST=

# 写成 pip 配置文件，让依赖自身的构建隔离环境（PEP 517）也走同一个索引。
RUN pip config set global.index-url "$PIP_INDEX_URL" \
    && if [ -n "$PIP_TRUSTED_HOST" ]; then pip config set global.trusted-host "$PIP_TRUSTED_HOST"; fi

RUN pip install --no-cache-dir \
        pandas \
        numpy \
        scipy \
        statsmodels \
        matplotlib \
        seaborn \
        scikit-learn \
        lifelines \
        scanpy \
        anndata \
        biopython \
        openpyxl \
        pypdf

# 镜像内预建非 root 用户；实际启动时由沙箱代码用宿主 uid:gid 覆盖 --user，
# 既保持非 root，又保证挂载的临时目录对容器进程可写。
RUN useradd --create-home --shell /usr/sbin/nologin sandbox

# 容器根文件系统只读、只给 /tmp 一个内存文件系统：把 HOME 与各类缓存都指到 /tmp，
# 否则 matplotlib 写配置目录、Python 写字节码都会因只读根而报错。
ENV HOME=/tmp \
    MPLCONFIGDIR=/tmp/matplotlib \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /work
USER sandbox
