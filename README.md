# buildLog2CompileCommands

将make构建日志转换为compile_commands.json格式的工具

## 功能

- 解析make日志中的C/C++编译命令
- 提取源文件路径、编译参数等信息
- 将绝对路径转换为相对路径
- 生成标准的compile_commands.json文件

## 安装

```bash
pip install .
```

或直接使用Python运行：

```bash
python main.py make.log project_name
```

## 使用方法

```bash
python main.py [日志文件路径] [项目名称] [-o 输出文件名]
```

### 参数说明

- `日志文件路径`: make构建日志文件路径(必需)
- `项目名称`: 要从绝对路径中剥离的项目名称目录(必需)
- `-o/--output`: 输出JSON文件名(可选，默认为compile_commands.json)

## 输出格式

生成的compile_commands.json文件包含以下字段的数组：

```json
{
  "directory": "编译时的工作目录",
  "arguments": ["编译参数列表"],
  "file": "源文件相对路径"
}
```

## 示例

```bash
python main.py make.log xiaoju -o compile_commands.json
```

输入日志示例：
```
arm-linux-g++ -c -I/home/user/xiaoju/include src/main.cpp -o build/main.o
```

输出示例：
```json
[
  {
    "directory": "/current/working/dir",
    "arguments": ["-Iinclude"],
    "file": "src/main.cpp"
  }
]
```

## 注意事项

1. 目前仅支持解析包含`arm-linux-g++`或`arm-linux-gcc`的编译命令
2. 路径转换基于项目名称目录的精确匹配
3. 仅保留`-I`和`-D`编译参数
4. 需要确保make日志中包含完整的编译命令