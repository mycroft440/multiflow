import os
import re
import sys

def supports_color():
    """Verifica se o terminal suporta cores ANSI."""
    plat = sys.platform
    supported_platform = plat != 'win32' or 'ANSICON' in os.environ
    
    try:
        is_a_tty = sys.stdout.isatty()
    except AttributeError:
        is_a_tty = False
    
    return supported_platform and is_a_tty

class Colors:
    """Códigos ANSI para colorir a saída do terminal."""
    _enabled = supports_color()
    
    @classmethod
    def _get_color(cls, code):
        return code if cls._enabled else ''
    
    HEADER = property(lambda self: self._get_color('\033[95m'))
    BLUE = property(lambda self: self._get_color('\033[94m'))
    CYAN = property(lambda self: self._get_color('\033[96m'))
    GREEN = property(lambda self: self._get_color('\033[92m'))
    YELLOW = property(lambda self: self._get_color('\033[93m'))
    RED = property(lambda self: self._get_color('\033[91m'))
    WHITE = property(lambda self: self._get_color('\033[97m'))
    BOLD = property(lambda self: self._get_color('\033[1m'))
    UNDERLINE = property(lambda self: self._get_color('\033[4m'))
    END = property(lambda self: self._get_color('\033[0m'))

class BoxChars:
    """Caracteres Unicode para desenhar bordas."""
    if supports_color():
        TOP_LEFT = '╔'
        TOP_RIGHT = '╗'
        BOTTOM_LEFT = '╚'
        BOTTOM_RIGHT = '╝'
        
        HORIZONTAL = '═'
        VERTICAL = '║'
        
        T_DOWN = '╦'
        T_UP = '╩'
        T_RIGHT = '╠'
        T_LEFT = '╣'
        
        CROSS = '╬'
    else:
        TOP_LEFT = '+'
        TOP_RIGHT = '+'
        BOTTOM_LEFT = '+'
        BOTTOM_RIGHT = '+'
        
        HORIZONTAL = '-'
        VERTICAL = '|'
        
        T_DOWN = '+'
        T_UP = '+'
        T_RIGHT = '+'
        T_LEFT = '+'
        
        CROSS = '+'

def visible_length(text):
    """Calcula o comprimento visível de uma string, ignorando códigos ANSI."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_text = ansi_escape.sub('', text)
    return len(clean_text)

def clear_screen():
    """Limpa a tela do console."""
    os.system("cls" if os.name == "nt" else "clear")

def print_centered(text, width=60, char=' '):
    """Imprime texto centralizado com uma largura específica."""
    print(text.center(width, char))

def print_colored_box(title, content_lines=None, width=60, title_color=None):
    """Imprime uma caixa colorida com título e conteúdo."""
    if content_lines is None:
        content_lines = []
    if title_color is None:
        title_color = Colors().CYAN
    
    colors = Colors()

    print(f"{BoxChars.TOP_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.TOP_RIGHT}")
    
    title_text = f" {title_color}{colors.BOLD}{title}{colors.END} "
    visible_title_len = visible_length(title_text)
    padding = width - visible_title_len - 2
    left_padding = padding // 2
    right_padding = padding - left_padding
    print(f"{BoxChars.VERTICAL}{' ' * left_padding}{title_text}{' ' * right_padding}{BoxChars.VERTICAL}")
    
    if content_lines:
        print(f"{BoxChars.T_RIGHT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.T_LEFT}")
        
        for line in content_lines:
            current_visible_len = visible_length(line)
            max_content_width = width - 4
            if current_visible_len > max_content_width:
                truncated_line = ""
                visible_chars_count = 0
                for char in line:
                    if re.match(r'\\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', char):
                        truncated_line += char
                    else:
                        if visible_chars_count < max_content_width - 3:
                            truncated_line += char
                            visible_chars_count += 1
                        else:
                            break
                line_to_print = truncated_line + "..." + colors.END
            else:
                line_to_print = line
            padding = width - visible_length(line_to_print) - 2
            print(f"{BoxChars.VERTICAL} {line_to_print}{' ' * padding}{BoxChars.VERTICAL}")
    
    print(f"{BoxChars.BOTTOM_LEFT}{BoxChars.HORIZONTAL * (width - 2)}{BoxChars.BOTTOM_RIGHT}")

def print_menu_option(number, description, status=None, color=None, width=60):
    """Formata uma opção de menu com possível status."""
    colors = Colors()
    if color is None:
        color = colors.WHITE

    number_text = f"{colors.BOLD}{color}[{number}]{colors.END}"
    
    if status:
        status_text = f"{status}"
        available_desc_space = width - visible_length(number_text) - visible_length(status_text) - 4
    else:
        available_desc_space = width - visible_length(number_text) - 3
    current_desc_visible_len = visible_length(description)
    if current_desc_visible_len > available_desc_space:
        truncated_description = ""
        visible_chars_count = 0
        for char in description:
            if re.match(r'\\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', char):
                truncated_description += char
            else:
                if visible_chars_count < available_desc_space - 3:
                    truncated_description += char
                    visible_chars_count += 1
                else:
                    break
        description_to_print = truncated_description + "..." + colors.END
    else:
        description_to_print = description
    if status:
        option_text = f" {number_text} {description_to_print}"
        padding = width - visible_length(option_text) - visible_length(status_text) - 2
        print(f"{BoxChars.VERTICAL}{option_text}{' ' * padding}{status_text} {BoxChars.VERTICAL}")
    else:
        option_text = f" {number_text} {description_to_print}"
        padding = width - visible_length(option_text) - 2
        print(f"{BoxChars.VERTICAL}{option_text}{' ' * padding}{BoxChars.VERTICAL}")


