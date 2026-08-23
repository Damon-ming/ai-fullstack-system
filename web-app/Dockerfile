# nginx alpine，只拿打包好的静态文件
# node.js 是一个**可以在服务器 / 电脑上运行 JavaScript 的运行环境**。
# 浏览器里面可以跑 JS；**Node 让 JS 脱离浏览器，在操作系统（Linux/macOS/windows）直接运行**。
# 这就需要**打包编译**，把 JSX/TSX 翻译成浏览器能看懂普通 JS、CSS。
FROM node:22-alpine AS builder

# `corepack`：node 自带工具，用来管理包管理器 pnpm/yarn
# `prepare pnpm@9.0.0 --activate`：安装并激活固定版本 pnpm@9.0.0，容器内就可以用 pnpm 命令
RUN corepack enable && corepack prepare pnpm@9.0.0 --activate

WORKDIR /web-app

# 复制全部源码进入容器（宿主机本来就无node_modules，不用担心拷入）
COPY . .

# 严格按照 pnpm-lock.yaml 锁定版本，不升级版本，保证构建环境和本地一致
# `--no-optional=false`：把可选依赖也一起安装上
# 在容器内部执行安装，pnpm自动创建workspace符号链接
RUN pnpm install --frozen-lockfile --no-optional=false

# 打包
# 执行 package.json 脚本 `build:docker`，前端打包命令，生成 dist 目录，里面是 html/js/css 静态资源。
# Docker 容器内构建	使用生产环境配置，针对容器化部署优化
RUN pnpm build:docker

# 阶段2 Nginx不变
# 重新开启一个全新基础镜像，nginx alpine，只有 nginx，没有 node、pnpm、没有源码。
FROM nginx:alpine

# `--from=builder`：**从上面 builder 阶段的容器中复制打包好的 dist 静态文件**，复制到 nginx 网页根目录 `/usr/share/nginx/html`。
COPY --from=builder /web-app/src/app/main/dist /usr/share/nginx/html
# 把宿主机的 nginx 配置文件复制到 nginx 配置目录，覆盖默认配置。一般用来处理前端路由（history 模式）、反向代理转发 api 请求到后端 app‑server:8000。
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 只是文档声明，告诉别人这个容器使用 80 端口，**不会真正做端口发布**，真正端口映射靠 compose 的`ports: - "80:80"`。
EXPOSE 80

# nginx 的标准前台启动命令
# nginx 默认是后台守护进程启动；`daemon off;`让 nginx 跑在前台，docker 容器才不会直接退出。
# ["-g"]	Nginx 的全局配置参数（global directive）
# ["daemon off;"]	Nginx 配置：关闭守护进程模式，在前台运行
CMD ["nginx", "-g", "daemon off;"]