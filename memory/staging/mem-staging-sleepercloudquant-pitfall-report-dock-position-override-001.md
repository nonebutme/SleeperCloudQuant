# Memory Entry

## Basic

- `id`: mem-staging-sleepercloudquant-pitfall-report-dock-position-override-001
- `type`: Pitfall
- `scope`: project:SleeperCloudQuant
- `status`: staging
- `summary`: 给既有固定结果抽屉追加通用工作区类时，后加载样式可能覆盖固定定位并使长报告突破视口。

## Content

- `rule`: 扩展固定抽屉时不得在通用附加类中重设 `position`；必须用组合选择器保留固定定位、内部纵向滚动、横向裁切和底部粘性导航安全留白，并进行滚动后测量。
- `context`: 适用于结果抽屉、模态工作区、侧滑面板和包含粘性头部/底部导航的长内容容器。
- `abstraction_note`: 去除具体阶段号和像素，只保留 CSS 加载顺序、选择器覆盖和视口约束之间的稳定风险。

## Evidence

- `source`: stage-77-1-report-ui-display-completeness-fix
- `evidence`: 新报告通用类覆盖既有固定抽屉定位，桌面与窄屏容器高度膨胀；恢复组合选择器和内部滚动后，抽屉回到视口高度且文档横向溢出消失。
- `timestamp`: 2026-07-26T20:00:00+08:00
- `confirm_count`: 1
- `retrieval_count`: 0

## Notes

- `notes`: user_reported_display_incomplete | verified_with_desktop_and_mobile_headless_layout_measurement | synced_to_root_staging | local_reference_only
