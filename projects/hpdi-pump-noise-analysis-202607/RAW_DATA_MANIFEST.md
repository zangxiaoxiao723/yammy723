# 原始数据清单

本项目原始数据目录：

```text
C:\FRCloud\FRQ\04_Pump Development\06_HPDI低温泵_加密\03_Testing\02_LNG测试\260709
```

本仓库保存了分析结果、脚本和报告，未保存原始视频和WAV。

## 已知数据分组

### 东德竞品

```text
C:\FRCloud\FRQ\04_Pump Development\06_HPDI低温泵_加密\03_Testing\02_LNG测试\260709\东德泵老程序测试_0707
```

包含转速：

- 700 rpm
- 800 rpm
- 900 rpm
- 1000 rpm
- 1125 rpm

每个转速目录通常包含：

- 对应rpm视频，例如`700.mp4`
- 功能数据文件，例如`20260707_*.dat...`
- `运行日志.txt`

### 富瑞自研初始状态

```text
C:\FRCloud\FRQ\04_Pump Development\06_HPDI低温泵_加密\03_Testing\02_LNG测试\260709\富瑞泵老程序测试_0709
```

包含：

- `台架1.mp4`
- `台架2.mp4`
- 600 rpm
- 700 rpm
- 800 rpm
- 900 rpm
- 1000 rpm
- 1125 rpm

其中`台架1.mp4`和`台架2.mp4`作为干扰声音参考，`1000rpm\1000.mp4`曾用于早期声音事件分析。

## 复跑提醒

另一台电脑如果不能访问上述FRCloud路径，需要先把原始数据同步到相同路径，或修改`scripts/quantify_hpdi_thump_loudness.py`里的源路径。

