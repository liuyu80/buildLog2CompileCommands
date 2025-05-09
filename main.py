import re
import json
import os
import argparse

c_cpp_files = []

def scan_source_files() :
    """
    扫描当前目录及其子目录下的所有.c和.cpp文件，返回绝对路径列表(使用"/"分隔符)
    
    返回:
        List[str]: 包含所有.c和.cpp文件绝对路径的列表
    """
    source_files = []
    for root, _, files in os.walk('.'):
        for file in files:
            if file.endswith('.c') or file.endswith('.cpp'):
                # 获取绝对路径并统一使用正斜杠
                abs_path = os.path.abspath(os.path.join(root, file)).replace('\\', '/')
                source_files.append(abs_path)
    return source_files

def convert_to_relative_path(absolute_path, project_name_to_strip):
    """
    将绝对路径转换为相对于 project_name_to_strip 的路径。
    例如：/home/user/project/xiaoju/src/file.c，其中 project_name_to_strip 为 'xiaoju'
             转换为 src/file.c
    """
    if not project_name_to_strip:
        return absolute_path

    # 规范化路径分隔符以实现一致的拆分
    normalized_path = absolute_path.replace('\\\\', '/')
    
    parts = normalized_path.split('/')
    try:
        # 查找要剥离的项目名称目录的索引
        idx = -1
        for i, part in enumerate(parts):
            if part == project_name_to_strip:
                idx = i
                break
        
        if idx != -1 and idx + 1 < len(parts):
            # Join the parts after the project_name_to_strip directory
            relative_parts = parts[idx+1:]
            # 处理类似'../../'的情况，如果不小心处理可能会导致前导空字符串
            # 但是，os.path.join 或类似方法会处理这种情况，这里简单连接即可
            return "/".join(relative_parts)
        else:
            # 如果未找到要剥离的项目名称作为目录组件，
            # 或者它是最后一个组件，返回原始路径或作为错误处理
            return absolute_path 
    except ValueError:
        # Fallback if project_name_to_strip is not in path parts
        return absolute_path

def parse_compile_line(line, project_name_to_strip, current_run_directory):
    """
    解析 make 日志中的单行，以提取编译信息。
    """
    # Remove ANSI escape codes (color codes, etc.)
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    cleaned_line = ansi_escape.sub('', line.strip())

    # 匹配 C/C++ 编译行（通常包含 'arm-linux-g++ -c' 或 'arm-linux-gcc -c'）
    # 此正则表达式试图捕获编译器、选项、源文件和输出文件。
    # 它假设源文件是 .c 或 .cpp 文件。
    # 示例：arm-linux-g++ -c [选项] source.cpp -o output.o
    match = re.match(r'\s*(arm-linux-g\+\+|arm-linux-gcc|ccache arm-linux-gnueabihf-g\+\+|ccache arm-linux-gnueabihf-gcc)\s+-c\s+(.*)', cleaned_line)
    if not match:
        return None

    compiler_call_args_str = match.group(2)
    args = compiler_call_args_str.split()

    compile_info = {
        "directory": current_run_directory,
        "arguments": [],
        "file": None
    }

    source_file_path = None
    
    try:
        o_index = -1
        # Find the -o option and its argument (output object file)
        for i, arg_val in enumerate(args):
            if arg_val == '-o':
                o_index = i
                break
        
        if o_index == -1 or o_index + 1 >= len(args):
            return None # No -o option or no argument after -o

        # 确定源文件：通常是 -o 之前最后一个非选项的 .c 或 .cpp 文件
        for i in range(o_index - 1, -1, -1):
            arg_val = args[i]
            if (arg_val.endswith('.c') or arg_val.endswith('.cpp')) and not arg_val.startswith('-'):
                # Check if it's a path (contains '/') or is in the current directory context of make
                # 此检查有助于区分 -D__FILENAME__="file.cpp" 的情况
                if '/' in arg_val or '\\\\' in arg_val or os.path.exists(arg_val): # A simple check
                    source_file_path = arg_val
                    break
        
        if not source_file_path:
            # 备选方案：如果 .c/.cpp 文件直接位于 -o 之前且不是选项
            # 如果选项可能看起来像文件名，这可能过于简单化。
            # 日志显示源文件是完整路径。
            # 更可靠的方法是查找是路径且以 .c/.cpp 结尾的参数
            # 并且不是其他选项（如 -D__FILENAME__）的输出
            # 提供的日志显示源文件通常被显式列出。
            # 假设 -o 之前最后一个非选项参数是源文件（以 .c/.cpp 结尾）
            # 日志结构通常是 `... 选项 ... source.cpp -o target.o` 或 `... 选项 ... -shared source.cpp -o target.so`
            # 对于 -c 情况更简单。
            # 示例 `arm-linux-g++ -c ... -shared /path/to/source.cpp -o /path/to/object.o`
            # 源文件是 `/path/to/source.cpp`
            # 参数 `args[o_index-1]` 不总是源文件，如果存在 `-shared` 或其他标志。
            # 我们需要在 `-o` 之前的参数中查找实际的源文件路径。
            # 它就是正在编译的那个文件。
            # 日志显示源文件路径通常是 -o 之前最后一个 .c/.cpp 文件
            # 让我们重新迭代以更可靠地找到它
            temp_source_candidate = None
            for i in range(o_index -1, -1, -1):
                if (args[i].endswith(".c") or args[i].endswith(".cpp")) and \
                   not args[i].startswith("-") and \
                   not (args[i].startswith('"') and args[i].endswith('"')): # Avoid -D__FILENAME__="foo.c"
                    temp_source_candidate = args[i]
                    break
            if temp_source_candidate:
                if not os.path.isabs(temp_source_candidate):
                    # 如果不是绝对路径，尝试在c_cpp_files中匹配文件名
                    filename = os.path.basename(temp_source_candidate)
                    for full_path in c_cpp_files:
                        if filename == os.path.basename(full_path):
                            temp_source_candidate = full_path
                            break
                source_file_path = temp_source_candidate
            else:
                return None


        compile_info["file"] = convert_to_relative_path(source_file_path, project_name_to_strip)

        # 根据文件后缀决定编译器类型
        if source_file_path.endswith('.c'):
            compile_info["arguments"].append('gcc')
        else:
            compile_info["arguments"].append('g++')

        # 收集参数（仅限 -I 和 -D 标志，按照用户期望的 JSON 格式）
        for i in range(o_index): 
            arg = args[i]
            
            if arg == source_file_path:  # Don't add the source file itself to 'arguments'
                continue
            
            if arg.startswith("-I"):
                path_part = arg[2:]
                # 用户希望在参数列表中包含 -I 前缀
                if len(arg) == 2:
                    next_arg = args[i+1]
                    compile_info["arguments"].append(f"-I{convert_to_relative_path(next_arg, project_name_to_strip)}")
                else:
                    compile_info["arguments"].append(f"-I{convert_to_relative_path(path_part, project_name_to_strip)}")
            elif arg.startswith("-D"):
                if len(arg) == 2:
                    compile_info["arguments"].append(arg+args[i+1])
                else:
                    compile_info["arguments"].append(arg)
            # 所有其他编译器标志（如 -c, -g, -O0, -fpic, -std= 等）在此字段中被忽略

    except Exception:
        # 如果解析此特定行结构时发生任何错误
        return None

    if not compile_info["file"]: # Ensure a file was found
        return None
        
    return compile_info

def create_compile_commands(log_file_path, project_name_to_strip, output_file_path="compile_commands.json"):
    """
    读取 make 日志文件，解析编译命令，并写入 compile_commands.json。
    """
    compile_commands_list = []
    current_run_directory = os.getcwd()  # Directory where this script is run

    if not os.path.exists(log_file_path):
        print(f"Error: Log file not found at {log_file_path}")
        return

    with open(log_file_path, 'r', encoding='utf-8') as f:
        for line_num, line_content in enumerate(f):
            parsed_info = parse_compile_line(line_content, project_name_to_strip, current_run_directory)
            if parsed_info:
                # Ensure 'file' is not None and 'arguments' is a list
                if parsed_info.get("file") and isinstance(parsed_info.get("arguments"), list):
                    compile_commands_list.append(parsed_info)
                # else:
                #     print(f"Warning: Skipped malformed parsed info from line {line_num+1}")


    if not compile_commands_list:
        print("No compile commands found or parsed from the log file.")
    
    try:
        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(compile_commands_list, f, indent=2, ensure_ascii=False)
        print(f"Successfully generated {output_file_path} with {len(compile_commands_list)} entries.")
    except IOError as e:
        print(f"Error writing to output file {output_file_path}: {e}")
    except TypeError as e:
        print(f"Error during JSON serialization: {e}. Check parsed data.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将 make 日志转换为 compile_commands.json。")
    parser.add_argument("log_file", help="make.log 文件的路径。")
    parser.add_argument("project_name",
                        help="要从绝对路径中剥离的项目名称目录，以使其成为相对路径（例如，“xiaoju”）。")
    parser.add_argument("-o", "--output", default="compile_commands.json",
                        help="输出 JSON 文件名（默认：compile_commands.json）。")

    cli_args = parser.parse_args()

    c_cpp_files = scan_source_files()
    create_compile_commands(cli_args.log_file, cli_args.project_name, cli_args.output)
