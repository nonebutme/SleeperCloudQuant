# VisActor VTable 本地分发说明

- 包名：`@visactor/vtable`
- 固定版本：`1.23.1`
- 分发文件：`dist/vtable.min.js`
- 获取地址：`https://unpkg.com/@visactor/vtable@1.23.1/dist/vtable.min.js`
- 上游仓库：`https://github.com/VisActor/VTable`
- 许可证：MIT，完整文本见同目录 `LICENSE`
- 用途：SleeperCloudQuant 全局数据表格渲染；运行时不访问公网 CDN

版本升级必须同步更新 `package.json`、本文件、`web/index.html` 和
`window.AppVTable.version`，并执行 VTable 全局采用专项验证。
