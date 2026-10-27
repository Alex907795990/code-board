# 贪吃蛇：从零到完整游戏

打开 `tutorial.html` 阅读九步讲解；打开 `snake.html` 游玩。游戏是一个独立 HTML 文件，无需安装依赖或启动服务器。

`scope.yaml` 按页面、状态和函数拆分代码片段，顺序拼接后与整个 `snake.html` 完全一致。全部 136 行都在范围内，包括 HTML、CSS、JavaScript 和空行。片段末尾的空行通过 YAML `|2+` 保留。

`stages/01-board.html` 是先完成的静止画面；`stages/02-moving.html` 是随后完成的直行版本。教程引用其中实际存在的移动和启动代码来解释演进；中间版本不替代最终代码的覆盖。

从 skill 根目录重新生成：

```sh
python scripts/code-board.py check examples/snake/scope.yaml examples/snake/walkthrough.yaml
python scripts/code-board.py build examples/snake/scope.yaml examples/snake/walkthrough.yaml -o examples/snake/tutorial.html
```

点击开始后，每 140 毫秒前进一格，用方向键转向。第一颗食物固定在前方，之后从空位里随机选择。每吃一颗增长一节并得一分；撞墙或身体结束，填满棋盘获胜。重新开始恢复同一初始位置。
