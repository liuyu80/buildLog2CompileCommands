import re
import json
import os
import argparse

def convert_to_relative_path(absolute_path, project_name_to_strip):
    """
    将绝对路径转换为相对于 project_name_to_strip 的路径。
    例如：/home/user/project/xiaoju/src/file.c，其中 project_name_to_strip 为 'xiaoju'
             转换为 src/file.c
    """
    if not project_name_to_strip:
        return absolute_path

    # Normalize path separators for consistent splitting
    normalized_path = absolute_path.replace('\\\\', '/')
    
    parts = normalized_path.split('/')
    try:
        # Find the index of the project_name_to_strip directory
        idx = -1
        for i, part in enumerate(parts):
            if part == project_name_to_strip:
                idx = i
                break
        
        if idx != -1 and idx + 1 < len(parts):
            # Join the parts after the project_name_to_strip directory
            relative_parts = parts[idx+1:]
            # Handle cases like '../../' which might result in leading empty strings if not careful
            # However, os.path.join or similar would handle this, but simple join is fine here.
            return "/".join(relative_parts)
        else:
            # If project_name_to_strip is not found as a directory component,
            # or it's the last component, return the original path or handle as error
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

    # Match C/C++ compilation lines (typically containing 'arm-linux-g++ -c' or 'arm-linux-gcc -c')
    # This regex tries to capture the compiler, options, source file, and output file.
    # It assumes source file is a .c or .cpp file.
    # Example: arm-linux-g++ -c [options] source.cpp -o output.o
    match = re.match(r'\s*(arm-linux-g\+\+|arm-linux-gcc)\s+-c\s+(.*)', cleaned_line)
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

        # Identify the source file: usually the last .c or .cpp file before -o
        # that is not an option itself.
        for i in range(o_index - 1, -1, -1):
            arg_val = args[i]
            if (arg_val.endswith('.c') or arg_val.endswith('.cpp')) and not arg_val.startswith('-'):
                # Check if it's a path (contains '/') or is in the current directory context of make
                # This check helps differentiate from -D__FILENAME__="file.cpp"
                if '/' in arg_val or '\\\\' in arg_val or os.path.exists(arg_val): # A simple check
                    source_file_path = arg_val
                    break
        
        if not source_file_path:
            # Fallback: if a .c/.cpp file is directly before -o without being an option
            # This might be too simplistic if options can look like filenames.
            # The log shows source files are full paths.
            # A more robust way is to look for the argument that is a path and ends with .c/.cpp
            # and is not an output of another option (like -D__FILENAME__)
            # The provided log shows source files are often explicitly listed.
            # Let's assume the last non-option argument before -o that ends with .c/.cpp is the source.
            # The log structure is often `... options ... source.cpp -o target.o` or `... options ... -shared source.cpp -o target.so`
            # For -c, it's simpler.
            # The example `arm-linux-g++ -c ... -shared /path/to/source.cpp -o /path/to/object.o`
            # The source is `/path/to/source.cpp`
            # The argument `args[o_index-1]` is not always the source file if `-shared` or other flags are present.
            # We need to find the actual source file path among the arguments before `-o`.
            # It's the one that is being compiled.
            # The log shows the source file path is often the last argument before -o that is a .c/.cpp file.
            # Let's re-iterate to find it more reliably.
            temp_source_candidate = None
            for i in range(o_index -1, -1, -1):
                if (args[i].endswith(".c") or args[i].endswith(".cpp")) and \
                   not args[i].startswith("-") and \
                   not (args[i].startswith('"') and args[i].endswith('"')): # Avoid -D__FILENAME__="foo.c"
                    temp_source_candidate = args[i]
                    break
            if temp_source_candidate:
                source_file_path = temp_source_candidate
            else:
                return None


        compile_info["file"] = convert_to_relative_path(source_file_path, project_name_to_strip)

        # Collect arguments (ONLY -I and -D flags as per user's desired JSON format)
        for i in range(o_index): 
            arg = args[i]
            if arg == source_file_path:  # Don't add the source file itself to 'arguments'
                continue
            
            if arg.startswith("-I"):
                path_part = arg[2:]
                # User wants the -I prefix in the arguments list
                compile_info["arguments"].append(f"-I{convert_to_relative_path(path_part, project_name_to_strip)}")
            elif arg.startswith("-D"):
                compile_info["arguments"].append(arg)
            # All other compiler flags (like -c, -g, -O0, -fpic, -std=, etc.) are ignored for this field.

    except Exception:
        # If any error occurs during parsing this specific line's structure
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

    create_compile_commands(cli_args.log_file, cli_args.project_name, cli_args.output)
